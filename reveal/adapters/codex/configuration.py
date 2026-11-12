"""Execution facts and immutable masked observations for Codex TOML config."""
import math

from ...utils.document_read import document_proof_error
from ...utils.results import AnalysisCompleteness, FailureCause, failure_execution_facts, result_execution_facts


def execution_facts(result):
    proof = result.get('meta', {}).get('installation_analysis', {})
    if proof.get('request_rejected'):
        cause = FailureCause.ANALYSIS if proof.get('failed_operations') else FailureCause.INVALID_REQUEST
        return failure_execution_facts(cause)
    state = AnalysisCompleteness.COMPLETE
    if proof.get('failed_operations'):
        state = AnalysisCompleteness.INCOMPLETE if proof.get('usable') else AnalysisCompleteness.FAILED
    return result_execution_facts(result, completeness=state)


def _same_value(left, right):
    if type(left) is not type(right):
        return False
    if left is right:
        return True
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_same_value(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_same_value(a, b) for a, b in zip(left, right))
    if isinstance(left, float) and math.isnan(left):
        return math.isnan(right)
    return left == right


def answer_requirement_error(adapter, result, prior_facts):
    if result.get('source') != str(adapter.CODEX_HOME / 'config.toml') or result.get('source_type') != 'file':
        return 'Codex config changed its TOML source identity'
    proof = result.get('meta', {}).get('installation_analysis')
    error = document_proof_error(proof, label='Codex configuration')
    if error:
        return error
    expected = adapter._config_answer
    if proof != expected['meta']['installation_analysis']:
        return 'Codex configuration changed its source acquisition decisions'
    for key in ('config', 'key', 'value', 'error'):
        if (key in result) != (key in expected) or not _same_value(result.get(key), expected.get(key)):
            return 'Codex configuration changed its masked observations or request diagnostic'
    return None
