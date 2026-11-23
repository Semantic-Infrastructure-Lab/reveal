"""The element-retirement seam (BACK-2764): one ``target:SCHEME.element`` RETIREMENTS row lets a scheme that binds its
query keep answering a positional element, with its note, until the cut; a bound noun with no row refuses it as before.

Shared owners: ``cli/invocation.py`` (the rows and ``element_retirement``), the CLI's URI route (``uri._resolve``, which
also classifies a bound constructor's refusal as the request's fault) and ``api.query``. Effect on every noun: only
``help://``, ``reveal://`` and ``diff://`` have a row; every other bound noun (env, stats, sqlite, json, the analysis
nouns...) refuses an element exactly as before. The row is read whether or not the scheme binds its query (BACK-2768):
``diff://`` binds nothing and its element answered unnoted; every other unbound adapter and plugin has no row, so its
element answers exactly as before.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from conftest import _run_reveal_direct  # noqa: E402

from reveal.cli.invocation import RETIREMENTS, element_retirement  # noqa: E402

pytestmark = [pytest.mark.unit]


def test_only_help_reveal_and_diff_keep_a_positional_element():
    rows = sorted(key for key in RETIREMENTS if key.startswith('target:') and key.endswith('.element'))
    assert rows == ['target:diff.element', 'target:help.element', 'target:reveal.element']
    assert all(RETIREMENTS[key].stage == 'note' for key in rows)
    assert element_retirement('help') == 'target:help.element'
    assert element_retirement('reveal') == 'target:reveal.element'
    assert element_retirement('diff') == 'target:diff.element'


def test_the_notes_name_the_replacement():
    assert RETIREMENTS['target:help.element'].text == 'help:// TOPIC is deprecated and works until 1.0; use help://TOPIC.'
    assert 'reveal PATH ELEMENT' in RETIREMENTS['target:reveal.element'].text
    assert RETIREMENTS['target:diff.element'].text == ('diff://LEFT:RIGHT ELEMENT is deprecated and works until 1.0; '
                                                      'use diff://LEFT:RIGHT/ELEMENT.')


def test_of_the_unbound_schemes_only_diff_has_a_row():
    """Effect on every noun of reading the row for an unbound scheme too (BACK-2768): diff:// alone gains a note."""
    import reveal.adapters  # noqa: F401
    from reveal.adapters.base import get_adapter_class, list_supported_schemes
    from reveal.adapters.factory import uses_bound_query_call
    unbound = [s for s in list_supported_schemes() if not uses_bound_query_call(get_adapter_class(s))]
    assert 'diff' in unbound and 'domain' in unbound
    assert [s for s in unbound if element_retirement(s)] == ['diff']


def _diff_pair(tmp_path):
    a, b = tmp_path / 'ok.py', tmp_path / 'ok2.py'
    a.write_text('def ok():\n    return 1\n', encoding='utf-8')
    b.write_text('def ok():\n    return 2\n', encoding='utf-8')
    return f'diff://{a.as_posix()}::{b.as_posix()}'


def _noted(doc):
    return [w['field'] for w in (doc.get('meta') or {}).get('warnings') or [] if w.get('code') == 'retired_spelling']


def test_cli_an_unbound_scheme_with_a_row_answers_its_element_with_the_note(tmp_path, monkeypatch):
    uri = _diff_pair(tmp_path)
    run = _run_reveal_direct(uri, 'ok', '--format', 'json')
    assert run.returncode == 0, run.stderr
    assert _noted(json.loads(run.stdout)) == ['target:diff.element']
    monkeypatch.delitem(RETIREMENTS, 'target:diff.element')  # the row is the whole switch: without it, no note
    run = _run_reveal_direct(uri, 'ok', '--format', 'json')
    assert run.returncode == 0 and _noted(json.loads(run.stdout)) == [], run.stderr


def test_api_an_unbound_scheme_with_a_row_answers_its_element_with_the_note(tmp_path, monkeypatch):
    from reveal import api
    uri = _diff_pair(tmp_path)
    doc = api.query(uri, 'ok')
    assert doc['type'] == 'diff_element' and _noted(doc) == ['target:diff.element']
    monkeypatch.delitem(RETIREMENTS, 'target:diff.element')
    doc = api.query(uri, 'ok')
    assert doc['type'] == 'diff_element' and _noted(doc) == []


# --- the CLI's URI route (uri._resolve) ------------------------------------------------------------------------------

def test_every_other_bound_noun_has_no_row():
    """Effect on every noun: of the schemes that bind their query, only help:// and reveal:// keep an element."""
    import reveal.adapters  # noqa: F401
    from reveal.adapters.base import get_adapter_class, list_supported_schemes
    from reveal.adapters.factory import uses_bound_query_call
    bound = [s for s in list_supported_schemes() if uses_bound_query_call(get_adapter_class(s))]
    assert {'env', 'stats', 'metrics', 'json', 'sqlite'} <= set(bound)
    assert [s for s in bound if element_retirement(s) and s not in ('help', 'reveal')] == []


def test_cli_a_bound_noun_without_a_row_still_refuses_the_element():
    run = _run_reveal_direct('env://', 'PATH', '--format', 'json')
    assert run.returncode == 2, run.stderr
    assert "env:// takes no positional element ('PATH')" in run.stdout + run.stderr


@pytest.mark.parametrize('uri', ['stats://.?bogus=1', 'metrics://.?bogus=1'])
def test_cli_an_unqualified_bound_constructor_refusal_is_the_invalid_request(uri):
    """stats:// (and help://, reveal:// once they bind) refuse an unknown key while binding: exit 2, as metrics:// does;
    an unqualified operation counted it as a failed answer, exit 1."""
    run = _run_reveal_direct(uri, '--format', 'json')
    assert run.returncode == 2, (uri, run.returncode, run.stderr)
    assert "unsupported control 'bogus'" in run.stdout + run.stderr, run.stderr
    json.loads(run.stdout)  # the invalid-request JSON document


# --- api.query -------------------------------------------------------------------------------------------------------

def test_api_a_bound_noun_without_a_row_still_refuses_the_element():
    from reveal import api
    from reveal.errors import RequestValidationError
    with pytest.raises(RequestValidationError, match=r"env:// takes no positional element \('PATH'\)"):
        api.query('env://', 'PATH')


def test_api_a_bound_scheme_with_a_row_answers_its_element_with_the_note(monkeypatch):
    """The seam alone: a scheme that binds its query (here reveal:// made bound by its own PARAM_SPECS, as its adapter
    declares it) and has a row answers get_element with the row's note in meta.warnings, and refuses an unknown keyword
    beside it, which it used to forward to get_element."""
    from reveal import api
    from reveal.adapters.factory import uses_bound_query_call
    from reveal.adapters.reveal.adapter import RevealAdapter
    from reveal.errors import UnsupportedOverrideError
    monkeypatch.setattr(RevealAdapter, 'PARAM_SPECS', (), raising=False)
    assert uses_bound_query_call(RevealAdapter)
    doc = api.query('reveal://adapters/env.py', 'EnvAdapter')
    assert doc['type'] == 'code_element'
    assert [w['field'] for w in doc['meta']['warnings'] if w.get('code') == 'retired_spelling'] == \
        ['target:reveal.element']
    with pytest.raises(UnsupportedOverrideError, match='bogus'):
        api.query('reveal://adapters/env.py', 'EnvAdapter', bogus=1)
