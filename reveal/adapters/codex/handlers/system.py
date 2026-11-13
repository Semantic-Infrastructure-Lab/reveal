"""System resource handlers for codex:// adapter — info, history, config, memories, rules."""
from reveal.utils.path_utils import to_posix

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
from reveal.reveal_types import CONTRACT_VERSION

from ....utils.results import ResultBuilder
from ....utils.document_read import DocumentRead
from ..history import read_history
from ....utils.secrets import redact_secrets
from ....utils.path_inventory import path_info as _path_info
from ..info import read_db_stats, attach_info_evidence

import tomllib




def get_info(codex_home: Path, db_path: Path) -> Dict[str, Any]:
    """Return path map + DB stats for codex://info."""
    base: Dict[str, Any] = ResultBuilder.create(
        result_type='codex_info',
        source=to_posix(db_path),
        source_type='database',
        contract_version=CONTRACT_VERSION,
    )

    paths = {
        'codex_home': _path_info(codex_home),
        'db': _path_info(db_path),
        'sessions_dir': _path_info(codex_home / 'sessions'),
        'history': _path_info(codex_home / 'history.jsonl'),
        'config': _path_info(codex_home / 'config.toml'),
        'memories': _path_info(codex_home / 'memories'),
        'rules': _path_info(codex_home / 'rules'),
    }

    db_stats, operations = read_db_stats(db_path, paths['db']['exists'], connector=sqlite3.connect)
    return attach_info_evidence({**base, 'paths': paths, 'db_stats': db_stats}, operations)


def get_history(codex_home: Path, query_params: Dict[str, Any]) -> Dict[str, Any]:
    """Read ~/.codex/history.jsonl and return entries."""
    return read_history(codex_home, opener=open)


def get_config(codex_home: Path, query_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Read ~/.codex/config.toml, mask secrets, return parsed dict.

    Supports ?key=dotpath (BACK-944, parity with claude://config, claude://settings)
    to drill into a single value — applied AFTER secret masking, so a masked value
    can never be un-redacted by requesting it directly via ?key=.
    """
    query_params = query_params or {}
    config_path = codex_home / 'config.toml'
    base: Dict[str, Any] = ResultBuilder.create(
        result_type='codex_config',
        source=to_posix(config_path),
        source_type='file',
        contract_version=CONTRACT_VERSION,
    )

    read = DocumentRead(config_path, label='Codex TOML')
    try:
        read.select()
        with read.operation('load'):
            with open(config_path, 'rb') as fh:
                parsed = tomllib.load(fh)
                read.parsed = True
    except (OSError, ValueError) as exc:
        if not read.parsed:
            message = f'Config not found: {config_path}' if isinstance(exc, FileNotFoundError) and not read.selected else str(exc)
            return read.attach({**base, 'config': {}, 'error': message})
    try:
        with read.operation('mask'):
            masked = redact_secrets(parsed)
        read.usable = True
    except (OSError, ValueError) as exc:
        return read.attach({**base, 'config': {}, 'error': str(exc)})

    key = (query_params.get('key') or '').strip()
    if key:
        val: Any = masked
        found = True
        for part in key.split('.'):
            if not isinstance(val, dict) or part not in val:
                val, found = None, False
                break
            val = val[part]
        if not found:
            read.error('key', KeyError(f'Config key not found: {key}'), rejected=True)
        return read.attach({**base, 'key': key, 'value': val})

    return read.attach({**base, 'config': masked})


def get_memories(codex_home: Path) -> Dict[str, Any]:
    """List files in ~/.codex/memories/ with their content."""
    memories_dir = codex_home / 'memories'
    base: Dict[str, Any] = ResultBuilder.create(
        result_type='codex_memories',
        source=to_posix(memories_dir),
        source_type='file',
        contract_version=CONTRACT_VERSION,
    )

    if not memories_dir.exists():
        return {**base, 'memories': [], 'total': 0}

    memories: List[Dict[str, Any]] = []
    # boundary-ok: walker -- the Codex home, not a code tree
    for path in sorted(memories_dir.rglob('*')):
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            content = ''
        memories.append({
            'path': to_posix(path),
            'name': path.name,
            'size_bytes': path.stat().st_size,
            'content': content,
        })

    return {**base, 'memories': memories, 'total': len(memories)}


def get_memories_pipeline(db_path: Path) -> Dict[str, Any]:
    """Return Stage1/Stage2 memory pipeline status from stage1_outputs table."""
    base: Dict[str, Any] = ResultBuilder.create(
        result_type='codex_memories_pipeline',
        source=to_posix(db_path),
        source_type='database',
        contract_version=CONTRACT_VERSION,
    )

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
    base: Dict[str, Any] = ResultBuilder.create(
        result_type='codex_rules',
        source=to_posix(rules_dir),
        source_type='file',
        contract_version=CONTRACT_VERSION,
    )

    if not rules_dir.exists():
        return {**base, 'rules': [], 'total': 0}

    rules: List[Dict[str, Any]] = []
    for path in sorted(rules_dir.glob('*.rules')):
        try:
            content = path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            content = ''
        rules.append({
            'path': to_posix(path),
            'name': path.name,
            'size_bytes': path.stat().st_size,
            'content': content,
        })

    return {**base, 'rules': rules, 'total': len(rules)}
