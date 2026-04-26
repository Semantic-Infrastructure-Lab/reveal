"""Re-export shim — preserves backward-compat imports from adapters.ast.nav.

Split into focused modules (BACK-185):
  nav_outline.py  — element_outline, scope_chain, render_outline, render_scope_chain, render_branchmap
  nav_varflow.py  — VarFlowWalker, var_flow, render_var_flow, all_var_flow
  nav_calls.py    — range_calls, render_range_calls
  nav_exits.py    — collect_exits, collect_deps, collect_mutations, render_exits, render_deps, render_mutations
  nav_effects.py  — collect_effects, render_effects (BACK-199)
  nav_boundary.py — collect_boundary, render_boundary (BACK-201)
"""

from __future__ import annotations

from .nav_outline import (  # noqa: F401
    SCOPE_NODES,
    ALTERNATIVE_NODES,
    FUNCTION_TYPES,
    EXIT_NODES,
    KEYWORD_LABEL,
    _node_label,
    _make_item,
    element_outline,
    _collect_outline,
    _collect_scope_interior,
    scope_chain,
    _find_ancestors,
    render_outline,
    render_scope_chain,
    render_branchmap,
)
from .nav_varflow import (  # noqa: F401
    var_flow,
    VarFlowWalker,
    render_var_flow,
    _collect_identifier_names,
    all_var_flow,
)
from .nav_calls import (  # noqa: F401
    range_calls,
    _extract_callee,
    _extract_first_arg,
    render_range_calls,
)
from .nav_exits import (  # noqa: F401
    _EXIT_CALL_NAMES,
    _EXIT_KIND,
    _HARD_EXIT_KINDS,
    _SOFT_EXIT_KINDS,
    collect_exits,
    render_exits,
    collect_deps,
    collect_mutations,
    render_deps,
    render_mutations,
    collect_gate_chains,
    render_gate_chains,
)
from .nav_effects import (  # noqa: F401
    classify_call,
    collect_effects,
    render_effects,
)
from .nav_boundary import (  # noqa: F401
    collect_boundary,
    render_boundary,
)
from .nav_cross_varflow import (  # noqa: F401
    cross_var_flow,
    render_cross_var_flow,
)
from .nav_narrow import (  # noqa: F401
    collect_narrowing,
    render_narrowing,
)
