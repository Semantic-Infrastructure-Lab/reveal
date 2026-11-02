"""Opt-in uncertain contexts do not alter the existing positional scope contract."""
from dataclasses import dataclass

import pytest

from reveal.core.node_taxonomy import edge_scope


@dataclass
class Node:
    kind: str
    parent: 'Node | None' = None


def _call(*ancestors):
    parent = None
    for kind in reversed(ancestors):
        parent = Node(kind, parent)
    return Node('call', parent)


@pytest.mark.parametrize('ancestors,default,qualified', [
    ((), 'module', 'module'),
    (('class', 'program'), 'module', 'module'),
    (('module', 'program'), 'module', 'module'),
    (('method', 'class', 'program'), 'local', 'local'),
    (('singleton_method', 'program'), 'local', 'local'),
    (('do_block', 'program'), 'module', None),
    (('block', 'program'), 'module', None),
    (('lambda', 'program'), 'local', None),
    (('do_block', 'method', 'program'), 'local', 'local'),
    (('block', 'singleton_method', 'program'), 'local', 'local'),
    (('lambda', 'method', 'program'), 'local', 'local'),
    (('method', 'do_block', 'program'), 'local', 'local'),
    (('do_block', 'class', 'module', 'program'), 'module', None),
    (('do_block', 'lambda', 'method', 'program'), 'local', 'local'),
])
def test_context_uncertainty_is_opt_in_and_known_local_owner_wins(ancestors, default, qualified):
    node = _call(*ancestors)
    assert edge_scope(node) == default
    assert edge_scope(node, unclassified_kinds=frozenset({'do_block', 'block', 'lambda'})) == qualified
    assert edge_scope(node, unclassified_kinds=frozenset()) == default
