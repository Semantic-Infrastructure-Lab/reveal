"""Nav-flag handlers — implementations of --outline, --varflow, --calls, etc.

This module owns the per-view handler functions and the ELEMENT_HANDLERS lookup.
file_handler.py orchestrates: it parses the file, builds a _NavCtx, then
delegates to the handler of the bound request's answer (ELEMENT_HANDLERS).
A handler prints its text answer and returns None, or returns its JSON answer
(``_nav_json``), which the route prints or hands to its answer consumer.

Imports from adapters.ast.nav are deferred inside each handler to avoid the
cli/adapters circular import at module-load time (see file_handler.py header).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from .core import tree_root
from reveal.utils.lines import split_lines
from reveal.utils.path_utils import to_posix

if TYPE_CHECKING:
    from .adapters.ast.nav_outline import OutlineDepth
    from .adapters.ast.nav_exits import ExitOwnership


# Branch keywords for --ifmap and --catchmap filtering
_IF_KEYWORDS: frozenset = frozenset({'IF', 'ELIF', 'ELSE', 'UNLESS', 'SWITCH', 'CASE', 'DEFAULT'})
_CATCH_KEYWORDS: frozenset = frozenset({'TRY', 'CATCH', 'EXCEPT', 'FINALLY'})


def _resolve_range(request, func_start: int, func_end: int):
    """Return (from_line, to_line) for an element view, respecting the request's bound ``--range`` (a (start, end)
    pair, or None when it was not given)."""
    range_arg = request.range
    if range_arg:
        return _parse_line_range(range_arg, func_start, func_end)
    return func_start, func_end


def _parse_line_range(range_str, default_start: int, default_end: int):
    """Parse 'START-END' range string (or pre-parsed tuple) into (start, end) ints.

    Accepts either a 'START-END' string or a (start, end) tuple as produced by
    validate_navigation_args().  Falls back to (default_start, default_end) on
    None input or parse failure.
    """
    import re  # noqa: I006
    if range_str is None:
        return default_start, default_end
    if isinstance(range_str, tuple):
        start, end = range_str
        return start, (end if end is not None else default_end)
    m = re.match(r'^(\d+)-(\d+)$', range_str.strip())
    if m:
        return int(m.group(1)), int(m.group(2))
    # Single number: treat as start, use default_end
    m2 = re.match(r'^(\d+)$', range_str.strip())
    if m2:
        return int(m2.group(1)), default_end
    return default_start, default_end


def callsites_lines(value) -> Optional[tuple]:
    """The lines a ``--callsites`` value selects: None for the whole element (bare ``--callsites``), else the
    (start, end) of ``START-END``, ``START-`` or ``START`` (end None: to the element's end). Anything else is an
    invalid request (D6): ``--callsites abc`` used to answer the whole element (BACK-2627 E4)."""
    from .errors import NavRequestValidationError
    from .utils.query_parser import line_range
    if value is None or value == 'FULL':
        return None
    if isinstance(value, tuple):
        return value
    text = str(value).strip()
    try:
        return line_range(text if '-' in text else text + '-')
    except ValueError as exc:
        raise NavRequestValidationError(f'--callsites takes a line range START-END (1-indexed); got {value!r}: {exc}') \
            from None


def _require_variable(ctx: '_NavCtx', var_name: str, from_line: int, to_line: int, option: str,
                      events: Optional[list] = None) -> None:
    """Plan rule 9: a variable that is read or written nowhere in the searched lines is a target that matches
    nothing, an invalid request naming what was searched, not an empty answer (BACK-2627 E1). A variable that occurs
    with no events of the view's kind (no key access, no narrowing) is a genuine zero. *events* is the caller's own
    var_flow answer when it has one, so the lines are walked once."""
    from .adapters.ast.nav import var_flow  # noqa: I006
    from .errors import NavRequestValidationError
    if events is None:
        events = var_flow(ctx.func_node, var_name, from_line, to_line, ctx.get_text)
    if events:
        return
    searched = ctx.element or 'the file'
    raise NavRequestValidationError(
        f'{option} {var_name}: no read or write of {var_name!r} in {searched} (L{from_line}-L{to_line}) of '
        f'{to_posix(ctx.analyzer.path)}; check the name, or widen the element or range.')


def _nav_json(flag: str, path: str, element: str, from_line: int, to_line: int,
              findings, extra_meta: Optional[dict] = None,
              warnings: Optional[List[str]] = None) -> Dict[str, Any]:
    """Nav findings as their JSON envelope: the answer the route (``file_handler._dispatch_nav``) prints, or hands to
    the path read's answer consumer (the Python API, BACK-2627 note #10)."""
    from .utils.results import ResultBuilder
    from .reveal_types import CONTRACT_VERSION
    meta: Dict[str, Any] = {'flag': flag, 'file': to_posix(path), 'element': element,
            'from_line': from_line, 'to_line': to_line}
    if extra_meta:
        meta.update(extra_meta)
    extra_warnings = [warning if isinstance(warning, dict) else
                        {'type': 'navigation_warning', 'message': warning}
                        for warning in warnings or []]
    meta['warnings'] = [*meta.get('warnings', []), *extra_warnings]
    result: Dict[str, Any] = ResultBuilder.create(
        'element_view', to_posix(path), source_type='file', contract_version=CONTRACT_VERSION,
        meta=meta, data={'findings': findings, 'warnings': warnings or []})
    return result


def _varflow_trust_warning(analyzer) -> Optional[str]:
    """Return a one-line trust caveat for --varflow on *analyzer*'s language,
    or None when the language's varflow capability is fully verified.

    Grounded in the BACK-444 capability registry (reveal/capabilities.py) —
    only languages in the deep conformance matrix (tests/test_conformance_matrix.py)
    are "verified"; everything else is smoke-tested-at-best or has no
    nav-flag surface at all, and should say so rather than imply parity.
    """
    from .capabilities import get_capability, VARFLOW_VERIFIED  # noqa: I006

    from .capabilities import CONFORMANCE_UNTESTED  # noqa: I006
    cap = get_capability(analyzer)
    # An untested language's answers carry the one tier warning on every view instead (file_handler, BACK-2627 X15).
    if cap is None or cap.varflow == VARFLOW_VERIFIED or cap.conformance_level == CONFORMANCE_UNTESTED:
        return None
    return (
        f"--varflow is '{cap.varflow}' for {cap.language} (not fully "
        f"conformance-verified) — see `reveal --language-info {cap.language}` "
        f"for known limitations."
    )


def _print_rules(result: Dict[str, Any], *, fields: tuple = (), standing_types: frozenset = frozenset()) -> None:
    """A view's standing caveats as the one Rules pointer line; their full text stays in the JSON fields it names
    (COMMAND_MODEL rule 7, BACK-2599, BACK-2627)."""
    from .utils.warning_render import rule_text_lines
    for line in rule_text_lines(result, fields=fields, standing_types=standing_types):
        print(line)


def _print_standing_warning(message: Optional[str]) -> None:
    """A standing caveat the JSON carries as a ``navigation_warning`` in meta.warnings (the varflow trust note), as the
    Rules pointer to that field."""
    if message:
        _print_rules({'meta': {'warnings': [{'type': 'navigation_warning', 'message': message}]}},
                     standing_types=frozenset({'navigation_warning'}))


@dataclass
class _NavCtx:
    func_node: Any
    element: str
    analyzer: Any
    as_json: bool
    request: Any  # the bound nav_params.ElementRequest
    func_start: int
    func_end: int
    depth: int  # the structural (nesting) depth of the flow and loops views
    get_text: Callable


def _emit_depth_navigation(ctx: _NavCtx, flag: str, from_line: int, to_line: int, findings: list,
                           evidence: OutlineDepth, render: Callable[[], str]) -> Optional[Dict[str, Any]]:
    """Expose the structural budget and regions not expanded by it."""
    from .utils.results import note_warning
    from .utils.warning_render import render_meta_warnings

    limited = evidence.overlaps(from_line, to_line)
    structure_scope = {
        'rule': 'Recognized structural nodes; exit expressions may be omitted.',
        'exit_sites': 'Inspect --view exits for candidate exit sites.',
    }
    result = {'meta': {'depth': ctx.depth, 'depth_limited': limited,
                       'structure_scope': structure_scope}}
    if flag == 'flow':
        result['meta']['flow_selectors'] = list(ctx.request.kind)
    if limited:
        note_warning(result, {
            'type': 'depth_limited', 'field': 'findings', 'cause': 'max_depth',
            'message': f'Control-structure expansion limited by depth {ctx.depth}; deeper structural '
                       'regions overlapping this selection were not expanded. Increase --nesting-depth to expand them.',
        })
    if ctx.as_json:
        return _nav_json(flag, ctx.analyzer.path, ctx.element, from_line, to_line,
                         findings, extra_meta=result['meta'])
    else:
        print(f'Navigation depth {ctx.depth}')
        print(render())
        render_meta_warnings(result)
        _print_rules(result, fields=('meta.structure_scope.rule', 'meta.structure_scope.exit_sites'))


def _nav_flow(ctx: _NavCtx) -> Optional[Dict[str, Any]]:
    from .adapters.ast.nav import OutlineDepth, element_outline, render_outline, LOOP_KEYWORDS

    from_line, to_line = _resolve_range(ctx.request, ctx.func_start, ctx.func_end)
    evidence = OutlineDepth()
    items = element_outline(ctx.func_node, ctx.get_text, max_depth=ctx.depth,
                            depth_evidence=evidence)
    projections = {'if': _IF_KEYWORDS, 'loop': LOOP_KEYWORDS, 'try': _CATCH_KEYWORDS}
    selectors = ctx.request.kind
    keywords = frozenset().union(*(projections[name] for name in selectors))
    items = [item for item in items
             if from_line <= item['line_start'] <= to_line
             and (not selectors or item['keyword'] in keywords)]
    return _emit_depth_navigation(ctx, 'flow', from_line, to_line, items, evidence,
                                  lambda: render_outline(ctx.element, ctx.func_start, ctx.func_end,
                                                         items, depth=ctx.depth))


def _nav_varflow(ctx: _NavCtx) -> Optional[Dict[str, Any]]:
    from .adapters.ast.nav import (  # noqa: I006
        var_flow, render_var_flow, cross_var_flow, render_cross_var_flow,
    )
    var_name = ctx.request.value
    from_line, to_line = _resolve_range(ctx.request, ctx.func_start, ctx.func_end)
    trust_warning = _varflow_trust_warning(ctx.analyzer)
    if ctx.request.cross_calls:
        _require_variable(ctx, var_name, from_line, to_line, '--varflow')
        frames = cross_var_flow(ctx.analyzer, ctx.func_node, var_name, from_line, to_line, ctx.get_text)
        if ctx.as_json:
            # Each frame's 'events' carries var_flow's internal tree-sitter
            # Node objects (needed for column-sort/dedup) — strip them before
            # serializing, same as the plain --varflow path below (BACK-429).
            json_frames = [
                {**frame, 'events': [{'kind': e['kind'], 'line': e['line']} for e in frame['events']]}
                for frame in frames
            ]
            return _nav_json('cross_varflow', ctx.analyzer.path, ctx.element, from_line, to_line, json_frames,
                             extra_meta={'var': var_name},
                             warnings=[trust_warning] if trust_warning else None)
        else:
            print(render_cross_var_flow(var_name, frames, split_lines(ctx.analyzer.content)))
            _print_standing_warning(trust_warning)
        return
    events = var_flow(ctx.func_node, var_name, from_line, to_line, ctx.get_text)
    _require_variable(ctx, var_name, from_line, to_line, '--varflow', events)
    if ctx.as_json:
        findings = [{'kind': e['kind'], 'line': e['line']} for e in events]
        return _nav_json('varflow', ctx.analyzer.path, ctx.element, from_line, to_line, findings,
                         extra_meta={'var': var_name},
                         warnings=[trust_warning] if trust_warning else None)
    else:
        print(render_var_flow(var_name, events, split_lines(ctx.analyzer.content)))
        _print_standing_warning(trust_warning)


def _nav_narrow(ctx: _NavCtx) -> Optional[Dict[str, Any]]:
    from .adapters.ast.nav import collect_narrowing, render_narrowing  # noqa: I006
    var_name = ctx.request.value
    from_line, to_line = _resolve_range(ctx.request, ctx.func_start, ctx.func_end)
    _require_variable(ctx, var_name, from_line, to_line, '--narrow')
    events = collect_narrowing(ctx.func_node, var_name, ctx.get_text)
    if ctx.as_json:
        findings = [] if events is None else [
            {'kind': e['kind'], 'line': e['line'],
             'type_set': sorted(e['type_set']), 'depth': e['depth']}
            for e in events
        ]
        # No annotation is a decline, not a zero: the JSON says the text's sentence (BACK-2627 E2, X14).
        decline = [render_narrowing(var_name, None, [])] if events is None else None
        return _nav_json('narrow', ctx.analyzer.path, ctx.element, from_line, to_line,
                         findings, extra_meta={'var': var_name}, warnings=decline)
    else:
        print(render_narrowing(var_name, events, split_lines(ctx.analyzer.content)))


def _implicit_nodes(ctx: _NavCtx) -> list:
    """Call sites the analyzer knows of that are not call-expression nodes
    (Ruby paren-less calls, BACK-1299); [] for analyzers without the hook."""
    hook = getattr(ctx.analyzer, '_implicit_call_nodes', None)
    return hook(ctx.func_node) if hook else []


def _nav_calls(ctx: _NavCtx) -> Optional[Dict[str, Any]]:
    from .adapters.ast.nav import range_calls, render_range_calls  # noqa: I006
    # The value is 'FULL' (bare --callsites) or a range string (--callsites 89-120), validated by callsites_lines; bare,
    # the request's --range selects the lines, as every line-reading view's does (X9, BACK-2627 F1).
    lines = callsites_lines(ctx.request.value)
    from_line, to_line = (_parse_line_range(lines, ctx.func_start, ctx.func_end) if lines is not None
                          else _resolve_range(ctx.request, ctx.func_start, ctx.func_end))
    calls = range_calls(ctx.func_node, from_line, to_line, ctx.get_text,
                        implicit_nodes=_implicit_nodes(ctx), include_jsx=True)
    if ctx.as_json:
        return _nav_json('callsites', ctx.analyzer.path, ctx.element, from_line, to_line, calls)
    else:
        print(render_range_calls(calls, from_line, to_line))


def _emit_exit_navigation(ctx: _NavCtx, flag: str, from_line: int, to_line: int, findings: list,
                          ownership: ExitOwnership, render: Callable[[], str]) -> Optional[Dict[str, Any]]:
    from .utils.results import note_warning
    from .utils.warning_render import render_meta_warnings

    result = {'meta': {'exit_scope': ownership.scope_metadata()}}
    for warning in ownership.warnings():
        note_warning(result, dict(warning))
    if ctx.as_json:
        return _nav_json(flag, ctx.analyzer.path, ctx.element, from_line, to_line,
                         findings, extra_meta=result['meta'])
    else:
        label = ('selected callable execution regions' if ownership.mode == 'selected_callable'
                 else 'source inventory; may include multiple callable owners')
        print(f'Exit scope: {label}')
        print(render())
        render_meta_warnings(result)
        _print_rules(result, fields=('meta.exit_scope.rule', 'meta.exit_scope.implicit_tail_rule'))


def _nav_exits(ctx: _NavCtx) -> Optional[Dict[str, Any]]:
    from .adapters.ast.nav import collect_gate_chains, render_gate_chains  # noqa: I006
    from .adapters.ast.nav_exits import ExitOwnership
    from_line, to_line = _resolve_range(ctx.request, ctx.func_start, ctx.func_end)
    ownership = ExitOwnership(getattr(ctx.analyzer, 'language', ''), ctx.func_node)
    exits = collect_gate_chains(ctx.func_node, from_line, to_line, ctx.get_text, ownership=ownership)
    return _emit_exit_navigation(ctx, 'exits', from_line, to_line,
                                 exits, ownership,
                                 lambda: render_gate_chains(exits, from_line, to_line))


def _nav_deps(ctx: _NavCtx) -> Optional[Dict[str, Any]]:
    from .adapters.ast.nav import collect_deps, render_deps  # noqa: I006
    from_line, to_line = _resolve_range(ctx.request, ctx.func_start, ctx.func_end)
    deps = collect_deps(ctx.func_node, from_line, to_line, ctx.get_text,
                        language=getattr(ctx.analyzer, 'language', None))
    if ctx.as_json:
        findings = [
            {'kind': 'builtin' if d.get('classification') == 'builtin' else 'dep',
             'var': d['var'], 'line': d['first_read_line'],
             'first_write_line': d['first_write_line']}
            for d in deps
        ]
        return _nav_json('inputs', ctx.analyzer.path, ctx.element, from_line, to_line, findings)
    else:
        print(render_deps(deps, from_line, to_line))


def _nav_mutations(ctx: _NavCtx) -> Optional[Dict[str, Any]]:
    from .adapters.ast.nav import collect_mutations, render_mutations  # noqa: I006
    from_line, to_line = _resolve_range(ctx.request, ctx.func_start, ctx.func_end)
    mutations = collect_mutations(ctx.func_node, from_line, to_line, ctx.get_text)
    if ctx.as_json:
        findings = [
            {'kind': 'mutation', 'var': m['var'], 'line': m['last_write_line'],
             'next_read_line': m['next_read_line']}
            for m in mutations
        ]
        return _nav_json('outputs', ctx.analyzer.path, ctx.element, from_line, to_line, findings)
    else:
        print(render_mutations(mutations, from_line, to_line))


def _nav_sideeffects(ctx: _NavCtx) -> Optional[Dict[str, Any]]:
    from .adapters.ast.nav import (  # noqa: I006
        collect_effects, collect_effects_transitive, render_effects, render_effects_transitive,
    )
    from .adapters.ast.nav_effects import (  # noqa: I006
        EffectList, ambiguous_hops_note, skipped_files_note, _traversal_note,
    )
    from_line, to_line = _resolve_range(ctx.request, ctx.func_start, ctx.func_end)
    language = getattr(ctx.analyzer, 'language', None)
    transitive = ctx.request.transitive

    if transitive:
        depth = ctx.request.depth  # the hop budget in effect: the given 1..5 or the default 2
        effects = collect_effects_transitive(
            ctx.analyzer.path, ctx.element, ctx.func_node, from_line, to_line, ctx.get_text,
            language=language, depth=depth,
        )
    else:
        effects = EffectList(collect_effects(
            ctx.func_node, from_line, to_line, ctx.get_text, language=language,
            implicit_nodes=_implicit_nodes(ctx),
        ))

    if ctx.as_json:
        findings = [
            {'kind': e['kind'], 'line': e['line'], 'callee': e['callee'],
             'first_arg': e.get('first_arg'), 'has_more_args': e.get('has_more_args', False),
             'via': e.get('via', 'call'),
             **({'hop': e['hop'], 'chain': e['chain']} if transitive else {}),
             **({'file': to_posix(e['file'])} if transitive and e['hop'] > 0 else {})}
            for e in effects if e['kind'] is not None
        ]
        note = skipped_files_note(effects.skipped) if transitive else None
        return _nav_json('sideeffects', ctx.analyzer.path, ctx.element, from_line, to_line, findings,
                         warnings=[n for n in (note, _traversal_note(effects.traversal_failures),
                                               ambiguous_hops_note(effects.ambiguous)) if n])
    elif transitive:
        note = skipped_files_note(effects.skipped)
        print(render_effects_transitive(effects, ctx.element, depth)
              + (f'\n\nWarning: {note}' if note else ''))
    else:
        print(render_effects(effects, from_line, to_line))


def _nav_fanout(ctx: _NavCtx) -> Optional[Dict[str, Any]]:
    from .adapters.ast.nav import OutlineDepth, collect_fanout, render_fanout  # noqa: I006
    from_line, to_line = _resolve_range(ctx.request, ctx.func_start, ctx.func_end)
    evidence = OutlineDepth()
    loops = collect_fanout(
        ctx.func_node, from_line, to_line, ctx.get_text,
        language=getattr(ctx.analyzer, 'language', None), max_depth=ctx.depth,
        depth_evidence=evidence,
    )
    return _emit_depth_navigation(ctx, 'fanout', from_line, to_line, loops, evidence,
                                  lambda: render_fanout(loops, from_line, to_line))


def _nav_statewrites(ctx: _NavCtx) -> Optional[Dict[str, Any]]:
    from .adapters.ast.nav import collect_statewrites, render_statewrites  # noqa: I006
    from_line, to_line = _resolve_range(ctx.request, ctx.func_start, ctx.func_end)
    writes = collect_statewrites(
        ctx.func_node, from_line, to_line, ctx.get_text,
        language=getattr(ctx.analyzer, 'language', None),
    )
    if ctx.as_json:
        return _nav_json('statewrites', ctx.analyzer.path, ctx.element, from_line, to_line, writes)
    else:
        print(render_statewrites(writes, from_line, to_line))


def _nav_keys(ctx: _NavCtx) -> Optional[Dict[str, Any]]:
    from .adapters.ast.nav import collect_keys, render_keys  # noqa: I006
    var_name = ctx.request.value
    from_line, to_line = _resolve_range(ctx.request, ctx.func_start, ctx.func_end)
    _require_variable(ctx, var_name, from_line, to_line, '--keys')
    events = collect_keys(ctx.func_node, var_name, from_line, to_line, ctx.get_text)
    if ctx.as_json:
        return _nav_json('keys', ctx.analyzer.path, ctx.element, from_line, to_line, events,
                         extra_meta={'var': var_name})
    else:
        print(render_keys(var_name, events, from_line, to_line))


def _boundary_effect_finding(effect: Dict[str, Any], transitive: bool) -> Dict[str, Any]:
    finding = {key: effect.get(key) for key in ('kind', 'line', 'callee', 'first_arg')}
    if effect.get('via') == 'assignment':
        finding['via'] = 'assignment'
    if transitive:
        finding.update(hop=effect['hop'], chain=effect['chain'])
        if effect['hop'] > 0:
            finding['file'] = to_posix(effect['file'])
    return finding


def _boundary_warnings(boundary: Dict[str, Any], transitive: bool) -> List[str]:
    """The --boundary JSON `warnings`: what a --transitive walk skipped, lost or declined, then the coverage note."""
    from .adapters.ast.nav_effects import ambiguous_hops_note, skipped_files_note, _traversal_note  # noqa: I006
    note = skipped_files_note(boundary.get('skipped') or []) if transitive else None
    notes = (note, _traversal_note(boundary.get('traversal_failures') or []),
             ambiguous_hops_note(boundary.get('ambiguous') or []), boundary.get('assignment_coverage_note'))
    return [n for n in notes if n]


def _nav_boundary(ctx: _NavCtx) -> Optional[Dict[str, Any]]:
    from .adapters.ast.nav import (  # noqa: I006
        collect_boundary, collect_boundary_transitive, render_boundary, render_boundary_transitive,
    )
    from_line, to_line = _resolve_range(ctx.request, ctx.func_start, ctx.func_end)
    language = getattr(ctx.analyzer, 'language', None)
    transitive = ctx.request.transitive

    if transitive:
        # The depth the walk uses, stated as such in text and JSON (BACK-2627 E8): the given 1..5 or the default 2.
        depth = ctx.request.depth
        boundary = collect_boundary_transitive(
            ctx.analyzer.path, ctx.element, ctx.func_node, from_line, to_line, ctx.get_text,
            language=language, depth=depth,
        )
    else:
        boundary = collect_boundary(
            ctx.func_node, from_line, to_line, ctx.get_text, language=language,
            implicit_nodes=_implicit_nodes(ctx),
        )

    if ctx.as_json:
        findings = (
            [{'kind': 'input', 'var': d['var'], 'line': d['first_read_line'],
              'first_write_line': d['first_write_line']}
             for d in boundary['inputs']]
            + [{'kind': 'builtin', 'var': d['var'], 'line': d['first_read_line']}
               for d in boundary.get('builtins', [])]
            + [{'kind': 'superglobal', 'var': d['var'], 'line': d['first_read_line']}
               for d in boundary['superglobals']]
            + [_boundary_effect_finding(e, transitive)
               for e in boundary['effects'] if e['kind'] is not None]
        )
        warnings = _boundary_warnings(boundary, transitive)
        return _nav_json('boundary', ctx.analyzer.path, ctx.element, from_line, to_line, findings,
                         extra_meta={'depth': depth} if transitive else None, warnings=warnings)
    elif transitive:
        print(render_boundary_transitive(boundary, ctx.element, from_line, to_line, depth))
    else:
        print(render_boundary(boundary, from_line, to_line))


# Each element answer's handler, keyed by the bound request's ``ElementRequest.answer`` (the view, effects by its mode,
# or the standalone operation). The declarations decide which answer a request selects (one answer per request), so
# this is a lookup, not a precedence; --scope and --around answer on a line reference before it (_dispatch_nav).
ELEMENT_HANDLERS: Dict[str, Callable[[_NavCtx], Optional[Dict[str, Any]]]] = {
    'boundary': _nav_boundary, 'flow': _nav_flow, 'exits': _nav_exits,
    'effects:ordinary': _nav_sideeffects, 'effects:loops': _nav_fanout, 'effects:state': _nav_statewrites,
    'inputs': _nav_deps, 'outputs': _nav_mutations, 'callsites': _nav_calls,
    'varflow': _nav_varflow, 'keys': _nav_keys, 'narrow': _nav_narrow,
}


def _no_value_words() -> frozenset:
    """The element words that take no value, from the declarations: the view's and flow's no-value legacy words, and
    the switch operations with their legacy words (the names MCP ``reveal_nav`` takes without a flag_value)."""
    from .nav_params import ELEMENT_VIEW_SPECS, KIND, VIEW
    words = {entry.name for spec in (VIEW, KIND) for entry in spec.legacy if not entry.flag_optional}
    words |= {word for spec in ELEMENT_VIEW_SPECS if spec.role == 'operation' and spec.type == 'boolean'
              for word in (spec.name, *spec.legacy_words)}
    return frozenset(words)


NAV_BOOLEAN_FLAG_NAMES: frozenset = _no_value_words()


def _single_line_ref(element: Optional[str], flag: str) -> int:
    """The line number a --scope/--around element names; NavRequestValidationError (exit 2) when it names none.

    A range is refused too: both flags answer for one line, and `:100-110 --around 2` used to
    print 98-102 and drop the rest of the range without a word (BACK-2272).
    """
    from .display.element import _parse_element_syntax  # noqa: I006
    from .errors import NavRequestValidationError
    syntax = _parse_element_syntax(element) if element else None
    if element is None or syntax is None or syntax['type'] != 'line':
        # An invalid request (D6): exit 2, as the range case below (BACK-2627 E9).
        raise NavRequestValidationError(
            f'{flag} requires a line reference (e.g., reveal file.py :123 {flag}); got element {element!r}.')
    start: int = syntax['start_line']
    end = syntax['end_line']
    if end is not None and end != start:
        # An invalid request (D6) raised as every element view's refusal is, so the library API gets it, not an exit.
        hint = f'drop {flag} to print lines {element[1:]}' if flag == '--around' else 'run it once per line'
        raise NavRequestValidationError(
            f"{flag} takes a single line, not the range '{element}'; only line {start} would be used.\n"
            f'  Give one line (:{start}), or {hint}.')
    return start


def _nav_scope(analyzer, element: str, as_json: bool) -> Optional[Dict[str, Any]]:
    """Handle --scope: show lexical scope chain for a line reference."""
    from .adapters.ast.nav import scope_chain, render_scope_chain  # noqa: I006
    line_no = _single_line_ref(element, '--scope')
    chain = scope_chain(tree_root(analyzer.tree), line_no, analyzer._get_node_text)
    if as_json:
        return _nav_json('scope', analyzer.path, element, line_no, line_no, chain)
    else:
        content_lines = split_lines(analyzer.content)
        line_text = content_lines[line_no - 1].strip() if 0 < line_no <= len(content_lines) else ''
        print(render_scope_chain(line_no, chain, line_text))


def _nav_around(analyzer, element: str, as_json: bool, n: int) -> Optional[Dict[str, Any]]:
    """Handle --around N: show N lines of context around a line reference."""
    from .errors import NavRequestValidationError
    if n < 0:  # used to print nothing, exit 0, with from_line after to_line (BACK-2627 E10)
        raise NavRequestValidationError(f'--around takes 0 or more context lines; got {n}.')
    line_no = _single_line_ref(element, '--around')
    content_lines = split_lines(analyzer.content)
    total = len(content_lines)
    start = max(1, line_no - n)
    end = min(total, line_no + n)
    if as_json:
        findings = [
            {'line': i + 1, 'text': content_lines[i], 'is_target': (i + 1) == line_no}
            for i in range(start - 1, end)
        ]
        return _nav_json('around', analyzer.path, element, start, end, findings,
                         extra_meta={'target_line': line_no, 'context': n})
    else:
        for i in range(start - 1, end):
            prefix = '▶' if (i + 1) == line_no else ' '
            print(f'{prefix}{i + 1:5}  {content_lines[i]}')
