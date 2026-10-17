"""BACK-1896: expected gate polarity across grammar shapes, including controls."""
import json
from pathlib import Path

import pytest
from tree_sitter_language_pack import get_parser

from conftest import _run_reveal_direct
from reveal.adapters.ast.nav_exits import collect_exits, collect_gate_chains
from reveal.core.treesitter_compat import _zero_arg, tree_root, ts_parse

pytestmark = pytest.mark.conformance
FIXTURES = Path(__file__).parent / 'fixtures' / 'conformance' / 'returns_back1896'
EXPECTED = json.loads((FIXTURES / 'expected.json').read_text(encoding='utf-8'))


def _collect(language, source):
    tree = ts_parse(get_parser(language), source)
    root = tree_root(tree)
    assert not _zero_arg(root, 'has_error'), source
    content = source.encode('utf-8')
    def text(node):
        return content[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')].decode('utf-8')
    return tree, root, text


@pytest.mark.parametrize('language', sorted(EXPECTED))
def test_branch_polarity_json_and_repeated_calls(language):
    expected = EXPECTED[language]
    path = FIXTURES / expected['file']
    source = path.read_text(encoding='utf-8')
    tree, root, text = _collect(language, source)
    cold = collect_gate_chains(root, 1, 999, text)
    assert [f['gates'] for f in cold] == expected['gates']
    assert [f['line'] for f in cold] == expected['lines']
    # Sibling --exits keeps the same exits, without gate annotations.
    assert [{k: v for k, v in f.items() if k != 'gates'} for f in cold] == collect_exits(root, 1, 999, text)
    assert collect_gate_chains(root, 1, 999, text) == cold
    fresh_tree, fresh_root, fresh_text = _collect(language, source)
    assert collect_gate_chains(fresh_root, 1, 999, fresh_text) == cold
    result = _run_reveal_direct(path, '--returns', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['findings'] == cold


@pytest.mark.parametrize('language,source', [
    ('python', 'def f(a):\n if a:\n  try:\n   return 1\n  except ValueError:\n   return 2\n  finally:\n   return 3\n return 4\n'),
    ('javascript', 'function f(a) {if(a) {try {return 1;} catch(e) {return 2;} finally {return 3;}} return 4;}'),
    ('java', 'class E { int f(boolean a) {if(a) {try {return 1;} catch(Exception e) {return 2;} finally {return 3;}} return 4;} }'),
    ('kotlin', 'fun f(a: Boolean): Int {if(a) {try {return 1} catch(e: Exception) {return 2} finally {return 3}}; return 4}'),
    ('php', '<?php function f($a) {if($a) {try {return 1;} catch(Exception $e) {return 2;} finally {return 3;}} return 4;}'),
    ('ruby', 'def f(a)\n if a\n  begin\n   return 1\n  rescue ArgumentError\n   return 2\n  ensure\n   return 3\n  end\n end\n return 4\nend'),
])
def test_exception_handlers_have_context_only_in_handler(language, source):
    tree, root, text = _collect(language, source)
    findings = collect_gate_chains(root, 1, 999, text)
    a = '$a' if language == 'php' else 'a'
    assert [[g['text'] for g in f['gates']] for f in findings] == [
        [a], [a, 'on exception'], [a], [],
    ]
    assert findings[1]['gates'][-1]['line'] == (5 if language in ('python', 'ruby') else 1)


@pytest.mark.parametrize('source,expected', [
    ('def f(a,b,c):\n if a and b:\n  return 1\n elif c:\n  if b:\n   return 2\n  else:\n   return 3\n else:\n  return 4\n', [['a and b'], ['not (a and b)', 'c', 'b'], ['not (a and b)', 'c', 'not (b)'], ['not (a and b)', 'not (c)']]),
    ('def f(a,b,c):\n if a:\n  return 1\n elif b:\n  return 2\n elif c:\n  return 3\n else:\n  return 4\n', [['a'], ['not (a)', 'b'], ['not (a)', 'not (b)', 'c'], ['not (a)', 'not (b)', 'not (c)']]),
])
def test_compound_nested_and_flat_elif_chains(source, expected):
    tree, root, text = _collect('python', source)
    assert [[g['text'] for g in f['gates']] for f in collect_gate_chains(root, 1, 999, text)] == expected


def test_ruby_unless_else_and_modifier_control():
    source = 'def f(a)\n unless a\n  return 1\n else\n  return 2\n end\n return 3 unless a\nend'
    tree, root, text = _collect('ruby', source)
    assert [[g['text'] for g in f['gates']] for f in collect_gate_chains(root, 1, 999, text)] == [
        ['unless a'], ['not (unless a)'], ['unless a'],
    ]


@pytest.mark.parametrize('language', sorted(EXPECTED))
def test_sibling_exits_and_positive_branch_controls(language):
    expected = EXPECTED[language]
    path = FIXTURES / expected['file']
    source = path.read_text(encoding='utf-8')
    tree, root, text = _collect(language, source)
    findings = collect_gate_chains(root, 1, 999, text)
    assert findings[0]['gates'] == expected['gates'][0]
    assert findings[-1]['gates'] == []
    result = _run_reveal_direct(path, '--exits', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['findings'] == collect_exits(root, 1, 999, text)
    assert [f['line'] for f in collect_exits(root, 1, 999, text)] == expected['lines']


@pytest.mark.parametrize('language,variable', [('ruby', 'b'), ('php', '$b')])
def test_shared_elif_taxonomy_outline_and_condition_reads(language, variable):
    expected = EXPECTED[language]
    path = FIXTURES / expected['file']
    outline = _run_reveal_direct(path, '--ifmap', '--format', 'json')
    assert outline.returncode == 0, outline.stderr
    assert [(f['keyword'], f['line_start']) for f in json.loads(outline.stdout)['findings']] == [
        ('IF', expected['gates'][0][0]['line']),
        ('ELIF', expected['gates'][1][1]['line']),
        ('ELSE', expected['lines'][2] - 1),
    ]
    flow = _run_reveal_direct(path, '--varflow', variable, '--format', 'json')
    assert flow.returncode == 0, flow.stderr
    assert {'kind': 'READ/COND', 'line': expected['gates'][1][1]['line']} in json.loads(flow.stdout)['findings']


def test_ruby_rescue_modifier_only_gates_handler_expression():
    tree, root, text = _collect('ruby', 'def f\n raise("first") rescue raise("second")\nend')
    assert [[g['text'] for g in f['gates']] for f in collect_gate_chains(root, 1, 999, text)] == [
        [], ['on exception'],
    ]
