"""Measured, read-only acquisition of the existing Codex UUID lookup."""
from reveal.utils.path_utils import to_posix
import sqlite3
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ...utils.results import note_warning

USER_FILTER = "(thread_source IS NULL OR thread_source = 'user') AND archived = 0"
LOOKUP_RULE = 'Observed rows from exact UUID lookup (limit 1) then prefix lookup (limit 6); user-visible, non-archived threads only; bounded candidate suggestions are not an exhaustive session census'


def connect_readonly(path: Path, connector: Optional[Callable[..., sqlite3.Connection]] = None) -> sqlite3.Connection:
    conn = (connector or sqlite3.connect)(path.absolute().as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    return conn


class SessionLookup:
    def __init__(self, path: Path, identifier: str, connector: Optional[Callable[..., sqlite3.Connection]] = None):
        self.path, self.identifier, self.connector = path, identifier, connector
        self.source_present: Optional[bool] = None
        self.opened = False
        self.queries: List[Dict[str, Any]] = []
        self.failures: List[Dict[str, str]] = []
        self.observed: List[Dict[str, Any]] = []
        self.selected: Optional[Dict[str, Any]] = None
        self.decision = 'failed'

    def _failure(self, phase, exc):
        self.failures.append({'phase': phase, 'cause': type(exc).__name__, 'message': str(exc)})

    def _source_available(self):
        try:
            self.path.stat()
            self.source_present = True
            return True
        except FileNotFoundError:
            self.source_present, self.decision = False, 'source_absent'
        except OSError as exc:
            self._failure('metadata', exc)
        return False

    def _query(self, conn, phase, sql, value, limit):
        step = {'phase': phase, 'rows': 0, 'limit': limit, 'complete': False}
        self.queries.append(step)
        rows = []
        try:
            for row in conn.execute(sql, (value,)):
                rows.append(dict(row))
                step['rows'] += 1
            step['complete'] = True
        except sqlite3.Error as exc:
            self._failure(phase, exc)
        self.observed.extend(rows)
        return rows

    def _select(self, conn):
        exact = self._query(conn, 'exact', f'SELECT * FROM threads WHERE id = ? AND {USER_FILTER} LIMIT 1', self.identifier, 1)
        if exact:
            self.selected = exact[0]
        elif not self.failures and len(self.identifier) < 36:
            rows = self._query(conn, 'prefix', f'SELECT * FROM threads WHERE id LIKE ? AND {USER_FILTER} ORDER BY id LIMIT 6', self.identifier + '%', 6)
            if len(rows) == 1 and not self.failures:
                self.selected = rows[0]

    def find(self) -> Tuple[Optional[Dict[str, Any]], List[str]]:
        if not self._source_available():
            return None, []
        conn = None
        try:
            conn = connect_readonly(self.path, self.connector)
            self.opened = True
            self._select(conn)
        except (sqlite3.Error, OSError) as exc:
            self._failure('open', exc)
        finally:
            if conn is not None:
                try:
                    conn.close()
                except sqlite3.Error as exc:
                    self._failure('close', exc)
        return self._decision()

    def _decision(self) -> Tuple[Optional[Dict[str, Any]], List[str]]:
        if self.selected is not None:
            self.decision = 'selected'
            return self.selected, []
        if len(self.observed) > 1:
            self.decision = 'ambiguous'
            return None, [row['id'] for row in self.observed]
        self.decision = 'failed' if self.failures else 'missing'
        return None, []

    def receipt(self) -> Dict[str, Any]:
        return {'source': to_posix(self.path), 'requested_id': self.identifier,
                'source_present': self.source_present, 'opened': self.opened,
                'decision': self.decision, 'selected_id': self.selected['id'] if self.selected is not None else None,
                'queries': [dict(step) for step in self.queries],
                'observed_ids': [row['id'] for row in self.observed],
                'failed_operations': len(self.failures), 'failures': [dict(item) for item in self.failures],
                'count_rule': LOOKUP_RULE}


def attach_lookup_evidence(result: Dict[str, Any], lookup: Optional[SessionLookup]) -> Dict[str, Any]:
    if lookup is None:
        return result
    proof = lookup.receipt()
    result.setdefault('meta', {'warnings': [], 'errors': []})['session_lookup'] = proof
    if proof['failed_operations']:
        note_warning(result, {'type': 'analysis_incomplete', 'code': 'analysis_incomplete', 'field': 'session_lookup',
                              'message': f"Codex session lookup: {proof['failed_operations']} required source operation(s) failed; observed rows retained. Source decisions: JSON meta.session_lookup."})
    return result
