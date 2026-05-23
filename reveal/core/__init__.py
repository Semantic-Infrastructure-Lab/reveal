"""
Core reveal modules and utilities.

This package contains foundational components used across reveal:
- Base classes for analyzers and adapters
- Tree-sitter compatibility and utilities
- Registry system
- Type system

Modules:
    treesitter_compat: Tree-sitter compatibility layer and warning suppression
"""

from .treesitter_compat import (
    suppress_treesitter_warnings,
    node_children,
    node_prev_sibling,
    node_next_sibling,
)

__all__ = [
    'suppress_treesitter_warnings',
    'node_children',
    'node_prev_sibling',
    'node_next_sibling',
]
