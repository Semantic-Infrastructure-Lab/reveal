"""Installation path slots and independent read-only SQLite count observations."""
from reveal.utils.path_utils import to_posix
import sqlite3
from typing import Any, Dict

from ...utils.path_inventory import valid_path_info, path_counts
from ...utils.results import AnalysisCompleteness, note_warning, result_execution_facts
from .lookup import USER_FILTER, connect_readonly

PATH_KEYS = ('codex_home', 'db', 'sessions_dir', 'history', 'config', 'memories', 'rules')
QUERIES = (('total_threads', 'SELECT COUNT(*) FROM threads'),
           ('user_sessions', f'SELECT COUNT(*) FROM threads WHERE {USER_FILTER}'))
INFO_RULE = 'Seven named path slots, including confirmed absence, counted independently of aliases; SQLite aggregate observations are sequential reads, not an atomic cross-query census'


def _failure(phase, exc):
    return {'phase': phase, 'outcome': 'failed', 'cause': type(exc).__name__, 'message': str(exc)}


def _query_counts(conn, stats, operations):
    for field, sql in QUERIES:
        try:
            row = conn.execute(sql).fetchone()
            if row is None or type(row[0]) is not int or row[0] < 0:
                raise ValueError('SQLite aggregate returned no valid nonnegative count')
            stats[field] = row[0]
            operations.append({'phase': field, 'outcome': 'ok', 'value': row[0]})
        except (sqlite3.Error, OSError, ValueError) as exc:
            operations.append(_failure(field, exc))
            stats['error'] = str(exc)
            break


def read_db_stats(path, present, *, connector):
    stats: Dict[str, Any] = {}
    operations: list[dict[str, Any]] = []
    if present is not True:
        return stats, operations
    conn = None
    try:
        conn = connect_readonly(path, connector)
        operations.append({'phase': 'open', 'outcome': 'ok'})
        _query_counts(conn, stats, operations)
    except (sqlite3.Error, OSError) as exc:
        operations.append(_failure('open', exc))
        stats['error'] = str(exc)
    finally:
        if conn is not None:
            try:
                conn.close()
                operations.append({'phase': 'close', 'outcome': 'ok'})
            except (sqlite3.Error, OSError) as exc:
                operations.append(_failure('close', exc))
                stats['error'] = str(exc)
    return stats, operations


def attach_info_evidence(result: Dict[str, Any], operations) -> Dict[str, Any]:
    proof = {**path_counts(result['paths']), 'db_operations': operations,
             'failed_db_operations': sum(op['outcome'] == 'failed' for op in operations), 'count_rule': INFO_RULE}
    result.setdefault('meta', {'warnings': [], 'errors': []})['info_analysis'] = proof
    if proof['failed_paths'] or proof['failed_db_operations']:
        note_warning(result, {'type': 'analysis_incomplete', 'code': 'analysis_incomplete', 'field': 'info_analysis',
                              'message': 'Required Codex installation inspection lost metadata or DB operations; known observations retained. See JSON meta.info_analysis.'})
    return result


def execution_facts(result):
    proof = result.get('meta', {}).get('info_analysis', {})
    state = AnalysisCompleteness.COMPLETE
    if proof.get('failed_paths') or proof.get('failed_db_operations'):
        state = AnalysisCompleteness.INCOMPLETE if proof.get('usable_paths') else AnalysisCompleteness.FAILED
    return result_execution_facts(result, completeness=state)


def _proof_error(proof, paths):
    if not isinstance(proof, dict) or proof.get('count_rule') != INFO_RULE:
        return 'Codex info missing required inspection decisions'
    for key, count in path_counts(paths).items():
        if type(proof.get(key)) is not int or proof[key] != count:
            return 'Codex info counts disagree with its path observations'
    operations = proof.get('db_operations')
    if not isinstance(operations, list) or not all(_valid_operation(op) for op in operations):
        return 'Codex info missing database operation decisions'
    failed = sum(op['outcome'] == 'failed' for op in operations)
    if type(proof.get('failed_db_operations')) is not int or proof['failed_db_operations'] != failed:
        return 'Codex info database loss count disagrees with operations'
    return None


def _valid_operation(op):
    if not isinstance(op, dict) or op.get('outcome') not in ('ok', 'failed'):
        return False
    if op.get('phase') not in ('open', 'total_threads', 'user_sessions', 'close'):
        return False
    if op['outcome'] == 'ok' and op['phase'] in ('total_threads', 'user_sessions'):
        return type(op.get('value')) is int and op['value'] >= 0
    return True


def _stats_error(stats, paths, proof):
    if not isinstance(stats, dict):
        return 'Codex info missing database statistics'
    for field, _ in QUERIES:
        if field in stats and (type(stats[field]) is not int or stats[field] < 0):
            return 'Codex info missing known nonnegative database counts'
    if paths['db']['exists'] is True and not proof['failed_db_operations']:
        if not all(field in stats for field, _ in QUERIES):
            return 'Codex info lost completed database counts'
    return None


def answer_requirement_error(adapter, result, prior_facts):
    if result.get('source') != to_posix(adapter.CODEX_DB) or result.get('source_type') != 'database':
        return 'Codex info changed its database source identity'
    paths = result.get('paths')
    if not isinstance(paths, dict) or set(paths) != set(PATH_KEYS) or not all(valid_path_info(row) for row in paths.values()):
        return 'Codex info missing measured path slots'
    proof = result.get('meta', {}).get('info_analysis')
    error = _proof_error(proof, paths)
    if error:
        return error
    error = _stats_error(result.get('db_stats'), paths, proof)
    if error:
        return error
    expected = adapter._info_answer
    if (proof != expected['meta']['info_analysis'] or paths != expected['paths']
            or result.get('db_stats') != expected['db_stats']):
        return 'Codex info changed its inspection decisions or observations'
    return None
