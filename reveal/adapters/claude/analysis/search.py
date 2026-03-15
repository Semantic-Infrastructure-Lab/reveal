"""Cross-session content search for the claude:// adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ....utils.parallel import grep_files
from .messages import _find_excerpt, _content_to_blocks, _collect_block_matches


def _extract_first_snippet(jsonl_path: Path, term: str) -> Dict[str, str]:
    """Scan a JSONL file line-by-line and return the first matching excerpt.

    Parses only lines that contain the term bytes — skips all others.  Returns
    a dict with ``excerpt``, ``role``, and ``timestamp``.  Falls back to empty
    strings on any error so a missing snippet never breaks the search result.

    Args:
        jsonl_path: Path to the session ``.jsonl`` file.
        term: Search term (case-insensitive).

    Returns:
        Dict with keys ``excerpt``, ``role``, ``timestamp``.
    """
    lower = term.lower()
    try:
        with open(jsonl_path, encoding='utf-8', errors='replace') as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or lower not in line.lower():
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                role = msg.get('type', '')
                if role not in ('user', 'assistant'):
                    continue
                content = msg.get('message', {}).get('content', [])
                blocks = _content_to_blocks(content)
                ts = (msg.get('timestamp') or '')[:16].replace('T', ' ')
                matches = _collect_block_matches(blocks, lower, term, 0, role, ts)
                if matches:
                    return {
                        'excerpt': matches[0].get('excerpt', ''),
                        'role': role,
                        'timestamp': ts,
                    }
    except Exception:
        pass
    return {'excerpt': '', 'role': '', 'timestamp': ''}


def search_sessions_for_term(
    sessions: List[Dict[str, Any]],
    term: str,
    *,
    workers: int = 8,
) -> List[Dict[str, Any]]:
    """Search across multiple sessions for a term and return one snippet per match.

    Uses a two-phase approach:

    * **Phase 1** — ``grep_files()`` runs a parallel byte-level pre-filter
      across all JSONL files.  Only sessions whose file contains the term bytes
      proceed to phase 2.

    * **Phase 2** — parse only the matching files line-by-line to extract one
      representative snippet per session.

    Args:
        sessions: List of session dicts (each must have ``path``, ``session``,
            ``modified``, ``project``).  Produced by
            ``_collect_sessions_from_dir``.
        term: Search term (case-insensitive substring match).
        workers: Parallel workers for phase 1.  Defaults to 8.

    Returns:
        List of match dicts, sorted most-recent-first, each containing:
        ``session``, ``modified``, ``project``, ``size_kb``,
        ``readme_present``, ``excerpt``, ``role``, ``timestamp``.
    """
    if not sessions or not term:
        return []

    # Build a path → session-dict index for quick lookup after grep.
    path_to_session: Dict[Path, Dict[str, Any]] = {
        Path(s['path']): s for s in sessions if s.get('path')
    }
    all_paths = list(path_to_session)

    # Phase 1: parallel byte-level pre-filter.
    matching_paths = grep_files(all_paths, term, workers=workers)

    # Phase 2: extract one snippet per matching session.
    results = []
    for path in matching_paths:
        session = path_to_session[path]
        snippet = _extract_first_snippet(path, term)
        results.append({
            'session':       session['session'],
            'modified':      session['modified'],
            'project':       session.get('project', ''),
            'size_kb':       session.get('size_kb', 0),
            'readme_present': session.get('readme_present', False),
            'excerpt':       snippet['excerpt'],
            'role':          snippet['role'],
            'timestamp':     snippet['timestamp'],
        })

    results.sort(key=lambda x: x['modified'], reverse=True)
    return results
