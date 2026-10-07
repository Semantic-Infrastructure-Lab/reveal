"""Session list and search handlers for codex:// adapter (SQLite-backed)."""

import json
import sqlite3
from datetime import date as _date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from reveal.reveal_types import CONTRACT_VERSION

from ....utils.results import ResultBuilder, note_truncation
from ..analysis.normalize import normalize_record
from reveal.utils.lines import split_lines

_USER_FILTER = "(thread_source IS NULL OR thread_source = 'user') AND archived = 0"


def _resolve_date_bound(value: str) -> str:
    """Resolve 'today' to an ISO date; pass through anything else unchanged."""
    return _date.today().isoformat() if value == 'today' else value


def _apply_date_range(sessions: List[Dict[str, Any]], since: str, until: str) -> List[Dict[str, Any]]:
    """Filter a list of session dicts (with formatted ISO 'updated_at') by [since, until]."""
    if since:
        sessions = [s for s in sessions if (s.get('updated_at') or '') >= since]
    if until:
        sessions = [s for s in sessions if (s.get('updated_at') or '') <= until + 'T23:59:59Z']
    return sessions


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return dict(row)


def _format_ts(unix_sec: Optional[int]) -> str:
    if unix_sec is None:
        return ''
    try:
        return datetime.utcfromtimestamp(unix_sec).strftime('%Y-%m-%dT%H:%M:%SZ')
    except (ValueError, OverflowError, OSError):
        return str(unix_sec)


def list_sessions(db_path: Path) -> Dict[str, Any]:
    """List all user-visible sessions from SQLite, newest first.

    Returns codex_session_list result.
    """
    base: Dict[str, Any] = ResultBuilder.create(
        result_type='codex_session_list',
        source=str(db_path),
        source_type='database',
        contract_version=CONTRACT_VERSION,
    )

    if not db_path.exists():
        return {**base, 'sessions': [], 'total': 0,
                'error': f'Codex DB not found: {db_path}'}

    try:
        conn = _connect(db_path)
        try:
            rows = conn.execute(
                f"SELECT id, title, first_user_message, model, model_provider, "
                f"reasoning_effort, tokens_used, cwd, created_at, updated_at, "
                f"cli_version, git_branch, approval_mode "
                f"FROM threads WHERE {_USER_FILTER} "
                f"ORDER BY updated_at DESC"
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return {**base, 'sessions': [], 'total': 0, 'error': str(exc)}

    sessions = []
    for row in rows:
        d = _row_to_dict(row)
        sessions.append({
            'id': d['id'],
            'title': d.get('title', ''),
            'first_user_message': d.get('first_user_message', ''),
            'model': d.get('model'),
            'model_provider': d.get('model_provider'),
            'reasoning_effort': d.get('reasoning_effort'),
            'tokens_used': d.get('tokens_used'),
            'cwd': d.get('cwd'),
            'created_at': _format_ts(d.get('created_at')),
            'updated_at': _format_ts(d.get('updated_at')),
            'cli_version': d.get('cli_version'),
            'git_branch': d.get('git_branch'),
            'approval_mode': d.get('approval_mode'),
        })

    return {**base, 'sessions': sessions, 'total': len(sessions)}


def filter_sessions(db_path: Path, filter_term: str, since: str = '', until: str = '') -> Dict[str, Any]:
    """Filter sessions by title / first_user_message substring (SQLite metadata, no JSONL scan).

    Returns codex_session_list result filtered to matches. Query param: ?filter=<term>
    (renamed from ?search= — BACK-947 — to match claude://'s filter/search split).
    Optional ?since=/?until= (ISO date or "today") scope by updated_at — BACK-945.
    """
    base_result = list_sessions(db_path)
    if 'error' in base_result:
        return base_result

    since = _resolve_date_bound(since)
    until = _resolve_date_bound(until)

    term = filter_term.lower()
    filtered = [
        s for s in base_result.get('sessions', [])
        if term in (s.get('title') or '').lower()
        or term in (s.get('first_user_message') or '').lower()
    ]
    filtered = _apply_date_range(filtered, since, until)
    base_result['sessions'] = filtered
    base_result['total'] = len(filtered)
    base_result['filter'] = filter_term
    base_result['since'] = since or None
    base_result['until'] = until or None
    return base_result


def _message_snippet(line: str, term: str) -> Optional[Dict[str, Any]]:
    """The user/agent message on one rollout line, if it contains *term*."""
    try:
        rec = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(rec, dict):
        return None
    rec = normalize_record(rec)  # current rollouts' item_completed turns (BACK-1566)
    payload = rec.get('payload') or {}
    ptype = payload.get('type', '')
    text = payload.get('message') or ''
    if ptype not in ('user_message', 'agent_message') or term not in text.lower():
        return None
    return {
        'role': 'user' if ptype == 'user_message' else 'agent',
        'timestamp': rec.get('timestamp'),
        'snippet': text[:200],
    }


def _collect_snippets(content: str, raw_forms: set, term: str, cap: int) -> tuple:
    """(kept snippets, every match found) in one rollout; cap <= 0 keeps them all."""
    snippets: List[Dict[str, Any]] = []
    found = 0
    for line in split_lines(content):
        line_lower = line.lower()
        if not any(form in line_lower for form in raw_forms):
            continue
        snippet = _message_snippet(line, term)
        if snippet:
            found += 1
            if cap <= 0 or len(snippets) < cap:
                snippets.append(snippet)
    return snippets, found


def search_sessions(db_path: Path, query: str, max_matches_per_session: int = 3,
                     since: str = '', until: str = '') -> Dict[str, Any]:
    """Full-text search across session JSONL content.

    Query param: ?search=<term> (renamed from ?content= — BACK-947 — to match
    claude://'s ?search= meaning full-text content search, not metadata filtering).
    Optional ?since=/?until= (ISO date or "today") scope the corpus by updated_at
    before scanning JSONL — BACK-945.

    Scans agent_message and user_message payloads in each session's rollout file.
    Returns matched sessions with up to max_matches_per_session snippets each
    (0 keeps every snippet); a cut is disclosed through note_truncation (BACK-1384).
    """
    since = _resolve_date_bound(since)
    until = _resolve_date_bound(until)

    base: Dict[str, Any] = ResultBuilder.create(
        result_type='codex_content_search',
        source=str(db_path),
        source_type='database',
        contract_version=CONTRACT_VERSION,
        data={'query': query, 'since': since or None, 'until': until or None},
    )

    if not db_path.exists():
        return {**base, 'sessions': [], 'total': 0,
                'error': f'Codex DB not found: {db_path}'}

    try:
        conn = _connect(db_path)
        try:
            rows = conn.execute(
                f"SELECT id, rollout_path, title, first_user_message, model, updated_at "
                f"FROM threads WHERE {_USER_FILTER} ORDER BY updated_at DESC"
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return {**base, 'sessions': [], 'total': 0, 'error': str(exc)}

    if since or until:
        rows = [
            row for row in rows
            if _apply_date_range([{'updated_at': _format_ts(row['updated_at'])}], since, until)
        ]

    term = query.lower()
    # The prefilters read raw JSON lines, where a quote, backslash or (in some rollouts)
    # non-ASCII character is escaped: 'awkwardly" name' is stored as 'awkwardly\\" name', so
    # matching the plain term alone found 0 of 1 sessions. _message_snippet then matches the
    # decoded text, so an encoded form only widens the prefilter.
    raw_forms = {term, json.dumps(term, ensure_ascii=False)[1:-1], json.dumps(term)[1:-1]}
    matched: List[Dict[str, Any]] = []
    found_total = 0

    for row in rows:
        d = _row_to_dict(row)
        rollout_raw = d.get('rollout_path')
        if not rollout_raw:
            continue
        rollout = Path(rollout_raw)
        if not rollout.exists():
            continue
        try:
            content = rollout.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue

        lowered = content.lower()
        if not any(form in lowered for form in raw_forms):
            continue

        snippets, found = _collect_snippets(content, raw_forms, term, max_matches_per_session)

        if snippets:
            found_total += found
            matched.append({
                'id': d['id'],
                'title': d.get('title', ''),
                'updated_at': _format_ts(d.get('updated_at')),
                'model': d.get('model'),
                'matches': snippets,
                'match_count': len(snippets),
            })

    result = {**base, 'sessions': matched, 'total': len(matched)}
    note_truncation(result, 'matches', sum(len(m['matches']) for m in matched), found_total,
                    'matches_per_session', hint='raise ?matches=N (0 keeps every match)')
    return result
