"""Public D001 answers must preserve executable Python literal distinctions."""
import json

import pytest

from conftest import _run_reveal_direct as run
from reveal import api

pytestmark = pytest.mark.component


def _pair(first, second):
    return (f'def first(value):\n    result = {first}\n    return result + value\n\n'
            f'def second(value):\n    result = {second}\n    return result + value\n')


@pytest.mark.parametrize('first,second', [
    ('"#alpha"', '"#beta"'),
    ('"https://alpha.invalid/path"', '"https://beta.invalid/path"'),
    ('"one  two"', '"one two"'),
    ('"/*alpha*/value"', '"/*beta*/value"'),
    ('"""first\n  second"""', '"""first\n second"""'),
])
def test_public_check_does_not_equate_distinct_literal_values(tmp_path, first, second):
    path = tmp_path / 'literals.py'
    path.write_text(_pair(first, second), encoding='utf-8')
    assert api.check(str(path), select=['D001']) == []
    answer = run('check', str(path), '--select', 'D001', '--format', 'json')
    assert answer.returncode == 0, (answer.stdout, answer.stderr)
    assert 'D001' not in [d['rule_code'] for d in json.loads(answer.stdout).get('detections', [])]


def test_genuine_duplicate_comments_hooks_and_scope_controls(tmp_path):
    path = tmp_path / 'controls.py'
    path.write_text(
        'def first(value):\n    """first documentation"""\n    result = value + 101 # first comment\n    return result\n\n'
        'def second(value):\n    """other documentation"""\n    result = value + 101 # other comment\n    return result\n\n'
        'class A:\n    def hook(self):\n        return None\n'
        'class B:\n    def hook(self):\n        return None\n', encoding='utf-8')
    detections = api.check(str(path), select=['D001'])
    assert len(detections) == 1
    assert "'second' identical to 'first'" in detections[0].message
    assert detections[0].line == 6


def test_nonpython_duplicate_record_is_unchanged(tmp_path):
    path = tmp_path / 'controls.js'
    path.write_text('function first(value) {\n const result = value + 101;\n return result;\n}\n'
                    'function second(value) {\n const result = value + 101;\n return result;\n}\n', encoding='utf-8')
    detections = api.check(str(path), select=['D001'])
    assert len(detections) == 1
    assert detections[0].line == 5
    assert detections[0].message == "Duplicate function detected: 'second' identical to 'first' (line 1)"
    assert detections[0].suggestion == 'Refactor to share implementation with first'


@pytest.mark.parametrize('first,second', [
    (r'r"\x41"', r'r"\x42"'),
    (r'"a\tb"', '"a b"'),
    ('value // 2', 'value // 3'),
])
def test_escape_raw_and_floor_division_values_stay_distinct(tmp_path, first, second):
    path = tmp_path / 'values.py'
    path.write_text(_pair(first, second), encoding='utf-8')
    assert api.check(str(path), select=['D001']) == []


def test_matching_nontrivial_methods_in_distinct_classes_keep_scope(tmp_path):
    path = tmp_path / 'scopes.py'
    body = '    def compute(self, value):\n        result = value + 101\n        return result\n'
    path.write_text('class First:\n' + body + '\nclass Second:\n' + body, encoding='utf-8')
    assert api.check(str(path), select=['D001']) == []
