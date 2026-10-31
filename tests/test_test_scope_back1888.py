"""patches:// and testability:// choose their test files by one rule, ``is_test_path`` (BACK-1888, Q-P4-1).

Before, testability:// accepted only directories named tests/test/spec directly under the target or its
parent (celery's ``t/`` layout: "no tests found") while patches:// scanned every .py file (patch-like calls
in source files counted), so two answers about one suite differed by 1000x with no flag.
"""
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run

PATCH = "from unittest import mock\n\n\ndef test_x():\n    with mock.patch('pkg.mod.target'):\n        pass\n"
SOURCE_WITH_PATCH_CALL = "from unittest import mock\n\n\ndef helper():\n    return mock.patch('pkg.mod.other')\n"


def _w(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _json(uri: str, *args: str) -> dict:
    done = run(uri, '--format', 'json', *args)
    return json.loads(done.stdout)


@pytest.fixture
def t_layout(tmp_path):
    """The celery shape: package at the root, tests under ``t/`` (not tests/test/spec)."""
    root = tmp_path / 'repo'
    _w(root / 'pkg' / 'mod.py', 'def target():\n    return 1\n')
    _w(root / 'pkg' / 'util.py', SOURCE_WITH_PATCH_CALL)  # a patch-like call in a SOURCE file
    _w(root / 't' / 'unit' / 'test_mod.py', PATCH)
    _w(root / 't' / 'unit' / 'test_more.py', PATCH)
    return root


def test_t_layout_is_applicable_and_both_views_agree(t_layout):
    patches = _json(f'patches://{t_layout}')
    report = _json(f'testability://{t_layout}')
    assert report.get('applicable') is not False, report.get('reason')
    assert patches['total_uses'] == report['summary']['total_patch_uses'] == 2
    assert patches['test_scope'] == report['test_scope'] == {
        'rule': 'is_test_path', 'files_scanned': 2, 'anchor': '.',
        'source': 'scan_root_fallback', 'include_anchor_name': True,
        'basis': 'scan-root name and relative paths; project boundary unknown', 'suite_roots': ['.']}


def test_negative_control_a_patch_call_in_a_source_file_is_not_a_test_use(t_layout):
    # pkg/util.py holds a patch-like call; the old patches:// scanned every .py file and counted it (3).
    assert _json(f'patches://{t_layout}')['total_uses'] == 2


def test_a_test_directory_given_as_the_path_is_all_tests(tmp_path):
    suite = tmp_path / 'repo' / 'tests'
    _w(suite / 'helpers.py', PATCH)  # no test_ prefix: the root IS a test directory
    assert _json(f'patches://{suite}')['total_uses'] == 1


def test_directories_above_the_root_never_decide(tmp_path):
    inside = tmp_path / 'tests' / 'checkout'  # a checkout that lives under a tests/ directory
    _w(inside / 'src' / 'mod.py', SOURCE_WITH_PATCH_CALL)
    _w(inside / 'src' / 'test_mod.py', PATCH)
    assert _json(f'patches://{inside}')['total_uses'] == 1


def test_sibling_test_directory_of_a_package_is_found(tmp_path):
    root = tmp_path / 'repo'
    _w(root / 'pkg' / 'mod.py', 'def target():\n    return 1\n')
    _w(root / 'tests' / 'helpers.py', PATCH)
    report = _json(f'testability://{root / "pkg"}')
    assert report['summary']['total_patch_uses'] == 1
    assert report['test_scope']['rule'] == 'is_test_path'


def test_explicit_tests_is_trusted_as_the_suite(tmp_path):
    root = tmp_path / 'repo'
    _w(root / 'pkg' / 'mod.py', 'def target():\n    return 1\n')
    _w(root / 'custom' / 'helpers.py', PATCH)  # not test-named; the caller says this is the suite
    report = _json(f'testability://{root / "pkg"}?tests={root / "custom"}')
    assert report['summary']['total_patch_uses'] == 1
    assert report['test_scope'] == {'rule': 'tests=', 'files_scanned': 1}


def test_no_test_files_is_not_applicable_and_says_which_rule(tmp_path):
    _w(tmp_path / 'repo' / 'pkg' / 'mod.py', 'def target():\n    return 1\n')
    report = _json(f'testability://{tmp_path / "repo"}')
    assert report.get('applicable') is False
    assert 'is_test_path' in report['reason'] and 'tests=' in report['reason']


def test_text_output_names_the_rule(t_layout):
    for uri in (f'patches://{t_layout}', f'testability://{t_layout}'):
        out = run(uri).stdout
        assert 'Test scope: is_test_path (2 test files scanned)' in out, uri
