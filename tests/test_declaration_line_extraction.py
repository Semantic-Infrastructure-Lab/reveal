"""Declaration lines share named extraction spans (BACK-1918, BACK-1933)."""

import pytest

from reveal.display.element import (
    _extract_by_name, _extract_by_syntax, _extract_element_at_line,
    _parse_element_syntax,
)
from reveal.registry import get_analyzer

pytestmark = pytest.mark.component


@pytest.fixture(params=['dart', 'zig'])
def analyzer(request, tmp_path):
    if request.param == 'dart':
        declaration = "import 'dart:math';"
        function = 'int {name}() {{\n  return {value};\n}}'
        variable = 'const value = 4;'
    else:
        declaration = 'const std = @import("std");'
        function = 'fn {name}() u32 {{\n  return {value};\n}}'
        variable = 'const value: u32 = 4;'
    source = '\n'.join([
        '// Declaration-line controls.', declaration, '',
        function.format(name='first', value=1), '',
        function.format(name='second', value=2),
        function.format(name='third', value=3), '', variable, '',
    ])
    path = tmp_path / f'controls.{request.param}'
    path.write_text(source, encoding='utf-8')
    instance = get_analyzer(str(path))(str(path))
    assert not instance.has_parse_errors()
    return instance


@pytest.mark.parametrize('name,start,end', [
    ('first', 4, 6), ('second', 8, 10), ('third', 11, 13),
])
def test_declaration_body_and_closing_line_match_named(analyzer, name, start, end):
    named = _extract_by_name(analyzer, name)
    assert (named['line_start'], named['line_end'], named['name']) == (start, end, name)
    for _ in range(2):
        for line in range(start, end + 1):
            assert _extract_element_at_line(analyzer, line) == named


@pytest.mark.parametrize('line', [1, 2, 3, 7, 14, 15, 16, 17])
def test_comments_imports_blanks_and_variables_are_not_functions(analyzer, line):
    assert _extract_element_at_line(analyzer, line) is None


def test_explicit_range_crosses_adjacent_functions_without_snapping(analyzer):
    result = _extract_by_syntax(analyzer, ':9-12', _parse_element_syntax(':9-12'))
    assert (result['line_start'], result['line_end'], result['name']) == (9, 12, 'lines:9-12')
    assert result['source'] == '\n'.join(analyzer.lines[8:12])


def test_blank_line_still_uses_context_window(analyzer):
    result = _extract_by_syntax(analyzer, ':7', _parse_element_syntax(':7'))
    assert result['name'].startswith('lines:')
    assert result['line_start'] == 1
    assert 'first' in result['source'] and 'second' in result['source']
