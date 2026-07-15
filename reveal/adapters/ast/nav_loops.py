"""Loop-focused navigation: collect_loops (--loopmap), collect_fanout (--fanout).

BACK-439b: agents routinely need "which loops exist, what do they iterate,
and which side effects happen inside them" for N+1 database checks, per-item
HTTP calls, filesystem fan-out, and retry-safety review. The raw facts
already exist via two composed calls (--outline for loop nesting,
--calls/--sideeffects for effects inside a range) — the gap is correlation,
not existence. collect_loops reuses element_outline's existing FOR/WHILE/
LOOP/DO keyword taxonomy (no new per-language field parsing needed);
collect_fanout reuses collect_effects per loop range to remove the manual
line-number matching busywork.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .nav_outline import element_outline, render_branchmap
from .nav_effects import collect_effects, format_effect_target

LOOP_KEYWORDS: frozenset = frozenset({'FOR', 'WHILE', 'LOOP', 'DO'})


def collect_loops(
    func_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    max_depth: int = 3,
) -> List[Dict[str, Any]]:
    """Return loop nodes (FOR/WHILE/LOOP/DO) within a line range.

    Each item carries 'depth' (structural nesting from element_outline, so a
    loop nested inside another loop — or inside an intervening IF/TRY — has
    a higher depth than its enclosing loop).
    """
    items = element_outline(func_node, get_text, max_depth=max_depth)
    return [
        item for item in items
        if item['keyword'] in LOOP_KEYWORDS and from_line <= item['line_start'] <= to_line
    ]


def collect_fanout(
    func_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    language: Optional[str] = None,
    max_depth: int = 3,
) -> List[Dict[str, Any]]:
    """Return each loop in the range paired with its classified side effects."""
    loops = collect_loops(func_node, from_line, to_line, get_text, max_depth=max_depth)
    results = []
    for loop in loops:
        effects = collect_effects(
            func_node, loop['line_start'], loop['line_end'], get_text, language,
        )
        results.append({**loop, 'effects': [e for e in effects if e['kind'] is not None]})
    return results


def render_loopmap(items: List[Dict[str, Any]], from_line: int, to_line: int) -> str:
    """Render collect_loops output as text (reuses the branch/exception map layout)."""
    if not items:
        return f'No loop nodes found in L{from_line}→L{to_line}'
    return render_branchmap(items, from_line, to_line)


def render_fanout(loops: List[Dict[str, Any]], from_line: int, to_line: int) -> str:
    """Render collect_fanout output as text: each loop, then its effects indented."""
    if not loops:
        return f'No loops found in L{from_line}→L{to_line}'
    lines: List[str] = []
    for loop in loops:
        indent = '  ' * loop['depth']
        lrange = f'L{loop["line_start"]}→L{loop["line_end"]}'
        lines.append(f'{indent}{loop["label"]}  {lrange}')
        if not loop['effects']:
            lines.append(f'{indent}  (no classified side effects)')
            continue
        for e in loop['effects']:
            target = format_effect_target(e)
            lines.append(f'{indent}  L{e["line"]:<6}  {e["kind"]:<8}  {target}')
    return '\n'.join(lines)
