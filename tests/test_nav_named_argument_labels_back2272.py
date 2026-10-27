"""Call-site named-argument labels are not variable reads (BACK-2272).

`requests.post(url, json={'total': total})` listed `json` as a PARAM under `--deps` and as an
INPUT under `--boundary`: the label names the callee's parameter and binds nothing in the
caller. The same shape exists in C# (`f(json: x)`), Dart (`f(json: x)`), Kotlin (`f(json = x)`)
and Swift (`f(json: x)`). Scala, Ruby, PHP, JavaScript and Lua already excluded their spelling;
they are the negative controls and must not change.
"""

import json

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.ast.nav_varflow import all_var_flow, var_flow
from reveal.element_resolve import resolve_bare_name
from reveal.registry import get_analyzer
from reveal.treesitter import FUNCTION_NODE_TYPES

pytestmark = pytest.mark.component


def _scope(tmp_path, extension, source):
    path = tmp_path / f'flow.{extension}'
    path.write_text(source, encoding='utf-8')
    analyzer = get_analyzer(str(path))(str(path))
    assert not analyzer.has_parse_errors()
    resolution = resolve_bare_name(analyzer, 'target', (FUNCTION_NODE_TYPES,))
    assert resolution is not None
    return resolution.node, analyzer._get_node_text


def _events(scope, get_text, name):
    return [(event['kind'], event['line']) for event in var_flow(scope, name, 1, 100, get_text)]


PYTHON = '''import requests


def target(order, url, payload):
    total = order.price
    requests.post(url, json={"total": total}, timeout=5)
    send(total=total)
    send(order=1, data=payload)
    return total
'''


def test_python_keyword_labels_are_not_candidate_inputs(tmp_path):
    scope, text = _scope(tmp_path, 'py', PYTHON)
    names = set(all_var_flow(scope, 1, 100, text))
    assert not names & {'json', 'timeout', 'data'}, names
    # Values stay reads: `payload` is only ever passed as a keyword value.
    assert {'order', 'url', 'payload', 'total', 'requests', 'send'} <= names


def test_python_label_colliding_with_a_local_adds_no_read(tmp_path):
    scope, text = _scope(tmp_path, 'py', PYTHON)
    # `send(total=total)` on line 7 is one read (the value), not two.
    assert _events(scope, text, 'total') == [('WRITE', 5), ('READ', 6), ('READ', 7), ('READ', 9)]
    # `send(order=1)` on line 8 does not read the `order` parameter (line 4 is its declaration).
    assert _events(scope, text, 'order') == [('READ', 4), ('READ', 5)]


def test_python_dict_key_variable_inside_keyword_value_is_still_a_read(tmp_path):
    scope, text = _scope(tmp_path, 'py', 'def target(key):\n    return post(x={key: 1})\n')
    # Negative control: a dictionary key that is a variable is a real read (line 1 is the parameter).
    assert _events(scope, text, 'key') == [('READ', 1), ('READ', 2)]
    assert 'x' not in all_var_flow(scope, 1, 100, text)


@pytest.mark.parametrize('flag, kind', [('--deps', 'dep'), ('--boundary', 'input')])
def test_cli_deps_and_boundary_omit_keyword_labels(tmp_path, flag, kind):
    path = tmp_path / 'app.py'
    path.write_text(PYTHON, encoding='utf-8')
    result = _run_reveal_direct(str(path), 'target', flag, '--format', 'json')
    assert result.returncode == 0, result.stderr
    found = {f['var'] for f in json.loads(result.stdout)['findings'] if f['kind'] == kind}
    assert not found & {'json', 'timeout', 'data'}, found
    assert {'order', 'url', 'payload'} <= found


# The languages whose named-argument label parsed as an identifier read.
LABELLED = {
    'cs': ('class A {\n'
           '    int target(int order, string url) {\n'
           '        var total = order + 1;\n'
           '        Post(url, json: total);\n'
           '        Post(order: 2);\n'
           '        return total;\n'
           '    }\n'
           '}\n', 4, 5),
    'dart': ('int target(int order, String url) {\n'
             '  var total = order + 1;\n'
             '  post(url, json: total);\n'
             '  post(order: 2);\n'
             '  return total;\n'
             '}\n', 3, 4),
    'kt': ('fun target(order: Int, url: String): Int {\n'
           '    val total = order + 1\n'
           '    post(url, json = total)\n'
           '    post(order = 2)\n'
           '    return total\n'
           '}\n', 3, 4),
    'swift': ('func target(order: Int, url: String) -> Int {\n'
              '    let total = order + 1\n'
              '    post(url, json: total)\n'
              '    post(order: 2)\n'
              '    return total\n'
              '}\n', 3, 4),
}

# Already right before the fix: their label is not an identifier read (Scala's walker
# special case, a Ruby hash key, a PHP `name`, a JS/Lua table key). They must not change.
UNLABELLED = {
    'scala': ('object A {\n'
              '  def target(order: Int, url: String): Int = {\n'
              '    val total = order + 1\n'
              '    post(url, json = total)\n'
              '    post(order = 2)\n'
              '    total\n'
              '  }\n'
              '}\n', 4, 5),
    'rb': ('def target(order, url)\n'
           '  total = order + 1\n'
           '  post(url, json: total)\n'
           '  post(order: 2)\n'
           '  total\n'
           'end\n', 3, 4),
    'js': ('function target(order, url) {\n'
           '  const total = order + 1;\n'
           '  post(url, {json: total});\n'
           '  post({order: 2});\n'
           '  return total;\n'
           '}\n', 3, 4),
    'lua': ('function target(order, url)\n'
            '  local total = order + 1\n'
            '  post(url, {json = total})\n'
            '  post({order = 2})\n'
            '  return total\n'
            'end\n', 3, 4),
}


def _nav(tmp_path, ext, source, *flag):
    path = tmp_path / f'flow.{ext}'
    path.write_text(source, encoding='utf-8')
    result = _run_reveal_direct(str(path), 'target', *flag, '--format', 'json')
    assert result.returncode == 0, (ext, result.stderr)
    return json.loads(result.stdout)['findings']


@pytest.mark.parametrize('ext', sorted(LABELLED) + sorted(UNLABELLED))
def test_named_argument_label_is_not_a_read(tmp_path, ext):
    # Through the CLI: Dart's resolved function node is its signature, so the walker
    # alone would not see the body.
    source, call_line, collide_line = {**LABELLED, **UNLABELLED}[ext]
    deps = {f['var'] for f in _nav(tmp_path, ext, source, '--deps')}
    assert 'json' not in deps, (ext, deps)
    assert {'order', 'url'} <= deps, (ext, deps)
    # The value is still read on the call line, once.
    total = _nav(tmp_path, ext, source, '--varflow', 'total')
    assert [e['line'] for e in total if e['kind'] == 'READ'].count(call_line) == 1, (ext, total)
    # A label spelled like a parameter does not read it.
    order = _nav(tmp_path, ext, source, '--varflow', 'order')
    assert collide_line not in [e['line'] for e in order], (ext, order)


def test_php_named_argument_value_is_still_read(tmp_path):
    # Negative control on the `argument` kind C# shares: PHP 8 `f(json: $x)` keeps `$total`.
    scope, text = _scope(tmp_path, 'php', '<?php\nfunction target($order) {\n'
                         '    $total = $order + 1;\n    post(json: $total);\n    return $total;\n}\n')
    assert _events(scope, text, '$total') == [('WRITE', 3), ('READ', 4), ('READ', 5)]
