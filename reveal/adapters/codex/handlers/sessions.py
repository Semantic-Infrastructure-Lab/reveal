"""Session list and search handlers for codex:// adapter (SQLite-backed)."""
from reveal.utils.path_utils import to_posix

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union
from reveal.reveal_types import CONTRACT_VERSION

from ....utils.match_terms import match_terms, term_echo
from ....utils.results import ResultBuilder, note_truncation
from ....utils.time_window import resolve_today
from ..analysis.normalize import normalize_record

from ..lookup import USER_FILTER as _USER_FILTER, connect_readonly
from ..catalog import CatalogRead
from ..content import scan_rollout, attach_content_evidence


def _apply_date_range(sessions: List[Dict[str, Any]], since: str, until: str) -> List[Dict[str, Any]]:
    """Filter a list of session dicts (with formatted ISO 'updated_at') by [since, until]."""
    if since:
        sessions = [s for s in sessions if (s.get('updated_at') or '') >= since]
    if until:
        sessions = [s for s in sessions if (s.get('updated_at') or '') <= until + 'T23:59:59Z']
    return sessions


def _connect(db_path: Path) -> sqlite3.Connection:
    return connect_readonly(db_path)


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return dict(row)


def _format_ts(unix_sec: Optional[int], on_failure=None) -> str:
    if unix_sec is None:
        return ''
    try:
        return datetime.utcfromtimestamp(unix_sec).strftime('%Y-%m-%dT%H:%M:%SZ')
    except (TypeError, ValueError, OverflowError, OSError) as exc:
        if on_failure is not None:
            on_failure(exc)
        return str(unix_sec)


def list_sessions(db_path: Path) -> Dict[str, Any]:
    """List all user-visible sessions from SQLite, newest first.

    Returns codex_session_list result.
    """
    base: Dict[str, Any] = ResultBuilder.create(
        result_type='codex_session_list',
        source=to_posix(db_path),
        source_type='database',
        contract_version=CONTRACT_VERSION,
    )

    acquisition = CatalogRead(db_path, _connect)
    acquisition.read()
    rows = acquisition.rows

    sessions = []
    for d in rows:
        sessions.append({
            'id': d['id'],
            'title': d.get('title', ''),
            'first_user_message': d.get('first_user_message', ''),
            'model': d.get('model'),
            'model_provider': d.get('model_provider'),
            'reasoning_effort': d.get('reasoning_effort'),
            'tokens_used': d.get('tokens_used'),
            'cwd': d.get('cwd'),
            'created_at': _format_ts(d.get('created_at'), lambda exc: acquisition.failure('created_at', exc)),
            'updated_at': _format_ts(d.get('updated_at'), lambda exc: acquisition.failure('updated_at', exc)),
            'cli_version': d.get('cli_version'),
            'git_branch': d.get('git_branch'),
            'approval_mode': d.get('approval_mode'),
        })

    return acquisition.attach({**base, 'sessions': sessions, 'total': len(sessions)})


def filter_sessions(db_path: Path, where: Sequence[str], since: str = '', until: str = '') -> Dict[str, Any]:
    """Filter sessions by ``session~=TEXT`` terms, ANDed: each a case-insensitive substring of the title or the first
    user message (SQLite metadata, no JSONL scan). Legacy ``?filter=TEXT`` is the one term ``session~=TEXT`` (ruling
    Q2). Optional ?since=/?until= (a time-window bound: a date, a time or "today") scope by updated_at — BACK-945.

    Returns codex_session_list result filtered to matches, echoing its ``where`` terms.
    """
    base_result = list_sessions(db_path)
    if 'error' in base_result:
        return base_result

    since = resolve_today(since)
    until = resolve_today(until)

    needles = [term.partition('~=')[2].lower() for term in where]
    filtered = [
        s for s in base_result.get('sessions', [])
        if all(needle in (s.get('title') or '').lower() or needle in (s.get('first_user_message') or '').lower()
               for needle in needles)
    ]
    filtered = _apply_date_range(filtered, since, until)
    base_result['sessions'] = filtered
    base_result['total'] = len(filtered)
    base_result['where'] = list(where)
    base_result['since'] = since or None
    base_result['until'] = until or None
    return base_result


def _record_snippet(rec, terms):
    rec = normalize_record(rec)  # current rollouts' item_completed turns (BACK-1566)
    payload = rec.get('payload')
    if not isinstance(payload, dict):
        return None
    ptype = payload.get('type', '')
    text = payload.get('message') or ''
    if ptype not in ('user_message', 'agent_message') or not isinstance(text, str):
        return None
    held = [term for term in terms if term in text.lower()]
    if not held:
        return None
    return {
        'role': 'user' if ptype == 'user_message' else 'agent',
        'timestamp': rec.get('timestamp'),
        'snippet': text[:200],
    }, held


def search_sessions(db_path: Path, query: Union[str, Sequence[str]], max_matches_per_session: int = 3,
                     since: str = '', until: str = '') -> Dict[str, Any]:
    """Full-text search across session JSONL content.

    Query param: ?search=<term> (renamed from ?content= — BACK-947 — to match
    claude://'s ?search= meaning full-text content search, not metadata filtering).
    Optional ?since=/?until= (a time-window bound) scope the corpus by updated_at
    before scanning JSONL — BACK-945.

    Scans agent_message and user_message payloads in each session's rollout file. *query* is the legacy search's
    string, echoed as given, or ``--match``'s terms, echoed as a list and ANDed per session: a session matches when
    every term is in one of its messages (COMMAND_MODEL "Conflicting values", rule 19), and each message holding any
    of them is a snippet. Returns matched sessions with up to max_matches_per_session snippets each
    (0 keeps every snippet); a cut is disclosed through note_truncation (BACK-1384).
    """
    since = resolve_today(since)
    until = resolve_today(until)

    base: Dict[str, Any] = ResultBuilder.create(
        result_type='codex_content_search',
        source=to_posix(db_path),
        source_type='database',
        contract_version=CONTRACT_VERSION,
        data={'query': query if isinstance(query, str) else term_echo(match_terms(query)),
              'since': since or None, 'until': until or None},
    )

    acquisition = CatalogRead(db_path, _connect, 'id, rollout_path, title, first_user_message, model, updated_at')
    acquisition.read()
    rows = []
    for raw in acquisition.rows:
        row = dict(raw)
        row['updated_at'] = _format_ts(raw.get('updated_at'), lambda exc: acquisition.failure('updated_at', exc))
        rows.append(row)
    rows = _apply_date_range(rows, since, until)

    terms = [term.lower() for term in match_terms(query)]
    matched: List[Dict[str, Any]] = []
    found_total = 0

    sources = []
    for d in rows:
        snippets, found, proof = scan_rollout(d, terms, max_matches_per_session, _record_snippet)
        sources.append(proof)
        if snippets:
            found_total += found
            matched.append({
                'id': d['id'], 'title': d.get('title', ''), 'updated_at': d['updated_at'],
                'model': d.get('model'), 'matches': snippets, 'match_count': len(snippets),
            })

    result = acquisition.attach({**base, 'sessions': matched, 'total': len(matched)})
    attach_content_evidence(result, sources)
    note_truncation(result, 'matches', sum(len(m['matches']) for m in matched), found_total,
                    'matches_per_session', hint='raise --matches N (0 keeps every match)')
    return result
