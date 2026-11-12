"""Prompt-history decisions from the shared JSONL reader, before display scope."""
from datetime import date, datetime
from typing import Any, Dict

from ...reveal_types import CONTRACT_VERSION
from ...utils.results import (AnalysisCompleteness, ExecutionFacts, FailureCause, ResultBuilder,
                              note_warning, result_execution_facts)
from .analysis.records import TranscriptRecords, valid_record_proof


def read_history(home, params, *, opener) -> Dict[str, Any]:
    path = home / 'history.jsonl'
    search, project = params.get('search', '').lower(), params.get('project', '').lower()
    since = params.get('since', '')
    since = date.today().isoformat() if since == 'today' else since
    reader = TranscriptRecords(path, replace_decode=True, opener=opener)
    entries, interpreted, error = _read_entries(reader, since, search, project)
    proof = {**reader.receipt(), 'analyzed_entries': interpreted,
             'failed_entries': reader.analyzed - interpreted,
             'request_absent': not reader.opened and isinstance(error, FileNotFoundError),
             'source_opened': reader.opened,
             'count_rule': 'All nonblank history records before date/project/text/display filters; decoded objects are interpreted until EOF or the first required operation failure'}
    result: Dict[str, Any] = dict(ResultBuilder.create(
        'claude_history', str(path), source_type='file', contract_version=CONTRACT_VERSION,
        data={'search': search or None, 'project': project or None, 'since': since or None,
              'total_entries': reader.analyzed, 'match_count': len(entries), 'entries': entries},
        meta={'history_analysis': proof, 'warnings': [], 'errors': []}))
    if error is not None:
        result['error'] = f'History file not found: {path}' if proof['request_absent'] else str(error)
    if proof['request_absent']:
        result['meta']['errors'].append({'code': 'invalid_request', 'message': result['error']})
    elif _lost(proof):
        note_warning(result, {'type': 'analysis_incomplete', 'code': 'analysis_incomplete',
                              'field': 'history_analysis',
                              'message': 'Required prompt history records were lost or repaired. Decisions: JSON meta.history_analysis.'})
    return result


def _read_entries(reader, since, search, project):
    entries, interpreted, error = [], 0, None
    try:
        for record in reader.records():
            entry = _history_entry(record, since, search, project)
            interpreted += 1
            if entry is not None:
                entries.append(entry)
    except (OSError, ValueError, OverflowError) as exc:
        error = exc
        if not reader.failures:
            reader.failures.append({'phase': 'analysis', 'cause': type(exc).__name__, 'message': str(exc)})
    entries.reverse()
    return entries, interpreted, error


def _history_entry(record, since, search, project_filter):
    prompt, project = record.get('display', ''), record.get('project', '')
    timestamp = record.get('timestamp', 0)
    iso = datetime.fromtimestamp(timestamp / 1000).isoformat(timespec='seconds') if timestamp else ''
    if since and iso[:10] < since:
        return None
    if search and search not in prompt.lower():
        return None
    if project_filter and project_filter not in project.lower():
        return None
    return {'prompt': prompt, 'project': project, 'timestamp': iso, 'session_id': record.get('sessionId')}


def _lost(proof):
    return bool(proof.get('failed_records') or proof.get('recovered_records') or proof.get('failures')
                or proof.get('decision') != 'exhausted')


def history_execution_facts(result):
    errors = result.get('meta', {}).get('errors', ())
    if any(error.get('code') == 'invalid_adapter_answer' for error in errors):
        return result_execution_facts(result, completeness=AnalysisCompleteness.FAILED)
    proof = result.get('meta', {}).get('history_analysis', {})
    if proof.get('request_absent'):
        return result_execution_facts(result, completeness=AnalysisCompleteness.COMPLETE,
                                      failure_cause=FailureCause.INVALID_REQUEST)
    state = AnalysisCompleteness.COMPLETE
    if _lost(proof):
        if proof.get('analyzed_entries'):
            # Legacy transports retain their error marker; this owner measures usable partial entries.
            return ExecutionFacts(AnalysisCompleteness.INCOMPLETE)
        state = AnalysisCompleteness.FAILED
    return result_execution_facts(result, completeness=state)


def history_requirement_error(adapter, result, prior_facts):
    from copy import deepcopy
    proof = result.get('meta', {}).get('history_analysis')
    error = _proof_error(proof, result)
    if error:
        return error
    if prior_facts is None:
        adapter._history_proof = deepcopy(proof)
    if proof != adapter._history_proof:
        return 'Claude presentation cannot change history source decisions'
    return None


def _proof_error(proof, result):
    from ...utils.observations import has_truncation_receipt
    if not valid_record_proof(proof):
        return 'Claude history answer missing consistent record decisions'
    keys = ('analyzed_entries', 'failed_entries', 'recovered_records')
    if not all(type(proof.get(key)) is int and proof[key] >= 0 for key in keys):
        return 'Claude history answer missing nonnegative source counts'
    if proof['analyzed_entries'] + proof['failed_entries'] != proof['analyzed_records']:
        return 'Claude history payload counts disagree with decoded records'
    rows, count = result.get('entries'), result.get('match_count')
    if not isinstance(rows, list) or type(count) is not int or count < 0:
        return 'Claude history answer missing observations and count'
    if count != len(rows) and not has_truncation_receipt(result, ('entries',), len(rows), count):
        return 'Claude history count disagrees with display observations'
    return None
