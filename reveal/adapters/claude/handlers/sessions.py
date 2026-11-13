"""Session-level resource handlers for the claude:// adapter."""
import json
import logging
import re
import stat as stat_module
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, date as _date
from reveal.reveal_types import CONTRACT_VERSION
from reveal.utils.lines import split_lines
from reveal.utils.path_utils import to_posix

from ..analysis import search_sessions_for_term, get_files_touched
from ....utils.results import ResultBuilder, note_warning
from .workspace import skipped_entries_warning
from ..catalog import SessionEntries, collect_session_entries, attach_catalog_evidence
from ..discovery import directory_entries
from ..content import ContentScans
from ..analysis.records import TranscriptRecords
from ....errors import RequestValidationError

logger = logging.getLogger(__name__)

_BOILERPLATE_PREFIXES = ('# Session Continuation Context',)
_BADGE_RE = re.compile(r'session badge\s+"([^"]+)"')

# Scanning the projects directory fails in these ways: it or a session file is gone or
# unreadable (OSError), or a file's mtime is not a representable date (ValueError,
# OverflowError from datetime.fromtimestamp). Anything else is a bug.
_SCAN_ERRORS = (OSError, ValueError, OverflowError)


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
    except ValueError:
        # Malformed/truncated JSONL line — skip it, keep scanning for a title.
        return None
    if not isinstance(rec, dict) or rec.get('type') != 'user':
        return None
    message = rec.get('message')
    content = message.get('content', '') if isinstance(message, dict) else ''
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
    # Skip very short single-word responses (e.g. "aye") — not meaningful titles
    if len(candidate) < 5:
        return None
    # Skip harness-injected XML tags (<local-command-caveat>, <command-name>, <bash-input>, etc.)
    if re.match(r'^<[a-z]', candidate):
        return None
    return candidate[:80] or None


def _scan_jsonl_for_title(jsonl_path: Path) -> Optional[str]:
    """Scan first 50 lines of JSONL for a display title.

    Priority: session badge (from assistant Bash calls) > first adequate user text.
    """
    text_fallback: Optional[str] = None
    try:
        with open(jsonl_path, 'r', errors='replace', encoding='utf-8') as fh:
            for i, line in enumerate(fh):
                if i > 50:
                    break
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue  # malformed/truncated JSONL line — skip, keep scanning
                if not isinstance(rec, dict):
                    continue
                rec_type = rec.get('type')
                message = rec.get('message')
                if rec_type == 'assistant' and isinstance(message, dict):
                    for block in message.get('content') or []:
                        if isinstance(block, dict) and block.get('type') == 'tool_use' and block.get('name') == 'Bash':
                            command = (block.get('input') or {}).get('command')
                            m = _BADGE_RE.search(command) if isinstance(command, str) else None
                            if m:
                                return m.group(1)
                elif rec_type == 'user' and text_fallback is None:
                    title = _parse_jsonl_line_for_title(line)
                    if title is not None:
                        text_fallback = title
    except OSError:
        # Session file may be missing or unreadable (non-UTF8 bytes are replaced,
        # malformed lines skipped above) — best-effort title lookup.
        pass
    return text_fallback


def _read_session_title(jsonl_path: Path) -> Optional[str]:
    """Read first user text message from JSONL as a display title.

    Reads only the first 30 lines to avoid loading entire file.
    """
    return _scan_jsonl_for_title(jsonl_path)


def _read_session_stats(jsonl_path: Path) -> Dict[str, Any]:
    """Read duration and message count from a JSONL session file.

    Reads the full file to count entries and compute elapsed time from
    first to last timestamp. Only called for displayed sessions (≤20).
    """
    stats: Dict[str, Any] = {}
    try:
        lines = [line for line in split_lines(jsonl_path.read_text(encoding='utf-8', errors='replace'))
                 if line.strip().startswith('{')]
        if not lines:
            return stats
        stats['message_count'] = len(lines)
        first_ts = json.loads(lines[0]).get('timestamp')
        last_ts = json.loads(lines[-1]).get('timestamp')
        if first_ts and last_ts:
            t0 = datetime.fromisoformat(first_ts.replace('Z', '+00:00'))
            t1 = datetime.fromisoformat(last_ts.replace('Z', '+00:00'))
            secs = int((t1 - t0).total_seconds())
            if secs > 0:
                h, rem = divmod(secs, 3600)
                m = rem // 60
                stats['duration'] = f"{h}h{m:02d}m" if h else f"{m}m"
    # Unreadable file, malformed JSONL, a line that isn't an object, or a timestamp
    # that isn't an ISO string: stats are decorative sidebar info, partial stats
    # beat a crash. Anything else is a bug and propagates.
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return stats


def _extract_project_from_dir(dir_name: str) -> str:
    """Derive a short project label from an encoded Claude project directory name.

    E.g. '-home-user-src-tia-sessions-hosefobe-0314' → 'tia'
         '-home-user-src-projects-reveal-external-git' → 'reveal'
    """
    _SKIP = {'home', 'src', 'projects', 'external', 'internal', 'git'}
    prefix = dir_name.split('-sessions-')[0] if '-sessions-' in dir_name else dir_name
    parts = [p for p in prefix.lstrip('-').split('-') if p and p not in _SKIP]
    return parts[-1] if parts else ''


def _collect_sessions_from_dir(project_dir: Path) -> SessionEntries:
    """Collect session entry dicts from one project directory."""
    sessions = SessionEntries()
    paths = directory_entries(project_dir, sessions.discovery_failures)
    readme_present = any(p.match('README*.md') for p in paths)
    project = _extract_project_from_dir(project_dir.name)
    for jsonl_file in paths:
        if not jsonl_file.match('*.jsonl') or jsonl_file.stem.startswith('agent-'):
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
        sessions.candidate_entries += 1
        try:
            stat = jsonl_file.stat()
            if not stat_module.S_ISREG(stat.st_mode):
                raise ValueError('JSONL-named entry is not a regular transcript file')
            modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
        except _SCAN_ERRORS as exc:
            sessions.metadata_failures.append((jsonl_file, exc))
            continue
        sessions.append({
            'session': session_name,
            'path': to_posix(jsonl_file),
            'modified': modified,
            'size_kb': stat.st_size // 1024,
            'project': project,
        })
        if readme_present:
            sessions[-1]['readme_present'] = True
    return sessions


def _find_session_readme(session_name: str, sessions_dir: Optional[Path], failures=None) -> Optional[Path]:
    """Find the most recent README for a session in the sessions directory."""
    if sessions_dir is None:
        return None
    failures = [] if failures is None else failures
    session_dir = sessions_dir / session_name
    try:
        if not stat_module.S_ISDIR(session_dir.stat().st_mode):
            raise NotADirectoryError(str(session_dir))
    except FileNotFoundError:
        return None
    except OSError as exc:
        failures.append((session_dir, exc))
        return None
    readmes = sorted((p for p in directory_entries(session_dir, failures) if p.match('README*.md')), reverse=True)
    return readmes[0] if readmes else None


def _parse_readme_frontmatter(readme_path: Path, failures=None) -> Dict[str, Any]:
    """Parse YAML frontmatter from a README file."""
    import yaml
    try:
        text = readme_path.read_text(encoding='utf-8')
        if text.startswith('---'):
            end = text.find('\n---', 3)
            if end == -1:
                raise ValueError('README frontmatter has no closing delimiter')
            loaded = yaml.safe_load(text[3:end].strip())
            if loaded is not None and not isinstance(loaded, dict):
                raise ValueError('README frontmatter is not a mapping')
            return loaded if isinstance(loaded, dict) else {}
    except (OSError, ValueError, yaml.YAMLError) as exc:
        if failures is not None:
            failures.append((readme_path, exc))
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
    base: Dict[str, Any] = ResultBuilder.create(
        result_type='claude_session_list',
        source=to_posix(conversation_base),
        source_type='directory',
        contract_version=CONTRACT_VERSION,
    )

    name_filter = (query_params.get('filter') or query_params.get('search', '')).lower()

    catalog = collect_session_entries(conversation_base, _collect_sessions_from_dir)
    sessions = sorted(catalog, key=lambda x: x['modified'], reverse=True)
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

    return attach_catalog_evidence(base, catalog)


def search_sessions(conversation_base: Path, query_params: Dict[str, Any]) -> Dict[str, Any]:
    """Cross-session content search using ``?search=term``.

    Supports ``?since=DATE`` to scope the corpus before scanning.

    Returns:
        Dict of type ``claude_cross_session_search`` with ``matches`` list.
    """
    term = query_params.get('search', '')
    since = query_params.get('since', '')
    until = query_params.get('until', '')

    if since == 'today':
        since = _date.today().isoformat()
    if until == 'today':
        until = _date.today().isoformat()

    catalog = collect_session_entries(conversation_base, _collect_sessions_from_dir)
    all_sessions = list(catalog)
    if since:
        all_sessions = [s for s in all_sessions if s.get('modified', '') >= since]
    if until:
        all_sessions = [s for s in all_sessions if s.get('modified', '') <= until + 'T23:59:59.999999']

    whole_word = 'word' in query_params
    try:
        snippet_window = max(60, min(500, int(query_params.get('snippet', 120))))
    except (ValueError, TypeError):
        snippet_window = 120
    skipped: List[Tuple[Path, BaseException]] = []
    scans = ContentScans(len(all_sessions) if term else 0)
    matches = search_sessions_for_term(all_sessions, term, whole_word=whole_word,
                                       window_chars=snippet_window, errors_out=skipped, reads_out=scans.reads)

    result = ResultBuilder.create(
        result_type='claude_cross_session_search',
        source=to_posix(conversation_base),
        source_type='directory',
        contract_version=CONTRACT_VERSION,
        data={
            'term': term,
            'since': since or None,
            'until': until or None,
            'whole_word': whole_word,
            'sessions_scanned': len(all_sessions),
            'match_count': len(matches),
            'matches': matches,
        }
    )
    note_warning(result, skipped_entries_warning(
        'sessions', skipped, "they were not searched, so matches may be missing"))
    return scans.attach(attach_catalog_evidence(result, catalog))


def _extract_session_ops(session: Dict[str, Any], file_path: str,
                         reads_out: Optional[List[TranscriptRecords]] = None) -> Optional[Dict[str, Any]]:
    reader = TranscriptRecords(Path(session['path']))
    if reads_out is not None:
        reads_out.append(reader)
    messages = list(reader.records())
    contract_base = {'contract_version': CONTRACT_VERSION, 'source': session['path'], 'source_type': 'file'}
    files_result = get_files_touched(messages, session['session'], contract_base)

    ops_for_file: Dict[str, int] = {}
    for op, files_dict in files_result.get('by_operation', {}).items():
        count = sum(v for k, v in files_dict.items() if file_path in k)
        if count:
            ops_for_file[op] = count

    if not ops_for_file:
        return None
    return {
        'session': session['session'],
        'project': session.get('project', ''),
        'modified': session['modified'],
        'ops': ops_for_file,
        'total_ops': sum(ops_for_file.values()),
    }


def track_file_sessions(conversation_base: Path, resource: str, query_params: Dict[str, Any]) -> Dict[str, Any]:
    """Cross-session file tracking using ``claude://files/<path>``.

    Reads session records and extracts per-session operations for the given path.

    Supports ``?since=DATE`` to scope the corpus before scanning.

    Returns:
        Dict of type ``claude_file_sessions`` with ``sessions`` list.
    """
    file_path = resource[len('files/'):].strip('/')
    since = query_params.get('since', '')

    if since == 'today':
        since = _date.today().isoformat()

    if not file_path:
        raise RequestValidationError('No file path provided. Usage: claude://files/path/to/file.py')

    catalog = collect_session_entries(conversation_base, _collect_sessions_from_dir)
    all_sessions = list(catalog)
    if since:
        all_sessions = [s for s in all_sessions if s.get('modified', '') >= since]

    results = []
    skipped: List[Tuple[Path, BaseException]] = []
    scans = ContentScans(len(all_sessions))
    for session in all_sessions:
        try:
            entry = _extract_session_ops(session, file_path, scans.reads)
            if entry:
                results.append(entry)
        # One session file written by another program (any shape; get_files_touched does
        # not validate message shapes) must not end the cross-session search; the skipped
        # session is named in meta.warnings below.
        except Exception as e:  # boundary-ok: broad-except -- per-session isolation, skip is disclosed in meta.warnings
            logger.warning("skipping unparseable session %s: %s", session.get('path'), e)
            skipped.append((Path(session['path']), e))
            if scans.reads and not scans.reads[-1].failures:
                scans.reads[-1].failures.append({'phase': 'analysis', 'cause': type(e).__name__, 'message': str(e)})

    results.sort(key=lambda x: x['modified'], reverse=True)

    result = ResultBuilder.create(
        result_type='claude_file_sessions',
        source=to_posix(conversation_base),
        source_type='directory',
        contract_version=CONTRACT_VERSION,
        data={
            'file_path': file_path,
            'since': since or None,
            'sessions_scanned': len(all_sessions),
            'match_count': len(results),
            'sessions': results,
        }
    )
    note_warning(result, skipped_entries_warning(
        'sessions', skipped, "they were not checked, so matches may be missing"))
    return scans.attach(attach_catalog_evidence(result, catalog))


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
    from ..chain import ChainTraversal
    traversal = ChainTraversal(sessions_dir, _find_session_readme, _parse_readme_frontmatter)
    chain = traversal.walk(session_name)
    return traversal.attach({
        **contract_base,
        'type': 'claude_chain',
        'source': to_posix(sessions_dir) if sessions_dir else f'claude://session/{session_name}/chain',
        'source_type': 'directory' if sessions_dir else 'runtime',
        'session': session_name,
        'chain': chain,
        'chain_length': len(chain),
        'sessions_dir': to_posix(sessions_dir) if sessions_dir else None,
    })
