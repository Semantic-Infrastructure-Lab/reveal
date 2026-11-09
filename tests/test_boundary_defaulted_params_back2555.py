"""BACK-2555: a parameter with a default value is an input like any other parameter.

Python recorded `default_parameter`/`typed_default_parameter` names (and JS
`assignment_pattern` parameters) as WRITEs, so `--inputs`/`--boundary` dropped
every defaulted parameter that the body reads. The name now follows the walk's
context: an input in the function's own parameter list, a binding inside a
lambda's parameters and inside destructuring.
"""

import textwrap

from reveal.core import treesitter_parse as ts
from reveal.adapters.ast.nav_boundary import collect_boundary
from reveal.adapters.ast.nav_varflow import var_flow
from reveal.core.treesitter_compat import _zero_arg, ts_parse, tree_root, node_children

_FUNCTION_KINDS = {
    'python': ('function_definition',),
    'javascript': ('function_declaration',),
}


def _target(language: str, code: str):
    src = textwrap.dedent(code).lstrip('\n')
    data = src.encode('utf-8')
    root = tree_root(ts_parse(ts.get_parser(language), src))

    def get_text(node):
        return data[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')].decode('utf-8')

    stack = [root]
    while stack:
        node = stack.pop()
        if _zero_arg(node, 'kind') in _FUNCTION_KINDS[language] and \
                get_text(node.child_by_field_name('name')) == 'target':
            return node, get_text
        stack.extend(node_children(node))
    raise AssertionError('no function named target')


def _inputs(language: str, code: str) -> set:
    node, get_text = _target(language, code)
    end = _zero_arg(node, 'end_position').row + 1
    result = collect_boundary(node, 1, end, get_text, language=language)
    return {d['var'] for d in result['inputs']}


def test_python_defaulted_parameter_is_an_input():
    code = """
    def target(self, a, b=None, **opts):
        self.x = b
        return opts, a
    """
    assert {'a', 'b', 'opts', 'self'} <= _inputs('python', code)


def test_python_keyword_only_and_typed_defaults_are_inputs():
    code = """
    def target(a, *, k=2, t: int = 3, **kw):
        return a, k, t, kw
    """
    assert {'a', 'k', 't', 'kw'} <= _inputs('python', code)


def test_python_lambda_default_stays_bound_to_the_lambda():
    code = """
    def target(a):
        f = lambda x, y=3: x + y
        return f(a)
    """
    inputs = _inputs('python', code)
    assert 'a' in inputs
    assert not {'x', 'y'} & inputs


def test_javascript_defaulted_and_destructured_defaults_are_inputs():
    code = """
    function target(a, b = 1, {c = 2} = {}, ...rest) {
        return a + b + c + rest.length;
    }
    """
    assert {'a', 'b', 'c', 'rest'} <= _inputs('javascript', code)


def test_javascript_destructuring_default_is_still_a_write():
    code = """
    function target(arr) {
        const [x = 1] = arr;
        return x;
    }
    """
    assert 'x' not in _inputs('javascript', code)
    node, get_text = _target('javascript', code)
    end = _zero_arg(node, 'end_position').row + 1
    kinds = [e['kind'] for e in var_flow(node, 'x', 1, end, get_text)]
    assert kinds[0] == 'WRITE'
