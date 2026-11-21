"""System resource handlers for codex:// adapter — info, history, config."""
from reveal.utils.path_utils import to_posix

import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional
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
