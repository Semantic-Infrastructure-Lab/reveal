"""tree_root returns one root object per tree (BACK-1880 follow-up).

On the language-pack 1.8.1 binding every `root_node` access builds a new Node wrapper that is
neither equal nor hash-equal to the last, so the rules' root-keyed kind index was built twice
per file (B003 and M104 each asked for the root of the same memoized tree).
"""

from reveal.core import get_tree, tree_root
from reveal.core.treesitter_compat import _ROOT_MEMO_MAX
from reveal.rules.base_mixins import _kind_buckets, kind_nodes

SRC_A = "class A { void f() { int x = 1; } }\n"
SRC_B = "class B { void g() { int y = 2; int z = 3; } }\n"


def test_the_same_tree_gives_the_same_root_object():
    tree = get_tree("java", SRC_A)
    assert tree_root(tree) is tree_root(tree)


def test_different_trees_give_different_roots():
    assert tree_root(get_tree("java", SRC_A)) is not tree_root(get_tree("java", SRC_B))


def test_the_kind_index_is_built_once_per_tree_not_once_per_caller():
    _kind_buckets.cache_clear()
    tree = get_tree("java", SRC_B)
    first = kind_nodes(tree_root(tree), "variable_declarator")
    second = kind_nodes(tree_root(tree), "variable_declarator")
    assert len(first) == 2 and first is second
    assert _kind_buckets.cache_info().misses == 1


def test_the_memo_is_bounded_and_still_answers_after_eviction():
    trees = [get_tree("java", f"class C{i} {{ }}\n") for i in range(_ROOT_MEMO_MAX + 3)]
    roots = [tree_root(t) for t in trees]
    assert all(r is not None for r in roots)
    assert tree_root(trees[-1]) is roots[-1]
