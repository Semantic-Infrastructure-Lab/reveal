"""Handler/branch ownership for Dart and Zig grammar shapes."""
import json

import pytest
from tree_sitter_language_pack import get_parser

from conftest import _run_reveal_direct
from reveal.complexity import calculate_complexity_and_depth
from reveal.adapters.ast.nav_exits import collect_exits, collect_gate_chains
from reveal.adapters.ast.nav_loops import collect_fanout, collect_loops
from reveal.adapters.ast.nav_outline import element_outline, scope_chain
from reveal.core.treesitter_compat import _zero_arg, tree_root, ts_parse

pytestmark = pytest.mark.conformance


def _parse(language, source):
    tree = ts_parse(get_parser(language), source)
    root = tree_root(tree)
    assert not _zero_arg(root, 'has_error'), source
    content = source.encode('utf-8')

    def text(node):
        return content[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')].decode('utf-8')

    return tree, root, text


@pytest.mark.parametrize('language,source,expected', [
    ('dart', '''int f() {
  try { return 1; }
  on FormatException catch(e) { return 2; }
  on StateError { return 3; }
  catch(e) { return 4; }
  finally { return 5; }
  return 6;
}
''', [(2, []), (3, [(3, 'on exception')]), (4, [(4, 'on exception')]),
      (5, [(5, 'on exception')]), (6, []), (7, [])]),
    ('zig', '''fn f(a: bool, b: bool) i32 {
  if (a) {
    return 1;
  } else if (b) {
    return 2;
  } else {
    return 3;
  }
  return 4;
}
''', [(3, [(2, 'a')]), (5, [(2, 'not (a)'), (4, 'b')]),
      (7, [(2, 'not (a)'), (4, 'not (b)')]), (9, [])]),
    ('zig', '''fn f(a: bool) i32 {
  const x = risky(if (a) blk: { return 1; } else 2) catch {
    return 3;
  };
  return 4;
}
''', [(2, [(2, 'a')]), (3, [(2, 'on exception')]), (5, [])]),
    ('zig', '''fn f(a: bool) i32 {
  const x = risky() catch |err| {
    if (a) { return 1; }
    const y = retry(err) catch {
      return 2;
    };
    return 3;
  };
  return 4;
}
''', [(3, [(2, 'on exception'), (3, 'a')]),
      (5, [(2, 'on exception'), (4, 'on exception')]),
      (7, [(2, 'on exception')]), (9, [])]),
])
def test_handler_branch_context_and_sibling_exits(tmp_path, language, source, expected):
    tree, root, text = _parse(language, source)
    findings = collect_gate_chains(root, 1, 999, text)
    assert [(f['line'], [(g['line'], g['text']) for g in f['gates']])
            for f in findings] == expected
    exits = [{k: v for k, v in f.items() if k != 'gates'} for f in findings]
    assert collect_exits(root, 1, 999, text) == exits
    assert collect_gate_chains(root, 1, 999, text) == findings
    fresh_tree, fresh_root, fresh_text = _parse(language, source)
    assert collect_gate_chains(fresh_root, 1, 999, fresh_text) == findings
    path = tmp_path / f'control.{language}'
    path.write_text(source, encoding='utf-8')
    for flag, expected_output in [('--returns', findings), ('--exits', exits)]:
        result = _run_reveal_direct(path, flag, '--format', 'json')
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)['findings'] == expected_output


def test_zig_loop_taxonomy_fanout_and_ordinary_binary_control():
    source = '''fn f(items: []const i32) i32 {
  const x = 1 + 2;
  for (items) |item| {
    cache.set(item);
  }
  cache.set(x);
  return x;
}
'''
    tree, root, text = _parse('zig', source)
    loops = collect_loops(root, 1, 99, text)
    assert [(f['keyword'], f['line_start'], f['line_end']) for f in loops] == [('FOR', 3, 5)]
    fanout = collect_fanout(root, 1, 99, text, 'zig')
    assert [[(e['kind'], e['line']) for e in f['effects']] for f in fanout] == [[('cache', 4)]]
    assert collect_loops(root, 6, 8, text) == []
    assert collect_loops(root, 1, 99, text) == loops
    assert collect_fanout(root, 1, 99, text, 'zig') == fanout
    assert [f for f in element_outline(root, text) if f['keyword'] == 'CATCH'] == []
    assert [(f['line'], f['gates']) for f in collect_gate_chains(root, 1, 99, text)] == [(7, [])]


@pytest.mark.parametrize('language,source', [
    ('dart', 'int f(int a) { return a + 1; }'),
    ('zig', 'fn f(a: i32) i32 { const b = a + 1; cache.set(b); return b; }'),
    ('javascript', 'function f(a) { try { return a; } catch(e) { return 2; } return 3; }'),
])
def test_independent_unguarded_and_existing_handler_controls(language, source):
    tree, root, text = _parse(language, source)
    findings = collect_gate_chains(root, 1, 99, text)
    expected = [[], [{'line': 1, 'text': 'on exception'}], []] if language == 'javascript' else [[]]
    assert [f['gates'] for f in findings] == expected
    assert collect_gate_chains(root, 1, 99, text) == findings


def test_zig_catch_outline_starts_at_operator_and_excludes_operand_scope():
    source = '''fn f(a: bool) i32 {
  const x = risky(if (a) blk: { return 1; } else 2)
    catch {
      return 3;
    };
  return 4;
}
'''
    tree, root, text = _parse('zig', source)
    outline = element_outline(root, text, max_depth=9)
    assert [(f['keyword'], f['line_start']) for f in outline if f['keyword'] in ('IF', 'CATCH')] == [
        ('IF', 2), ('CATCH', 3)]
    assert next(f for f in outline if f['keyword'] == 'CATCH')['label'] == 'CATCH'
    assert [f['keyword'] for f in scope_chain(root, 2, text)] == ['DEF', 'IF']
    assert [f['keyword'] for f in scope_chain(root, 4, text)] == ['DEF', 'CATCH']
    assert [(f['line'], f['gates']) for f in collect_gate_chains(root, 3, 4, text)] == [
        (4, [{'line': 3, 'text': 'on exception'}])]


@pytest.mark.parametrize('source,expected', [
    ('fn f(items: []const i32) void { for (items) |item| {consume(item);} }', (2, 1)),
    ('fn f(a: bool, b: bool) i32 { const x = if (a) if (b) 1 else 2 else 3; return x; }', (3, 2)),
    ('fn f(a: i32) i32 { return a + 1; }', (1, 0)),
])
def test_zig_shared_control_flow_family_metrics(source, expected):
    tree, root, text = _parse('zig', source)
    assert calculate_complexity_and_depth(root) == expected
    assert calculate_complexity_and_depth(root) == expected
