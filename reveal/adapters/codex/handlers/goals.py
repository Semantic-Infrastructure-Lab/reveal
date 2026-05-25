"""Goals handler for codex:// — reads goals_1.sqlite thread_goals table."""

import sqlite3
from pathlib import Path
from typing import Any, Dict


def get_goal(codex_home: Path, thread_id: str) -> Dict[str, Any]:
    """Return thread goal from goals_1.sqlite for the given thread_id."""
    goals_db = codex_home / 'goals_1.sqlite'
    base: Dict[str, Any] = {
        'contract_version': '1.0',
        'type': 'codex_goal',
        'source': str(goals_db),
        'source_type': 'sqlite',
        'thread_id': thread_id,
    }

    if not goals_db.exists():
        return {**base, 'goal': None}

    try:
        conn = sqlite3.connect(str(goals_db))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                'SELECT * FROM thread_goals WHERE thread_id = ?', (thread_id,)
            ).fetchone()
            return {**base, 'goal': dict(row) if row else None}
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return {**base, 'goal': None, 'error': str(exc)}
