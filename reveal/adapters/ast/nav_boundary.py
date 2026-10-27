from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Sequence

from .nav_exits import collect_deps
from .nav_statewrites import collect_statewrites
from .nav_effects import (
    collect_effects,
    collect_effects_transitive,
    format_effect_target,
    render_effects_transitive,
    ambiguous_hops_note,
    skipped_files_note,
    _traversal_note,
)


_PHP_SUPERGLOBALS = frozenset({
    '$_GET', '$_POST', '$_SESSION', '$_SERVER', '$_FILES',
    '$_COOKIE', '$_ENV', '$GLOBALS', '$_REQUEST',
})

_ASSIGNMENT_COVERAGE_NOTE = (
    'Assignment coverage: assignments only in the entry function; '
    'call effects follow project-local callees.'
)


def _without_assignment_properties(
    effects: List[Dict[str, Any]], assignments: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Remove one LHS property event per write, retaining same-line RHS reads."""
    replaced = Counter((w['kind'], w['line'], w['callee']) for w in assignments)
    kept = []
    for effect in effects:
        if effect['kind'] is None:
            continue
        key = (effect['kind'], effect['line'], effect['callee'])
        if effect.get('via') == 'property' and effect.get('hop', 0) == 0 and replaced[key]:
            replaced[key] -= 1
        else:
            kept.append(effect)
    return kept


def _boundary_effects(
    effects: List[Dict[str, Any]], scope_node: Any, from_line: int, to_line: int,
    get_text: Callable, language: Optional[str], root_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Merge assignment writes, retaining call effects and other property reads."""
    assignments = [
        dict(kind=w['kind'], line=w['line'], callee=w['target'], first_arg=None,
             has_more_args=False, via='assignment')
        for w in collect_statewrites(scope_node, from_line, to_line, get_text, language)
        if w['via'] == 'assignment'
    ]
    classified = _without_assignment_properties(effects, assignments)
    if root_name is not None:
        for write in assignments:
            write.update(hop=0, chain=[root_name])
    return sorted(classified + assignments, key=lambda e: (e.get('hop', 0), e['line']))


def _is_superglobal(var_name: str) -> bool:
    return var_name in _PHP_SUPERGLOBALS


def collect_boundary(
    scope_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    language: Optional[str] = None,
    implicit_nodes: Sequence[Any] = (),
) -> Dict[str, Any]:
    """Collect INPUTS, ENVIRONMENT, and EFFECTS for a boundary report.

    Returns a dict with four keys:
        inputs       -- deps that are neither builtins nor PHP superglobals
        builtins     -- known unshadowed language builtins
        superglobals -- deps that are PHP superglobals ($_GET, $_SESSION, etc.)
        effects      -- classified calls, property reads, and assignment writes
    """
    deps = collect_deps(scope_node, from_line, to_line, get_text, language=language)
    builtins = [d for d in deps if d.get('classification') == 'builtin']
    inputs = [d for d in deps if not _is_superglobal(d['var'])
              and d.get('classification') != 'builtin']
    superglobals = [d for d in deps if _is_superglobal(d['var'])]
    effects = collect_effects(scope_node, from_line, to_line, get_text, language,
                              implicit_nodes=implicit_nodes)
    classified = _boundary_effects(effects, scope_node, from_line, to_line, get_text, language)
    return {'inputs': inputs, 'superglobals': superglobals, 'builtins': builtins, 'effects': classified}


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

    builtins = result.get('builtins', [])
    if builtins:
        lines = ['BUILTINS:']
        for d in builtins:
            lines.append(f'  {d["var"]:<30}  first read L{d["first_read_line"]}')
        sections.append('\n'.join(lines))

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
    """Render inputs, optional builtins/environment, and effects."""
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
) -> Dict[str, Any]:
    """Collect INPUTS, ENVIRONMENT, and transitive EFFECTS for a boundary report.

    Same three-section contract as collect_boundary, but EFFECTS follows calls
    into project-local helpers (BACK-546 — the same interprocedural walk
    BACK-545 added for --sideeffects). INPUTS/ENVIRONMENT stay intra-procedural
    since they describe the entry function's own signature, not its callees.
    """
    deps = collect_deps(scope_node, from_line, to_line, get_text, language=language)
    builtins = [d for d in deps if d.get('classification') == 'builtin']
    inputs = [d for d in deps if not _is_superglobal(d['var'])
              and d.get('classification') != 'builtin']
    superglobals = [d for d in deps if _is_superglobal(d['var'])]
    effects = collect_effects_transitive(
        path, root_name, scope_node, from_line, to_line, get_text,
        language=language, depth=depth,
    )
    classified = _boundary_effects(effects, scope_node, from_line, to_line, get_text,
                                   language, root_name=root_name)
    result: Dict[str, Any] = {'inputs': inputs, 'superglobals': superglobals, 'builtins': builtins, 'effects': classified}
    result['assignment_coverage_note'] = _ASSIGNMENT_COVERAGE_NOTE
    if effects.skipped:
        result['skipped'] = [list(item) for item in effects.skipped]
    if effects.traversal_failures:
        result['traversal_failures'] = list(effects.traversal_failures)
    if effects.ambiguous:
        result['ambiguous'] = list(effects.ambiguous)
    return result


def render_boundary_transitive(
    result: Dict[str, Any],
    root_name: str,
    from_line: int,
    to_line: int,
    depth: int,
) -> str:
    """Render collect_boundary_transitive output, EFFECTS grouped by hop/call chain."""
    sections = _render_boundary_header(result, from_line, to_line)

    effects = result['effects']
    directory_note = _traversal_note(result.get('traversal_failures') or [])
    header = f'EFFECTS (--transitive, depth={depth}):'
    if effects:
        body = render_effects_transitive(effects, root_name, depth)
        sections.append(f'{header}\n' + '\n'.join(f'  {line}' for line in body.split('\n')))
    elif directory_note:
        sections.append(f'{header}\n  none observed in the analyzed portion of {root_name} '
                        'or its callees; analysis is incomplete')
    else:
        sections.append(f'{header}\n  none in {root_name} or its callees')

    note = skipped_files_note(result.get('skipped') or [])
    if note:
        sections.append(f'Warning: {note}')
    if directory_note:
        sections.append(f'Warning: {directory_note}')
    ambiguous = ambiguous_hops_note(result.get('ambiguous') or [])
    if ambiguous:
        sections.append(f'Warning: {ambiguous}')
    if result.get('assignment_coverage_note'):
        sections.append(result['assignment_coverage_note'])

    return '\n\n'.join(sections)
