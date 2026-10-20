"""BACK-2075: depends:// on an ignored target inside a project that has other files.

BACK-2065 made the walker's ``scope_hidden`` warning appear when a walk kept nothing to
analyze. ``depends://`` walks from the project root, so a project with ordinary source
elsewhere kept files and an ignored *target* still printed 'No internal imports found'
(or 'No dependents found') with no warning. The question is whether anything is left to
analyze at the target, not at the root.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.skipif(shutil.which('git') is None, reason='git not installed')

HINT = 'entries hidden by .gitignore (use --no-gitignore to show)'

A_PY = 'from pkg import b\n\n\ndef caller():\n    return b.helper()\n'
B_PY = 'import requests\n\n\ndef helper():\n    return requests.get("http://example.invalid")\n'


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A git repo with real source in src/ and an ignored gen/ tree beside it."""
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', os.devnull)  # no developer excludes file
    root = tmp_path / 'repo'
    root.mkdir()
    subprocess.run(['git', '-C', str(root), 'init', '-q'], check=True, capture_output=True)
    _write(root, '.gitignore', 'gen/\n')
    _write(root, 'src/app/main.py', 'from app import util\n\nutil.run()\n')
    _write(root, 'src/app/util.py', 'def run():\n    return 1\n')
    _write(root, 'gen/pkg/a.py', A_PY)
    _write(root, 'gen/pkg/b.py', B_PY)
    return root


def _scope_hidden(data):
    return [w for w in (data.get('meta') or {}).get('warnings', []) if w.get('type') == 'scope_hidden']


@pytest.mark.parametrize('target', ['gen/pkg', 'gen/pkg/a.py'])
def test_ignored_target_inside_a_live_project_says_so(repo, target):
    uri = f'depends://{(repo / target).as_posix()}'
    text = _run_reveal_direct(uri)
    assert text.returncode == 0, text.stderr
    assert f'1 {HINT}' in text.stdout
    assert text.stdout.count(HINT) == 1  # once, not once per renderer layer

    out = _run_reveal_direct(uri, '--format', 'json')
    assert out.returncode == 0, out.stderr
    [warning] = _scope_hidden(json.loads(out.stdout))
    assert (warning['count'], warning['unit'], warning['hidden'], warning['causes'], warning['suggestion']) == (
        1, 'entries', {'gitignore': 1}, ['gitignore'], '--no-gitignore')
    assert f'1 {HINT}' in warning['message']


def test_no_gitignore_drops_the_warning(repo):
    """Positive control: with nothing hidden the target is analyzed and nothing is flagged."""
    uri = f'depends://{(repo / "gen" / "pkg").as_posix()}'
    text = _run_reveal_direct(uri, '--no-gitignore')
    assert HINT not in text.stdout
    data = json.loads(_run_reveal_direct(uri, '--no-gitignore', '--format', 'json').stdout)
    assert _scope_hidden(data) == []


@pytest.mark.parametrize('target', ['src/app', 'src/app/util.py'])
def test_visible_target_next_to_an_ignored_tree_stays_quiet(repo, target):
    """Negative control: gen/ is hidden in the same walk, but the target is not under it."""
    uri = f'depends://{(repo / target).as_posix()}'
    assert HINT not in _run_reveal_direct(uri).stdout
    data = json.loads(_run_reveal_direct(uri, '--format', 'json').stdout)
    assert _scope_hidden(data) == []


def test_visible_target_without_code_next_to_an_ignored_tree_stays_quiet(repo):
    """Negative control: nothing to analyze under docs/ either, but .gitignore is not why."""
    _write(repo, 'docs/readme.md', '# notes\n')
    data = json.loads(_run_reveal_direct(f'depends://{(repo / "docs").as_posix()}', '--format', 'json').stdout)
    assert _scope_hidden(data) == []


def test_ignored_subdirectory_of_the_target_with_code_left_stays_quiet(repo):
    """Negative control: the ordinary case (ignored build output inside analyzed source)."""
    _write(repo, 'src/app/gen/c.py', B_PY)
    data = json.loads(_run_reveal_direct(f'depends://{(repo / "src" / "app").as_posix()}', '--format', 'json').stdout)
    assert _scope_hidden(data) == []


@pytest.mark.parametrize('engine', ['imports', 'calls_target', 'calls_uncalled', 'surface'])
def test_sibling_engines_already_warn_for_the_same_target(repo, engine):
    """Sibling-path control: these walk the target itself, so the same ignored target
    was never silent; the shared seam change must keep it that way."""
    t = (repo / 'gen' / 'pkg').as_posix()
    uri = {'imports': f'imports://{t}', 'calls_target': f'calls://{t}?target=helper',
           'calls_uncalled': f'calls://{t}?uncalled', 'surface': f'surface://{t}'}[engine]
    data = json.loads(_run_reveal_direct(uri, '--format', 'json').stdout)
    [warning] = _scope_hidden(data)
    assert warning['suggestion'] == '--no-gitignore'
