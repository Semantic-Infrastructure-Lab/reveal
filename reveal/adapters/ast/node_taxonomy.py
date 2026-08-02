"""Back-compat shim — moved to reveal.core.node_taxonomy (BACK-911).

node_taxonomy.py had zero internal dependencies (pure tree-sitter node-kind
taxonomy data), so it was relocated out of adapters/ast/ to break the
analyzers -> adapters import cycle: analyzers/zig.py depended on
adapters/ast/nav_calls.py, which depended on this module, dragging the
whole adapters package into the analyzer import graph. All existing
imports of `reveal.adapters.ast.node_taxonomy` keep working unchanged.
"""

from ...core.node_taxonomy import *  # noqa: F401,F403
