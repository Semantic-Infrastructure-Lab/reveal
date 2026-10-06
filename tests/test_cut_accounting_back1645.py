"""BACK-1645: one cut, one pair of numbers; git:// history lists are sliceable."""
import json
import os
import subprocess

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component


def _json(*args):
    proc = _run_reveal_direct(*args, '--format', 'json')
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout), proc


def _cut(data, field):
    [entry] = [w for w in data['meta']['warnings']
               if w.get('type') == 'truncated' and w['field'] == field]
    return entry


def _functions(tmp_path, count):
    (tmp_path / 'm.py').write_text(
        ''.join(f"def f{i}():\n    return {i}\n\n" for i in range(count)), encoding='utf-8')
    return f"ast://{tmp_path}?type=function"


def test_budget_total_agrees_with_truncation_when_adapter_capped_first(tmp_path):
    """ast caps at 200 itself, then --max-items cuts that page: both say 250 matched."""
    data, _ = _json(_functions(tmp_path, 250), '--max-items', '5')
    cut = _cut(data, 'results')
    assert (cut['shown'], cut['total']) == (5, 250)
    assert data['meta']['budget']['total_available'] == cut['total'] == 250
    assert data['meta']['budget']['returned'] == len(data['results']) == 5


def test_budget_total_unchanged_when_only_max_items_cuts(tmp_path):
    """Negative control: no adapter cap involved, the two numbers were already equal."""
    data, _ = _json(_functions(tmp_path, 30), '--max-items', '5')
    assert data['meta']['budget']['total_available'] == _cut(data, 'results')['total'] == 30


@pytest.fixture
def repo(tmp_path):
    env = {**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t',
           'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@t'}
    subprocess.run(['git', 'init', '-q'], cwd=tmp_path, check=True, env=env, timeout=60)
    for i in range(12):
        (tmp_path / 'f.txt').write_text(f"{i}\n", encoding='utf-8')
        subprocess.run(['git', 'add', 'f.txt'], cwd=tmp_path, check=True, env=env, timeout=60)
        subprocess.run(['git', 'commit', '-qm', f"c{i}"], cwd=tmp_path, check=True,
                       capture_output=True, env=env, timeout=60)
    return tmp_path


@pytest.mark.parametrize('view, field', [('', 'history'), ('/f.txt', 'commits')])
def test_git_history_list_is_sliced_by_max_items(repo, view, field):
    uri = f"git://{repo}{view}?type=history&limit=8"
    data, proc = _json(uri, '--max-items', '3')
    assert len(data[field]) == 3
    cut = _cut(data, field)
    assert (cut['shown'], cut['exact']) == (3, False)
    assert cut['total'] >= 9
    assert 'no effect' not in proc.stderr


def test_git_without_max_items_keeps_its_own_cut(repo):
    """Negative control: --max-items absent, the adapter's ?limit cut is untouched."""
    data, _ = _json(f"git://{repo}?type=history&limit=8")
    assert len(data['history']) == 8
    assert _cut(data, 'history')['shown'] == 8
