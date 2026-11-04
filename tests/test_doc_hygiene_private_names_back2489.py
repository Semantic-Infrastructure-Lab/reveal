"""The push gate's private-name check says whether it ran, and the push gate cannot skip it (BACK-2489).

Before: with no terms the check printed one line near the top of a long log and exited 0; with terms
and no hits it printed nothing, so 'ran clean' and 'did not run' read the same. ci-local.sh --push ran
it only when the maintainer remembered to export REVEAL_PRIVATE_TERMS_FILE.
"""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from test_calls_gate_trigger_back2204 import commit_file, repo, run_push_dispatch  # noqa: F401  (repo is a fixture)

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'scripts' / 'check_doc_hygiene.py'
pytestmark = pytest.mark.skipif(shutil.which('git') is None, reason='git required')

PLANTED = 'acme-planted-partner'
ABSENT = 'zz-no-such-term-back2489'


@pytest.fixture
def hygiene(tmp_path, monkeypatch):
    """The real script, run in-process over a two-file git repo (the full public repo takes a minute)."""
    root = tmp_path / 'public'
    root.mkdir()
    (root / 'README.md').write_text('# Project\n\nNothing private here.\n', encoding='utf-8')
    (root / 'notes.py').write_text(f'# written for {PLANTED.upper()}\n', encoding='utf-8')
    for args in (['init', '-q'], ['add', 'README.md', 'notes.py']):
        subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, timeout=30)
    spec = importlib.util.spec_from_file_location('check_doc_hygiene_back2489', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'PROJECT_ROOT', root)
    monkeypatch.setattr(module, 'check_broken_links', lambda md_file: [])  # spawns reveal per file
    for name in ('REVEAL_PRIVATE_TERMS', 'REVEAL_PRIVATE_TERMS_FILE'):
        monkeypatch.delenv(name, raising=False)
    return module


def run_main(module, monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['check_doc_hygiene.py'])
    with pytest.raises(SystemExit) as stop:
        module.main()
    out, err = capsys.readouterr()
    return stop.value.code, out, err


def status_lines(out):
    return [line for line in out.splitlines() if line.startswith('Private-name check:')]


def test_clean_check_prints_a_pass_line(hygiene, monkeypatch, capsys):
    monkeypatch.setenv('REVEAL_PRIVATE_TERMS', ABSENT)
    code, out, _ = run_main(hygiene, monkeypatch, capsys)
    lines = status_lines(out)
    assert code == 0 and len(lines) == 1 and '1 term(s), 0 hit(s) in 2 tracked files' in lines[0], out


def test_skipped_check_says_skipped(hygiene, monkeypatch, capsys):
    code, out, _ = run_main(hygiene, monkeypatch, capsys)
    lines = status_lines(out)
    assert code == 0 and len(lines) == 1 and 'SKIPPED' in lines[0], out


def test_status_is_in_the_last_lines_the_gate_shows(hygiene, monkeypatch, capsys):
    # ci-local.sh's bg_wait prints only the last three lines of a passing parallel step.
    monkeypatch.setenv('REVEAL_PRIVATE_TERMS', ABSENT)
    _, out, _ = run_main(hygiene, monkeypatch, capsys)
    tail = out.rstrip('\n').splitlines()[-3:]
    assert any(line.startswith('Private-name check:') for line in tail), tail


def test_planted_term_fails_without_printing_it(hygiene, monkeypatch, capsys):
    monkeypatch.setenv('REVEAL_PRIVATE_TERMS', PLANTED)
    code, out, err = run_main(hygiene, monkeypatch, capsys)
    assert code == 1 and 'private name(s) in the public repo' in err, (out, err)
    assert '  ! notes.py:1' in out.splitlines()
    assert PLANTED not in (out + err).lower()


def test_terms_file_is_read(hygiene, monkeypatch, capsys, tmp_path):
    terms = tmp_path / 'terms.txt'
    terms.write_text(f'# comment line\n{PLANTED}\n', encoding='utf-8')
    monkeypatch.setenv('REVEAL_PRIVATE_TERMS_FILE', str(terms))
    code, out, err = run_main(hygiene, monkeypatch, capsys)
    assert code == 1 and '  ! notes.py:1' in out.splitlines(), (out, err)


shell_only = pytest.mark.skipif(sys.platform == 'win32' or shutil.which('bash') is None,
                                reason='ci-local is a POSIX shell script')


@shell_only
def test_push_refuses_to_run_without_private_terms(repo, tmp_path):  # noqa: F811
    commit_file(repo, 'reveal/utils/results.py')
    result, marker, _ = run_push_dispatch(repo, tmp_path, ['--push'], extra_env={
        'REVEAL_PRIVATE_TERMS': '', 'REVEAL_PRIVATE_TERMS_FILE': '',
        'REVEAL_PRIVATE_TERMS_DEFAULT': str(tmp_path / 'no-such-terms.txt')})
    assert result.returncode == 2 and not marker.exists(), (result.stdout, result.stderr)
    assert 'private' in result.stderr.lower()


@shell_only
def test_push_defaults_to_the_maintainer_terms_file(repo, tmp_path):  # noqa: F811
    terms = tmp_path / 'sensitive-terms.txt'
    terms.write_text('zz-term\n', encoding='utf-8')
    commit_file(repo, 'reveal/utils/results.py')
    body = 'printf "%s" "$REVEAL_PRIVATE_TERMS_FILE" > "$SUITE_MARKER"\n'
    result, marker, _ = run_push_dispatch(repo, tmp_path, ['--push'], suite_body=body, extra_env={
        'REVEAL_PRIVATE_TERMS': '', 'REVEAL_PRIVATE_TERMS_FILE': '',
        'REVEAL_PRIVATE_TERMS_DEFAULT': str(terms)})
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert marker.read_text(encoding='utf-8') == str(terms)
