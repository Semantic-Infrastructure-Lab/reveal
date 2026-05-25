"""Session list and search handlers for codex:// adapter (SQLite-backed)."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_USER_FILTER = "(thread_source IS NULL OR thread_source = 'user') AND archived = 0"


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
    except Exception:
        return str(unix_sec)


def list_sessions(db_path: Path) -> Dict[str, Any]:
    """List all user-visible sessions from SQLite, newest first.

    Returns codex_session_list result.
    """
    base: Dict[str, Any] = {
        'contract_version': '1.0',
        'type': 'codex_session_list',
        'source': str(db_path),
        'source_type': 'sqlite',
    }

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


def search_sessions(db_path: Path, search: str) -> Dict[str, Any]:
    """Search sessions by title / first_user_message substring.

    Returns codex_session_list result filtered to matches.
    """
    base_result = list_sessions(db_path)
    if 'error' in base_result:
        return base_result

    term = search.lower()
    filtered = [
        s for s in base_result.get('sessions', [])
        if term in (s.get('title') or '').lower()
        or term in (s.get('first_user_message') or '').lower()
    ]
    base_result['sessions'] = filtered
    base_result['total'] = len(filtered)
    base_result['search'] = search
    return base_result


def content_search_sessions(db_path: Path, query: str, max_matches_per_session: int = 3) -> Dict[str, Any]:
    """Search session JSONL files for a text query.

    Scans agent_message and user_message payloads in each session's rollout file.
    Returns matched sessions with up to max_matches_per_session snippets each.
    """
    base: Dict[str, Any] = {
        'contract_version': '1.0',
        'type': 'codex_content_search',
        'source': str(db_path),
        'source_type': 'sqlite',
        'query': query,
    }

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

    term = query.lower()
    matched: List[Dict[str, Any]] = []

    for row in rows:
        d = _row_to_dict(row)
        rollout = Path(d.get('rollout_path', ''))
        if not rollout.exists():
            continue
        try:
            content = rollout.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue

        if term not in content.lower():
            continue

        # Parse lines and collect matching message snippets
        snippets: List[Dict[str, Any]] = []
        for line in content.splitlines():
            if len(snippets) >= max_matches_per_session:
                break
            if term not in line.lower():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ptype = rec.get('payload', {}).get('type', '')
            if ptype not in ('user_message', 'agent_message'):
                continue
            text = rec.get('payload', {}).get('message', '')
            if term not in (text or '').lower():
                continue
            snippets.append({
                'role': 'user' if ptype == 'user_message' else 'agent',
                'timestamp': rec.get('timestamp'),
                'snippet': text[:200],
            })

        matched.append({
            'id': d['id'],
            'title': d.get('title', ''),
            'updated_at': _format_ts(d.get('updated_at')),
            'model': d.get('model'),
            'matches': snippets,
            'match_count': len(snippets),
        })

    return {**base, 'sessions': matched, 'total': len(matched)}
