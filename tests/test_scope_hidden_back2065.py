"""BACK-2065: analysis engines said a clean zero when .gitignore hid the whole tree.

``imports://`` printed 'Total Files: 0', ``depends://`` 'No internal imports found',
``calls://?target=`` 'No callers found', ``calls://?uncalled`` 'Total defined: 0' and
``surface://`` 'No external surfaces detected' for a directory under an ignored path,
while the path forms (tree, ``--grep``) already said '... N entries hidden by .gitignore
(use --no-gitignore to show)' (BACK-1224, BACK-1546). The walker's ``on_hidden`` tally
now reaches each engine's result as one ``scope_hidden`` warning, in text and JSON.
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

# Two files that import, call and reach the network: each engine has a real answer
# for them once they are not hidden.
A_PY = 'from pkg import b\n\n\ndef caller():\n    return b.helper()\n'
B_PY = 'import requests\n\n\ndef helper():\n    return requests.get("http://example.invalid")\n'


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A git repo whose .gitignore hides gen/, the tree every engine is pointed at."""
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', os.devnull)  # no developer excludes file
    root = tmp_path / 'repo'
    root.mkdir()
    subprocess.run(['git', '-C', str(root), 'init', '-q'], check=True, capture_output=True)
    _write(root, '.gitignore', 'gen/\n')
    _write(root, 'gen/pyproject.toml', '[project]\nname = "pkg"\n')  # depends:// project root
    _write(root, 'gen/pkg/a.py', A_PY)
    _write(root, 'gen/pkg/b.py', B_PY)
    return root


def _uris(target: Path):
    t = target.as_posix()
    return {
        'imports': f'imports://{t}',
        'depends': f'depends://{t}',
        'calls_target': f'calls://{t}?target=helper',
        'calls_uncalled': f'calls://{t}?uncalled',
        'surface': f'surface://{t}',
    }


def _scope_hidden(data):
    return [w for w in (data.get('meta') or {}).get('warnings', []) if w.get('type') == 'scope_hidden']


# depends:// walks from the project root it finds (gen/, by its pyproject.toml): pkg/ and
# pyproject.toml are the entries hidden there. The others walk gen/pkg: a.py and b.py.
EXPECTED_HIDDEN = {'imports': 2, 'depends': 2, 'calls_target': 2, 'calls_uncalled': 2, 'surface': 2}


@pytest.mark.parametrize('engine', sorted(EXPECTED_HIDDEN))
def test_every_engine_says_what_gitignore_hid(repo, engine):
    uri = _uris(repo / 'gen' / 'pkg')[engine]
    text = _run_reveal_direct(uri)
    assert text.returncode == 0, text.stderr
    count = EXPECTED_HIDDEN[engine]
    assert f'{count} {HINT}' in text.stdout
    assert text.stdout.count(HINT) == 1  # once, not once per renderer layer

    out = _run_reveal_direct(uri, '--format', 'json')
    assert out.returncode == 0, out.stderr
    [warning] = _scope_hidden(json.loads(out.stdout))
    assert (warning['count'], warning['unit'], warning['hidden'], warning['causes'], warning['suggestion']) == (
        count, 'entries', {'gitignore': count}, ['gitignore'], '--no-gitignore')
    assert f'{count} {HINT}' in warning['message']


def test_no_gitignore_answers_and_drops_the_warning(repo):
    """Positive control: the fixture has real answers once nothing is hidden."""
    uris = _uris(repo / 'gen' / 'pkg')
    expected = {
        'imports': 'Total Files:   2',
        'calls_target': 'Total:      1',
        'calls_uncalled': 'Total defined:        2',
        'surface': 'import requests',
    }
    for engine, needle in expected.items():
        text = _run_reveal_direct(uris[engine], '--no-gitignore')
        assert needle in text.stdout, (engine, text.stdout)
        assert HINT not in text.stdout
        data = json.loads(_run_reveal_direct(uris[engine], '--no-gitignore', '--format', 'json').stdout)
        assert _scope_hidden(data) == []


def test_a_tree_with_analyzable_files_left_has_no_warning(repo):
    """Only a walk that kept nothing to analyze says so: an ignored sibling of real
    source is the ordinary case (build/, generated code) and stays quiet."""
    _write(repo, 'src/pkg/a.py', A_PY)
    _write(repo, 'src/pkg/b.py', B_PY)
    _write(repo, 'src/pkg/gen/c.py', B_PY)
    _write(repo, '.gitignore', 'gen/\n')
    for engine, uri in _uris(repo / 'src').items():
        out = _run_reveal_direct(uri, '--format', 'json')
        assert out.returncode == 0, (engine, out.stderr)
        assert _scope_hidden(json.loads(out.stdout)) == [], engine


def test_resolution_walk_reports_each_hidden_entry_once(repo):
    """walk_with_causes descends a gitignored directory (its files are import targets);
    the directory is reported, its contents are not reported again under it."""
    from reveal.utils.path_utils import ANALYSIS, RESOLUTION, HiddenTally, walk_tree, walk_with_causes
    _write(repo, 'gen/pkg/sub/c.py', B_PY)
    tally = HiddenTally()
    found = sorted(p.name for p, _cause in walk_with_causes(repo, RESOLUTION, on_hidden=tally))
    assert found == ['.gitignore', 'a.py', 'b.py', 'c.py', 'pyproject.toml']  # still targets
    assert dict(tally) == {'gitignore': 1}  # gen/, once
    plain = HiddenTally()
    assert [f for _root, _dirs, files in walk_tree(repo, ANALYSIS, on_hidden=plain) for f in files] == ['.gitignore']
    assert dict(plain) == dict(tally)


def test_warning_policy():
    from reveal.utils.path_utils import hidden_entries_warning
    assert hidden_entries_warning({'gitignore': 3}, analyzed=1) is None  # something was analyzed
    assert hidden_entries_warning({}, analyzed=0) is None  # nothing hidden: a real zero
    assert hidden_entries_warning({'noise': 3}, analyzed=0) is None  # no flag shows noise
    warning = hidden_entries_warning({'exclude': 1, 'gitignore': 2}, analyzed=0)
    assert (warning['count'], warning['hidden'], warning['causes'], warning['suggestion']) == (
        3, {'gitignore': 2, 'exclude': 1}, ['exclude', 'gitignore'], '--no-gitignore')
    assert '3 entries hidden (2 by .gitignore (use --no-gitignore to show); 1 by --exclude)' in warning['message']
    assert 'suggestion' not in hidden_entries_warning({'exclude': 1}, analyzed=0)
