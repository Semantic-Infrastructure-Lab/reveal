"""Measured acquisition of the existing settings/config JSON documents."""
from typing import Any, Dict

from ...utils.results import (AnalysisCompleteness, ExecutionFacts, FailureCause,
                              note_warning, result_execution_facts)
from ...utils.query_parser import peek_query_items
from ...utils.document_read import DocumentRead as JsonDocumentRead, document_proof_error



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
    return document_proof_error(proof, label='Claude installation')
