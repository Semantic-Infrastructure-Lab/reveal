"""System-level resource handlers for the claude:// adapter — history, settings, info, config."""
import json
import os
import stat as stat_module
from pathlib import Path
from typing import Any, Dict, Optional
from reveal.reveal_types import CONTRACT_VERSION

from ....utils.results import ResultBuilder
from ....utils.path_utils import failure_of
from ..installation import JsonDocumentRead


def _path_info(p: Path) -> Dict[str, Any]:
    try:
        metadata = p.stat()
    except (FileNotFoundError, NotADirectoryError):
        return {'path': str(p), 'exists': False}
    except OSError as exc:
        return {'path': str(p), 'exists': None, 'error_phase': 'metadata', 'cause': type(exc).__name__,
                'error': f'metadata unreadable: {failure_of(exc).cause}'}
    if stat_module.S_ISDIR(metadata.st_mode):
        count = 0
        try:
            for _ in p.iterdir():
                count += 1
        except OSError as exc:
            return {'path': str(p), 'exists': True, 'kind': 'dir', 'count': None,
                    'entries_seen': count, 'error_phase': 'directory-count', 'cause': type(exc).__name__,
                    'error': f'directory unreadable: {failure_of(exc).cause}'}
        return {'path': str(p), 'exists': True, 'kind': 'dir', 'count': count}
    return {'path': str(p), 'exists': True, 'kind': 'file', 'size_bytes': metadata.st_size}


def get_history(claude_home: Path, query_params: Dict[str, Any]) -> Dict[str, Any]:
    """Read prompt history with measured source and payload decisions."""
    from ..history import read_history
    return read_history(claude_home, query_params, opener=open)


def get_settings(claude_home: Path, query_params: Dict[str, Any]) -> Dict[str, Any]:
    """Read and return ~/.claude/settings.json, with optional ?key= extraction."""
    settings_path = claude_home / 'settings.json'
    base: Dict[str, Any] = dict(ResultBuilder.create(
        result_type='claude_settings',
        source=str(settings_path),
        source_type='file',
        contract_version=CONTRACT_VERSION,
    ))
    source = JsonDocumentRead(settings_path)
    try:
        source.select()
        with source.operation('read-json'):
            with open(settings_path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
        source.parsed = source.usable = True
    except (OSError, ValueError) as e:  # unreadable, not UTF-8 or not JSON (JSONDecodeError is a ValueError)
        error = f'Not found: {settings_path}' if isinstance(e, FileNotFoundError) and not source.selected else str(e)
        return source.attach({**base, 'error': error, 'settings': {}})

    key = query_params.get('key', '')
    if key:
        parts = key.split('.')
        val: Any = data
        try:
            for part in parts:
                val = val[part]
            return source.attach({**base, 'key': key, 'value': val})
        except (KeyError, TypeError) as exc:
            source.error('key', exc, rejected=True)
            return source.attach({**base, 'key': key, 'error': f'Key not found: {key}', 'value': None})

    return source.attach({**base, 'settings': data})


def get_info(
    claude_home: Path,
    conversation_base: Path,
    plans_dir: Path,
    claude_json: Path,
    sessions_dir: Optional[Path],
) -> Dict[str, Any]:
    """Diagnostic dump of all resolved Claude Code data paths and env overrides."""
    from ..info import attach_info_evidence
    return attach_info_evidence(dict(ResultBuilder.create(
        result_type='claude_info',
        source=str(claude_home),
        source_type='directory',
        contract_version=CONTRACT_VERSION,
        data={
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
    )))


def get_config(claude_json: Path, query_params: Dict[str, Any]) -> Dict[str, Any]:
    """Read ~/.claude.json — per-install config (projects, MCP servers, feature flags)."""
    base: Dict[str, Any] = dict(ResultBuilder.create(
        result_type='claude_config',
        source=str(claude_json),
        source_type='file',
        contract_version=CONTRACT_VERSION,
    ))
    source = JsonDocumentRead(claude_json)
    try:
        source.select()
        with source.operation('read'):
            text = claude_json.read_text(encoding='utf-8', errors='surrogateescape')
        text = source.repair(text)
        with source.operation('parse-json'):
            data = json.loads(text)
        source.parsed = True
    except (OSError, ValueError) as e:  # unreadable or not JSON
        error = f'Config not found: {claude_json}' if isinstance(e, FileNotFoundError) and not source.selected else str(e)
        return source.attach({**base, 'error': error, 'projects': [], 'flags': {}})
    if not isinstance(data, dict):  # valid JSON of another shape: .get below would raise (BACK-1857)
        error = f'{claude_json} is not a JSON object (top-level {type(data).__name__})'
        source.error('validate-root', ValueError(error))
        return source.attach({**base, 'error': error, 'projects': [], 'flags': {}})
    source.usable = True

    # ?key=dotpath — drill into a specific value
    key = query_params.get('key', '').strip()
    if key:
        val: Any = data
        for part in key.split('.'):
            val = val.get(part) if isinstance(val, dict) else None
        return source.attach({**base, 'key': key, 'value': val})

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

    return source.attach({
        **base,
        'projects_count': len(projects_raw),
        'projects': project_list,
        'flags': flags,
    })
