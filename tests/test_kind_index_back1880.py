"""BACK-1880: tree-sitter rules read one per-tree kind index instead of each walking the tree.

`kind_nodes` must return exactly what filtering a full `iter_tree` by kind returns: the same
nodes in the same order, for one kind and for several. The agreement check is exercised on
input where the kinds exist (an empty answer agrees with anything) and shown to notice a
wrong order and a dropped kind.
"""

import pytest

from reveal.core import get_tree, iter_tree, tree_root
from reveal.core.treesitter_compat import _zero_arg
from reveal.rules.base_mixins import TreeSitterParsingMixin, _kind_buckets, kind_nodes

SOURCES = {
    'java': ('class A { int[] xs = {1, 2}; void f() { String s = "a"; '
             'try { g(); } catch (Exception e) { } int[] ys = {3}; } }'),
    'javascript': 'const a = [1, 2]; function f() { const b = ["x"]; try { f(); } catch (e) {} }',
    'go': 'package p\nvar a = []int{1}\nconst b = 2\nfunc f() { c := 3; _ = c }\n',
    'rust': 'const A: [i32; 2] = [1, 2];\nfn f() { let b = [3]; let c = 4; }\n',
    'c_sharp': 'class A { void F() { try { G(); } catch (Exception e) { } } }',
}
KINDS = {
    'java': [('variable_declarator',), ('catch_clause',), ('variable_declarator', 'catch_clause'),
             ('identifier', 'variable_declarator', 'block')],
    'javascript': [('variable_declarator',), ('catch_clause', 'variable_declarator')],
    'go': [('var_spec', 'const_spec', 'short_var_declaration'), ('short_var_declaration',)],
    'rust': [('let_declaration', 'const_item'), ('let_declaration',)],
    'c_sharp': [('catch_clause',)],
}
CASES = [(lang, kinds) for lang, groups in KINDS.items() for kinds in groups]


def _root(language):
    return tree_root(get_tree(language, SOURCES[language]))


def _expected(root, kinds):
    return [n for n in iter_tree(root) if _zero_arg(n, 'kind') in kinds]


def _key(node):
    # Node.id is absent from the 1.8.1 binding; kind + byte span identifies a node
    return tuple(_zero_arg(node, a) for a in ('kind', 'start_byte', 'end_byte'))


def _problem(root, kinds, got):
    want = _expected(root, kinds)
    if [_key(n) for n in got] != [_key(n) for n in want]:
        return f'{kinds}: got {len(got)} nodes, iter_tree filter gives {len(want)} (or order differs)'
    return None


@pytest.mark.parametrize('language,kinds', CASES)
def test_kind_nodes_equal_the_filtered_walk_it_replaced(language, kinds):
    root = _root(language)
    assert _expected(root, kinds), 'the fixture contains the kinds (positive control)'
    assert _problem(root, kinds, kind_nodes(root, *kinds)) is None


def test_multi_kind_result_interleaves_in_document_order():
    root = _root('java')
    got = kind_nodes(root, 'variable_declarator', 'catch_clause')
    assert [_zero_arg(n, 'kind') for n in got].count('catch_clause') == 1
    assert [_zero_arg(n, 'kind') for n in got].count('variable_declarator') >= 3
    starts = [_zero_arg(n, 'start_byte') for n in got]
    assert starts == sorted(starts)
    assert _zero_arg(got[0], 'kind') == 'variable_declarator' and any(
        _zero_arg(n, 'kind') == 'catch_clause' for n in got[1:-1]), 'catch sits between declarators'


def test_the_agreement_check_notices_a_wrong_order_and_a_dropped_kind():
    root = _root('java')
    kinds = ('variable_declarator', 'catch_clause')
    good = kind_nodes(root, *kinds)
    assert _problem(root, kinds, list(reversed(good)))
    assert _problem(root, kinds, [n for n in good if _zero_arg(n, 'kind') != 'catch_clause'])


def test_unknown_kind_and_missing_root_are_empty():
    root = _root('java')
    assert kind_nodes(root, 'no_such_kind') == []
    assert kind_nodes(root, 'no_such_kind', 'also_missing') == []
    assert kind_nodes(root, 'catch_clause', 'no_such_kind') == kind_nodes(root, 'catch_clause')
    assert kind_nodes(None, 'catch_clause') == []


def test_one_pass_is_shared_by_everything_that_asks_about_the_same_tree():
    root = _root('java')
    _kind_buckets.cache_clear()
    kind_nodes(root, 'catch_clause')
    kind_nodes(root, 'variable_declarator')
    TreeSitterParsingMixin()._ts_nodes_of_kind(root, 'identifier')
    info = _kind_buckets.cache_info()
    assert (info.misses, info.hits) == (1, 2)
