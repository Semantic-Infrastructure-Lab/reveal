"""A removed subcommand stays a command word and exits 2 with its RETIREMENTS row's text (BACK-2771).

The cut deletes a retired noun's CommandSpec (BACK-2149 S7) and marks its ``subcommand:NOUN`` row ``removed``. The
word must not then fall to the path read ("hotspots not found", "is a URI noun", an argparse usage error for the dead
noun's flags) or to a silent ``--stdin`` skip: the router, the ``--stdin`` classifier and MCP ``reveal_run`` read one
predicate in ``cli/invocation.py`` (a command word is a COMMANDS key or has a removed ``subcommand:`` row) and answer
with the row's generated text (ruling D1 of the hotspots H1 report; stormy-rainbow-1124 retire rulings 1 and 2). A
bare word stays the verb and ``./NOUN`` stays the path (BACK-1112), and the shadow hint prints before the error.

Each test removes a noun the way the cut will: the row patched to ``error`` + ``removed`` and the CommandSpec deleted.
"""
from dataclasses import replace

import pytest

from conftest import _run_reveal_in
from reveal.cli.invocation import COMMANDS, RETIREMENTS

APP = ('import os\n\n\ndef helper(name):\n    return os.path.join("a", name)\n\n\n'
       'def main():\n    if helper("b"):\n        return 1\n    return 0\n')

# Every noun the table retires as a subcommand, so a row added later is covered without an edit.
RETIRED_NOUNS = sorted(key.split(':', 1)[1] for key in RETIREMENTS if key.startswith('subcommand:'))


@pytest.fixture
def proj(tmp_path):
    (tmp_path / 'app.py').write_text(APP, encoding='utf-8')
    return tmp_path


def _remove(monkeypatch, noun):
    """Remove *noun* as the cut does: its row at error and removed, its CommandSpec deleted. Returns the row."""
    key = f'subcommand:{noun}'
    monkeypatch.setitem(RETIREMENTS, key, replace(RETIREMENTS[key], stage='error', removed=True))
    monkeypatch.delitem(COMMANDS, noun)
    return RETIREMENTS[key]


def _error_lines(stderr):
    return [line for line in stderr.splitlines() if line.startswith('error:')]


def _mcp(call):
    try:
        return call()
    except Exception as exc:  # a raised tool error is the refusal on MCP; its text is the measured outcome
        return f'[reveal error: {exc}]'


# --- CLI -------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('noun', RETIRED_NOUNS)
def test_a_removed_subcommand_exits_2_with_its_rows_text(proj, monkeypatch, noun):
    row = _remove(monkeypatch, noun)
    assert row.text.startswith(f'reveal {noun} was removed; use ')
    result = _run_reveal_in(proj, noun, '.')
    assert result.returncode == 2, result.stdout[:300]
    assert _error_lines(result.stderr) == [f'error: {row.text}'], result.stderr
    assert 'not found' not in result.stderr and 'URI noun' not in result.stderr
    assert result.stdout == ''


def test_the_dead_nouns_own_flags_do_not_reach_the_main_parser(proj, monkeypatch):
    """``trace --from`` is a flag only the deleted parser knew: the word is refused before any parser reads it."""
    row = _remove(monkeypatch, 'trace')
    result = _run_reveal_in(proj, 'trace', '.', '--from', 'main', '--depth', '2')
    assert result.returncode == 2
    assert _error_lines(result.stderr) == [f'error: {row.text}'], result.stderr
    assert 'usage:' not in result.stderr


def test_global_options_before_a_removed_word_keep_it_a_command(proj, monkeypatch):
    row = _remove(monkeypatch, 'hotspots')
    result = _run_reveal_in(proj, '--format', 'text', 'hotspots', '.')
    assert result.returncode == 2
    assert _error_lines(result.stderr) == [f'error: {row.text}'], result.stderr


def test_json_mode_also_names_the_rows_text(proj, monkeypatch):
    """The JSON document of an error-stage retirement is step R3 (BACK-2627 item 3); here only the meaning."""
    row = _remove(monkeypatch, 'deps')
    result = _run_reveal_in(proj, 'deps', '.', '--format', 'json')
    assert result.returncode == 2
    assert row.text in result.stdout + result.stderr
    assert 'not found' not in result.stdout + result.stderr


def test_an_unknown_word_is_still_a_missing_path(proj, monkeypatch):
    """Negative control: the predicate holds the removed rows only, not every word."""
    _remove(monkeypatch, 'hotspots')
    result = _run_reveal_in(proj, 'nosuchnoun', '.')
    assert result.returncode == 2
    assert 'nosuchnoun not found' in result.stderr
    assert 'was removed' not in result.stderr


def test_a_live_noun_that_answers_the_question_is_unchanged(proj, monkeypatch):
    """Sibling: the replacement the hotspots row names answers equally before and after the removal."""
    before = _run_reveal_in(proj, 'metrics', '.', '--view', 'hotspots')
    assert before.returncode == 0, before.stderr
    _remove(monkeypatch, 'hotspots')
    after = _run_reveal_in(proj, 'metrics', '.', '--view', 'hotspots')
    assert (after.returncode, after.stdout, after.stderr) == (before.returncode, before.stdout, before.stderr)


def test_a_dot_slash_spelling_still_reads_the_directory(proj, monkeypatch):
    """BACK-1112's precedence: ``./NOUN`` is the path, whatever the word means."""
    (proj / 'hotspots').mkdir()
    (proj / 'hotspots' / 'inner.py').write_text('def inner():\n    return 1\n', encoding='utf-8')
    _remove(monkeypatch, 'hotspots')
    result = _run_reveal_in(proj, './hotspots')
    assert result.returncode == 0, result.stderr
    assert 'inner.py' in result.stdout


# --- shadow hint (B3) ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('removed', [False, True], ids=['error-stage', 'removed'])
def test_the_shadow_hint_prints_before_a_retired_subcommands_error(proj, monkeypatch, removed):
    (proj / 'hotspots').mkdir()
    (proj / 'hotspots' / 'inner.py').write_text('def inner():\n    return 1\n', encoding='utf-8')
    key = 'subcommand:hotspots'
    if removed:
        row = _remove(monkeypatch, 'hotspots')
    else:
        row = replace(RETIREMENTS[key], stage='error')
        monkeypatch.setitem(RETIREMENTS, key, row)
    result = _run_reveal_in(proj, 'hotspots', '.')
    assert result.returncode == 2, result.stdout[:300]
    lines = result.stderr.splitlines()
    hint = 'note: ./hotspots/ exists — use ./hotspots or hotspots/ to target it'
    assert hint in lines and f'error: {row.text}' in lines, result.stderr
    assert lines.index(hint) < lines.index(f'error: {row.text}')


# --- MCP reveal_run --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('noun', RETIRED_NOUNS)
def test_mcp_reveal_run_refuses_a_removed_subcommand_with_its_rows_text(proj, monkeypatch, noun):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_run
    row = _remove(monkeypatch, noun)
    monkeypatch.chdir(proj)
    shown = _mcp(lambda: reveal_run([noun, '.']))
    assert 'reveal error' in shown and row.text in shown, shown[:300]
    assert 'not found' not in shown


def test_mcp_reveal_run_answers_a_live_noun_beside_a_removed_one(proj, monkeypatch):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_run
    _remove(monkeypatch, 'hotspots')
    monkeypatch.chdir(proj)
    shown = _mcp(lambda: reveal_run(['ast', '.']))
    assert 'reveal error' not in shown and 'helper' in shown, shown[:300]


# --- --stdin ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('noun', RETIRED_NOUNS)
def test_a_stdin_line_naming_a_removed_subcommand_exits_2_with_its_text(proj, monkeypatch, noun):
    row = _remove(monkeypatch, noun)
    batch = _run_reveal_in(proj, '--stdin', stdin=f'{noun} .\ndeleted.py\n')
    assert batch.returncode == 2, batch.stderr
    assert f'error: {row.text}' in batch.stderr.splitlines(), batch.stderr
    assert f'{noun} . not found' not in batch.stderr
    assert 'deleted.py not found, skipping' in batch.stderr  # the path line after it is still a path line


def test_stdin_lines_that_name_no_command_are_still_skipped(proj, monkeypatch):
    """Negative control: a missing path and an unknown first word stay path lines, exit 0 (BACK-1426, BACK-2707)."""
    _remove(monkeypatch, 'hotspots')
    batch = _run_reveal_in(proj, '--stdin', stdin='deleted.py\nnosuchnoun .\n')
    assert batch.returncode == 0, batch.stderr
    assert 'deleted.py not found, skipping' in batch.stderr
    assert 'nosuchnoun . not found, skipping' in batch.stderr


# --- guard -----------------------------------------------------------------------------------------------------------

def test_every_subcommand_and_scheme_row_names_live_code_or_is_removed():
    """A cut that deletes a CommandSpec or an adapter without marking its row removed would orphan the row: the word
    would fall to the path read and the row would never be read. A removed row whose code still answers is dead code."""
    from reveal.cli.invocation import orphaned_retirements
    assert orphaned_retirements() == []


def test_the_guard_names_each_kind_of_orphan(monkeypatch):
    from reveal.cli.invocation import orphaned_retirements
    monkeypatch.delitem(COMMANDS, 'trace')  # code deleted, row not marked removed
    monkeypatch.setitem(RETIREMENTS, 'subcommand:hotspots',  # row marked removed, code still there
                        replace(RETIREMENTS['subcommand:hotspots'], stage='error', removed=True))
    monkeypatch.setitem(RETIREMENTS, 'scheme:stats', replace(RETIREMENTS['scheme:stats'], stage='error', removed=True))
    assert orphaned_retirements() == ['scheme:stats', 'subcommand:hotspots', 'subcommand:trace']
