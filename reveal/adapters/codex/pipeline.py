"""Codex memory pipeline (``stage1_outputs``) with measured read-only SQLite acquisition (BACK-2618 Step 3).

Current Codex keeps the pipeline in ``memories_1.sqlite``; older installs keep it in the state database, which is
read when the memories database is confirmed absent. A database that is not there, or one without
``stage1_outputs`` (an install that never ran the memory pipeline), is a complete empty answer (ruling Q7:
``source_absent`` / ``table_absent``). A failed selection, opening, query or close is lost input, exit 3, with the
counts read before it kept. ``recent_outputs`` holds the newest 20 rows; the total is known, so the cut is marked.
"""
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

from reveal.reveal_types import CONTRACT_VERSION
from reveal.utils.path_utils import failure_of, to_posix

from ...utils.observations import count_observations, validate_observation_counts
from ...utils.results import (AnalysisCompleteness, ResultBuilder, note_truncation, note_warning,
                              result_execution_facts)
from .lookup import connect_readonly

RECENT = 20
PIPELINE_RULE = ('stage1_outputs rows of the memories database (memories_1.sqlite, else the state database): the '
                 'totals are COUNT(*) reads, sequential, not one atomic census; recent_outputs holds the newest 20 by '
                 'source_updated_at')
_TABLE = "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'stage1_outputs'"
_COUNTS = (('stage1_total', 'SELECT COUNT(*) FROM stage1_outputs'),
           ('stage2_selected', 'SELECT COUNT(*) FROM stage1_outputs WHERE selected_for_phase2 = 1'))
_RECENT = ('SELECT thread_id, rollout_slug, generated_at, selected_for_phase2, usage_count, last_usage '
           'FROM stage1_outputs ORDER BY source_updated_at DESC LIMIT ?')
_PHASES = ('select', 'open', 'table', 'stage1_total', 'stage2_selected', 'recent', 'close')
DECISIONS = ('read', 'source_absent', 'table_absent', 'failed')


class PipelineRead:
    """One pipeline acquisition: the selected database, each operation's outcome and the decision."""

    def __init__(self, home: Path, state_db: Path, connector=None):
        self.connector = connector
        self.operations: List[Dict[str, Any]] = []
        self.decision = 'failed'
        self.counts: Dict[str, int] = {}
        self.rows: List[Dict[str, Any]] = []
        self.path = self._select(home / 'memories_1.sqlite', state_db)

    def _failed(self, phase: str, exc: BaseException) -> None:
        self.operations.append({'phase': phase, 'outcome': 'failed', 'cause': type(exc).__name__,
                                'message': failure_of(exc).cause})

    def _select(self, memories_db: Path, state_db: Path) -> Path:
        for path in (memories_db, state_db):
            try:
                path.stat()
            except FileNotFoundError:
                continue
            except OSError as exc:
                self._failed('select', exc)
                return path
            self.operations.append({'phase': 'select', 'outcome': 'ok'})
            return path
        self.decision = 'source_absent'
        return memories_db

    def _count(self, conn, phase: str, sql: str) -> int:
        row = conn.execute(sql).fetchone()
        if row is None or type(row[0]) is not int or row[0] < 0:
            raise ValueError('SQLite aggregate returned no valid nonnegative count')
        self.operations.append({'phase': phase, 'outcome': 'ok', 'value': row[0]})
        return row[0]

    def _query(self, conn) -> None:
        phase = 'table'
        try:
            if not self._count(conn, phase, _TABLE):
                self.decision = 'table_absent'
                return
            for phase, sql in _COUNTS:
                self.counts[phase] = self._count(conn, phase, sql)
            phase = 'recent'
            self.rows = [dict(row) for row in conn.execute(_RECENT, (RECENT,)).fetchall()]
            self.operations.append({'phase': phase, 'outcome': 'ok', 'value': len(self.rows)})
            self.decision = 'read'
        except (sqlite3.Error, ValueError) as exc:
            self._failed(phase, exc)

    def read(self) -> 'PipelineRead':
        if self.failed_operations or self.decision == 'source_absent':
            return self
        conn = None
        try:
            conn = connect_readonly(self.path, self.connector)
            self.operations.append({'phase': 'open', 'outcome': 'ok'})
            self._query(conn)
        except (sqlite3.Error, OSError) as exc:
            self._failed('open', exc)
        finally:
            if conn is not None:
                try:
                    conn.close()
                    self.operations.append({'phase': 'close', 'outcome': 'ok'})
                except sqlite3.Error as exc:
                    self._failed('close', exc)
        if self.failed_operations:
            self.decision = 'failed'
        return self

    @property
    def failed_operations(self) -> int:
        return sum(op['outcome'] == 'failed' for op in self.operations)

    def receipt(self) -> Dict[str, Any]:
        return {'source': to_posix(self.path), 'decision': self.decision, 'operations': deepcopy(self.operations),
                'failed_operations': self.failed_operations, 'count_rule': PIPELINE_RULE}


def get_memories_pipeline(home: Path, state_db: Path, *, connector=None) -> Dict[str, Any]:
    read = PipelineRead(home, state_db, connector).read()
    result: Dict[str, Any] = dict(ResultBuilder.create(
        result_type='codex_memories_pipeline', source=to_posix(read.path), source_type='database',
        contract_version=CONTRACT_VERSION,
        data={'stage1_total': read.counts.get('stage1_total', 0),
              'stage2_selected': read.counts.get('stage2_selected', 0), 'recent_outputs': read.rows}))
    result.setdefault('meta', {'warnings': [], 'errors': []})['pipeline_analysis'] = read.receipt()
    if read.failed_operations:
        result['error'] = next(op['message'] for op in read.operations if op['outcome'] == 'failed')
        note_warning(result, {'type': 'analysis_incomplete', 'code': 'analysis_incomplete', 'field': 'pipeline_analysis',
                              'message': 'Required Codex memory pipeline input was lost; counts read before it are '
                                         'kept. Decisions: JSON meta.pipeline_analysis.'})
    elif 'stage1_total' in read.counts:
        note_truncation(result, 'recent_outputs', len(read.rows), read.counts['stage1_total'], 'pipeline_recent',
                        hint=f'the pipeline lists the newest {RECENT}; stage1_total counts every row')
    return result


def execution_facts(result):
    proof = result.get('meta', {}).get('pipeline_analysis', {})
    state = AnalysisCompleteness.COMPLETE
    if proof.get('failed_operations'):
        known = any(op.get('outcome') == 'ok' and op.get('phase') in ('stage1_total', 'stage2_selected', 'recent')
                    for op in proof.get('operations', ()))
        state = AnalysisCompleteness.INCOMPLETE if known else AnalysisCompleteness.FAILED
    return result_execution_facts(result, completeness=state)


def _proof_error(proof) -> Optional[str]:
    if not isinstance(proof, dict) or proof.get('count_rule') != PIPELINE_RULE or proof.get('decision') not in DECISIONS:
        return 'Codex memory pipeline missing its acquisition decision'
    operations = proof.get('operations')
    if not isinstance(operations, list) or not all(
            isinstance(op, dict) and op.get('phase') in _PHASES and op.get('outcome') in ('ok', 'failed')
            for op in operations):
        return 'Codex memory pipeline missing its operation decisions'
    failed = sum(op['outcome'] == 'failed' for op in operations)
    if proof.get('failed_operations') != failed or (proof['decision'] == 'failed') != bool(failed):
        return 'Codex memory pipeline loss disagrees with its operations'
    return None


def answer_requirement_error(adapter, result, prior_facts):
    proof = result.get('meta', {}).get('pipeline_analysis')
    error = _proof_error(proof)
    if error:
        return error
    if result.get('source') != proof['source'] or result.get('source_type') != 'database':
        return 'Codex memory pipeline changed its database source identity'
    expected = adapter._pipeline_answer
    if proof != expected['meta']['pipeline_analysis']:
        return 'Codex memory pipeline changed its acquisition decisions'
    for key in ('stage1_total', 'stage2_selected'):
        if type(result.get(key)) is not int or result[key] != expected[key]:
            return 'Codex memory pipeline changed its counts'
    if not isinstance(result.get('recent_outputs'), list):
        return 'Codex memory pipeline missing its recent outputs'
    return validate_observation_counts(result, count_observations(expected, (('recent_outputs',),)),
                                       count_observations(result, (('recent_outputs',),)),
                                       label='Codex memory pipeline')
