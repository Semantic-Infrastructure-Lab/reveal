"""A retired spelling an owner recognizes as it binds ends the request as every retired spelling does (BACK-2773).

Most retired spellings are noted by the routers before an adapter runs (a URI's scheme, keys and values:
``uri_retirement_keys``; a subcommand's flags). Help's older search address, the term in the path
(``help://search/TERM``, ruling S7), is a resource form only help's constructor can recognize, so help says its note
there. The router's adapter-call boundary (``uri._call_adapter``, shared by the URI and declared routes) turned every
exception into a failed answer, so at the cut that row would have answered exit 3 with an ``adapter_error`` envelope
instead of the retired spelling's exit 2 and its text. Effect on every other noun: none raises ``RetiredSpellingError``
inside an adapter call today; a note-stage row inside one keeps answering with its note (the negative control).
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from conftest import _run_reveal_direct  # noqa: E402
from undeclared_plugin import UndeclaredPluginAdapter, undeclared_plugin  # noqa: E402,F401  (the plugin fixture)

from reveal.cli.invocation import RETIREMENTS, Retirement, retirement_note  # noqa: E402

pytestmark = [pytest.mark.unit]

KEY = 'target:undeclared.form'


def _noting(real):
    """*real* get_structure, saying the retired form's row first, as an owner that recognizes it while binding does."""
    def get_structure(self, **kwargs):
        retirement_note(KEY)
        return real(self, **kwargs)
    return get_structure


@pytest.fixture
def owners(undeclared_plugin, monkeypatch):  # noqa: F811
    """Two owners that say the row inside an adapter call: the undeclared plugin (the URI route) and env (declared)."""
    from reveal.adapters.env import EnvAdapter
    for adapter in (UndeclaredPluginAdapter, EnvAdapter):
        monkeypatch.setattr(adapter, 'get_structure', _noting(adapter.get_structure))
    return (f'{undeclared_plugin}://x', 'env://PATH')


def _row(monkeypatch, stage):
    row = Retirement('undeclared://OLD', 'undeclared://NEW', stage)
    monkeypatch.setitem(RETIREMENTS, KEY, row)
    return row


@pytest.mark.parametrize('which', [0, 1], ids=['uri-route', 'declared-route'])
def test_an_error_stage_spelling_said_in_an_adapter_call_exits_2_with_its_text(owners, monkeypatch, which):
    row = _row(monkeypatch, 'error')
    run = _run_reveal_direct(owners[which], '--format', 'json')
    assert run.returncode == 2, (run.returncode, run.stderr)
    assert f'error: {row.text}' in run.stderr
    assert run.stdout == ''


@pytest.mark.parametrize('which', [0, 1], ids=['uri-route', 'declared-route'])
def test_a_note_stage_spelling_said_in_an_adapter_call_answers_with_its_note(owners, monkeypatch, which):
    _row(monkeypatch, 'note')
    run = _run_reveal_direct(owners[which], '--format', 'json')
    assert run.returncode == 0, run.stderr
    warnings = json.loads(run.stdout).get('meta', {}).get('warnings', [])
    assert [w['field'] for w in warnings if w.get('type') == 'retired_spelling'] == [KEY]
