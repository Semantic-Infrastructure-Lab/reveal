"""Measured acquisition of the existing settings/config JSON documents."""
from contextlib import contextmanager
from typing import Any, Dict

from ...utils.results import (AnalysisCompleteness, ExecutionFacts, FailureCause,
                              note_warning, result_execution_facts)
from ...utils.query_parser import peek_query_items


class JsonDocumentRead:
    def __init__(self, path):
        self.path = path
        self.selected = self.parsed = self.usable = False
        self.operations: list[Dict[str, Any]] = []

    @contextmanager
    def operation(self, phase, *, missing_request=False):
        try:
            yield
        except (OSError, ValueError) as exc:
            self.error(phase, exc, rejected=missing_request and isinstance(exc, FileNotFoundError))
            raise
        else:
            self.operations.append({'phase': phase, 'outcome': 'ok'})

    def select(self):
        with self.operation('select', missing_request=True):
            self.path.stat()
        self.selected = True

    def error(self, phase, exc, *, rejected=False):
        self.operations.append({'phase': phase, 'outcome': 'rejected' if rejected else 'failed',
                                'cause': type(exc).__name__, 'message': str(exc)})

    def repair(self, text):
        with self.operation('decode'):
            repaired = text.encode('utf-8', errors='surrogateescape').decode('utf-8', errors='replace')
        if repaired != text:
            self.operations[-1]['outcome'] = 'recovered'
            self.operations[-1]['message'] = 'Invalid UTF-8 bytes replaced using the existing config codec'
        return repaired

    def attach(self, result: Dict[str, Any]) -> Dict[str, Any]:
        states = [op['outcome'] for op in self.operations]
        proof = {'source': str(self.path), 'selected': self.selected, 'parsed': self.parsed,
                 'usable': self.usable, 'failed_operations': states.count('failed'),
                 'recovered_operations': states.count('recovered'),
                 'request_rejected': 'rejected' in states, 'operations': list(self.operations),
                 'count_rule': 'Authored selection/read/parse/decode stages and failed key/root validation; not syscall counts or universal payload validation'}
        result.setdefault('meta', {})['installation_analysis'] = proof
        if proof['request_rejected']:
            result['meta'].setdefault('errors', []).append({'code': 'invalid_request', 'message': result['error']})
        if proof['failed_operations'] or proof['recovered_operations']:
            note_warning(result, {'type': 'analysis_incomplete', 'code': 'analysis_incomplete',
                                  'field': 'installation_analysis',
                                  'message': 'Required installation JSON input was lost or repaired. Decisions: JSON meta.installation_analysis.'})
        return result


def installation_execution_facts(result):
    meta = result.get('meta', {})
    if any(e.get('code') == 'invalid_adapter_answer' for e in meta.get('errors', ())):
        return result_execution_facts(result, completeness=AnalysisCompleteness.FAILED)
    proof = meta.get('installation_analysis', {})
    if proof.get('request_rejected'):
        return result_execution_facts(result, completeness=AnalysisCompleteness.COMPLETE,
                                      failure_cause=FailureCause.INVALID_REQUEST)
    if proof.get('failed_operations') or proof.get('recovered_operations'):
        if proof.get('usable'):
            return ExecutionFacts(AnalysisCompleteness.INCOMPLETE)
        return result_execution_facts(result, completeness=AnalysisCompleteness.FAILED)
    return result_execution_facts(result, completeness=AnalysisCompleteness.COMPLETE)


def installation_requirement_error(adapter, result, expected_type, prior_facts):
    from copy import deepcopy
    proof = result.get('meta', {}).get('installation_analysis')
    error = _proof_error(proof)
    if error:
        return error
    if proof.get('source') != result.get('source'):
        return 'Claude installation source identity disagrees with acquisition decisions'
    if prior_facts is None:
        adapter._installation_proof = deepcopy(proof)
    if proof != adapter._installation_proof:
        return 'Claude presentation cannot change installation source decisions'
    if result.get('error'):
        return None
    fields = installation_fields(adapter, expected_type)
    if not all(key in result and isinstance(result[key], kind) for key, kind in fields.items()):
        return 'Claude installation answer missing required JSON observations'
    if expected_type == 'claude_config' and 'projects' in fields:
        count = result.get('projects_count')
        if type(count) is not int or count < len(result['projects']):
            return 'Claude config answer missing consistent project count'
    return None


def installation_fields(adapter, expected_type):
    key = dict(peek_query_items(adapter.query_params)).get('key', '')
    if expected_type == 'claude_config':
        key = key.strip()
    if key:
        return {'value': object}
    return {'settings': object} if expected_type == 'claude_settings' else {'projects': list, 'flags': dict}


def installation_scalar_error(adapter, result, fields, prior_facts):
    scalars = {key: (type(result[key]), result[key]) for key in fields
               if key in result and not isinstance(result[key], (list, str, dict))}
    if prior_facts is None:
        adapter._installation_scalars = scalars
    if scalars != adapter._installation_scalars:
        return 'Claude presentation cannot change installation scalar observations'
    return None


def _proof_error(proof):
    if not isinstance(proof, dict):
        return 'Claude installation answer missing source decisions'
    if not all(type(proof.get(k)) is bool for k in ('selected', 'parsed', 'usable', 'request_rejected')):
        return 'Claude installation answer missing source states'
    if (proof['usable'] and not proof['parsed']) or (proof['parsed'] and not proof['selected']):
        return 'Claude installation source states are inconsistent'
    operations = proof.get('operations')
    if not isinstance(operations, list) or not operations:
        return 'Claude installation answer missing acquisition stages'
    if not all(isinstance(op, dict) and op.get('outcome') in ('ok', 'failed', 'recovered', 'rejected')
               and isinstance(op.get('phase'), str) for op in operations):
        return 'Claude installation acquisition stages are inconsistent'
    return _counts_error(proof, operations)


def _counts_error(proof, operations):
    states = [op['outcome'] for op in operations]
    for key, state in (('failed_operations', 'failed'), ('recovered_operations', 'recovered')):
        if type(proof.get(key)) is not int or proof[key] != states.count(state):
            return 'Claude installation counts disagree with acquisition stages'
    if proof['request_rejected'] != ('rejected' in states):
        return 'Claude installation request state disagrees with acquisition stages'
    return None
