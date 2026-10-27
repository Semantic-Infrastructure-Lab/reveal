"""BACK-2271: `pack PATH --since REF --budget N` names the changed files the budget dropped.

The header said changed files are "boosted to top priority", but a changed file larger than the
remaining budget was dropped with only `[N files excluded — exceeded budget]`, and
`meta.changed_files_count` counted every file git reported, including files outside PATH.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters import pack

pytestmark = [
    pytest.mark.cli,
    pytest.mark.skipif(shutil.which('git') is None, reason='git not installed'),
]

WARNING = 'changed_files_over_budget'


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
         '-c', 'commit.gpgsign=false', '-c', 'core.excludesFile=', *args],
        check=True, capture_output=True, text=True, encoding='utf-8', timeout=30,
    )


@pytest.fixture
def repo(tmp_path):
    """src/small.py and src/big.py (~12k tokens) change; README.md and tests/ change outside src/."""
    root = tmp_path / 'repo'
    (root / 'src').mkdir(parents=True)
    _git(root, 'init', '-q')
    (root / 'src' / 'small.py').write_text('def small():\n    return 1\n', encoding='utf-8')
    (root / 'src' / 'big.py').write_text(
        ''.join(f'def f{i}():\n    return {i}\n' for i in range(3000)), encoding='utf-8')
    (root / 'src' / 'stable.py').write_text('def stable():\n    return 0\n', encoding='utf-8')
    (root / 'README.md').write_text('x\n', encoding='utf-8')
    _git(root, 'add', '--all')
    _git(root, 'commit', '-q', '-m', 'one')
    for rel in ('src/small.py', 'src/big.py', 'README.md'):
        with open(root / rel, 'a', encoding='utf-8') as fh:
            fh.write('# changed\n')
    (root / 'tests').mkdir()
    (root / 'tests' / 'test_a.py').write_text('def test_a():\n    pass\n', encoding='utf-8')
    _git(root, 'add', '--all')
    _git(root, 'commit', '-q', '-m', 'two')
    return root


def _over_budget(meta):
    return [w for w in meta.get('warnings', []) if w.get('type') == WARNING]


def test_json_names_the_changed_file_that_did_not_fit(repo):
    result = run('pack', str(repo / 'src'), '--since', 'HEAD~1', '--budget', '2000', '--format', 'json')
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert [f['relative'] for f in data['files'] if f['changed']] == ['small.py']
    warning, = _over_budget(data['meta'])
    assert warning['files'] == ['big.py']
    assert 'big.py' in warning['message'] and '--budget' in warning['message']


def test_text_names_the_changed_file_that_did_not_fit(repo):
    result = run('pack', str(repo / 'src'), '--since', 'HEAD~1', '--budget', '2000')
    assert result.returncode == 0, result.stderr
    assert 'big.py' in result.stdout + result.stderr
    assert result.stdout.count('did not fit the budget') == 1


def test_changed_count_is_scoped_to_path(repo):
    data = pack.PackAdapter(str(repo / 'src'), 'budget=2000&since=HEAD~1').get_structure()
    assert data['meta']['changed_files_count'] == 2   # small.py, big.py; not README.md, tests/


def test_single_file_path_counts_only_itself(repo):
    changed = pack.PackAdapter(str(repo / 'src' / 'small.py'), 'budget=8000&since=HEAD~1').get_structure()
    stable = pack.PackAdapter(str(repo / 'src' / 'stable.py'), 'budget=8000&since=HEAD~1').get_structure()
    assert changed['meta']['changed_files_count'] == 1
    assert stable['meta']['changed_files_count'] == 0


def test_mcp_pack_text_carries_the_warning(repo):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_pack
    answer = reveal_pack(str(repo / 'src'), budget=2000, since='HEAD~1', content=False)
    assert 'big.py' in answer and 'did not fit the budget' in answer


# Controls: nothing changes when every changed file fits, or with no --since.

def test_control_every_changed_file_fits(repo):
    data = pack.PackAdapter(str(repo / 'src'), 'budget=100000&since=HEAD~1').get_structure()
    assert sorted(f['relative'] for f in data['files'] if f['changed']) == ['big.py', 'small.py']
    assert not _over_budget(data['meta'])


def test_control_repository_root_counts_every_change(repo):
    data = pack.PackAdapter(str(repo), 'budget=100000&since=HEAD~1').get_structure()
    assert data['meta']['changed_files_count'] == 4


def test_control_no_since_has_no_changed_warning(repo):
    data = pack.PackAdapter(str(repo / 'src'), 'budget=2000').get_structure()
    assert 'changed_files_count' not in data['meta'] and not _over_budget(data['meta'])
    assert data['meta']['skipped'] == 1   # big.py is still cut, as before, and not named
