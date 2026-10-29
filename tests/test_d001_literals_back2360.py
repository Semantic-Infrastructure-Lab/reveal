"""D001's Python comparison preserves literals and only removes real comments/docstrings."""

import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tokenize

import pytest

from reveal.analyzers.python import PythonAnalyzer
from reveal.rules.duplicates.D001 import D001


ROOT = Path(__file__).resolve().parents[1]


def _pair(first, second):
    return f'def first(value):\n{first}\n\ndef second(value):\n{second}\n'


def _check(tmp_path, source, suffix='.py'):
    path = tmp_path / ('sample' + suffix)
    path.write_text(source, encoding='utf-8')
    env = {**os.environ, 'PYTHONPATH': str(ROOT), 'REVEAL_DISK_CACHE': '0',
           'REVEAL_MAX_WORKERS': '1', 'REVEAL_NO_UPDATE_CHECK': '1'}
    response = subprocess.run(
        [sys.executable, '-m', 'reveal', 'check', str(path), '--select', 'D001',
         '--no-gitignore', '--format', 'json'],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', timeout=60,
    )
    answer = json.loads(response.stdout)
    assert answer['coverage']['failed'] == answer['coverage']['unavailable'] == 0
    assert answer['scan_disclosures'] == []
    return response, answer['detections']


@pytest.mark.integration
@pytest.mark.parametrize('first,second', [
    ('return "prefix#red"', 'return "prefix#blue"'),
    ('return "https://red.example/path"', 'return "https://blue.example/path"'),
    ('return "a/*red*/z"', 'return "a/*blue*/z"'),
    ('return "two  spaces"', 'return "two spaces"'),
    ('return "a\tb"', 'return "a b"'),
    (r'return "a\\#red"', r'return "a\\#blue"'),
    ('return r"prefix#red"', 'return r"prefix#blue"'),
    ('return f"prefix#{value}"', 'return f"prefix#{value + 1}"'),
    ('return value // 2', 'return value // 3'),
    ('text = """red#value\n    keep  spacing"""\n    return text',
     'text = """blue#value\n    keep  spacing"""\n    return text'),
    ('return """red#value\n    keep  spacing"""',
     'return """blue#value\n    keep  spacing"""'),
    ('if value:\n        """red text"""\n    return value',
     'if value:\n        """blue text"""\n    return value'),
    ('value += 1\n    """red text"""\n    return value',
     'value += 1\n    """blue text"""\n    return value'),
], ids=['hash', 'https', 'block-marker', 'spaces', 'tab', 'escape', 'raw', 'fstring',
        'floor-division', 'assigned-triple', 'returned-triple', 'if-string', 'later-string'])
def test_distinct_python_values_do_not_gate_as_duplicates(tmp_path, first, second):
    source = _pair('    ' + first, '    ' + second)
    tree = ast.parse(source)
    assert [node.name for node in tree.body] == ['first', 'second']
    response, detections = _check(tmp_path, source)
    assert detections == [], detections
    assert response.returncode == 0, response.stderr


@pytest.mark.integration
@pytest.mark.parametrize('first,second', [
    ('return value * 2 + 3', 'return value * 2 + 3'),
    ('# first comment\n    result = value + 1\n    return result',
     '# different comment\n    result   =   value + 1 # inline\n    return result'),
    ('"""First docs."""\n    return value + 1',
     '"""Second docs."""\n    return value + 1'),
    ('"First docs."\n    return value + 1', '"Second docs."\n    return value + 1'),
    ('("First "\n     "docs.")\n    return value + 1',
     '("Different docs.")\n    return value + 1'),
], ids=['genuine', 'comments-format', 'triple-docstring', 'single-docstring', 'parenthesized-docstring'])
def test_real_duplicates_survive_comment_and_docstring_normalization(tmp_path, first, second):
    source = _pair('    ' + first, '    ' + second)
    ast.parse(source)
    response, detections = _check(tmp_path, source)
    assert len(detections) == 1
    assert "'second' identical to 'first' (line 1)" in detections[0]['message']
    assert response.returncode == 1


@pytest.mark.integration
def test_noop_hooks_remain_exempt(tmp_path):
    source = _pair('    """First hook."""\n    return []',
                   '    """Second hook."""\n    return []')
    response, detections = _check(tmp_path, source)
    assert detections == []
    assert response.returncode == 0


@pytest.mark.integration
@pytest.mark.parametrize('suffix,source', [
    ('.java', 'class A {\n int first(int value) {\n  return value + 10;\n }\n'
              ' int second(int value) {\n  return value + 10;\n }\n}\n'),
    ('.rb', 'class A\n def first(value)\n  return value + 10\n end\n'
            ' def second(value)\n  return value + 10\n end\nend\n'),
    ('.lua', 'local function first(value)\n return value + 10\nend\n'
             'local function second(value)\n return value + 10\nend\n'),
])
def test_non_python_duplicate_behavior_is_unchanged(tmp_path, suffix, source):
    response, detections = _check(tmp_path, source, suffix)
    assert len(detections) == 1
    assert "'second' identical to 'first'" in detections[0]['message']
    assert response.returncode == 1


@pytest.mark.parametrize('failure', ['exception', 'error-token'])
def test_uncertain_tokenization_retains_distinct_source(tmp_path, monkeypatch, failure):
    source = _pair('    return "prefix#red"', '    return "prefix#blue"')
    path = tmp_path / 'sample.py'
    path.write_text(source, encoding='utf-8')
    structure = PythonAnalyzer(str(path)).get_structure()

    def uncertain(readline):
        if failure == 'exception':
            raise tokenize.TokenError('incomplete', (1, 0))
        yield tokenize.TokenInfo(tokenize.ERRORTOKEN, '"', (1, 0), (1, 1), '"')

    monkeypatch.setattr(tokenize, 'generate_tokens', uncertain)
    assert D001().check(str(path), structure, source) == []
