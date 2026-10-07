"""BACK-1751: an early-exit mode that reads no path must refuse one.

`reveal a.py b.py --rules` printed the rule list and exited 0: both paths were dropped without
a word (likewise --adapters, --languages, --list-schemas and the other pathless entries of
`reveal.main._SPECIAL_MODES`). The user named files and got an answer that ignores them. Each
is now a usage error (stderr names the flag and the ignored argument, exit 2, nothing on
stdout), declared once as PATHLESS_FLAGS next to ELEMENT_LESS_FLAGS. The completeness check
that every special mode is classified lives in test_element_less_completeness_back1735.py.

--disable-breadcrumbs is declared but not run here: on the unfixed code it writes the user's
real config file.
"""

import subprocess
import sys

import pytest

from conftest import _run_reveal_direct

# argv of every pathless mode exercised here (value flags carry a value)
PATHLESS = [
    ['--rules'], ['--adapters'], ['--languages'], ['--list-schemas'], ['--list-supported'],
    ['--agent-help'], ['--profiles'], ['--schema'], ['--discover'],
    ['--language-info', 'python'], ['--explain', 'B001'],
]


def _ids(flags):
    return [' '.join(f) for f in flags]


@pytest.fixture
def files(tmp_path):
    for name in ('a', 'b'):
        (tmp_path / f'{name}.py').write_text('x = 1\n', encoding='utf-8')
    return tmp_path


def _assert_refused(proc, flag, *ignored):
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert flag in proc.stderr
    assert 'takes no path' in proc.stderr
    for arg in ignored:
        assert arg in proc.stderr
    assert proc.stdout == ''


@pytest.mark.parametrize('flag', PATHLESS, ids=_ids(PATHLESS))
def test_pathless_mode_refuses_one_path(files, flag):
    a = str(files / 'a.py')
    _assert_refused(_run_reveal_direct(a, *flag), flag[0], a)


@pytest.mark.parametrize('flag', [['--rules'], ['--list-schemas'], ['--adapters']],
                         ids=_ids([['--rules'], ['--list-schemas'], ['--adapters']]))
def test_pathless_mode_refuses_two_paths_and_names_both(files, flag):
    a, b = str(files / 'a.py'), str(files / 'b.py')
    _assert_refused(_run_reveal_direct(a, b, *flag), flag[0], a, b)


def test_a_uri_is_refused_too(files):
    _assert_refused(_run_reveal_direct('ast://.', '--rules'), '--rules', 'ast://.')


def test_an_at_file_list_is_refused_too(files):
    listing = files / 'list.txt'
    listing.write_text(str(files / 'a.py') + '\n', encoding='utf-8')
    _assert_refused(_run_reveal_direct(f'@{listing}', '--languages'), '--languages', f'@{listing}')


def test_stdin_refuses_a_path_argument(files):
    """`reveal a.py --stdin` read the piped paths and dropped a.py. A subprocess, so stdin is real."""
    proc = subprocess.run([sys.executable, '-m', 'reveal', 'a.py', '--stdin'], cwd=files,
                          input='b.py\n', capture_output=True, text=True, encoding='utf-8',
                          timeout=60)
    _assert_refused(proc, '--stdin', 'a.py')


def test_hint_repeats_a_value_flag_with_its_value(files):
    proc = _run_reveal_direct(str(files / 'a.py'), '--explain', 'B001')
    assert 'reveal --explain B001' in proc.stderr


def test_every_declared_pathless_flag_is_a_real_parser_option():
    """A declaration naming a dest the parser lacks would silently guard nothing."""
    from reveal.cli.parser import create_argument_parser
    from reveal.cli.routing import PATHLESS_FLAGS
    dests = {a.dest: a.option_strings for a in create_argument_parser('x')._actions}
    for dest, spelling in PATHLESS_FLAGS.items():
        assert spelling in dests.get(dest, []), dest


# Negative controls: what must not change.
@pytest.mark.parametrize('flag', PATHLESS, ids=_ids(PATHLESS))
def test_pathless_mode_without_a_path_still_runs(flag):
    proc = _run_reveal_direct(*flag)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip()
    assert 'takes no path' not in proc.stderr


def test_a_mode_that_reads_the_path_still_takes_one(files):
    proc = _run_reveal_direct(str(files / 'a.py'), '--show-ast')
    assert proc.returncode == 0, proc.stderr
    assert 'takes no path' not in proc.stderr


def test_refusal_follows_the_mode_that_runs(files):
    """--show-ast is dispatched before --rules, so the path is read: no refusal (--rules is noted)."""
    proc = _run_reveal_direct(str(files / 'a.py'), '--rules', '--show-ast')
    assert proc.returncode == 0, proc.stderr
    assert 'takes no path' not in proc.stderr
    assert '--rules has no effect' in proc.stderr


def test_a_path_and_an_element_still_work(files):
    (files / 'f.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    proc = _run_reveal_direct(str(files / 'f.py'), 'f')
    assert proc.returncode == 0, proc.stderr
    assert 'return 1' in proc.stdout
