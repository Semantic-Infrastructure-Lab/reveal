"""Cross-session content search for the claude:// adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .messages import _content_to_blocks, _collect_block_matches, _find_excerpt, _matches_term


def _snippet_timestamp(record: Dict[str, Any]) -> str:
    value = record.get('timestamp')
    return value[:16].replace('T', ' ') if isinstance(value, str) else ''


def _extract_first_snippet(jsonl_path: Path, term: str, *, whole_word: bool = False,
                           window_chars: int = 120,
                           errors_out: List[Tuple[Path, BaseException]] | None = None) -> Dict[str, Any]:
    """Scan a JSONL file line-by-line and return the first matching excerpt.

    Parses every valid JSON line to maintain an accurate ``message_index`` that
    matches what ``reveal claude://session/NAME/message/N`` expects.  Returns a
    dict with ``excerpt``, ``role``, ``timestamp``, and ``message_index``.
    Falls back to empty strings / ``None`` when the file can't be read, so a
    missing snippet never breaks the search result; malformed lines are skipped.

    Args:
        jsonl_path: Path to the session ``.jsonl`` file.
        term: Search term (case-insensitive).
        whole_word: If True, only match whole words (word-boundary semantics).
        window_chars: Characters of context around the match (default 120).

    Returns:
        Dict with keys ``excerpt``, ``role``, ``timestamp``, ``message_index``.
        ``message_index`` is ``None`` when no match is found.
    """
    lower = term.lower()
    message_index = 0
    fallback: Dict[str, Any] | None = None
    try:
        with open(jsonl_path, encoding='utf-8', errors='replace') as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(msg, dict):
                    continue
                role = msg.get('type', '')
                message = msg.get('message')
                if fallback is None:
                    fallback = _sidecar_hit(msg, role, term, message_index, whole_word, window_chars)
                if role in ('user', 'assistant') and isinstance(message, dict):
                    content = message.get('content', [])
                    blocks = _content_to_blocks(content)
                    ts = _snippet_timestamp(msg)
                    matches = _collect_block_matches(blocks, lower, term, message_index, role, ts,
                                                    whole_word=whole_word, window_chars=window_chars)
                    if matches:
                        return {
                            'excerpt': matches[0].get('excerpt', ''),
                            'role': role,
                            'timestamp': ts,
                            'message_index': message_index,
                        }
                message_index += 1
    except OSError as exc:
        if errors_out is not None:
            errors_out.append((jsonl_path, exc))
    return fallback or {'excerpt': '', 'role': '', 'timestamp': '', 'message_index': None}


def _sidecar_hit(msg: Dict[str, Any], role: str, term: str, message_index: int,
                 whole_word: bool, window_chars: int) -> Dict[str, Any] | None:
    """Excerpt for a record whose match sits outside ``message.content`` (BACK-2088).

    The phase-1 byte filter matches anywhere in the file, e.g. the top-level
    ``toolUseResult`` sidecar, while the content-block matcher only sees
    ``message.content``. Without this the session is listed with no snippet.
    """
    sidecar = msg.get('toolUseResult')
    if sidecar is None:
        return None
    text = sidecar if isinstance(sidecar, str) else json.dumps(sidecar, ensure_ascii=False)
    if not _matches_term(text, term.lower(), whole_word):
        return None
    ts = _snippet_timestamp(msg)
    return {
        'excerpt': '[toolUseResult] ' + _find_excerpt(text, term, window=window_chars, whole_word=whole_word),
        'role': role,
        'timestamp': ts,
        'message_index': message_index,
    }


def search_sessions_for_term(
    sessions: List[Dict[str, Any]],
    term: str,
    *,
    workers: int = 8,
    whole_word: bool = False,
    window_chars: int = 120,
    lost_out: List[Path] | None = None,
    errors_out: List[Tuple[Path, BaseException]] | None = None,
) -> List[Dict[str, Any]]:
    """Search across multiple sessions for a term and return one snippet per match.

    Each session's existing JSONL reader matches decoded content and extracts one
    representative snippet. Raw JSON spelling cannot establish that content is absent.

    Args:
        sessions: List of session dicts (each must have ``path``, ``session``,
            ``modified``, ``project``).  Produced by
            ``_collect_sessions_from_dir``.
        term: Search term (case-insensitive substring match).
        workers: Compatibility argument for the former byte prefilter.
        whole_word: If True, only return sessions where the term appears as a
            whole word (word-boundary semantics).  Phase 1 grep is still
            substring for speed; whole-word filtering happens in phase 2.
        lost_out: Compatibility argument for the former byte pool; no workers are used.
        errors_out: When given, receives sessions whose required read failed.

    Returns:
        List of match dicts, sorted most-recent-first, each containing:
        ``session``, ``modified``, ``project``, ``size_kb``,
        ``readme_present``, ``excerpt``, ``role``, ``timestamp``,
        ``message_index`` (0-based index for ``claude://session/NAME/message/N``).
    """
    if not sessions or not term:
        return []

    # Build a path → session-dict index for quick lookup after grep.
    path_to_session: Dict[Path, Dict[str, Any]] = {
        Path(s['path']): s for s in sessions if s.get('path')
    }
    all_paths = list(path_to_session)

    results = []
    for path in all_paths:
        session = path_to_session[path]
        snippet = _extract_first_snippet(path, term, whole_word=whole_word,
                                         window_chars=window_chars, errors_out=errors_out)
        if snippet['message_index'] is None:
            continue
        results.append({
            'session':       session['session'],
            'modified':      session['modified'],
            'project':       session.get('project', ''),
            'size_kb':       session.get('size_kb', 0),
            'excerpt':       snippet['excerpt'],
            'role':          snippet['role'],
            'timestamp':     snippet['timestamp'],
            'message_index': snippet.get('message_index'),
        })
        if session.get('readme_present'):
            results[-1]['readme_present'] = True

    results.sort(key=lambda x: x['modified'], reverse=True)
    return results
