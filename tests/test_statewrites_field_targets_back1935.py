"""Field writes must follow the terminal target shape, not receiver spelling."""

import pytest
import tree_sitter_language_pack as ts

from reveal.adapters.ast.nav_statewrites import collect_statewrites
from reveal.core.treesitter_compat import _zero_arg, tree_root, ts_parse

pytestmark = pytest.mark.component

SOURCES = {
    'lua': '''function update(other, values, cache)
    local count = 0
    other.total = 1
    other.child.total = 2
    values[1].total = 3
    other.total, other.child.total, count = 4, 5, 6
    local snapshot = other.total
    values[1] = other.total
    other.values[1] = snapshot
    count = other.total
    cache.set(count)
end
''',
    'dart': '''class Batch {
  void update(dynamic other, List<dynamic> values, dynamic cache) {
    var count = 0;
    other.total = 1;
    other.child.total = 2;
    values[0].total = 3;
    var snapshot = other.total;
    values[0] = other.total;
    other.values[0] = snapshot;
    count = other.total;
    cache.set(count);
  }
}
''',
    'zig': '''fn update(other: *Batch, values: []Batch, cache: *Cache) void {
    var count: i32 = 0;
    other.total = 1;
    other.child.total = 2;
    values[0].total = 3;
    const snapshot = other.total;
    values[0] = other.child;
    other.values[0] = snapshot;
    count = other.total;
    cache.set(count);
}
''',
}


def _parse(language, source):
    tree = ts_parse(ts.get_parser(language), source)
    root = tree_root(tree)
    assert _zero_arg(root, 'has_error') is False, f'{language}: source must parse without recovery'
    content = source.encode('utf-8')

    def text(node):
        return content[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')].decode('utf-8')

    return tree, root, text


def _writes(language, source, start=1, end=None):
    tree, root, text = _parse(language, source)
    end = len(source.split('\n')) if end is None else end
    first = collect_statewrites(root, start, end, text, language)
    assert collect_statewrites(root, start, end, text, language) == first
    fresh_tree, fresh_root, fresh_text = _parse(language, source)
    assert collect_statewrites(fresh_root, start, end, fresh_text, language) == first
    return first


@pytest.mark.parametrize('language,expected', [
    ('lua', [(3, 'other.total'), (4, 'other.child.total'), (5, 'values[1].total'),
             (6, 'other.total'), (6, 'other.child.total')]),
    ('dart', [(4, 'other.total'), (5, 'other.child.total'), (6, 'values[0].total')]),
    ('zig', [(3, 'other.total'), (4, 'other.child.total'), (5, 'values[0].total')]),
])
def test_field_targets_preserve_receiver_and_multiassignment(language, expected):
    writes = _writes(language, SOURCES[language])
    fields = [w for w in writes if w['via'] == 'assignment']
    assert fields == [dict(kind='field', line=line, target=target, via='assignment')
                      for line, target in expected]
    cache_line = {'lua': 11, 'dart': 11, 'zig': 10}[language]
    assert [w for w in writes if w['via'] == 'call'] == [
        dict(kind='cache', line=cache_line, target='cache.set', via='call')]


@pytest.mark.parametrize('language,start,end', [('lua', 7, 10), ('dart', 7, 10), ('zig', 6, 9)])
def test_local_container_and_member_reads_are_not_field_writes(language, start, end):
    assert _writes(language, SOURCES[language], start, end) == []


@pytest.mark.parametrize('language,line', [('lua', 11), ('dart', 11), ('zig', 10)])
def test_call_based_cache_write_remains_separate(language, line):
    assert _writes(language, SOURCES[language], line, line) == [
        dict(kind='cache', line=line, target='cache.set', via='call')]


@pytest.mark.parametrize('language,source', [
    ('lua', 'function inspect(other)\n    local value = other.child.total\n    return other.child.total\nend\n'),
    ('dart', 'dynamic inspect(dynamic other) {\n    final value = other.child.total;\n    return other.child.total;\n}\n'),
    ('zig', 'fn inspect(other: *Batch) i32 {\n    const value = other.child.total;\n    return other.child.total;\n}\n'),
])
def test_read_only_receiver_access_does_not_become_a_write(language, source):
    assert _writes(language, source) == []


@pytest.mark.parametrize('language,source', [
    ('dart', 'void update(dynamic other) {\n    other.total += 1;\n}\n'),
    ('zig', 'fn update(other: *Batch) void {\n    other.total += 1;\n}\n'),
])
def test_compound_field_assignment_uses_the_same_target_contract(language, source):
    assert _writes(language, source) == [
        dict(kind='field', line=2, target='other.total', via='assignment')]


@pytest.mark.parametrize('language,line,target', [
    ('lua', 4, 'other.child.total'), ('dart', 5, 'other.child.total'),
    ('zig', 4, 'other.child.total'),
])
def test_range_keeps_only_the_selected_field_assignment(language, line, target):
    assert _writes(language, SOURCES[language], line, line) == [
        dict(kind='field', line=line, target=target, via='assignment')]


@pytest.mark.parametrize('language,source', [
    ('python', 'def update(other):\n    other.total = 1\n    count = other.total\n'),
    ('go', 'package main\nfunc update(other *Batch) {\n    other.Total = 1\n}\n'),
    ('kotlin', 'fun update(other: Batch) {\n    other.total = 1\n}\n'),
    ('swift', 'func update(other: Batch) {\n    other.total = 1\n}\n'),
])
def test_existing_member_target_siblings_keep_their_shape(language, source):
    writes = _writes(language, source)
    assert len(writes) == 1
    assert writes[0]['kind'] == 'field'
    assert writes[0]['via'] == 'assignment'
    assert writes[0]['target'] == ('other.Total' if language == 'go' else 'other.total')
