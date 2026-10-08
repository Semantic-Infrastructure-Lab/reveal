"""BACK-1764, BACK-1765, BACK-1767: silent gaps in the special modes and the --stdin route.

1764: the refusal for `reveal a.py b.py --decorator-stats` suggested `ls PATHS | reveal --stdin
      --decorator-stats`, which printed a note, scanned '.' and exited 0 (the mode is dispatched
      before --stdin). The same pipe into --explain-file/--capabilities/--show-ast printed a usage
      line and exited 1. A mode that reads one path cannot take --stdin: it is now refused (exit 2)
      and the hint names the per-path loop, which works.
1765: `printf 'a.md\\n' | reveal --stdin --section X` ignored --section and printed the outline,
      exit 0. It is refused like `reveal a.md b.md --section X` (BACK-1728): exit 2.
1767: `reveal --rules | head -2` printed "Exception ignored ... BrokenPipeError" and exited 120: the
      handler ends in sys.exit(0), which skipped the flush that BACK-1510 does after a mode runs.
"""

import subprocess
import sys

import pytest

from conftest import _run_reveal_direct

# path-reading early-exit modes that main._SPECIAL_MODES dispatches before --stdin
PATH_MODES = ['--decorator-stats', '--explain-file', '--capabilities', '--show-ast']


def _reveal(args, stdin=None):
    return subprocess.run(
        [sys.executable, '-m', 'reveal', *args], input=stdin, capture_output=True,
        text=True, encoding='utf-8', timeout=120,
    )


@pytest.fixture
def files(tmp_path):
    a, b = tmp_path / 'a.py', tmp_path / 'b.py'
    a.write_text('def f():\n    return 1\n', encoding='utf-8')
    b.write_text('def g():\n    return 2\n', encoding='utf-8')
    md = tmp_path / 'a.md'
    md.write_text('# A\ntext\n## B\nbody\n', encoding='utf-8')
    return a, b, md


@pytest.mark.parametrize('flag', PATH_MODES)
def test_second_path_hint_does_not_name_stdin(files, flag):
    a, b, _ = files
    r = _run_reveal_direct(str(a), str(b), flag)
    assert r.returncode == 2
    assert '--stdin' not in r.stderr, r.stderr
    assert f'reveal {flag}' in r.stderr, r.stderr  # names the per-path form


@pytest.mark.parametrize('flag', PATH_MODES)
def test_stdin_with_a_path_mode_is_refused(files, flag):
    a, b, _ = files
    r = _reveal(['--stdin', flag], stdin=f'{a}\n{b}\n')
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert r.stdout == ''
    assert flag in r.stderr and 'one path' in r.stderr, r.stderr


def test_the_hinted_per_path_form_answers_each_path(files):
    a, b, _ = files
    for path in (a, b):
        r = _run_reveal_direct(str(path), '--decorator-stats')
        assert r.returncode == 0 and f'Decorator Usage in {path}' in r.stdout, r.stdout


def test_stdin_hint_stays_for_flags_the_stdin_route_honours(files):
    # negative control: --check works through --stdin, so its hint is unchanged
    a, b, _ = files
    r = _run_reveal_direct(str(a), str(b), '--check')
    assert r.returncode == 2
    assert 'ls PATHS | reveal --stdin --check' in r.stderr, r.stderr
    ok = _reveal(['--stdin', '--check'], stdin=f'{a}\n{b}\n')
    assert ok.returncode == 0, (ok.stdout, ok.stderr)


def test_one_path_decorator_stats_unchanged(files):
    a, _, _ = files
    r = _run_reveal_direct(str(a), '--decorator-stats')
    assert r.returncode == 0 and 'Decorator Usage' in r.stdout


def test_stdin_refuses_section(files):
    _, _, md = files
    r = _reveal(['--stdin', '--section', 'B'], stdin=f'{md}\n')
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert r.stdout == ''
    assert '--section B' in r.stderr and '--stdin' in r.stderr, r.stderr


def test_stdin_without_section_and_section_on_one_file_unchanged(files):
    _, _, md = files
    plain = _reveal(['--stdin'], stdin=f'{md}\n')
    assert plain.returncode == 0 and 'Headings' in plain.stdout
    one = _run_reveal_direct(str(md), '--section', 'B')
    assert one.returncode == 0 and 'body' in one.stdout


@pytest.mark.skipif(sys.platform == 'win32', reason='POSIX pipe semantics')
@pytest.mark.parametrize('mode', ['--rules', '--discover'])
def test_special_mode_into_a_closed_pipe_is_quiet(mode):
    proc = subprocess.run(
        f'"{sys.executable}" -m reveal {mode} | head -c 1 >/dev/null',
        shell=True, capture_output=True, text=True, encoding='utf-8',
        executable='/bin/bash', timeout=120,
    )
    assert 'BrokenPipeError' not in proc.stderr, proc.stderr
    assert 'Exception ignored' not in proc.stderr, proc.stderr


def test_special_mode_output_and_exit_unchanged_when_read_fully():
    r = _run_reveal_direct('--rules')
    assert r.returncode == 0 and 'Total:' in r.stdout


def test_stdin_blind_flags_are_the_path_reading_modes_dispatched_before_stdin():
    # the declared set cannot drift from main._SPECIAL_MODES: every element-less mode that runs
    # before the 'stdin' entry is one --stdin cannot reach
    from reveal.cli.routing.file import ELEMENT_LESS_FLAGS, STDIN_BLIND_FLAGS
    from reveal.main import _SPECIAL_MODES
    dests = [d for d, _ in _SPECIAL_MODES]
    before_stdin = set(dests[:dests.index('stdin')])
    assert STDIN_BLIND_FLAGS == before_stdin & set(ELEMENT_LESS_FLAGS)
    assert set(PATH_MODES) == {f"--{d.replace('_', '-')}" for d in STDIN_BLIND_FLAGS}
