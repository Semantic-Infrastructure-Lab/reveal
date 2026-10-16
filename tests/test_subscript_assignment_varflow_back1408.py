"""``container[index] = value``: the container is read and mutated, the index only read.

BACK-1408: ``--boundary``/``--deps`` walked the whole target as a WRITE, so the index
``k`` was listed as written ("first write L9") while ``_cache`` -- needed and changed --
was not an input at all, hiding the module-level mutation.
"""
import textwrap

import pytest

from reveal.adapters.ast.nav_boundary import collect_boundary
from reveal.core import treesitter_parse as ts
from reveal.core.treesitter_compat import _zero_arg, node_children, tree_root, ts_parse

PYTHON = '''
_cache = {}

def target(self, k, v):
    _cache[k] = v
    self.items[k] = v
    local = {}
    local[k] = v
    return v
'''
JAVASCRIPT = '''
const cache = {};

function target(k, v) {
  cache[k] = v;
  const local = {};
  local[k] = v;
  return v;
}
'''
FUNCTION_KINDS = {'python': 'function_definition', 'javascript': 'function_declaration'}


def _inputs(language, code):
    src = textwrap.dedent(code).lstrip('\n')
    data = src.encode('utf-8')
    root = tree_root(ts_parse(ts.get_parser(language), src))

    def get_text(node):
        return data[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')].decode('utf-8')

    stack = [root]
    while stack:
        node = stack.pop()
        if _zero_arg(node, 'kind') == FUNCTION_KINDS[language] and \
                get_text(node.child_by_field_name('name')) == 'target':
            end = _zero_arg(node, 'end_position').row + 1
            result = collect_boundary(node, 1, end, get_text, language=language)
            return {d['var']: d for d in result['inputs']}
        stack.extend(node_children(node))
    raise AssertionError('no function named target')


@pytest.mark.parametrize('language, code, container', [
    ('python', PYTHON, '_cache'), ('javascript', JAVASCRIPT, 'cache')])
def test_the_mutated_container_is_an_input_that_is_written(language, code, container):
    inputs = _inputs(language, code)
    assert container in inputs, 'the mutated module-level container was hidden'
    assert inputs[container]['first_write_line'] is not None


@pytest.mark.parametrize('language, code', [('python', PYTHON), ('javascript', JAVASCRIPT)])
def test_the_index_is_read_never_written(language, code):
    inputs = _inputs(language, code)
    assert inputs['k']['first_write_line'] is None
    assert inputs['v']['first_write_line'] is None


@pytest.mark.parametrize('language, code', [('python', PYTHON), ('javascript', JAVASCRIPT)])
def test_negative_control_a_local_container_is_still_not_an_input(language, code):
    assert 'local' not in _inputs(language, code)


def test_an_attribute_container_still_writes_its_base():
    assert _inputs('python', PYTHON)['self']['first_write_line'] is not None
