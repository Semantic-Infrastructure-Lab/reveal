"""Registry-driven, oracle-free structure invariants (BACK-1096, slice 2).

Metamorphic relations over every tree-sitter analyzer in the registry:
  copy -> identical structure; appended comment -> identical named items;
  appended unrelated syntax error AFTER the definitions -> nothing defined
  before it disappears (the BACK-1460 class, for symbols, not just imports).
Citation integrity: every reported name occurs on its reported line.
Only reveal's own output is compared with itself, so no oracle is needed.
"""
import re

import pytest

import reveal.analyzers  # noqa: F401  (registers every analyzer)
from reveal import registry
from reveal.registry import get_analyzer
from reveal.treesitter import TreeSitterAnalyzer

pytestmark = [pytest.mark.component]

_W = 'class Widget'
# filename -> (source, appended comment or None, appended unrelated syntax
# error or None).  Code sources define a class `Widget` with a method `spin`
# and a top-level function `helper` (Lua/Bash/PowerShell: two functions).
CASES = {
    'a.py': ('class Widget:\n    def spin(self):\n        return 1\n\n\ndef helper(x):\n    return x\n',
             '# comment\n', 'def broken(\n'),
    'a.js': ('class Widget {\n  spin() { return 1; }\n}\n\nfunction helper(x) {\n  return x;\n}\n',
             '// comment\n', 'function broken(\n'),
    'a.ts': ('class Widget {\n  spin(): number { return 1; }\n}\n\nfunction helper(x: number): number {\n  return x;\n}\n',
             '// comment\n', 'function broken(\n'),
    'a.tsx': ('class Widget {\n  spin(): number { return 1; }\n}\n\nfunction helper(x: number): number {\n  return x;\n}\n',
              '// comment\n', 'function broken(\n'),
    'a.go': ('package demo\n\ntype Widget struct{}\n\nfunc (w Widget) Spin() int {\n\treturn 1\n}\n\nfunc helper(x int) int {\n\treturn x\n}\n',
             '// comment\n', 'func broken( { {{{\n'),
    'a.rs': ('struct Widget;\n\nimpl Widget {\n    fn spin(&self) -> i32 {\n        1\n    }\n}\n\nfn helper(x: i32) -> i32 {\n    x\n}\n',
             '// comment\n', 'fn broken(\n'),
    'a.zig': ('const Widget = struct {\n    pub fn spin(self: Widget) i32 {\n        return 1;\n    }\n};\n\npub fn helper(x: i32) i32 {\n    return x;\n}\n',
              '// comment\n', 'pub fn broken(\n'),
    'a.c': ('struct Widget { int a; };\n\nint spin(struct Widget *w) {\n    return 1;\n}\n\nint helper(int x) {\n    return x;\n}\n',
            '// comment\n', 'int broken(\n'),
    'a.cpp': ('class Widget {\npublic:\n    int spin() { return 1; }\n};\n\nint helper(int x) {\n    return x;\n}\n',
              '// comment\n', 'int broken(\n'),
    'a.java': ('class Widget {\n    int spin() {\n        return 1;\n    }\n    static int helper(int x) {\n        return x;\n    }\n}\n',
               '// comment\n', 'class Broken { int x = + ; @@\n'),
    'a.cs': ('class Widget {\n    int Spin() {\n        return 1;\n    }\n    static int Helper(int x) {\n        return x;\n    }\n}\n',
             '// comment\n', 'class Broken {\n'),
    'a.php': ('<?php\nclass Widget {\n    function spin() {\n        return 1;\n    }\n}\n\nfunction helper($x) {\n    return $x;\n}\n',
              '// comment\n', 'function broken(\n'),
    'a.rb': ('class Widget\n  def spin\n    1\n  end\nend\n\ndef helper(x)\n  x\nend\n',
             '# comment\n', 'def broken(\n'),
    'a.swift': ('class Widget {\n    func spin() -> Int {\n        return 1\n    }\n}\n\nfunc helper(x: Int) -> Int {\n    return x\n}\n',
                '// comment\n', 'func broken(\n'),
    'a.kt': ('class Widget {\n    fun spin(): Int {\n        return 1\n    }\n}\n\nfun helper(x: Int): Int {\n    return x\n}\n',
             '// comment\n', 'fun broken(\n'),
    'a.scala': ('class Widget {\n  def spin(): Int = 1\n}\n\ndef helper(x: Int): Int = x\n',
                '// comment\n', 'def broken(\n'),
    'a.dart': ('class Widget {\n  int spin() {\n    return 1;\n  }\n}\n\nint helper(int x) {\n  return x;\n}\n',
               '// comment\n', 'void broken(\n'),
    'a.gd': ('class Widget:\n\tfunc spin():\n\t\treturn 1\n\nfunc helper(x):\n\treturn x\n',
             '# comment\n', 'func broken(\n'),
    'a.lua': ('function helper(x)\n  return x\nend\n\nfunction spin()\n  return 1\nend\n',
              '-- comment\n', 'function broken(\n'),
    'a.sh': ('helper() {\n  echo "$1"\n}\n\nspin() {\n  return 1\n}\n',
             '# comment\n', 'echo $(\n'),
    'a.ex': ('defmodule Widget do\n  def spin do\n    1\n  end\n\n  def helper(x) do\n    x\n  end\nend\n',
             '# comment\n', 'def broken(\n'),
    'a.ps1': ('function Get-Helper {\n    param($x)\n    return $x\n}\n\nfunction Get-Spin {\n    return 1\n}\n',
              '# comment\n', 'function Broken {\n'),
    'a.sql': ('CREATE TABLE widget (id INT);\n\nCREATE FUNCTION helper(x INT) RETURNS INT AS $$ SELECT x $$ LANGUAGE sql;\n',
              '-- comment\n', 'CREATE TABLE (\n'),
    # Declarative formats: the structure is named sections/keys, not functions.
    'a.tf': ('variable "helper" {\n  default = 1\n}\n\nresource "aws_instance" "widget" {\n  ami = "x"\n}\n',
             '# comment\n', 'resource = = =\n'),
    'a.proto': ('syntax = "proto3";\n\nmessage Widget {\n  int32 id = 1;\n}\n\nmessage Helper {\n  int32 id = 1;\n}\n',
                '// comment\n', 'message Broken { int32 = ;\n'),
    'a.graphql': ('type Widget {\n  id: Int\n}\n\ntype Helper {\n  id: Int\n}\n',
                  '# comment\n', 'type Broken {\n'),
    'a.md': ('# Widget\n\ntext\n\n## Helper\n\nmore\n', '<!-- comment -->\n', None),
    'a.json': ('{"widget": {"a": 1}, "helper": [1]}\n', None, '{{{\n'),
    'a.yaml': ('widget:\n  a: 1\nhelper: 2\n', '# comment\n', 'x: [\n'),
    'a.toml': ('[widget]\nname = "x"\n\n[helper]\nk = 1\n', '# comment\n', '[broken\n'),
    'Dockerfile': ('FROM alpine\nRUN echo hi\n', '# comment\n', None),
}
CODE = {n for n in CASES if n.rsplit('.', 1)[-1] in {
    'py', 'js', 'ts', 'tsx', 'go', 'rs', 'zig', 'c', 'cpp', 'java', 'cs', 'php', 'rb',
    'swift', 'kt', 'scala', 'dart', 'gd', 'lua', 'sh', 'ex', 'ps1', 'sql'}}


def _analyzer(path):
    return get_analyzer(str(path))(str(path))


def items(structure):
    """Every named item of a structure: (list key, name, first line, last line)."""
    found = []
    for key, value in structure.items():
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, dict) and 'name' in item:
                first = item.get('line', item.get('line_start'))
                found.append((key, item['name'], first, item.get('line_end')))
    return found


def structure_of(path):
    analyzer = _analyzer(path)
    structure = analyzer.get_structure()
    return structure, analyzer.has_parse_errors()


def occurs(name, text):
    """Composite names (`aws_instance.widget`) cite their parts, not the dotted join."""
    return name in text or all(part in text for part in re.split(r'[.\s]+', name) if part)


def test_every_treesitter_analyzer_has_a_structure_fixture():
    classes = {cls for cls in registry.get_analyzer_mapping().values()
               if isinstance(cls, type) and issubclass(cls, TreeSitterAnalyzer)}
    covered = {_analyzer_class(name) for name in CASES}
    assert classes - covered == set(), 'registered tree-sitter analyzer without a fixture'


def _analyzer_class(name):
    from pathlib import Path
    return get_analyzer(str(Path(name)))


@pytest.mark.parametrize('name', CASES)
def test_structure_survives_copy_comment_and_trailing_error(tmp_path, name):
    source, comment, broken = CASES[name]
    base = tmp_path / 'clean'
    base.mkdir()
    clean_path = base / name
    clean_path.write_text(source, encoding='utf-8')
    clean, clean_errors = structure_of(clean_path)
    expected = items(clean)
    assert expected and not clean_errors, 'positive control must yield items from valid source'
    if name in CODE:
        assert [i for i in expected if i[0] == 'functions'], 'code fixture must yield a function'

    def variant(label, text):
        folder = tmp_path / label
        folder.mkdir()
        path = folder / name
        path.write_text(text, encoding='utf-8')
        return structure_of(path)

    copy, _ = variant('copy', source)
    assert items(copy) == expected
    if comment is not None:
        commented, errors = variant('comment', source + comment)
        assert items(commented) == expected, 'an appended comment moved or dropped a symbol'
        assert not errors
    if broken is not None:
        partial, errors = variant('partial', source + broken)
        assert errors, 'negative control: the appended text must actually be a parse error'
        lost = {i[:3] for i in expected} - {i[:3] for i in items(partial)}
        assert not lost, 'unrelated trailing syntax error erased symbols: %s' % sorted(lost)


@pytest.mark.parametrize('name', CASES)
def test_every_reported_name_occurs_on_its_reported_line(tmp_path, name):
    source, _, broken = CASES[name]
    for label, text in (('clean', source), ('partial', source + (broken or ''))):
        folder = tmp_path / label
        folder.mkdir()
        path = folder / name
        path.write_text(text, encoding='utf-8')
        structure, _ = structure_of(path)
        lines = text.splitlines()
        reported = items(structure)
        assert reported
        for key, item_name, first, last in reported:
            assert first is not None and 1 <= first <= len(lines), (key, item_name, first)
            assert occurs(item_name, lines[first - 1]), (
                '%s %r cited at line %d: %r' % (key, item_name, first, lines[first - 1]))
            if last is not None:
                assert first <= last <= len(lines)


@pytest.mark.parametrize('name', CASES)
def test_structure_ignores_encoding_and_line_ending_spelling(tmp_path, name):
    """The same program spelled with a BOM, CRLF, no final newline or a non-ASCII
    first comment line must report the same symbols (names are sliced by byte
    offsets, so a one-character BOM or accent shifts a character-indexed slice)."""
    source, comment, _ = CASES[name]
    clean_path = tmp_path / 'clean' / name
    clean_path.parent.mkdir()
    clean_path.write_text(source, encoding='utf-8')
    expected = items(structure_of(clean_path)[0])
    assert expected

    def spelled(label, text, bom=False):
        path = tmp_path / label / name
        path.parent.mkdir()
        path.write_bytes((b'\xef\xbb\xbf' if bom else b'') + text.encode('utf-8'))
        return items(structure_of(path)[0])

    assert spelled('bom', source, bom=True) == expected
    assert spelled('crlf', source.replace('\n', '\r\n')) == expected
    assert spelled('nonl', source.rstrip('\n')) == expected
    if comment is not None:
        # One non-ASCII comment line before the first symbol (after `<?php`).
        head = len('<?php\n') if source.startswith('<?php') else 0
        accented = source[:head] + comment.replace('comment', 'caf\u00e9 \u2603') + source[head:]
        shifted = [(k, n, first + 1, None if last is None else last + 1)
                   for k, n, first, last in expected]
        assert spelled('accent', accented) == shifted


SEPARATORS = {'formfeed': '\x0c', 'vtab': '\x0b', 'nel': '\x85', 'u2028': ' ', 'fs': '\x1c'}
# FileAnalyzer._read_file returns text.splitlines(), which also breaks lines at
# these characters, so every analyzer parses text with extra newlines and every
# later line number is off (BACK-1096 finding: form feed is routine in GNU C).
SPLITTERS_BREAK_LINES = pytest.mark.xfail(strict=True, reason=(
    'FileAnalyzer._read_file uses str.splitlines(): a line separator that is not \\n '
    'inflates every later line number'))


# Form feed for every language; the other separators share the mechanism, so one language.
SEPARATOR_CASES = [(n, 'formfeed') for n, c in CASES.items() if c[1] is not None] + [
    ('a.py', s) for s in SEPARATORS if s != 'formfeed']


@SPLITTERS_BREAK_LINES
@pytest.mark.parametrize('name,separator', SEPARATOR_CASES)
def test_symbol_lines_ignore_separators_that_are_not_newlines(tmp_path, name, separator):
    """A form feed (or U+2028 ...) inside a comment line is not a line break:
    editors, tree-sitter and `wc -l` all keep the symbols on the same lines."""
    source, comment, _ = CASES[name]
    clean_path = tmp_path / 'clean' / name
    clean_path.parent.mkdir()
    clean_path.write_text(source, encoding='utf-8')
    expected = items(structure_of(clean_path)[0])
    head = len('<?php\n') if source.startswith('<?php') else 0
    noisy = comment.replace('comment', 'a%sb' % SEPARATORS[separator])
    path = tmp_path / 'noisy' / name
    path.parent.mkdir()
    path.write_bytes((source[:head] + noisy + source[head:]).encode('utf-8'))
    assert items(structure_of(path)[0]) == [
        (k, n, first + 1, None if last is None else last + 1) for k, n, first, last in expected]
