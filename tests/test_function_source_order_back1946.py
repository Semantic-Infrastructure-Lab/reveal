"""Mixed definition kinds follow source order across fresh hash-seeded processes."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = pytest.mark.component

_PROBE = '''
import json
from pathlib import Path
import sys
import reveal
from reveal.display.element import _extract_by_name, _extract_ordinal_element
from reveal.registry import get_analyzer

assert Path(reveal.__file__).resolve().parent.parent == Path(sys.argv[2]).resolve()
path = sys.argv[1]
analyzer = get_analyzer(path)(path)
assert not analyzer._has_recovery_artifacts()
outline = analyzer.get_outline()['functions']
functions = analyzer.get_structure()['functions']
answer = {
    'outline': [(item['name'], item['line'], item['line_end']) for item in outline],
    'functions': [(item['name'], item['line'], item['line_end']) for item in functions],
}
if sys.argv[3] == 'ordinals':
    answer['ordinals'] = [_extract_ordinal_element(analyzer, ordinal, 'function')
                          for ordinal in range(1, len(functions) + 1)]
elif sys.argv[3] == 'named':
    answer['named'] = _extract_by_name(analyzer, 'run')
print(json.dumps(answer))
'''


def _fresh_probe(tmp_path, extension, source, seed, mode='ordinals'):
    path = tmp_path / f'ordered.{extension}'
    path.write_text(source, encoding='utf-8')
    root = Path(__file__).resolve().parent.parent
    env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH=str(root),
               REVEAL_DISK_CACHE='0', PYTHONIOENCODING='utf-8')
    result = subprocess.run(
        [sys.executable, '-c', _PROBE, str(path), str(root), mode],
        cwd=root, env=env, capture_output=True, text=True, encoding='utf-8', timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize('seed', ['0', '1'])
@pytest.mark.parametrize('extension,source,first,second', [
    ('rb', 'def first; 1; end; def self.second; 2; end\n',
     'def first; 1; end', 'def self.second; 2; end'),
    ('rb', 'def self.first; 1; end; def second; 2; end\n',
     'def self.first; 1; end', 'def second; 2; end'),
    ('rb', 'def outer; def self.inner; 1; end; 2; end\n',
     'def outer; def self.inner; 1; end; 2; end', 'def self.inner; 1; end'),
    ('js', 'function first() { return 1; } class Box { second() { return 2; } }\n',
     'function first() { return 1; }', 'second() { return 2; }'),
    ('js', 'class Box { first() { return 1; } } function second() { return 2; }\n',
     'first() { return 1; }', 'function second() { return 2; }'),
    ('js', 'function outer() { class Box { inner() { return 1; } } return 2; }\n',
     'function outer() { class Box { inner() { return 1; } } return 2; }',
     'inner() { return 1; }'),
])
def test_same_line_mixed_and_overlapping_definitions_use_source_order(
        tmp_path, seed, extension, source, first, second):
    answer = _fresh_probe(tmp_path, extension, source, seed)
    names = ['outer', 'inner'] if 'outer' in source else ['first', 'second']
    expected = [[name, 1, 1] for name in names]
    assert answer['outline'] == answer['functions'] == expected
    assert answer['ordinals'] == [
        {'name': names[0], 'line_start': 1, 'line_end': 1, 'source': first},
        {'name': names[1], 'line_start': 1, 'line_end': 1, 'source': second},
    ]


@pytest.mark.parametrize('seed', ['0', '1'])
@pytest.mark.parametrize('extension,source,selected', [
    ('rb', 'def run; 1; end; def self.run; 2; end\n', 'def run; 1; end'),
    ('rb', 'def self.run; 1; end; def run; 2; end\n', 'def self.run; 1; end'),
    ('js', 'function run() { return 1; } class Box { run() { return 2; } }\n',
     'function run() { return 1; }'),
    ('js', 'class Box { run() { return 1; } } function run() { return 2; }\n',
     'run() { return 1; }'),
])
def test_same_line_duplicate_name_selection_and_ambiguity_are_unchanged(
        tmp_path, seed, extension, source, selected):
    answer = _fresh_probe(tmp_path, extension, source, seed, 'named')
    assert answer['named']['source'] == selected
    assert [item['selected'] for item in answer['named']['candidates']] == [True, False]


@pytest.mark.parametrize('seed', ['0', '1'])
def test_nested_same_name_keeps_outer_selection(tmp_path, seed):
    source = 'def run; def self.run; 1; end; 2; end\n'
    answer = _fresh_probe(tmp_path, 'rb', source, seed, 'named')
    assert answer['named'] == {
        'name': 'run', 'line_start': 1, 'line_end': 1,
        'source': 'def run; def self.run; 1; end; 2; end',
    }


@pytest.mark.parametrize('seed', ['0', '1'])
def test_decorated_merge_remains_in_source_order(tmp_path, seed):
    source = 'def earlier():\n    return 1\n@wrap\ndef later():\n    return 2\n'
    answer = _fresh_probe(tmp_path, 'py', source, seed)
    expected = [['earlier', 1, 2], ['later', 3, 5]]
    assert answer['outline'] == answer['functions'] == expected
    assert answer['ordinals'] == [
        {'name': 'earlier', 'line_start': 1, 'line_end': 2,
         'source': 'def earlier():\n    return 1'},
        {'name': 'later', 'line_start': 3, 'line_end': 5,
         'source': '@wrap\ndef later():\n    return 2'},
    ]


@pytest.mark.parametrize('seed', ['0', '1'])
def test_language_specific_function_value_merge_is_unchanged(tmp_path, seed):
    source = 'const earlier = () => 1;\nfunction later() { return 2; }\n'
    answer = _fresh_probe(tmp_path, 'js', source, seed, 'structure')
    expected = [['earlier', 1, 1], ['later', 2, 2]]
    assert answer['outline'] == answer['functions'] == expected
