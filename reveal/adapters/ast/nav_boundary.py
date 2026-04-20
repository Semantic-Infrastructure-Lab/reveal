from typing import Any, Callable, Dict, List

from .nav_exits import collect_deps
from .nav_effects import collect_effects


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
    effects = collect_effects(scope_node, from_line, to_line, get_text)
    classified = [e for e in effects if e['kind'] is not None]
    return {'inputs': inputs, 'superglobals': superglobals, 'effects': classified}


def render_boundary(
    result: Dict[str, List[Dict[str, Any]]],
    from_line: int,
    to_line: int,
) -> str:
    """Render collect_boundary output as a three-section boundary contract."""
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

    effects = result['effects']
    if effects:
        kind_width = max(len(e['kind']) for e in effects)
        lines = ['EFFECTS:']
        for e in effects:
            callee = e['callee'] or '(unknown)'
            first_arg = e.get('first_arg')
            has_more = e.get('has_more_args', False)
            if first_arg:
                arg_str = f'({first_arg}{"..." if has_more else ""})'
            else:
                arg_str = '()'
            lines.append(f'  {e["kind"]:<{kind_width}}  L{e["line"]:<6}  {callee}{arg_str}')
        sections.append('\n'.join(lines))
    else:
        sections.append(f'EFFECTS:\n  none in L{from_line}–L{to_line}')

    return '\n\n'.join(sections)
