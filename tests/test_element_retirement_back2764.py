"""The element-retirement seam (BACK-2764): one ``target:SCHEME.element`` RETIREMENTS row lets a scheme that binds its
query keep answering a positional element, with its note, until the cut; a bound noun with no row refuses it as before.

Shared owners: ``cli/invocation.py`` (the rows and ``element_retirement``), the CLI's URI route (``uri._resolve``, which
also classifies a bound constructor's refusal as the request's fault) and ``api.query``. Effect on every noun: only
``help://``, ``reveal://`` and ``diff://`` have a row; every other bound noun (env, stats, sqlite, json, the analysis
nouns...) refuses an element exactly as before. The row is read whether or not the scheme binds its query (BACK-2768):
``diff://`` bound nothing then; it is a declared noun since BACK-2214, so no unbound scheme has a row now, and the seam is
held by a plugin given a row (tests/undeclared_plugin.py). On the declared route (``reveal diff://L:R NAME`` is read by
diff's own parser) the row's element joins the resource (``declared.legacy_element_resource``).
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from conftest import _run_reveal_direct  # noqa: E402
from undeclared_plugin import undeclared_plugin  # noqa: E402,F401  (a fixture: the plugin that declares nothing)

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


def test_no_unbound_scheme_has_a_row():
    """Effect on every noun of reading the row for an unbound scheme too (BACK-2768): diff:// was the one, and it binds
    its query since its declaration (BACK-2214), so no unbound scheme gains a note."""
    import reveal.adapters  # noqa: F401
    from reveal.adapters.base import get_adapter_class, list_supported_schemes
    from reveal.adapters.factory import uses_bound_query_call
    unbound = [s for s in list_supported_schemes() if not uses_bound_query_call(get_adapter_class(s))]
    assert 'diff' not in unbound and 'domain' in unbound
    assert [s for s in unbound if element_retirement(s)] == []


@pytest.fixture
def plugin_with_a_row(undeclared_plugin, monkeypatch):  # noqa: F811
    """The seam for an unbound scheme: a plugin that declares nothing, given a target:SCHEME.element row."""
    from reveal.cli.invocation import Retirement
    monkeypatch.setitem(RETIREMENTS, f'target:{undeclared_plugin}.element',
                        Retirement(f'{undeclared_plugin}://X NAME', f'{undeclared_plugin}://X/NAME'))
    return f'{undeclared_plugin}://x'


def _diff_pair(tmp_path):
    a, b = tmp_path / 'ok.py', tmp_path / 'ok2.py'
    a.write_text('def ok():\n    return 1\n', encoding='utf-8')
    b.write_text('def ok():\n    return 2\n', encoding='utf-8')
    return f'diff://{a.as_posix()}::{b.as_posix()}'


def _noted(doc):
    return [w['field'] for w in (doc.get('meta') or {}).get('warnings') or [] if w.get('code') == 'retired_spelling']


def test_cli_an_unbound_scheme_with_a_row_answers_its_element_with_the_note(plugin_with_a_row, monkeypatch):
    run = _run_reveal_direct(plugin_with_a_row, 'ok', '--format', 'json')
    assert run.returncode == 0, run.stderr
    doc = json.loads(run.stdout)
    assert doc['name'] == 'ok' and _noted(doc) == ['target:undeclared.element']
    monkeypatch.delitem(RETIREMENTS, 'target:undeclared.element')  # the row is the whole switch: without it, no note
    run = _run_reveal_direct(plugin_with_a_row, 'ok', '--format', 'json')
    assert run.returncode == 0 and _noted(json.loads(run.stdout)) == [], run.stderr


def test_api_an_unbound_scheme_with_a_row_answers_its_element_with_the_note(plugin_with_a_row, monkeypatch):
    from reveal import api
    doc = api.query(plugin_with_a_row, 'ok')
    assert doc['name'] == 'ok' and _noted(doc) == ['target:undeclared.element']
    monkeypatch.delitem(RETIREMENTS, 'target:undeclared.element')
    doc = api.query(plugin_with_a_row, 'ok')
    assert doc['name'] == 'ok' and _noted(doc) == []


def test_cli_diff_declared_route_joins_the_element_and_notes_it(tmp_path, monkeypatch):
    """diff's positional element is read by its own parser (a declared noun with a subcommand): the row's element joins
    the resource, so ``reveal diff://L::R ok`` answers as ``diff://L::R/ok`` with one note; without the row, diff refuses
    the element as every declared noun does (BACK-2214)."""
    uri = _diff_pair(tmp_path)
    run = _run_reveal_direct(uri, 'ok', '--format', 'json')
    assert run.returncode == 0, run.stderr
    doc = json.loads(run.stdout)
    assert doc['type'] == 'diff_element' and _noted(doc) == ['target:diff.element']
    embedded = json.loads(_run_reveal_direct(f'{uri}/ok', '--format', 'json').stdout)
    assert {k: v for k, v in doc.items() if k != 'meta'} == {k: v for k, v in embedded.items() if k != 'meta'}
    monkeypatch.delitem(RETIREMENTS, 'target:diff.element')
    run = _run_reveal_direct(uri, 'ok', '--format', 'json')
    assert run.returncode == 2 and "takes no positional element ('ok')" in run.stdout + run.stderr, run.stderr


def test_the_declared_route_joins_an_element_to_an_empty_resource_as_the_element_alone():
    """A noun whose resource may be empty (help's topic: ``reveal help:// quick`` once help is a declared subcommand,
    BACK-2773) joins the element as the resource itself, ``quick``, not ``/quick`` (an element no topic has). A resource
    keeps its own trailing-slash handling: ``L:R/`` and ``L:R`` join ``ok`` alike (diff, BACK-2768)."""
    from reveal.cli.routing.declared import legacy_element_resource
    assert legacy_element_resource('help', '', 'quick') == 'quick'
    assert legacy_element_resource('diff', 'a.py:b.py', 'ok') == 'a.py:b.py/ok'
    assert legacy_element_resource('diff', 'a.py:b.py/', 'ok') == 'a.py:b.py/ok'
    assert legacy_element_resource('env', 'PATH', 'x') is None  # no target:env.element row: refused as before


# --- the CLI's URI route (uri._resolve) ------------------------------------------------------------------------------

def test_every_other_bound_noun_has_no_row():
    """Effect on every noun: of the schemes that bind their query, only help://, reveal:// and diff:// keep an element."""
    import reveal.adapters  # noqa: F401
    from reveal.adapters.base import get_adapter_class, list_supported_schemes
    from reveal.adapters.factory import uses_bound_query_call
    bound = [s for s in list_supported_schemes() if uses_bound_query_call(get_adapter_class(s))]
    assert {'env', 'stats', 'metrics', 'json', 'sqlite'} <= set(bound)
    assert [s for s in bound if element_retirement(s) and s not in ('help', 'reveal', 'diff')] == []


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
