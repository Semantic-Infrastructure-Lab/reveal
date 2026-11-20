"""A --stdin batch line answers as its direct request: ``reveal LINE BATCH-FLAGS`` (BACK-2707, plan D20).

Scott 2026-11-19 (BACK-2707 note #3): a line that is an existing path is a path, taken whole; otherwise a line whose
first word is a reveal command or a URI is a command line, run through the CLI's own parse and dispatch with the
batch's options joined (they meet the line's own under "Conflicting values"); anything else stays a path line, and a
missing one keeps today's skip (BACK-1426). The batch exits with its most severe line (COMMAND_MODEL "Transports").
"""
import json

import pytest

from conftest import _run_reveal_in

APP = ('def process_order(order):\n    total = order["total"]\n    return total\n\n\n'
       'def main():\n    return process_order({"total": 1})\n')


@pytest.fixture
def proj(tmp_path):
    (tmp_path / 'app.py').write_text(APP, encoding='utf-8')
    return tmp_path


def _batch(proj, lines, *flags):
    return _run_reveal_in(proj, '--stdin', *flags, stdin=''.join(f'{line}\n' for line in lines))


def _direct(proj, *argv):
    return _run_reveal_in(proj, *argv)


@pytest.mark.parametrize('line', [
    'calls . --callers process_order',
    'ast . --kind function --sort=-lines --limit 1',
    "ast . --where 'lines>2'",
    'ast://. --limit 1',
])
def test_a_command_line_answers_as_its_direct_request(proj, line):
    import shlex
    direct = _direct(proj, *shlex.split(line))
    assert direct.returncode == 0 and direct.stdout.strip(), direct.stderr
    batch = _batch(proj, [line])
    assert batch.returncode == 0, batch.stderr
    assert batch.stdout == direct.stdout


def test_the_batch_options_join_every_command_line(proj):
    direct = _direct(proj, 'calls', '.', '--callers', 'process_order', '--format', 'json')
    batch = _batch(proj, ['calls . --callers process_order'], '--format', 'json')
    assert batch.returncode == 0, batch.stderr
    assert json.loads(batch.stdout) == json.loads(direct.stdout)


def test_a_line_flag_that_conflicts_with_a_batch_option_is_that_lines_exit_2(proj):
    direct = _direct(proj, 'ast', '.', '--limit', '1', '--limit', '2')
    assert direct.returncode == 2
    batch = _batch(proj, ['ast . --limit 1'], '--limit', '2')
    assert batch.returncode == 2
    assert 'limit' in batch.stderr and 'ast . --limit 1 failed (exit 2)' in batch.stderr


def test_the_batch_exits_with_its_most_severe_line_and_answers_every_line(proj):
    batch = _batch(proj, ['calls . --nope', 'calls . --callers process_order'])
    assert batch.returncode == 2
    assert "unsupported control '--nope'" in batch.stderr
    assert 'Callers of: process_order' in batch.stdout  # the line after the failure still answered


def test_path_lines_are_unchanged(proj):
    """Positive controls: a path line reads the file, and a missing path is still a skip with exit 0 (BACK-1426:
    git diff --name-only lists deleted files)."""
    batch = _batch(proj, ['app.py', 'deleted.py'])
    assert batch.returncode == 0, batch.stderr
    assert 'process_order(order)' in batch.stdout
    assert 'deleted.py not found, skipping' in batch.stderr


def test_an_existing_path_with_spaces_is_one_path_even_when_it_starts_with_a_command_word(proj):
    (proj / 'calls notes.py').write_text('def note():\n    return 1\n', encoding='utf-8')
    batch = _batch(proj, ['calls notes.py'])
    assert batch.returncode == 0, batch.stderr
    assert 'note()' in batch.stdout


def test_a_line_that_starts_with_no_command_stays_a_path_line(proj):
    batch = _batch(proj, ['some words here'])
    assert batch.returncode == 0
    assert 'some words here not found, skipping' in batch.stderr


def test_a_batch_line_cannot_read_stdin_itself(proj):
    batch = _batch(proj, ['calls . --callers process_order --stdin'])
    assert batch.returncode == 2
    assert 'cannot read --stdin itself' in batch.stderr


def test_batch_mode_keeps_one_uri_per_line_and_names_a_command_line_as_an_error_row(proj):
    batch = _batch(proj, ['ast://.', 'calls . --callers process_order'], '--batch', '--format', 'json')
    document = json.loads(batch.stdout)
    rows = {row['uri']: row for row in document['results']}
    assert rows['ast://.']['status'] != 'error'
    assert rows['calls . --callers process_order']['status'] == 'error'
    assert 'one URI per line' in rows['calls . --callers process_order']['error']


def test_an_at_file_list_takes_command_lines_too(proj):
    (proj / 'requests.txt').write_text('calls . --callers process_order\n', encoding='utf-8')
    direct = _direct(proj, 'calls', '.', '--callers', 'process_order')
    listed = _run_reveal_in(proj, '@requests.txt')
    assert listed.returncode == 0, listed.stderr
    assert listed.stdout == direct.stdout
