"""A flag whose value is optional is noted under the value it carries, as its URI key is (BACK-2774 ruling S1).

The subcommand route notes a declared flag's value under the URI's ``value:<noun>.<param>=<value>`` key
(``_note_retired_flags``). It looked the value up only for ``--flag=value`` when the flag's value is optional
(``nargs='?'``: Imports ``--importers [FILE]``, Calls ``--detail [LEVEL]``): ``--flag value`` (the value as the next word,
which argparse reads as the flag's value) and the bare ``--flag`` (which carries the flag's ``const``) were never looked
up. A value-keyed retirement on such a flag (Calls' valueless ``--detail`` and ``--detail true|false``, ruling S1) then
answered with no note on the subcommand while its URI twin noted it. A bare flag is looked up under the value it stands
for, spelled as a URI value (a boolean lowercase, as a bare URI key is ``true``).

Effect on every other noun: only a lookup changes; no ``value:`` row names an optional-value flag's value before ruling
S1, so no other answer gains or loses a note (the negative control: a canonical value with no row stays note-free).
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from conftest import _run_reveal_direct  # noqa: E402

from reveal.cli.invocation import RETIREMENTS, Retirement  # noqa: E402

pytestmark = [pytest.mark.unit]


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'app.py').write_text('def helper():\n    return 1\n', encoding='utf-8')
    (root / 'main.py').write_text('import app\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return root


def _row(monkeypatch, key):
    row = Retirement(f'OLD {key}', 'NEW', 'note')
    monkeypatch.setitem(RETIREMENTS, key, row)
    return row


def _noted(project, *flags):
    run = _run_reveal_direct('imports', 'proj', *flags, '--format', 'json')
    assert run.returncode == 0, run.stderr
    warnings = json.loads(run.stdout).get('meta', {}).get('warnings', [])
    return [w['field'] for w in warnings if w.get('type') == 'retired_spelling']


@pytest.mark.parametrize('flags', [('--importers', 'app.py'), ('--importers=app.py',)],
                         ids=['value-as-next-word', 'value-after-equals'])
def test_an_optional_value_flag_notes_the_value_it_carries(project, monkeypatch, flags):
    _row(monkeypatch, 'value:imports.importers=app.py')
    assert _noted(project, *flags) == ['value:imports.importers=app.py']


def test_a_bare_optional_value_flag_notes_the_value_it_stands_for(project, monkeypatch):
    _row(monkeypatch, 'value:imports.importers=true')  # const True, spelled as the bare URI key ?importers binds it
    assert _noted(project, '--importers') == ['value:imports.importers=true']


def test_a_value_with_no_row_stays_note_free(project, monkeypatch):
    _row(monkeypatch, 'value:imports.importers=other.py')
    assert _noted(project, '--importers', 'app.py') == []
    assert _noted(project, '--importers') == []
