"""BACK-2837: a JS/TS element read prints the source line it cites.

A function value was extracted from its function literal, so the binding that
names it was cut off: `const g = () => 2` printed `() => 2;`, a class-field
arrow `(e) => {`, an object member `() => 1`, `module.exports.f = function`
`function () {...}`, and `export function f` lost its `export`. The element
now widens to the binding (the whole declaration when it binds only this
name) and to an enclosing `export` statement, the way Go widens a type body to
its `type` declaration (COMMAND_MODEL rule 9: an element read returns the
whole unit).
"""
from pathlib import Path

import pytest

from reveal.display.element import _extract_by_syntax, _parse_element_syntax
from reveal.registry import get_analyzer

JS = """\
class Widget {
  handleClick = (e) => {
    return e.target;
  }
}
const api = {
  fetchAll: () => 1,
  save: function () { return 2; },
};
module.exports.helper = function () { return 3; };
exports.other = () => 4;
let a = () => 5, b = () => 6;
export const named = async () => 7;
export function plain() { return 8; }
export default class Main {}
const multi =
  () => 9;
const Wrapped = memo(() => 10);
const g = () => 2;
"""

# name -> (line_start, first source line). Each first line is the file's own
# line from its start, except `a` and `b`: one declaration binds both, so each
# is its own declarator (`b = () => 6;`), never the other's text.
EXPECTED_JS = {
    'Widget.handleClick': (2, '  handleClick = (e) => {'),
    'api.fetchAll': (7, '  fetchAll: () => 1'),
    'api.save': (8, '  save: function () { return 2; }'),
    'module.exports.helper': (10, 'module.exports.helper = function () { return 3; };'),
    'exports.other': (11, 'exports.other = () => 4;'),
    'a': (12, 'a = () => 5'),
    'b': (12, 'b = () => 6;'),
    'named': (13, 'export const named = async () => 7;'),
    'plain': (14, 'export function plain() { return 8; }'),
    'Main': (15, 'export default class Main {}'),
    'multi': (16, 'const multi ='),
    'Wrapped': (18, 'const Wrapped = memo(() => 10);'),
    'g': (19, 'const g = () => 2;'),
}

TS_EXTRA = """\
export interface Shape { area(): number }
class Panel {
  private onClose = (): void => {};
}
declare function Input(): void;
export declare function Output(): void;
"""
EXPECTED_TS_EXTRA = {
    'Shape': (20, 'export interface Shape { area(): number }'),
    'Panel.onClose': (22, '  private onClose = (): void => {};'),
    'Input': (24, 'declare function Input(): void;'),
    'Output': (25, 'export declare function Output(): void;'),
}


def _extract(path: Path, name: str):
    analyzer = get_analyzer(str(path))(str(path))
    result = _extract_by_syntax(analyzer, name, _parse_element_syntax(name))
    assert result, f'{name} not extracted from {path.name}'
    return result


def _first_lines(path: Path, expected: dict) -> dict:
    got = {}
    for name in expected:
        result = _extract(path, name)
        got[name] = (result['line_start'], result['source'].split('\n', 1)[0])
    return got


@pytest.mark.parametrize('suffix', ['.js', '.ts', '.tsx'])
def test_function_value_reads_carry_their_binding(tmp_path, suffix):
    path = tmp_path / f'shapes{suffix}'
    path.write_text(JS, encoding='utf-8')
    assert _first_lines(path, EXPECTED_JS) == EXPECTED_JS


def test_typescript_exported_and_modified_declarations(tmp_path):
    path = tmp_path / 'shapes.ts'
    path.write_text(JS + TS_EXTRA, encoding='utf-8')
    assert _first_lines(path, EXPECTED_TS_EXTRA) == EXPECTED_TS_EXTRA


def test_widened_read_keeps_the_whole_body(tmp_path):
    """The multi-line binding keeps its value line; the widened span is still the
    file's own text, start to end."""
    path = tmp_path / 'shapes.js'
    path.write_text(JS, encoding='utf-8')
    result = _extract(path, 'multi')
    assert result['source'] == 'const multi =\n  () => 9;'
    assert (result['line_start'], result['line_end']) == (16, 17)
