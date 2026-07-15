from typing import Any, Callable, Dict, List, Optional

from .nav_exits import collect_deps
from .nav_effects import (
    collect_effects,
    collect_effects_transitive,
    format_effect_target,
    render_effects_transitive,
)


_PHP_SUPERGLOBALS = frozenset({
    '$_GET', '$_POST', '$_SESSION', '$_SERVER', '$_FILES',
    '$_COOKIE', '$_ENV', '$GLOBALS', '$_REQUEST',
})


def _is_superglobal(var_name: str) -> bool:
    return var_name in _PHP_SUPERGLOBALS


def collect_boundary(
    scope_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    language: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Collect INPUTS, ENVIRONMENT, and EFFECTS for a boundary report.

    Returns a dict with three keys:
        inputs       -- deps that are not PHP superglobals
        superglobals -- deps that are PHP superglobals ($_GET, $_SESSION, etc.)
        effects      -- classified side-effect call sites
    """
    deps = collect_deps(scope_node, from_line, to_line, get_text)
    inputs = [d for d in deps if not _is_superglobal(d['var'])]
    superglobals = [d for d in deps if _is_superglobal(d['var'])]
    effects = collect_effects(scope_node, from_line, to_line, get_text, language)
    classified = [e for e in effects if e['kind'] is not None]
    return {'inputs': inputs, 'superglobals': superglobals, 'effects': classified}


def _render_boundary_header(
    result: Dict[str, List[Dict[str, Any]]],
    from_line: int,
    to_line: int,
) -> List[str]:
    """Render the INPUTS/ENVIRONMENT sections shared by both boundary renderers.

    These describe the entry function's own signature (undefined reads,
    superglobal reads) and stay intra-procedural even under --transitive —
    only EFFECTS follows calls into callees.
    """
    sections: List[str] = []

    inputs = result['inputs']
    if inputs:
        lines = [f'INPUTS (undefined reads):']
        for d in inputs:
            write = f', first write L{d["first_write_line"]}' if d['first_write_line'] else ''
            lines.append(f'  {d["var"]:<30}  first read L{d["first_read_line"]}{write}')
        sections.append('\n'.join(lines))
    else:
        sections.append(f'INPUTS (undefined reads):\n  none in L{from_line}–L{to_line}')

    superglobals = result['superglobals']
    if superglobals:
        lines = ['ENVIRONMENT (superglobal reads):']
        for d in superglobals:
            lines.append(f'  {d["var"]:<30}  first read L{d["first_read_line"]}')
        sections.append('\n'.join(lines))

    return sections


def render_boundary(
    result: Dict[str, List[Dict[str, Any]]],
    from_line: int,
    to_line: int,
) -> str:
    """Render collect_boundary output as a three-section boundary contract."""
    sections = _render_boundary_header(result, from_line, to_line)

    effects = result['effects']
    if effects:
        kind_width = max(len(e['kind']) for e in effects)
        lines = ['EFFECTS:']
        for e in effects:
            target = format_effect_target(e)
            lines.append(f'  {e["kind"]:<{kind_width}}  L{e["line"]:<6}  {target}')
        sections.append('\n'.join(lines))
    else:
        sections.append(f'EFFECTS:\n  none in L{from_line}–L{to_line}')

    return '\n\n'.join(sections)


def collect_boundary_transitive(
    path: str,
    root_name: str,
    scope_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    language: Optional[str] = None,
    depth: int = 2,
) -> Dict[str, List[Dict[str, Any]]]:
    """Collect INPUTS, ENVIRONMENT, and transitive EFFECTS for a boundary report.

    Same three-section contract as collect_boundary, but EFFECTS follows calls
    into project-local helpers (BACK-546 — the same interprocedural walk
    BACK-545 added for --sideeffects). INPUTS/ENVIRONMENT stay intra-procedural
    since they describe the entry function's own signature, not its callees.
    """
    deps = collect_deps(scope_node, from_line, to_line, get_text)
    inputs = [d for d in deps if not _is_superglobal(d['var'])]
    superglobals = [d for d in deps if _is_superglobal(d['var'])]
    effects = collect_effects_transitive(
        path, root_name, scope_node, from_line, to_line, get_text,
        language=language, depth=depth,
    )
    classified = [e for e in effects if e['kind'] is not None]
    return {'inputs': inputs, 'superglobals': superglobals, 'effects': classified}


def render_boundary_transitive(
    result: Dict[str, List[Dict[str, Any]]],
    root_name: str,
    from_line: int,
    to_line: int,
    depth: int,
) -> str:
    """Render collect_boundary_transitive output, EFFECTS grouped by hop/call chain."""
    sections = _render_boundary_header(result, from_line, to_line)

    effects = result['effects']
    header = f'EFFECTS (--transitive, depth={depth}):'
    if effects:
        body = render_effects_transitive(effects, root_name, depth)
        sections.append(f'{header}\n' + '\n'.join(f'  {line}' for line in body.split('\n')))
    else:
        sections.append(f'{header}\n  none in {root_name} or its callees')

    return '\n\n'.join(sections)
