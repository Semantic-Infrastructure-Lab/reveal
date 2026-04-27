"""Session-level resource handlers for the claude:// adapter."""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, date as _date

from ..analysis import search_sessions_for_term, get_files_touched
from ....utils.parallel import grep_files as _grep_files

logger = logging.getLogger(__name__)

_BOILERPLATE_PREFIXES = ('# Session Continuation Context',)


def _extract_text_from_content(content: Any) -> str:
    """Extract plain text from a message content (str or list of content blocks)."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get('type') == 'text':
                return item.get('text', '').strip()
    return ''


def _parse_jsonl_line_for_title(line: str) -> Optional[str]:
    """Parse one JSONL line and return user text as a title candidate, or None.

    Returns None to signal "skip this line, keep scanning" for boilerplate messages.
    """
    try:
        rec = json.loads(line)
    except Exception:
        return None
    if rec.get('type') != 'user':
        return None
    content = rec.get('message', {}).get('content', '')
    text = _extract_text_from_content(content)
    if not text:
        return None
    candidate = text.split('\n')[0].strip()
    # Skip auto-injected boilerplate preambles; try to extract real user text after ---
    if any(candidate.startswith(p) for p in _BOILERPLATE_PREFIXES):
        sep_idx = text.rfind('\n---\n')
        if sep_idx >= 0:
            candidate = text[sep_idx + 5:].strip().split('\n')[0].strip()
        else:
            return None
    # Skip bare boot commands — the real task will be in a later message
    if candidate.lower() == 'boot':
        return None
    return candidate[:80] or None


def _scan_jsonl_for_title(jsonl_path: Path) -> Optional[str]:
    """Scan first 50 lines of JSONL file for a user text title."""
    with open(jsonl_path, 'r', errors='replace') as fh:
        for i, line in enumerate(fh):
            if i > 50:
                break
            title = _parse_jsonl_line_for_title(line)
            if title is not None:
                return title
    return None


def _read_session_title(jsonl_path: Path) -> Optional[str]:
    """Read first user text message from JSONL as a display title.

    Reads only the first 30 lines to avoid loading entire file.
    """
    try:
        return _scan_jsonl_for_title(jsonl_path)
    except Exception:
        return None


def _extract_project_from_dir(dir_name: str) -> str:
    """Derive a short project label from an encoded Claude project directory name.

    E.g. '-home-user-src-tia-sessions-hosefobe-0314' → 'tia'
         '-home-user-src-projects-reveal-external-git' → 'reveal'
    """
    _SKIP = {'home', 'src', 'projects', 'external', 'internal', 'git'}
    prefix = dir_name.split('-sessions-')[0] if '-sessions-' in dir_name else dir_name
    parts = [p for p in prefix.lstrip('-').split('-') if p and p not in _SKIP]
    return parts[-1] if parts else ''


def _collect_sessions_from_dir(project_dir: Path) -> List[Dict[str, Any]]:
    """Collect session entry dicts from one project directory."""
    sessions = []
    readme_present = bool(list(project_dir.glob('README*.md'))[:1])
    project = _extract_project_from_dir(project_dir.name)
    for jsonl_file in project_dir.glob('*.jsonl'):
        if jsonl_file.stem.startswith('agent-'):
            continue
        dir_name = project_dir.name
        file_stem = jsonl_file.stem
        if '-sessions-' in dir_name:
            session_name = dir_name.split('-sessions-')[-1]
        elif len(file_stem) == 36 and file_stem.count('-') == 4:
            # UUID filename (Windows-style) — use the UUID as the session name
            session_name = file_stem
        else:
            session_name = dir_name
        stat = jsonl_file.stat()
        sessions.append({
            'session': session_name,
            'path': str(jsonl_file),
            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'size_kb': stat.st_size // 1024,
            'readme_present': readme_present,
            'project': project,
        })
    return sessions


def _find_session_readme(session_name: str, sessions_dir: Optional[Path]) -> Optional[Path]:
    """Find the most recent README for a session in the sessions directory."""
    if not sessions_dir or not sessions_dir.exists():
        return None
    session_dir = sessions_dir / session_name
    if not session_dir.exists():
        return None
    readmes = sorted(session_dir.glob('README*.md'), reverse=True)
    return readmes[0] if readmes else None


def _parse_readme_frontmatter(readme_path: Path) -> Dict[str, Any]:
    """Parse YAML frontmatter from a README file."""
    import yaml
    try:
        text = readme_path.read_text(encoding='utf-8')
        if text.startswith('---'):
            end = text.find('\n---', 3)
            if end != -1:
                frontmatter_text = text[3:end].strip()
                return yaml.safe_load(frontmatter_text) or {}
    except Exception:  # noqa: BLE001 — README may be absent, unreadable, or malformed
        pass
    return {}


def list_sessions(conversation_base: Path, query_params: Dict[str, Any]) -> Dict[str, Any]:
    """List available Claude Code sessions.

    Supports query params:
        ?filter=term  - filter session names by substring (case-insensitive)
        ?search=term  - alias for ?filter=term

    CLI flags (applied by routing.py):
        --head N      - show N most recent (default: 20)
        --all         - show all sessions
        --since DATE  - filter by modified date (e.g. 2026-02-27)
        --search TERM - filter session names (overrides ?filter=)

    Returns:
        Dictionary with full session list (routing.py applies display limits)
    """
    base: Dict[str, Any] = {
        'contract_version': '1.0',
        'type': 'claude_session_list',
        'source': str(conversation_base),
        'source_type': 'directory',
    }

    name_filter = (query_params.get('filter') or query_params.get('search', '')).lower()

    sessions = []
    try:
        for project_dir in conversation_base.iterdir():
            if not project_dir.is_dir():
                continue
            sessions.extend(_collect_sessions_from_dir(project_dir))
        sessions.sort(key=lambda x: x['modified'], reverse=True)  # type: ignore[arg-type, return-value]
    except Exception as e:
        base['error'] = str(e)

    if name_filter:
        sessions = [s for s in sessions if name_filter in str(s['session']).lower()]

    base.update({
        'session_count': len(sessions),
        'recent_sessions': sessions,  # routing.py applies head/since limits
        'usage': {
            'overview': 'reveal claude://session/<name>',
            'workflow': 'reveal claude://session/<name>/workflow',
            'files': 'reveal claude://session/<name>/files',
            'tools': 'reveal claude://session/<name>/tools',
            'errors': 'reveal claude://session/<name>?errors',
            'context': 'reveal claude://session/<name>/context',
            'specific_tool': 'reveal claude://session/<name>?tools=Bash',
            'composite': 'reveal claude://session/<name>?tools=Bash&errors',
            'thinking': 'reveal claude://session/<name>/thinking',
            'message': 'reveal claude://session/<name>/message/42',
        }
    })

    return base


def search_sessions(conversation_base: Path, query_params: Dict[str, Any]) -> Dict[str, Any]:
    """Cross-session content search using ``?search=term``.

    Supports ``?since=DATE`` to scope the corpus before scanning.

    Returns:
        Dict of type ``claude_cross_session_search`` with ``matches`` list.
    """
    term = query_params.get('search', '')
    since = query_params.get('since', '')

    if since == 'today':
        since = _date.today().isoformat()

    all_sessions: List[Dict[str, Any]] = []
    try:
        for project_dir in conversation_base.iterdir():
            if project_dir.is_dir():
                all_sessions.extend(_collect_sessions_from_dir(project_dir))
    except Exception as e:
        return {
            'contract_version': '1.0',
            'type': 'claude_cross_session_search',
            'source': str(conversation_base),
            'source_type': 'directory',
            'term': term,
            'error': str(e),
            'sessions_scanned': 0,
            'match_count': 0,
            'matches': [],
        }

    if since:
        all_sessions = [s for s in all_sessions if s.get('modified', '') >= since]

    whole_word = 'word' in query_params
    matches = search_sessions_for_term(all_sessions, term, whole_word=whole_word)

    return {
        'contract_version': '1.0',
        'type': 'claude_cross_session_search',
        'source': str(conversation_base),
        'source_type': 'directory',
        'term': term,
        'since': since or None,
        'whole_word': whole_word,
        'sessions_scanned': len(all_sessions),
        'match_count': len(matches),
        'matches': matches,
    }


def track_file_sessions(conversation_base: Path, resource: str, query_params: Dict[str, Any]) -> Dict[str, Any]:
    """Cross-session file tracking using ``claude://files/<path>``.

    Finds all sessions that touched a given file path using parallel
    byte-level pre-filtering, then extracts per-session operations.

    Supports ``?since=DATE`` to scope the corpus before scanning.

    Returns:
        Dict of type ``claude_file_sessions`` with ``sessions`` list.
    """
    file_path = resource[len('files/'):].strip('/')
    since = query_params.get('since', '')

    if since == 'today':
        since = _date.today().isoformat()

    _error_base: Dict[str, Any] = {
        'contract_version': '1.0',
        'type': 'claude_file_sessions',
        'source': str(conversation_base),
        'source_type': 'directory',
        'file_path': file_path,
        'since': since or None,
        'sessions_scanned': 0,
        'match_count': 0,
        'sessions': [],
    }

    if not file_path:
        return {**_error_base, 'error': 'No file path provided. Usage: claude://files/path/to/file.py'}

    all_sessions: List[Dict[str, Any]] = []
    try:
        for project_dir in conversation_base.iterdir():
            if project_dir.is_dir():
                all_sessions.extend(_collect_sessions_from_dir(project_dir))
    except Exception as e:
        return {**_error_base, 'error': str(e)}

    if since:
        all_sessions = [s for s in all_sessions if s.get('modified', '') >= since]

    # Parallel byte-scan pre-filter.
    matched_paths = _grep_files([Path(s['path']) for s in all_sessions], [file_path])
    matched_path_strs = {str(p) for p in matched_paths}
    candidates = [s for s in all_sessions if s['path'] in matched_path_strs]

    results = []
    for session in candidates:
        try:
            messages: List[Dict] = []
            with open(session['path'], 'r', encoding='utf-8') as fh:
                for line in fh:
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            contract_base = {
                'contract_version': '1.0',
                'source': session['path'],
                'source_type': 'file',
            }
            files_result = get_files_touched(messages, session['session'], contract_base)

            # Partial path match across all ops.
            ops_for_file: Dict[str, int] = {}
            for op, files_dict in files_result.get('by_operation', {}).items():
                count = sum(v for k, v in files_dict.items() if file_path in k)
                if count:
                    ops_for_file[op] = count

            if ops_for_file:
                results.append({
                    'session': session['session'],
                    'project': session.get('project', ''),
                    'modified': session['modified'],
                    'ops': ops_for_file,
                    'total_ops': sum(ops_for_file.values()),
                })
        except Exception as e:
            logger.debug("session parse failed for %s: %s", session.get('path'), e)
            continue

    results.sort(key=lambda x: x['modified'], reverse=True)

    return {
        'contract_version': '1.0',
        'type': 'claude_file_sessions',
        'source': str(conversation_base),
        'source_type': 'directory',
        'file_path': file_path,
        'since': since or None,
        'sessions_scanned': len(all_sessions),
        'match_count': len(results),
        'sessions': results,
    }


def get_chain(
    resource: str,
    session_name: str,
    sessions_dir: Optional[Path],
    contract_base: Dict[str, Any],
) -> Dict[str, Any]:
    """Traverse session continuation chain via README continuing_from: links.

    Reads REVEAL_SESSIONS_DIR/<session>/README*.md for each session,
    extracts YAML frontmatter, and follows continuing_from: until the
    chain ends or a cycle is detected (limit: 50 sessions).

    Returns:
        Output Contract v1.0 dict with type 'claude_chain' and chain list
    """
    chain: List[Dict[str, Any]] = []
    seen: set = set()
    current_name: Optional[str] = session_name

    while current_name and current_name not in seen and len(chain) < 50:
        seen.add(current_name)
        readme_path = _find_session_readme(current_name, sessions_dir)
        frontmatter = _parse_readme_frontmatter(readme_path) if readme_path else {}

        entry: Dict[str, Any] = {
            'session': current_name,
            'readme': str(readme_path) if readme_path else None,
            'date': frontmatter.get('date') or frontmatter.get('session_date'),
            'badge': frontmatter.get('badge'),
            'continuing_from': frontmatter.get('continuing_from'),
            'tests_start': frontmatter.get('tests_start'),
            'tests_end': frontmatter.get('tests_end'),
            'commits': frontmatter.get('commits'),
        }
        chain.append(entry)
        current_name = frontmatter.get('continuing_from')

    return {
        **contract_base,
        'type': 'claude_chain',
        'session': session_name,
        'chain': chain,
        'chain_length': len(chain),
        'sessions_dir': str(sessions_dir) if sessions_dir else None,
    }
