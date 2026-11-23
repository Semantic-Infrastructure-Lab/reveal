"""The element-retirement seam (BACK-2764): one ``target:SCHEME.element`` RETIREMENTS row lets a scheme that binds its
query keep answering a positional element, with its note, until the cut; a bound noun with no row refuses it as before.

Shared owners: ``cli/invocation.py`` (the rows and ``element_retirement``), the CLI's URI route (``uri._resolve``, which
also classifies a bound constructor's refusal as the request's fault) and ``api.query``. Effect on every noun: only
``help://`` and ``reveal://`` have a row; every other bound noun (env, stats, sqlite, json, the analysis nouns...)
refuses an element exactly as before, and unbound adapters and plugins never reach the check.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from conftest import _run_reveal_direct  # noqa: E402

from reveal.cli.invocation import RETIREMENTS, element_retirement  # noqa: E402

pytestmark = [pytest.mark.unit]


def test_only_help_and_reveal_keep_a_positional_element():
    rows = sorted(key for key in RETIREMENTS if key.startswith('target:') and key.endswith('.element'))
    assert rows == ['target:help.element', 'target:reveal.element']
    assert all(RETIREMENTS[key].stage == 'note' for key in rows)
    assert element_retirement('help') == 'target:help.element'
    assert element_retirement('reveal') == 'target:reveal.element'


def test_the_notes_name_the_replacement():
    assert RETIREMENTS['target:help.element'].text == 'help:// TOPIC is deprecated and works until 1.0; use help://TOPIC.'
    assert 'reveal PATH ELEMENT' in RETIREMENTS['target:reveal.element'].text


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
