"""overview's Hotspots skip test files by default; tests=include ranks them (BACK-1428, Q-P4-1).

Test files are chosen by the one shared rule, `path_utils.is_test_path` (the rule patches:// and testability://
use since BACK-1888), judged from the scan root's own name down. Before, the top-5 on kubernetes was a *_test.go
file and on elasticsearch two *Tests.java files: ranks a newcomer reads as the code to refactor.
"""
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run

LONG_BODY = '\n'.join(f'    x{i} = {i}' for i in range(110))
LONG_PY = f'def big():\n{LONG_BODY}\n    return x1\n'
LONG_GO = 'package p\n\nfunc big() int {\n' + '\n'.join(f'\tx{i} := {i}\n\t_ = x{i}' for i in range(60)) + '\n\treturn 1\n}\n'
LONG_JAVA = 'class T {\n    int big() {\n' + '\n'.join(f'        int x{i} = {i};' for i in range(110)) + '\n        return 1;\n    }\n}\n'


def _w(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _json(*cmd: str) -> dict:
    out = run(*cmd).stdout
    return json.loads(out[out.index('{'):])  # an unknown-parameter warning may precede the document


def _hotspot_files(root: Path, *args: str, uri_query: str = '') -> list:
    target = f'overview://{root}{uri_query}' if uri_query else str(root)
    cmd = (target, '--format', 'json', *args) if uri_query else ('overview', target, '--no-git', '--format', 'json', *args)
    data = _json(*cmd)
    return [h['file'] for h in data['stats']['hotspots']]


@pytest.fixture
def mixed(tmp_path):
    root = tmp_path / 'repo'
    _w(root / 'pkg' / 'big.py', LONG_PY)
    _w(root / 'pkg' / 'big_test.py', LONG_PY)
    _w(root / 'tests' / 'helpers.py', LONG_PY)
    _w(root / 'srv' / 'big.go', LONG_GO)
    _w(root / 'srv' / 'big_test.go', LONG_GO)
    _w(root / 'jv' / 'Big.java', LONG_JAVA)
    _w(root / 'jv' / 'BigTests.java', LONG_JAVA)
    return root


def test_default_overview_hotspots_skip_test_files(mixed):
    assert sorted(_hotspot_files(mixed, '--top', '20')) == ['jv/Big.java', 'pkg/big.py', 'srv/big.go']


def test_tests_include_ranks_them_again(mixed):
    files = _hotspot_files(mixed, uri_query='?top=20&tests=include&no_git=true')
    assert sorted(files) == ['jv/Big.java', 'jv/BigTests.java', 'pkg/big.py', 'pkg/big_test.py',
                             'srv/big.go', 'srv/big_test.go', 'tests/helpers.py']


def test_the_default_output_says_what_it_excluded_and_how_to_include_them(mixed):
    data = _json('overview', str(mixed), '--no-git', '--top', '20', '--format', 'json')
    assert data['stats']['test_scope'] == {'rule': 'is_test_path', 'tests': 'exclude', 'files_excluded': 4}
    text = run('overview', str(mixed), '--no-git', '--top', '20').stdout
    rule = [line for line in text.splitlines() if 'test files' in line and 'is_test_path' in line]
    assert len(rule) == 1 and 'tests=include' in rule[0] and '4' in rule[0], rule


def test_the_include_override_says_so(mixed):
    data = _json(f'overview://{mixed}?tests=include&no_git=true', '--format', 'json')
    assert data['stats']['test_scope']['tests'] == 'include'


def test_a_bad_tests_value_exits_2(mixed):
    assert run(f'overview://{mixed}?tests=maybe&no_git=true').returncode == 2


def test_negative_control_metrics_and_hotspots_nouns_keep_test_files(mixed):
    # The filter is a declared parameter of the shared stats owner whose default is unchanged:
    # `reveal hotspots` and metrics:// rank the test files exactly as before.
    metrics = _json(f'metrics://{mixed}?hotspots=true&top=20', '--format', 'json')
    assert 'pkg/big_test.py' in [h['file'] for h in metrics['hotspots']]
    hot = run('hotspots', str(mixed), '--format', 'json', '--top', '20').stdout
    assert 'big_test.py' in hot


def test_negative_control_a_tree_without_test_files_is_unchanged(tmp_path):
    root = tmp_path / 'repo'
    _w(root / 'pkg' / 'big.py', LONG_PY)
    _w(root / 'pkg' / 'other.py', LONG_PY)
    data = _json('overview', str(root), '--no-git', '--format', 'json')
    assert sorted(h['file'] for h in data['stats']['hotspots']) == ['pkg/big.py', 'pkg/other.py']
    assert data['stats']['test_scope']['files_excluded'] == 0


def test_a_checkout_under_a_tests_directory_is_not_all_tests(tmp_path):
    root = tmp_path / 'tests' / 'checkout'
    _w(root / 'pkg' / 'big.py', LONG_PY)
    assert _hotspot_files(root) == ['pkg/big.py']
