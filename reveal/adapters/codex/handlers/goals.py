"""Measured read-only acquisition of optional Codex thread goals."""
from reveal.utils.path_utils import to_posix

import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional
from reveal.reveal_types import CONTRACT_VERSION

from ....utils.results import ResultBuilder, note_warning
from ..lookup import connect_readonly

GOAL_RULE = 'Optional goals database; exact thread_id lookup, at most one goal row; missing database or row is a complete absence decision'


class GoalLookup:
    def __init__(self, path: Path, thread_id: str):
        self.path, self.thread_id = path, thread_id
        self.proof: Dict[str, Any] = {
            'source': to_posix(path), 'thread_id': thread_id, 'source_present': None,
            'opened': False, 'query_complete': False, 'rows': 0,
            'decision': 'failed', 'failed_operations': 0, 'failures': [], 'count_rule': GOAL_RULE,
        }
        self.goal: Optional[Dict[str, Any]] = None

    def _failure(self, phase, exc):
        self.proof['failures'].append({'phase': phase, 'cause': type(exc).__name__, 'message': str(exc)})
        self.proof['failed_operations'] += 1

    def _available(self):
        try:
            self.path.stat()
            self.proof['source_present'] = True
            return True
        except FileNotFoundError:
            self.proof.update(source_present=False, decision='source_absent')
        except OSError as exc:
            self._failure('metadata', exc)
        return False

    def _query(self, conn):
        try:
            row = conn.execute('SELECT * FROM thread_goals WHERE thread_id = ? LIMIT 1', (self.thread_id,)).fetchone()
            self.goal = dict(row) if row is not None else None
            self.proof.update(query_complete=True, rows=int(row is not None),
                              decision='selected' if row is not None else 'missing')
        except sqlite3.Error as exc:
            self._failure('query', exc)

    def read(self):
        if not self._available():
            return
        conn = None
        try:
            conn = connect_readonly(self.path)
            self.proof['opened'] = True
            self._query(conn)
        except (sqlite3.Error, OSError) as exc:
            self._failure('open', exc)
        finally:
            if conn is not None:
                try:
                    conn.close()
                except sqlite3.Error as exc:
                    self._failure('close', exc)


def get_goal(codex_home: Path, thread_id: str) -> Dict[str, Any]:
    """Return the native nullable goal plus measured optional-source decisions."""
    lookup = GoalLookup(codex_home / 'goals_1.sqlite', thread_id)
    lookup.read()
    result: Dict[str, Any] = ResultBuilder.create(
        result_type='codex_goal', source=to_posix(lookup.path), source_type='database',
        contract_version=CONTRACT_VERSION, data={'thread_id': thread_id, 'goal': lookup.goal},
    )
    result.setdefault('meta', {'warnings': [], 'errors': []})['goal_lookup'] = lookup.proof
    if lookup.proof['failed_operations']:
        if not lookup.proof['query_complete']:
            result['error'] = lookup.proof['failures'][0]['message']
        note_warning(result, {'type': 'analysis_incomplete', 'code': 'analysis_incomplete', 'field': 'goal_lookup',
                              'message': 'Codex goal acquisition lost a source operation; see JSON meta.goal_lookup.'})
    return result
