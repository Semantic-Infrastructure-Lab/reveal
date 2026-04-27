"""System-level resource handlers for the claude:// adapter — history, settings, info, config."""
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import date as _date

_SECRET_PATTERNS = ('api_key', 'apikey', 'api-key', 'secret', 'token', 'password', 'credential', 'auth')


def _mask_secrets(obj: Any, depth: int = 0) -> Any:
    """Recursively mask secret-looking string values in a config dict."""
    if depth > 6:
        return obj
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            k_lower = k.lower()
            if any(p in k_lower for p in _SECRET_PATTERNS) and isinstance(v, str) and len(v) > 8:
                result[k] = v[:4] + '***'
            else:
                result[k] = _mask_secrets(v, depth + 1)
        return result
    if isinstance(obj, list):
        return [_mask_secrets(i, depth + 1) for i in obj]
    return obj


def _path_info(p: Path) -> Dict[str, Any]:
    if not p.exists():
        return {'path': str(p), 'exists': False}
    if p.is_dir():
        try:
            count = sum(1 for _ in p.iterdir())
        except Exception:
            count = 0
        return {'path': str(p), 'exists': True, 'kind': 'dir', 'count': count}
    stat = p.stat()
    return {'path': str(p), 'exists': True, 'kind': 'file', 'size_bytes': stat.st_size}


def get_history(claude_home: Path, query_params: Dict[str, Any]) -> Dict[str, Any]:
    """Read and filter ~/.claude/history.jsonl prompt history.

    Streams the file line-by-line to handle large files without loading
    everything into memory.

    Supports query params:
        ?search=term    - substring match against prompt text (case-insensitive)
        ?project=path   - substring match against project path (case-insensitive)
        ?since=DATE     - ISO date (e.g. 2026-03-01) or 'today'

    Returns:
        Dict of type ``claude_history`` with ``entries`` list.
        Entries are newest-first.
    """
    from datetime import datetime as _dt

    history_path = claude_home / 'history.jsonl'
    search = query_params.get('search', '').lower()
    project_filter = query_params.get('project', '').lower()
    since = query_params.get('since', '')

    if since == 'today':
        since = _date.today().isoformat()

    base: Dict[str, Any] = {
        'contract_version': '1.0',
        'type': 'claude_history',
        'source': str(history_path),
        'source_type': 'file',
        'search': search or None,
        'project': project_filter or None,
        'since': since or None,
    }

    if not history_path.exists():
        return {**base, 'total_entries': 0, 'match_count': 0, 'entries': [],
                'error': f'History file not found: {history_path}'}

    entries = []
    total = 0

    try:
        with open(history_path, 'r', encoding='utf-8', errors='replace') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                total += 1

                prompt = obj.get('display', '')
                project = obj.get('project', '')
                ts_ms = obj.get('timestamp', 0)
                session_id = obj.get('sessionId')

                ts_iso = (
                    _dt.fromtimestamp(ts_ms / 1000).isoformat(timespec='seconds')
                    if ts_ms else ''
                )

                if since and ts_iso[:10] < since:
                    continue
                if search and search not in prompt.lower():
                    continue
                if project_filter and project_filter not in project.lower():
                    continue

                entries.append({
                    'prompt': prompt,
                    'project': project,
                    'timestamp': ts_iso,
                    'session_id': session_id,
                })
    except Exception as e:
        return {**base, 'total_entries': total, 'match_count': 0, 'entries': [],
                'error': str(e)}

    entries.reverse()  # file is oldest-first; return newest-first

    return {
        **base,
        'total_entries': total,
        'match_count': len(entries),
        'entries': entries,
    }


def get_settings(claude_home: Path, query_params: Dict[str, Any]) -> Dict[str, Any]:
    """Read and return ~/.claude/settings.json, with optional ?key= extraction."""
    settings_path = claude_home / 'settings.json'
    base: Dict[str, Any] = {
        'contract_version': '1.0',
        'type': 'claude_settings',
        'source': str(settings_path),
        'source_type': 'file',
    }
    if not settings_path.exists():
        return {**base, 'error': f'Not found: {settings_path}', 'settings': {}}
    try:
        with open(settings_path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except Exception as e:
        return {**base, 'error': str(e), 'settings': {}}

    key = query_params.get('key', '')
    if key:
        parts = key.split('.')
        val: Any = data
        try:
            for part in parts:
                val = val[part]
            return {**base, 'key': key, 'value': val}
        except (KeyError, TypeError):
            return {**base, 'key': key, 'error': f'Key not found: {key}', 'value': None}

    return {**base, 'settings': data}


def get_info(
    claude_home: Path,
    conversation_base: Path,
    plans_dir: Path,
    claude_json: Path,
    sessions_dir: Optional[Path],
) -> Dict[str, Any]:
    """Diagnostic dump of all resolved Claude Code data paths and env overrides."""
    return {
        'contract_version': '1.0',
        'type': 'claude_info',
        'source': str(claude_home),
        'source_type': 'directory',
        'paths': {
            'claude_home': _path_info(claude_home),
            'projects': _path_info(conversation_base),
            'history': _path_info(claude_home / 'history.jsonl'),
            'plans': _path_info(plans_dir),
            'settings': _path_info(claude_home / 'settings.json'),
            'config': _path_info(claude_json),
            'agents': _path_info(claude_home / 'agents'),
            'hooks': _path_info(claude_home / 'hooks'),
        },
        'env': {
            'REVEAL_CLAUDE_HOME': os.environ.get('REVEAL_CLAUDE_HOME', ''),
            'REVEAL_CLAUDE_JSON': os.environ.get('REVEAL_CLAUDE_JSON', ''),
            'REVEAL_CLAUDE_DIR': os.environ.get('REVEAL_CLAUDE_DIR', ''),
            'REVEAL_SESSIONS_DIR': os.environ.get('REVEAL_SESSIONS_DIR', ''),
        },
        'sessions_dir': str(sessions_dir) if sessions_dir else None,
    }


def get_config(claude_json: Path, query_params: Dict[str, Any]) -> Dict[str, Any]:
    """Read ~/.claude.json — per-install config (projects, MCP servers, feature flags)."""
    base: Dict[str, Any] = {
        'contract_version': '1.0',
        'type': 'claude_config',
        'source': str(claude_json),
        'source_type': 'file',
    }

    if not claude_json.exists():
        return {**base, 'error': f'Config not found: {claude_json}', 'projects': [], 'flags': {}}

    try:
        data = json.loads(claude_json.read_text(encoding='utf-8', errors='replace'))
    except Exception as e:
        return {**base, 'error': str(e), 'projects': [], 'flags': {}}

    # ?key=dotpath — drill into a specific value
    key = query_params.get('key', '').strip()
    if key:
        val: Any = data
        for part in key.split('.'):
            val = val.get(part) if isinstance(val, dict) else None
        return {**base, 'key': key, 'value': val}

    # Build per-project MCP server summary
    projects_raw = data.get('projects', {})
    project_list = []
    for path, proj in projects_raw.items():
        if not isinstance(proj, dict):
            continue
        mcp = proj.get('mcpServers', {})
        project_list.append({
            'path': path,
            'mcp_servers': list(mcp.keys()) if isinstance(mcp, dict) else [],
            'allowed_tools': proj.get('allowedTools', []),
        })

    # Key operational flags (skip noise like tipsHistory, cachedStatsig*)
    flag_keys = [
        'autoUpdates', 'autoCompactEnabled', 'verbose', 'installMethod',
        'numStartups', 'autoConnectIde', 'showSpinnerTree',
    ]
    flags = {k: data[k] for k in flag_keys if k in data}

    return {
        **base,
        'projects_count': len(projects_raw),
        'projects': project_list,
        'flags': flags,
    }
