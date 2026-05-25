"""System resource handlers for codex:// adapter — info, history, config, memories, rules."""

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

_SECRET_PATTERNS = ('api_key', 'apikey', 'api-key', 'secret', 'token', 'password', 'credential', 'auth')


def _mask_secrets(obj: Any, depth: int = 0) -> Any:
    """Recursively mask secret-looking string values."""
    if depth > 6:
        return obj
    if isinstance(obj, dict):
        result: Dict[str, Any] = {}
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


def get_info(codex_home: Path, db_path: Path) -> Dict[str, Any]:
    """Return path map + DB stats for codex://info."""
    base: Dict[str, Any] = {
        'contract_version': '1.0',
        'type': 'codex_info',
        'source': str(db_path),
        'source_type': 'sqlite',
    }

    paths = {
        'codex_home': _path_info(codex_home),
        'db': _path_info(db_path),
        'sessions_dir': _path_info(codex_home / 'sessions'),
        'history': _path_info(codex_home / 'history.jsonl'),
        'config': _path_info(codex_home / 'config.toml'),
        'memories': _path_info(codex_home / 'memories'),
        'rules': _path_info(codex_home / 'rules'),
    }

    db_stats: Dict[str, Any] = {}
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                row = conn.execute("SELECT COUNT(*) FROM threads").fetchone()
                db_stats['total_threads'] = row[0] if row else 0
                row2 = conn.execute(
                    "SELECT COUNT(*) FROM threads "
                    "WHERE (thread_source IS NULL OR thread_source = 'user') AND archived = 0"
                ).fetchone()
                db_stats['user_sessions'] = row2[0] if row2 else 0
            finally:
                conn.close()
        except sqlite3.Error as exc:
            db_stats['error'] = str(exc)

    return {**base, 'paths': paths, 'db_stats': db_stats}


def get_history(codex_home: Path, query_params: Dict[str, Any]) -> Dict[str, Any]:
    """Read ~/.codex/history.jsonl and return entries."""
    history_path = codex_home / 'history.jsonl'
    base: Dict[str, Any] = {
        'contract_version': '1.0',
        'type': 'codex_history',
        'source': str(history_path),
        'source_type': 'file',
    }

    if not history_path.exists():
        return {**base, 'entries': [], 'total_entries': 0,
                'error': f'History file not found: {history_path}'}

    entries: List[Any] = []
    try:
        with open(history_path, 'r', encoding='utf-8', errors='replace') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    entries.append({'raw': line})
    except OSError as exc:
        return {**base, 'entries': [], 'total_entries': 0, 'error': str(exc)}

    return {**base, 'entries': entries, 'total_entries': len(entries)}


def get_config(codex_home: Path) -> Dict[str, Any]:
    """Read ~/.codex/config.toml, mask secrets, return parsed dict."""
    config_path = codex_home / 'config.toml'
    base: Dict[str, Any] = {
        'contract_version': '1.0',
        'type': 'codex_config',
        'source': str(config_path),
        'source_type': 'file',
    }

    if not config_path.exists():
        return {**base, 'config': {}, 'error': f'Config not found: {config_path}'}

    if tomllib is None:
        try:
            raw = config_path.read_text(encoding='utf-8')
            return {**base, 'config': {'_raw': raw},
                    'warning': 'tomllib/tomli not available — returning raw text'}
        except OSError as exc:
            return {**base, 'config': {}, 'error': str(exc)}

    try:
        with open(config_path, 'rb') as fh:
            parsed = tomllib.load(fh)
        return {**base, 'config': _mask_secrets(parsed)}
    except Exception as exc:
        return {**base, 'config': {}, 'error': str(exc)}


def get_memories(codex_home: Path) -> Dict[str, Any]:
    """List files in ~/.codex/memories/ with their content."""
    memories_dir = codex_home / 'memories'
    base: Dict[str, Any] = {
        'contract_version': '1.0',
        'type': 'codex_memories',
        'source': str(memories_dir),
        'source_type': 'file',
    }

    if not memories_dir.exists():
        return {**base, 'memories': [], 'total': 0}

    memories: List[Dict[str, Any]] = []
    for path in sorted(memories_dir.rglob('*')):
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            content = ''
        memories.append({
            'path': str(path),
            'name': path.name,
            'size_bytes': path.stat().st_size,
            'content': content,
        })

    return {**base, 'memories': memories, 'total': len(memories)}


def get_memories_pipeline(db_path: Path) -> Dict[str, Any]:
    """Return Stage1/Stage2 memory pipeline status from stage1_outputs table."""
    base: Dict[str, Any] = {
        'contract_version': '1.0',
        'type': 'codex_memories_pipeline',
        'source': str(db_path),
        'source_type': 'sqlite',
    }

    if not db_path.exists():
        return {**base, 'stage1_total': 0, 'stage2_selected': 0, 'recent_outputs': []}

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT COUNT(*) FROM stage1_outputs").fetchone()
            total = row[0] if row else 0
            row2 = conn.execute(
                "SELECT COUNT(*) FROM stage1_outputs WHERE selected_for_phase2 = 1"
            ).fetchone()
            phase2_selected = row2[0] if row2 else 0
            rows = conn.execute(
                """SELECT thread_id, rollout_slug, generated_at,
                          selected_for_phase2, usage_count, last_usage
                   FROM stage1_outputs ORDER BY source_updated_at DESC LIMIT 20"""
            ).fetchall()
            return {
                **base,
                'stage1_total': total,
                'stage2_selected': phase2_selected,
                'recent_outputs': [dict(r) for r in rows],
            }
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return {**base, 'stage1_total': 0, 'stage2_selected': 0, 'recent_outputs': [],
                'error': str(exc)}


def get_rules(codex_home: Path) -> Dict[str, Any]:
    """List *.rules files in ~/.codex/rules/ with their content."""
    rules_dir = codex_home / 'rules'
    base: Dict[str, Any] = {
        'contract_version': '1.0',
        'type': 'codex_rules',
        'source': str(rules_dir),
        'source_type': 'file',
    }

    if not rules_dir.exists():
        return {**base, 'rules': [], 'total': 0}

    rules: List[Dict[str, Any]] = []
    for path in sorted(rules_dir.glob('*.rules')):
        try:
            content = path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            content = ''
        rules.append({
            'path': str(path),
            'name': path.name,
            'size_bytes': path.stat().st_size,
            'content': content,
        })

    return {**base, 'rules': rules, 'total': len(rules)}
