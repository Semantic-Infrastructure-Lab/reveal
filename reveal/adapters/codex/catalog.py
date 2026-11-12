"""Measured acquisition of the existing SQLite session catalog."""
from copy import deepcopy
import sqlite3
from pathlib import Path
from typing import Any, Callable, Dict, List

from ...utils.observations import count_observations, validate_observation_counts
from ...utils.results import AnalysisCompleteness, FailureCause, note_warning, result_execution_facts
from .lookup import USER_FILTER

CATALOG_PATHS = frozenset(('', '.', 'sessions', 'sessions/'))
CATALOG_COLUMNS = ('id, title, first_user_message, model, model_provider, reasoning_effort, '
                   'tokens_used, cwd, created_at, updated_at, cli_version, git_branch, approval_mode')
CATALOG_RULE = 'Observed user-visible non-archived SQLite rows in updated_at descending order, before metadata/date filtering and display cuts; interrupted acquisition retains its observed prefix'


class CatalogRead:
    def __init__(self, path: Path, connector: Callable[..., sqlite3.Connection], columns: str = CATALOG_COLUMNS):
        self.path, self.connector, self.columns = path, connector, columns
        self.rows: List[Dict[str, Any]] = []
        self.proof: Dict[str, Any] = {
            'source': str(path), 'source_present': None, 'opened': False,
            'query_complete': False, 'observed_rows': 0, 'failed_operations': 0,
            'failures': [], 'count_rule': CATALOG_RULE,
        }

    def failure(self, phase, exc):
        self.proof['failed_operations'] += 1
        self.proof['failures'].append({'phase': phase, 'cause': type(exc).__name__, 'message': str(exc)})

    def _available(self):
        try:
            self.path.stat()
            self.proof['source_present'] = True
            return True
        except FileNotFoundError:
            self.proof['source_present'] = False
        except OSError as exc:
            self.failure('metadata', exc)
        return False

    def _query(self, conn):
        try:
            for row in conn.execute(f'SELECT {self.columns} FROM threads WHERE {USER_FILTER} ORDER BY updated_at DESC'):
                self.rows.append(dict(row))
                self.proof['observed_rows'] += 1
            self.proof['query_complete'] = True
        except sqlite3.Error as exc:
            self.failure('query', exc)

    def read(self):
        if not self._available():
            return
        conn = None
        try:
            conn = self.connector(self.path)
            self.proof['opened'] = True
            self._query(conn)
        except (sqlite3.Error, OSError) as exc:
            self.failure('open', exc)
        finally:
            if conn is not None:
                try:
                    conn.close()
                except sqlite3.Error as exc:
                    self.failure('close', exc)

    def attach(self, result: Dict[str, Any]) -> Dict[str, Any]:
        result.setdefault('meta', {'warnings': [], 'errors': []})['session_catalog'] = deepcopy(self.proof)
        if self.proof['source_present'] is False:
            result['error'] = f'Codex DB not found: {self.path}'
        if self.proof['failed_operations']:
            if not self.rows and not self.proof['query_complete']:
                result['error'] = self.proof['failures'][0]['message']
            note_warning(result, {'type': 'analysis_incomplete', 'code': 'analysis_incomplete', 'field': 'session_catalog',
                                  'message': 'Codex catalog acquisition lost required source operations; observed rows retained. See JSON meta.session_catalog.'})
        return result


def execution_facts(result):
    proof = result.get('meta', {}).get('session_catalog', {})
    if proof.get('source_present') is False:
        return result_execution_facts(result, completeness=AnalysisCompleteness.COMPLETE, failure_cause=FailureCause.INVALID_REQUEST)
    state = AnalysisCompleteness.COMPLETE
    if proof.get('failed_operations'):
        usable = proof.get('observed_rows') or proof.get('query_complete')
        state = AnalysisCompleteness.INCOMPLETE if usable else AnalysisCompleteness.FAILED
    return result_execution_facts(result, completeness=state)


def answer_requirement_error(adapter, result, prior_facts):
    expected = adapter._catalog_answer
    if result.get('source') != str(adapter.CODEX_DB) or result.get('source_type') != 'database':
        return 'Codex catalog answer changed its database source identity'
    if result.get('meta', {}).get('session_catalog') != expected['meta']['session_catalog']:
        return 'Codex catalog answer changed its acquisition decisions'
    for key in ('error', 'filter', 'since', 'until'):
        if (key in result) != (key in expected) or result.get(key) != expected.get(key):
            return 'Codex catalog answer changed its source diagnostic or selection receipt'
    rows, total = result.get('sessions'), result.get('total')
    if not isinstance(rows, list) or type(total) is not int or total != expected['total']:
        return 'Codex catalog answer changed its observations or population count'
    current = count_observations(result, (('sessions',),))
    original = count_observations(expected, (('sessions',),))
    return validate_observation_counts(result, original, current, label='Codex catalog')
