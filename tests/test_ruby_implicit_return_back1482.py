"""BACK-1482: Ruby's last expression is the method's implicit return value.

--returns/--exits must report it the way they report Rust's tail expression
(nav_exits._find_rust_tail_expression): an if/unless/case as the last statement
returns its branch values, and an explicit `return` is never double-reported.
"""

import textwrap

import pytest
import tree_sitter_language_pack as ts

from reveal.adapters.ast.nav_exits import collect_exits, collect_gate_chains
from reveal.core.treesitter_compat import _zero_arg, ts_parse, tree_root


def _method(code: str, name: str):
    src = textwrap.dedent(code).lstrip('\n')
    data = src.encode('utf-8')
    root = tree_root(ts_parse(ts.get_parser('ruby'), src))

    def get_text(node):
        return data[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')].decode('utf-8')

    stack = [root]
    while stack:
        node = stack.pop()
        if _zero_arg(node, 'kind') in ('method', 'singleton_method'):
            name_node = node.child_by_field_name('name')
            if get_text(name_node) == name:
                return node, get_text
        stack.extend(node.children)
    raise AssertionError(name)


def _returns(code: str, name: str):
    node, get_text = _method(code, name)
    end = _zero_arg(node, 'end_position').row + 1
    return [(r['kind'], r['line'], r['text'])
            for r in collect_gate_chains(node, 1, end, get_text)
            if r['kind'] == 'RETURN']


def _exits(code: str, name: str):
    node, get_text = _method(code, name)
    end = _zero_arg(node, 'end_position').row + 1
    return [(r['kind'], r['line'], r['text'])
            for r in collect_exits(node, 1, end, get_text)
            if r['kind'] == 'RETURN']


SRC = """\
def plain(a)
  x = a + 1
  x
end

def branches(a)
  if a > 1
    5
  elsif a > 0
    6
  else
    7
  end
end

def cased(a)
  case a
  when 1 then :one
  else :other
  end
end

def self.single
  y = 1
  y
end

def explicit(a)
  return 1
end

def guarded(a)
  return 1 if a
  a.foo
end

def empty
end

def ends_in_raise(a)
  raise ArgumentError
end
"""


@pytest.mark.parametrize('fn', [_returns, _exits])
class TestRubyImplicitReturn:
    def test_last_expression_is_return(self, fn):
        assert fn(SRC, 'plain') == [('RETURN', 3, 'x')]

    def test_singleton_method(self, fn):
        assert fn(SRC, 'single') == [('RETURN', 24, 'y')]

    def test_if_elsif_else_returns_each_branch_value(self, fn):
        assert [(k, l, t) for k, l, t in fn(SRC, 'branches')] == [
            ('RETURN', 8, '5'), ('RETURN', 10, '6'), ('RETURN', 12, '7')]

    def test_case_returns_each_branch_value(self, fn):
        assert [(l, t) for _, l, t in fn(SRC, 'cased')] == [(17, ':one'), (18, ':other')]

    def test_guarded_modifier_return_kept_and_tail_added(self, fn):
        assert [(l, t) for _, l, t in fn(SRC, 'guarded')] == [(33, 'return 1'), (34, 'a.foo')]

    # negative controls: nothing new where there is no implicit value
    def test_explicit_return_not_double_reported(self, fn):
        assert fn(SRC, 'explicit') == [('RETURN', 29, 'return 1')]

    def test_empty_method_has_no_return(self, fn):
        assert fn(SRC, 'empty') == []

    def test_trailing_raise_is_not_a_return(self, fn):
        assert fn(SRC, 'ends_in_raise') == []
