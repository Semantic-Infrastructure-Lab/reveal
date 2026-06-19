"""Post-processing helpers for claude:// adapter result types."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Dict, Any, List

from .sessions import _read_session_title, _read_session_stats
from ....utils.threadsafe import main_thread_gc


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


def _post_process_workflow(result: Dict[str, Any], args: Any) -> None:
    """Apply --type, --search, and --head/--tail/--range to claude_workflow results."""
    workflow = result.get('workflow')
    if workflow is None:
        return
    total_before = len(workflow)

    type_filter = getattr(args, 'type', None)
    if type_filter:
        workflow = [s for s in workflow if (s.get('tool') or '').lower() == type_filter.lower()]

    search_term = getattr(args, 'name', None)
    if search_term:
        lower = search_term.lower()
        workflow = [
            s for s in workflow
            if lower in (s.get('detail') or '').lower()
            or lower in (s.get('tool') or '').lower()
        ]

    workflow = _slice_list(workflow, args)
    result['workflow'] = workflow
    result['displayed_steps'] = len(workflow)
    if len(workflow) < total_before:
        result['filtered_from'] = total_before


def _post_process_search_results(result: Dict[str, Any], args: Any) -> None:
    """Apply --head/--all display limits to claude_cross_session_search results."""
    matches = result.get('matches')
    if matches is None:
        return
    if not getattr(args, 'all', False):
        head = getattr(args, 'head', None)
        matches = matches[:head if head else 20]
    result['matches'] = matches
    result['displayed_count'] = len(matches)


def _post_process_history(result: Dict[str, Any], args: Any) -> None:
    """Apply --name/--search, --since, --head/--all filters to claude_history results."""
    entries = result.get('entries')
    if entries is None:
        return

    search_term = getattr(args, 'name', None)
    if search_term:
        lower = search_term.lower()
        entries = [e for e in entries if lower in e.get('prompt', '').lower()]

    since = getattr(args, 'since', None)
    if since:
        if since == 'today':
            since = date.today().isoformat()
        entries = [e for e in entries if e.get('timestamp', '') >= since]

    if not getattr(args, 'all', False):
        head = getattr(args, 'head', None)
        entries = entries[:head if head else 50]

    result['entries'] = entries
    result['displayed_count'] = len(entries)


def _normalize_date(val: str) -> str:
    return date.today().isoformat() if val == 'today' else val


def _post_process_session_list(result: Dict[str, Any], args: Any) -> None:
    """Apply --name/--search, --since, --head/--all filters to claude_session_list results."""
    sessions = result.get('recent_sessions')
    if sessions is None:
        return

    search_term = getattr(args, 'name', None)
    if search_term:
        lower = search_term.lower()
        sessions = [s for s in sessions if lower in s.get('session', '').lower()]

    since = getattr(args, 'since', None)
    if since:
        since = _normalize_date(since)
        sessions = [s for s in sessions if s.get('modified', '') >= since]

    until = getattr(args, 'until', None)
    if until:
        until = _normalize_date(until)
        sessions = [s for s in sessions if s.get('modified', '') <= until + 'T23:59:59.999999']

    if not getattr(args, 'all', False):
        head = getattr(args, 'head', None)
        sessions = sessions[:head if head else 20]

    result['recent_sessions'] = sessions
    result['displayed_count'] = len(sessions)

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
    msgs = _slice_list(msgs, args)
    result['messages'] = msgs
    result['total_turns'] = len(msgs)


def _post_process_message_range(result: Dict[str, Any], args: Any) -> None:
    """Apply --head/--tail/--range slicing to claude_message_range results."""
    msgs = result.get('messages')
    if msgs is None:
        return
    total_before = len(msgs)
    msgs = _slice_list(msgs, args)
    result['messages'] = msgs
    result['displayed'] = len(msgs)
    if len(msgs) < total_before:
        result['filtered_from'] = total_before
