"""Ruby method spans agree across named, line and ordinal extraction."""

import pytest

from reveal.display.element import (
    _extract_by_name, _extract_by_syntax, _extract_element_at_line,
    _extract_ordinal_element, _parse_element_syntax,
)
from reveal.registry import get_analyzer

pytestmark = pytest.mark.component


def _analyzer(tmp_path, source):
    path = tmp_path / 'methods.rb'
    path.write_text(source, encoding='utf-8')
    analyzer = get_analyzer(str(path))(str(path))
    assert not analyzer._has_recovery_artifacts()
    return analyzer


@pytest.fixture(params=[
    pytest.param(('  def run(value)\n    value + 1\n  end', 'run'), id='instance'),
    pytest.param(('  def self.build(value)\n    value * 2\n  end', 'build'), id='singleton'),
    pytest.param(('  def [](key)\n    key\n  end', '[]'), id='operator'),
    pytest.param(('  def value=(next_value)\n    @value = next_value\n  end', 'value='), id='setter'),
    pytest.param(('  def self.[]=(key, next_value)\n    @value = next_value\n  end', '[]='),
                 id='singleton_operator'),
    pytest.param(('  def +(other)\n    other\n  end', '+'), id='plus_operator'),
])
def method(request, tmp_path):
    body, name = request.param
    analyzer = _analyzer(tmp_path, f'class Box\n{body}\nend\n')
    expected = {'name': name, 'line_start': 2, 'line_end': 4, 'source': body}
    return analyzer, expected


def test_named_method_keeps_manual_name_and_span(method):
    analyzer, expected = method
    assert _extract_by_name(analyzer, expected['name']) == expected


def test_method_declaration_body_and_closing_line_match_named(method):
    analyzer, expected = method
    for _ in range(2):
        for line in (2, 3, 4):
            assert _extract_element_at_line(analyzer, line) == expected


def test_method_ordinal_keeps_manual_name_and_span(method):
    analyzer, expected = method
    assert _extract_ordinal_element(analyzer, 1, 'function') == expected


@pytest.mark.parametrize('receiver', ['', 'self.'], ids=['instance', 'singleton'])
@pytest.mark.parametrize('ordinal,name,value', [
    (1, 'first', 1),
    (2, 'second', 2),
])
def test_inline_ordinal_excludes_assignment_and_adjacent_method(tmp_path, receiver, ordinal, name, value):
    analyzer = _analyzer(tmp_path,
        f'seed = 1; def {receiver}first; 1; end; def {receiver}second; 2; end\n')
    source = f'def {receiver}{name}; {value}; end'
    expected = {'name': name, 'line_start': 1, 'line_end': 1, 'source': source}
    assert _extract_by_name(analyzer, name) == expected
    assert _extract_ordinal_element(analyzer, ordinal, 'function') == expected


def test_owner_paths_keep_adjacent_and_nested_methods_separate(tmp_path):
    analyzer = _analyzer(tmp_path,
        'class A\n  def run\n    1\n  end\nend\n'
        'class Outer\n  class Inner\n    def self.run\n      2\n    end\n  end\nend\n')
    for address, start, end, source in [
        ('A.run', 2, 4, '  def run\n    1\n  end'),
        ('Outer.Inner.run', 8, 10, '    def self.run\n      2\n    end'),
    ]:
        expected = {'name': address, 'line_start': start, 'line_end': end, 'source': source}
        assert _extract_by_syntax(analyzer, address, _parse_element_syntax(address)) == expected
        for line in range(start, end + 1):
            assert _extract_element_at_line(analyzer, line) == dict(expected, name='run')


def test_instance_and_singleton_duplicate_names_keep_ambiguity(tmp_path):
    analyzer = _analyzer(tmp_path,
        'class Box\n  def run\n    1\n  end\n  def self.run\n    2\n  end\nend\n')
    assert _extract_by_name(analyzer, 'run') == {
        'name': 'run', 'line_start': 2, 'line_end': 4, 'source': '  def run\n    1\n  end',
        'candidates': [
            {'name': 'Box.run', 'line_start': 2, 'line_end': 4,
             'address': ':2-4', 'selected': True},
            {'name': 'Box.run', 'line_start': 5, 'line_end': 7,
             'address': ':5-7', 'selected': False},
        ],
    }


@pytest.mark.parametrize('line', [1, 2, 3, 4, 5, 6, 7])
def test_class_nondefinition_and_anonymous_siblings_are_unchanged(tmp_path, line):
    analyzer = _analyzer(tmp_path,
        '# Header\nvalue = 1\ncallback = ->(item) { item }\nvalue.to_s\n'
        'class Empty\n  MARKER = 1\nend\n')
    assert _extract_element_at_line(analyzer, line) is None
    assert _extract_by_name(analyzer, 'Empty') == {
        'name': 'Empty', 'line_start': 5, 'line_end': 7,
        'source': 'class Empty\n  MARKER = 1\nend',
    }
