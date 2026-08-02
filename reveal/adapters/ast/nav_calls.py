"""Back-compat shim — moved to reveal.core.nav_calls (BACK-911).

nav_calls.py's only adapters-package dependency was node_taxonomy.py
(itself dependency-free), so both were relocated to reveal/core/ to break
the analyzers -> adapters import cycle: analyzers/zig.py imported
range_calls from here, which pulled in the whole adapters package
(adapters/__init__.py -> ... -> analyzers/__init__.py -> zig.py, a 42-file
cycle group per the BACK-911 review). analyzers/zig.py now imports
range_calls directly from reveal.core.nav_calls. All existing imports of
`reveal.adapters.ast.nav_calls` keep working unchanged via this shim.
"""

from ...core.nav_calls import (  # noqa: F401
    range_calls,
    render_range_calls,
    _extract_callee,
    _extract_first_arg,
)
