"""patches:// declines a tree whose tests it never reads and discloses the languages it skipped (BACK-2224).

The patch scan reads Python and JavaScript/TypeScript tests. A Go, Java or Rust tree used to answer
``total_uses: 0`` with exit 0: a zero that means "not scanned" read as "no patch pressure". The rule, shared with
``patches://?view=pressure`` and ``testability://`` (one decision in ``reveal.testability.patches``):

* no scannable test file under the root: decline (``applicable: false``, exit 0 per the exit-code contract: a
  ``not_applicable`` target is shown and never fails the run), naming the languages whose test files were found;
* some scannable files and some in a language the scan does not read: scan the readable ones and disclose the
  rest (warning ``language_not_scanned`` plus ``test_scope.unscanned``);
* a scanned JS/TS suite with no mock calls: a real 0.
"""
import json

import pytest

from conftest import _run_reveal_direct as run

PATCH = "from unittest import mock\n\n\ndef test_x():\n    with mock.patch('pkg.mod.target'):\n        pass\n"
GO_TEST = 'package pkg\n\nimport "testing"\n\nfunc TestX(t *testing.T) {}\n'


def _w(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _json(*args):
    proc = run(*args, '--format', 'json')
    return proc, json.loads(proc.stdout)


@pytest.fixture
def go_tree(tmp_path):
    root = tmp_path / 'goproj'
    _w(root / 'a.go', 'package pkg\n')
    _w(root / 'a_test.go', GO_TEST)
    _w(root / 'b_test.go', GO_TEST)
    return root


def test_patches_declines_a_go_tree_instead_of_reporting_zero(go_tree):
    proc, doc = _json(f'patches://{go_tree}')
    assert proc.returncode == 0  # not_applicable never fails the run (EXIT_CODE_CONTRACT)
    assert doc.get('applicable') is False, doc.get('total_uses')
    assert 'total_uses' not in doc  # no zero that reads as an answer
    assert 'Go' in doc['reason'] and 'not scanned' in doc['reason']


def test_patches_text_says_plainly_the_language_is_not_scanned(go_tree):
    proc = run(f'patches://{go_tree}')
    assert proc.returncode == 0
    out = proc.stdout + proc.stderr
    assert 'Go' in out and 'not scanned' in out
    assert 'Patch uses: 0' not in out


def test_the_pressure_view_and_testability_name_the_same_language(go_tree):
    for uri in (f'patches://{go_tree}?view=pressure', f'testability://{go_tree}'):
        proc, doc = _json(uri)
        assert proc.returncode == 0
        assert doc.get('applicable') is False
        assert 'Go' in doc['reason'] and 'not scanned' in doc['reason'], uri


def test_a_mixed_tree_scans_the_python_and_discloses_the_go(tmp_path):
    root = tmp_path / 'mixed'
    _w(root / 'tests' / 'test_a.py', PATCH)
    _w(root / 'tests' / 'a_test.go', GO_TEST)
    _w(root / 'tests' / 'b_test.go', GO_TEST)
    proc, doc = _json(f'patches://{root}')
    assert proc.returncode == 0
    assert doc['total_uses'] == 1
    assert doc['test_scope']['files_scanned'] == 1
    assert doc['test_scope']['unscanned'] == {'Go': 2}
    warning = [w for w in doc['meta']['warnings'] if w.get('code') == 'language_not_scanned']
    assert len(warning) == 1 and 'Go' in warning[0]['message']
    text = run(f'patches://{root}')
    assert 'not scanned' in text.stdout + text.stderr


def test_a_stray_script_beside_a_scanned_suite_is_not_disclosed(tmp_path):
    """The census rule (LanguageCoverage.should_warn): disclose once unread test files outnumber the read ones.
    python-celery's one test_cluster.sh among 184 Python tests keeps its answer byte-identical."""
    root = tmp_path / 'pyproj'
    for name in ('test_a.py', 'test_b.py', 'test_c.py'):
        _w(root / 'tests' / name, PATCH)
    _w(root / 'tests' / 'test_cluster.sh', 'echo ok\n')
    proc, doc = _json(f'patches://{root}')
    assert proc.returncode == 0 and doc['total_uses'] == 3
    assert doc['test_scope'] == {
        'rule': 'is_test_path', 'files_scanned': 3, 'anchor': '.',
        'source': 'scan_root_fallback', 'include_anchor_name': True,
        'basis': 'scan-root name and relative paths; project boundary unknown', 'suite_roots': ['.']}
    assert not [w for w in doc['meta']['warnings'] if w.get('code') == 'language_not_scanned']


def test_a_scanned_js_suite_with_no_mocks_is_a_real_zero(tmp_path):
    root = tmp_path / 'jsproj'
    _w(root / 'tests' / 'a.test.js', "test('x', () => { expect(1).toBe(1); });\n")
    proc, doc = _json(f'patches://{root}')
    assert proc.returncode == 0
    assert doc.get('applicable') is not False
    assert doc['total_uses'] == 0 and doc['test_scope']['files_scanned'] == 1
    assert 'unscanned' not in doc['test_scope']
    assert not [w for w in doc['meta']['warnings'] if w.get('code') == 'language_not_scanned']


def test_a_python_tree_with_data_files_discloses_nothing(tmp_path):
    root = tmp_path / 'pyproj'
    _w(root / 'tests' / 'test_a.py', PATCH)
    _w(root / 'tests' / 'data.json', '{}\n')
    _w(root / 'tests' / 'notes.md', '# notes\n')
    proc, doc = _json(f'patches://{root}')
    assert proc.returncode == 0
    assert doc['total_uses'] == 1
    assert 'unscanned' not in doc['test_scope']
    assert not [w for w in doc['meta']['warnings'] if w.get('code') == 'language_not_scanned']
