"""overview's Complex functions honour tests= like Hotspots (BACK-2257, follow-up of BACK-1428).

Same parameter (default exclude, path_utils.is_test_path judged from the scanned path down), same printed rule
line. The top-N is N non-test functions when they exist: the filter runs before the cut, not after ast://'s limit.
"""
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run


def _fn(name: str, branches: int) -> str:
    body = '\n'.join(f'    if x == {i}:\n        return {i}' for i in range(branches))
    return f'def {name}(x):\n{body}\n    return -1\n'


def _w(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _json(*cmd: str) -> dict:
    out = run(*cmd).stdout
    return json.loads(out[out.index('{'):])


def _names(data: dict) -> list:
    return [f['name'] for f in data['complex_functions']]


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / 'repo'
    _w(root / 'tests' / 'test_a.py', _fn('test_huge', 40) + _fn('test_big', 30) + _fn('test_mid', 25))
    _w(root / 'pkg' / 'a_test.py', _fn('helper_in_test_file', 35))
    _w(root / 'pkg' / 'core.py', _fn('core_a', 15) + _fn('core_b', 14) + _fn('core_c', 13))
    return root


def test_default_complex_functions_leave_out_test_files(repo):
    data = _json(f'overview://{repo}?top=20&no_git=true', '--format', 'json')
    assert _names(data) == ['core_a', 'core_b', 'core_c']


def test_tests_include_ranks_them_again(repo):
    data = _json(f'overview://{repo}?top=20&tests=include&no_git=true', '--format', 'json')
    assert _names(data)[:2] == ['test_huge', 'helper_in_test_file']
    assert len(_names(data)) == 7


def test_the_top_n_is_n_non_test_functions_not_what_survives_the_cut(repo):
    # Four test functions outrank every core function: a filter applied after limit=2 would return none.
    data = _json(f'overview://{repo}?top=2&no_git=true', '--format', 'json')
    assert _names(data) == ['core_a', 'core_b']
    cuts = [w for w in data['meta']['warnings'] if w.get('type') == 'truncated' and w.get('field') == 'complex_functions']
    assert len(cuts) == 1 and (cuts[0]['shown'], cuts[0]['total']) == (2, 3), cuts


def test_the_rule_line_is_printed_once_with_the_count(repo):
    data = _json(f'overview://{repo}?top=20&no_git=true', '--format', 'json')
    assert data['complex_test_scope'] == {'rule': 'is_test_path', 'tests': 'exclude', 'functions_excluded': 4}
    text = run('overview', str(repo), '--no-git', '--top', '20').stdout
    section = text[text.index('Complex functions'):]
    rule = [line for line in section.splitlines() if 'Test files' in line and 'is_test_path' in line]
    assert len(rule) == 1 and 'tests=include' in rule[0] and '4' in rule[0], rule


def test_all_complex_functions_in_tests_says_so(tmp_path):
    root = tmp_path / 'repo'
    _w(root / 'tests' / 'test_a.py', _fn('test_huge', 20))
    _w(root / 'pkg' / 'small.py', 'def tiny():\n    return 1\n')
    data = _json(f'overview://{root}?no_git=true', '--format', 'json')
    assert data['complex_functions'] == [] and data['complex_test_scope']['functions_excluded'] == 1
    text = run('overview', str(root), '--no-git').stdout
    assert 'Complex functions  (none outside test files)' in text and 'tests=include' in text


def test_negative_control_a_tree_without_test_files_keeps_its_list(tmp_path):
    root = tmp_path / 'repo'
    _w(root / 'pkg' / 'core.py', _fn('core_a', 15) + _fn('core_b', 14))
    excluded = _json(f'overview://{root}?no_git=true', '--format', 'json')
    included = _json(f'overview://{root}?no_git=true&tests=include', '--format', 'json')
    assert _names(excluded) == ['core_a', 'core_b']
    assert excluded['complex_functions'] == included['complex_functions']
    text = run('overview', str(root), '--no-git').stdout
    assert 'Complex functions' in text and 'none outside test files' not in text


def test_a_tree_without_test_files_counts_zero_excluded(tmp_path):
    root = tmp_path / 'repo'
    _w(root / 'pkg' / 'core.py', _fn('core_a', 15))
    data = _json(f'overview://{root}?no_git=true', '--format', 'json')
    assert data['complex_test_scope'] == {'rule': 'is_test_path', 'tests': 'exclude', 'functions_excluded': 0}


def test_negative_control_ast_and_hotspots_still_list_test_functions(repo):
    ast = _json(f'ast://{repo}?complexity>9&sort=-complexity', '--format', 'json')
    assert 'test_huge' in [f['name'] for f in ast['results']]
    hot = run('hotspots', str(repo), '--functions-only', '--format', 'json').stdout
    assert 'test_huge' in hot
