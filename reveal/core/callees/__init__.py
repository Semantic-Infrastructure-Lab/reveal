"""Shared call-site (callee) extraction used by both the analyzer and nav paths.

See internal-docs/design/CALLEE_EXTRACTION_SINGLE_IMPLEMENTATION_2026-09-18.md
(BACK-1279). Everything here is a pure function of (node, get_text) so the
analyzer (`TreeSitterAnalyzer._get_callee_name`) and nav
(`nav_calls._extract_callee`) delegate to one implementation instead of keeping
paired copies that drift.
"""

from .generic import (
    CHAIN_COLLAPSE,
    CHAIN_FULL,
    callee_name_from_node,
    unwrap_parenthesized_callee,
)

__all__ = [
    'CHAIN_COLLAPSE',
    'CHAIN_FULL',
    'callee_name_from_node',
    'unwrap_parenthesized_callee',
]
