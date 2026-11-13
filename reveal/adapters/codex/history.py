"""Measured acquisition of Codex history's native JSON values and raw fallbacks."""
from reveal.utils.path_utils import to_posix
from typing import Any, Dict

from ...reveal_types import CONTRACT_VERSION
from ...utils.jsonl_records import TranscriptRecords, valid_record_proof
from ...utils.observations import count_observations, validate_observation_counts
from ...utils.results import (AnalysisCompleteness, ExecutionFacts, FailureCause, ResultBuilder,
                              note_warning, result_execution_facts)

HISTORY_RULE = 'All consumed nonblank history lines before display cuts; any valid JSON value is decoded, invalid JSON is retained as a raw fallback without establishing successful parsing'


def _lost(proof):
    return bool(proof.get('failed_records') or proof.get('recovered_records') or proof.get('failures')
                or proof.get('decision') != 'exhausted')


def read_history(home, *, opener) -> Dict[str, Any]:
    path = home / 'history.jsonl'
    reader = TranscriptRecords(path, replace_decode=True, opener=opener, objects_only=False, keep_invalid=True)
    entries: list[Any] = []
    error: Exception | None = None
    try:
        entries.extend(reader.records())
    except (OSError, UnicodeDecodeError) as exc:
        error = exc
    proof = {**reader.receipt(), 'opened': reader.opened,
             'request_absent': not reader.opened and isinstance(error, FileNotFoundError),
             'retained_entries': len(entries), 'value_policy': 'all_json_values',
             'invalid_policy': 'raw_fallback', 'count_rule': HISTORY_RULE}
    result: Dict[str, Any] = dict(ResultBuilder.create(
        'codex_history', to_posix(path), source_type='file', contract_version=CONTRACT_VERSION,
        data={'entries': entries, 'total_entries': len(entries)},
        meta={'history_analysis': proof, 'warnings': [], 'errors': []}))
    if error is not None:
        result['error'] = f'History file not found: {path}' if proof['request_absent'] else str(error)
    if proof['request_absent']:
        result['meta']['errors'].append({'code': 'invalid_request', 'message': result['error']})
    elif _lost(proof):
        note_warning(result, {'type': 'analysis_incomplete', 'code': 'analysis_incomplete', 'field': 'history_analysis',
                              'message': 'Required Codex history input was lost or repaired; decoded prefixes and raw fallbacks retained. See JSON meta.history_analysis.'})
    return result


def execution_facts(result):
    proof = result.get('meta', {}).get('history_analysis', {})
    if proof.get('request_absent'):
        return result_execution_facts(result, completeness=AnalysisCompleteness.COMPLETE,
                                      failure_cause=FailureCause.INVALID_REQUEST)
    if _lost(proof):
        if proof.get('analyzed_records'):
            return ExecutionFacts(AnalysisCompleteness.INCOMPLETE)
        return result_execution_facts(result, completeness=AnalysisCompleteness.FAILED)
    return result_execution_facts(result, completeness=AnalysisCompleteness.COMPLETE)


def _proof_error(proof):
    if not valid_record_proof(proof):
        return 'Codex history missing consistent JSON record decisions'
    if (type(proof.get('retained_entries')) is not int or proof['retained_entries'] != proof['candidate_records']
            or type(proof.get('opened')) is not bool or type(proof.get('request_absent')) is not bool):
        return 'Codex history missing consistent source and raw-retention decisions'
    if (proof.get('value_policy') != 'all_json_values' or proof.get('invalid_policy') != 'raw_fallback'
            or proof.get('count_rule') != HISTORY_RULE):
        return 'Codex history changed its native value or recovery policy'
    return None


def answer_requirement_error(adapter, result, prior_facts):
    if result.get('source') != to_posix(adapter.CODEX_HOME / 'history.jsonl') or result.get('source_type') != 'file':
        return 'Codex history changed its required source identity'
    proof = result.get('meta', {}).get('history_analysis')
    error = _proof_error(proof)
    if error:
        return error
    expected = adapter._history_answer
    if (proof != expected['meta']['history_analysis'] or ('error' in result) != ('error' in expected)
            or result.get('error') != expected.get('error')):
        return 'Codex history changed its source decisions or diagnostic'
    if (not isinstance(result.get('entries'), list) or type(result.get('total_entries')) is not int
            or result['total_entries'] != expected['total_entries']):
        return 'Codex history changed its retained entry observations or source count'
    return validate_observation_counts(result, count_observations(expected, (('entries',),)),
                                       count_observations(result, (('entries',),)), label='Codex history')
