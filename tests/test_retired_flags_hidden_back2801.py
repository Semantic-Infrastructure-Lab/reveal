"""A declared noun's ``--help`` keeps hiding its retired flags at the cut (BACK-2801).

COMMAND_MODEL "Help" (BACK-2755): a declared noun's usage and ``--help`` list only canonical flags; an argument whose
long flags all have a RETIREMENTS row is hidden. ``hide_note_stage_flags`` read ``stage == 'note'``, so the cut, which
turns every note into an error, listed every retired flag again (``reveal ast --help`` showed ``--verbose`` and
``--type KIND``). A row that notes or refuses retires its flag; a ``phase7`` row only records it, its flag still current.
"""
import re
from dataclasses import replace

import pytest

from conftest import _run_reveal_direct
from reveal.cli.invocation import RETIREMENTS

ROWS = ('flag:--verbose', 'param:ast.type')


def _listed(help_text, option):
    """*option* on an argument line of --help (two-space indent, before the help column), not in prose."""
    return any(re.search(rf'(?<![\w-]){re.escape(option)}(?![\w-])', re.split(r'\s{2,}', line.strip())[0])
               for line in help_text.splitlines() if re.match(r'^  -', line))


def _help(monkeypatch, stage):
    for key in ROWS:
        monkeypatch.setitem(RETIREMENTS, key, replace(RETIREMENTS[key], stage=stage))
    result = _run_reveal_direct('ast', '--help')
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.mark.parametrize('stage', ['note', 'error'])
def test_a_retired_flag_is_hidden_at_the_note_and_the_error_stage(monkeypatch, stage):
    text = _help(monkeypatch, stage)
    assert not _listed(text, '--verbose') and not _listed(text, '--type'), text
    usage = text.split('\n\n')[0]
    assert '--verbose' not in usage and '--type' not in usage


def test_a_phase7_row_only_records_so_its_flag_is_listed(monkeypatch):
    text = _help(monkeypatch, 'phase7')
    assert _listed(text, '--verbose') and _listed(text, '--type')


@pytest.mark.parametrize('stage', ['note', 'error'])
def test_control_the_canonical_flags_stay_listed(monkeypatch, stage):
    text = _help(monkeypatch, stage)
    assert _listed(text, '--kind') and _listed(text, '--sort')
