"""BACK-1484: Swift's empty-tuple value `()` parsed with error recovery.

tree-sitter-swift cannot read `()` as a value (`MutableProperty(())`, `send(value: ())`,
`{ _ in () }`, `let a = ()`): it recovers by inserting a MISSING token, so a clean file was
reported as `parse-recovered` (158 of 2,051 files of the Swift corpus, 130 of them for this
alone). The surface scan now reads such a value as a placeholder identifier of the same width.
"""

from reveal.adapters.ast.nav_surface_swift import scan_file_surface_swift
from reveal.adapters.ast.surface_matrix import RECOVERED_KEY


def _scan(source, tmp_path):
    path = tmp_path / 'a.swift'
    path.write_text(source, encoding='utf-8')
    return scan_file_surface_swift(str(path))


UNIT_VALUES = (
    'import Foundation\n'
    'let a = MutableProperty(())\n'
    'let b = MutableProperty<Void>(())\n'
    'x.send(value: ())\n'
    'x.map { _ in () }\n'
    'let c = ()\n'
    'let k = Environment.get("HOME")\n'
)


def test_unit_values_do_not_make_a_clean_file_parse_recovered(tmp_path):
    result = _scan(UNIT_VALUES, tmp_path)
    assert RECOVERED_KEY not in result
    assert [(e['name'], e.get('in_error_region')) for e in result['env']] == [('HOME', None)]


def test_function_types_calls_and_literals_are_left_as_written(tmp_path):
    source = ('let f: () -> Void = {}\nlet g: () throws -> Int = { 1 }\nfoo()\nbar.baz()\n'
              'let s = "note ()"\n// trailing ()\n'
              'let k = Environment.get("A ()")\n')
    result = _scan(source, tmp_path)
    assert RECOVERED_KEY not in result
    assert [e['name'] for e in result['env']] == ['A ()']       # the string literal keeps its text


def test_a_genuinely_broken_file_is_still_disclosed(tmp_path):
    result = _scan('let a = MutableProperty(())\nfunc f( {\n let x = 1\n}}}\n', tmp_path)
    assert result[RECOVERED_KEY] == [str(tmp_path / 'a.swift')]
