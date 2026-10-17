"""Dart positional branch ownership, including flattened call conditions."""
import json

import pytest
from tree_sitter_language_pack import get_parser

from conftest import _run_reveal_direct
from reveal.adapters.ast.nav_exits import collect_exits, collect_gate_chains
from reveal.adapters.ast.nav_outline import scope_chain
from reveal.core.treesitter_compat import _zero_arg, tree_root, ts_parse

pytestmark = pytest.mark.conformance


def _parse(language, source):
    tree = ts_parse(get_parser(language), source)
    root = tree_root(tree)
    assert not _zero_arg(root, 'has_error'), source
    encoded = source.encode('utf-8')

    def text(node):
        return encoded[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')].decode('utf-8')

    return tree, root, text


@pytest.mark.parametrize('source,expected', [
    ('''int f(bool a, bool b, bool c) {
  assert(a);
  if (/* first */ a && b /* last */) // body comment
    return 1;
  else /* alternative */ if (c) { return 2; }
  else { return 3; }
  return 4;
}
''', [(4, [(3, 'a && b')]), (5, [(3, 'not (a && b)'), (5, 'c')]),
      (6, [(3, 'not (a && b)'), (5, 'not (c)')]), (7, [])]),
    ('''int f(int? value) {
  if (value != null) {
    if (value > 0) return value;
    else return -1;
  } else return 0;
  return -2;
}
''', [(3, [(2, 'value != null'), (3, 'value > 0')]),
      (4, [(2, 'value != null'), (3, 'not (value > 0)')]),
      (5, [(2, 'not (value != null)')]), (6, [])]),
    ('''int f(bool a, bool b) {
  try {
    if (a) { return 1; }
  } catch(e) {
    if (b) return 2;
    else return 3;
  } finally { assert(a); }
  return 4;
}
''', [(3, [(3, 'a')]), (5, [(4, 'on exception'), (5, 'b')]),
      (6, [(4, 'on exception'), (5, 'not (b)')]), (8, [])]),
    ('''int f() {
  if (probe(() { return true; }) == true) {
    return 1;
  } else {
    return 2;
  }
  return 3;
}
''', [(2, []), (3, [(2, 'probe(() { return true; }) == true')]),
      (5, [(2, 'not (probe(() { return true; }) == true)')]), (7, [])]),
    ('''// π before the function and its byte offsets
int f() {
  final marker = 'é'; if (test /* λ */ (nested('π'))) {
    return 1;
  } else return 2;
  return 3;
}
''', [(4, [(3, "test /* λ */ (nested('π'))")]),
      (5, [(3, "not (test /* λ */ (nested('π')))")]), (6, [])]),
    ('''int f() {
  if (() { return true; }()) {
    return 1;
  } else return 2;
  return 3;
}
''', [(2, []), (3, [(2, '() { return true; }()')]),
      (4, [(2, 'not (() { return true; }())')]), (5, [])]),
])
def test_dart_branch_polarity_condition_context_and_ranges(tmp_path, source, expected):
    tree, root, text = _parse('dart', source)
    findings = collect_gate_chains(root, 1, 999, text)
    assert [(f['line'], [(g['line'], g['text']) for g in f['gates']]) for f in findings] == expected
    exits = [{k: v for k, v in f.items() if k != 'gates'} for f in findings]
    assert collect_exits(root, 1, 999, text) == exits
    assert collect_gate_chains(root, 1, 999, text) == findings
    selected = findings[1]['line']
    assert collect_gate_chains(root, selected, selected, text) == [
        f for f in findings if f['line'] == selected]
    fresh_tree, fresh_root, fresh_text = _parse('dart', source)
    assert collect_gate_chains(fresh_root, 1, 999, fresh_text) == findings
    path = tmp_path / 'control.dart'
    path.write_text(source, encoding='utf-8')
    for flag, expected_findings in [('--returns', findings), ('--exits', exits)]:
        result = _run_reveal_direct(path, flag, '--format', 'json')
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)['findings'] == expected_findings


@pytest.mark.parametrize('language,source,expected', [
    ('dart', 'int f(bool a) { assert(a); return 1; }', [[]]),
    ('javascript', 'function f(a) { if(a) {return 1;} else {return 2;} return 3; }',
     [[{'line': 1, 'text': 'a'}], [{'line': 1, 'text': 'not (a)'}], []]),
    ('php', '<?php function f($a) { if($a) {return 1;} else {return 2;} return 3; }',
     [[{'line': 1, 'text': '$a'}], [{'line': 1, 'text': 'not ($a)'}], []]),
])
def test_assert_and_existing_fielded_branch_controls(language, source, expected):
    tree, root, text = _parse(language, source)
    findings = collect_gate_chains(root, 1, 999, text)
    assert [f['gates'] for f in findings] == expected
    assert collect_gate_chains(root, 1, 999, text) == findings


def test_dart_scope_condition_matches_gate_condition():
    source = "int f() {\n if (probe('π')) {\n  return 1;\n }\n return 2;\n}\n"
    tree, root, text = _parse('dart', source)
    findings = collect_gate_chains(root, 1, 999, text)
    assert findings[0]['gates'] == [{'line': 2, 'text': "probe('π')"}]
    assert next(f for f in scope_chain(root, 3, text) if f['keyword'] == 'IF')['condition'] == "probe('π')"
