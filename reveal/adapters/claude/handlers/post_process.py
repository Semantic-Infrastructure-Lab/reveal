"""Post-processing helpers for claude:// adapter result types."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Dict, Any

from .sessions import _read_session_title, _read_session_stats
from ....utils.threadsafe import main_thread_gc
from ....utils.results import note_truncation


def _slice_list(items: list, args: Any) -> list:
    """Slice a list by --head, --tail, or --range args."""
    head = getattr(args, 'head', None)
    tail = getattr(args, 'tail', None)
    rng = getattr(args, 'range', None)
    if head is not None:
        return items[:head]
    if tail is not None:
        return items[-tail:]
    if rng is not None:
        start, end = rng
        return items[start - 1:end]
    return items


def select_workflow_rows(workflow: list[Dict[str, Any]], tool=None, term=None) -> list[Dict[str, Any]]:
    """Existing literal workflow population, shared by native and CLI controls."""
    if tool is not None:
        workflow = [step for step in workflow if (step.get('tool') or '').lower() == tool.lower()]
    if term:
        needle = term.lower()
        workflow = [step for step in workflow
                    if needle in (step.get('detail') or '').lower()
                    or needle in (step.get('tool') or '').lower()]
    return workflow


def _post_process_workflow(result: Dict[str, Any], args: Any) -> None:
    """Apply --type, --search, and --head/--tail/--range to claude_workflow results."""
    workflow = result.get('workflow')
    if workflow is None:
        return
    total_before = len(workflow)

    workflow = select_workflow_rows(workflow, getattr(args, 'type', None) or None,
                                    getattr(args, 'name', None))

    workflow = _slice_list(workflow, args)
    result['workflow'] = workflow
    note_truncation(result, 'workflow', len(workflow), total_before, 'display-selection')
    result['displayed_steps'] = len(workflow)
    if len(workflow) < total_before:
        result['filtered_from'] = total_before


def _post_process_search_results(result: Dict[str, Any], args: Any) -> None:
    """Apply --head/--all display limits to claude_cross_session_search results."""
    matches = result.get('matches')
    if matches is None:
        return
    total_before = len(matches)
    if not getattr(args, 'all', False):
        head = getattr(args, 'head', None)
        matches = matches[:head if head else 20]
    result['matches'] = matches
    note_truncation(result, 'matches', len(matches), total_before, 'display-selection')
    result['displayed_count'] = len(matches)


def _post_process_history(result: Dict[str, Any], args: Any, query_params: Dict[str, Any]) -> None:
    """Apply --name/--search, ?since= (--since), --head/--all filters to claude_history results."""
    entries = result.get('entries')
    if entries is None:
        return
    total_before = len(entries)

    search_term = getattr(args, 'name', None)
    if search_term:
        lower = search_term.lower()
        entries = [e for e in entries if lower in e.get('prompt', '').lower()]

    since = result.get('since') or query_params.get('since')
    if since:
        since = _normalize_date(str(since))
        entries = [e for e in entries if e.get('timestamp', '') >= since]

    # The count the header reports is of the filtered set; it was taken before
    # --name/--since ran, so a filter changed the list but not its total (BACK-1549).
    result['match_count'] = len(entries)
    if not getattr(args, 'all', False):
        head = getattr(args, 'head', None)
        entries = entries[:head if head else 50]

    result['entries'] = entries
    note_truncation(result, 'entries', len(entries), total_before, 'display-selection')
    result['displayed_count'] = len(entries)


def _normalize_date(val: str) -> str:
    return date.today().isoformat() if val == 'today' else val


def _select_session_dates(result, query_params):
    """Select metadata rows once, before canonical where/page or legacy display cuts."""
    requested = {key: str(value) if value else None for key in ('since', 'until')
                 for value in (query_params.get(key),)}
    if not any(requested.values()):
        return
    scope = result.setdefault('scope', {})
    if scope.get('date_window', {}).get('requested') == requested:
        return
    today = _normalize_date('today') if 'today' in requested.values() else None
    bounds = {key: today if value == 'today' else value for key, value in requested.items()}
    rows = result['recent_sessions']
    selected = _rows_in_date_window(rows, bounds)
    result.update(recent_sessions=selected, session_count=len(selected))
    scope['date_window'] = {
        'requested': requested, **bounds, 'before': len(rows), 'selected': len(selected),
        'count_rule': 'Catalog metadata rows after the legacy query name filter, before canonical predicates/pages/display cuts; modified ISO strings compare lexically; until includes the whole day',
    }


def _rows_in_date_window(rows, bounds):
    if bounds['since']:
        rows = [row for row in rows if row.get('modified', '') >= bounds['since']]
    if bounds['until']:
        rows = [row for row in rows if row.get('modified', '') <= bounds['until'] + 'T23:59:59.999999']
    return rows


def _post_process_session_list(result: Dict[str, Any], args: Any, query_params: Dict[str, Any]) -> None:
    """Apply --name/--search, ?since=/?until= (--since/--until), --head/--all filters to
    claude_session_list results."""
    sessions = result.get('recent_sessions')
    if sessions is None:
        return
    total_before = len(sessions)

    search_term = getattr(args, 'name', None)
    if search_term:
        lower = search_term.lower()
        sessions = [s for s in sessions if lower in s.get('session', '').lower()]

    result['recent_sessions'] = sessions
    _select_session_dates(result, query_params)
    sessions = result['recent_sessions']

    result['session_count'] = len(sessions)  # of the filtered set (BACK-1549)
    if not getattr(args, 'all', False):
        head = getattr(args, 'head', None)
        sessions = sessions[:head if head else 20]

    result['recent_sessions'] = sessions
    note_truncation(result, 'recent_sessions', len(sessions), total_before, 'display-selection')
    result['displayed_count'] = len(sessions)

    _enrich_session_rows(result, args)


def _enrich_session_rows(result, args):
    """Optional row annotations shared by legacy and canonical display pages."""
    sessions = result.get('recent_sessions', [])
    for s in sessions:
        if 'title' not in s and s.get('path'):
            s['title'] = _read_session_title(Path(s['path']))

    if getattr(args, 'with_stats', False):
        result['with_stats'] = True
        sessions_with_paths = [s for s in sessions if s.get('path')]
        if sessions_with_paths:
            # main_thread_gc keeps cyclic collection on the main thread so a
            # worker can't finalize a lingering unsendable object off-thread.
            with main_thread_gc(), \
                    ThreadPoolExecutor(max_workers=min(8, len(sessions_with_paths))) as executor:
                future_to_session = {
                    executor.submit(_read_session_stats, Path(s['path'])): s
                    for s in sessions_with_paths
                }
                for future in as_completed(future_to_session):
                    future_to_session[future].update(future.result())


def _post_process_messages(result: Dict[str, Any], args: Any) -> None:
    """Apply --head/--tail/--range slicing to claude_messages results."""
    msgs = result.get('messages')
    if msgs is None:
        return
    total_before = len(msgs)
    msgs = _slice_list(msgs, args)
    result['messages'] = msgs
    note_truncation(result, 'messages', len(msgs), total_before, 'display-selection')
    result['total_turns'] = len(msgs)


def _post_process_message_range(result: Dict[str, Any], args: Any) -> None:
    """Apply --head/--tail/--range slicing to claude_message_range results."""
    msgs = result.get('messages')
    if msgs is None:
        return
    total_before = len(msgs)
    msgs = _slice_list(msgs, args)
    result['messages'] = msgs
    note_truncation(result, 'messages', len(msgs), total_before, 'display-selection')
    result['displayed'] = len(msgs)
    if len(msgs) < total_before:
        result['filtered_from'] = total_before
