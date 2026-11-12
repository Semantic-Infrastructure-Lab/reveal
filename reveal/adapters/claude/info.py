"""Measured path-slot inventory for the existing installation diagnostic view."""
from copy import deepcopy
from typing import Any, Dict
from ...utils.path_inventory import valid_path_info as _valid_path, path_counts as _counts

from ...utils.results import (AnalysisCompleteness, ExecutionFacts, note_warning,
                              result_execution_facts)

PATH_KEYS = ('claude_home', 'projects', 'history', 'plans', 'settings', 'config', 'agents', 'hooks')
ENV_KEYS = ('REVEAL_CLAUDE_HOME', 'REVEAL_CLAUDE_JSON', 'REVEAL_CLAUDE_DIR', 'REVEAL_SESSIONS_DIR')




def attach_info_evidence(result: Dict[str, Any]) -> Dict[str, Any]:
    paths = result['paths']
    proof = {**_counts(paths),
             'count_rule': 'Eight named path slots, including confirmed absence; directory count failures retain known metadata; slots count independently of path aliases',
             'failures': [{'slot': slot, 'source': row['path'], 'phase': row['error_phase'],
                           'cause': row['cause'], 'message': row['error']}
                          for slot, row in paths.items() if row.get('error')]}
    result.setdefault('meta', {})['info_analysis'] = proof
    metadata_error = next((row['error'] for row in paths.values() if row.get('error_phase') == 'metadata'), None)
    if metadata_error:
        # Keep the legacy failure marker while qualified facts retain partial inventory data.
        result['error'] = metadata_error
    if proof['failed_paths']:
        note_warning(result, {'type': 'analysis_incomplete', 'code': 'analysis_incomplete',
                              'field': 'info_analysis',
                              'message': 'Required installation path inspection failed. Known metadata is retained. Decisions: JSON meta.info_analysis.'})
    return result


def info_execution_facts(result):
    meta = result.get('meta', {})
    if any(e.get('code') == 'invalid_adapter_answer' for e in meta.get('errors', ())):
        return result_execution_facts(result, completeness=AnalysisCompleteness.FAILED)
    proof = meta.get('info_analysis', {})
    if proof.get('failed_paths'):
        if proof.get('usable_paths'):
            return ExecutionFacts(AnalysisCompleteness.INCOMPLETE)
        return result_execution_facts(result, completeness=AnalysisCompleteness.FAILED)
    return result_execution_facts(result, completeness=AnalysisCompleteness.COMPLETE)


def info_requirement_error(adapter, result, prior_facts):
    paths, env = result.get('paths'), result.get('env')
    if not isinstance(paths, dict) or set(paths) != set(PATH_KEYS) or not all(_valid_path(row) for row in paths.values()):
        return 'Claude info answer missing measured path slots'
    if (not isinstance(env, dict) or set(env) != set(ENV_KEYS)
            or not all(isinstance(value, str) for value in env.values()) or 'sessions_dir' not in result):
        return 'Claude info answer missing environment observations'
    proof = result.get('meta', {}).get('info_analysis')
    error = _proof_error(proof, paths)
    if error:
        return error
    observations = {'paths': paths, 'env': env, 'sessions_dir': result.get('sessions_dir')}
    if prior_facts is None:
        adapter._info_proof, adapter._info_observations = deepcopy(proof), deepcopy(observations)
    if proof != adapter._info_proof or observations != adapter._info_observations:
        return 'Claude presentation cannot change installation inventory decisions or observations'
    return None




def _proof_error(proof, paths):
    if not isinstance(proof, dict):
        return 'Claude info answer missing path acquisition decisions'
    for key, expected in _counts(paths).items():
        if type(proof.get(key)) is not int or proof[key] != expected:
            return 'Claude info counts disagree with path observations'
    failures = proof.get('failures')
    if not isinstance(failures, list) or len(failures) != proof['failed_paths']:
        return 'Claude info answer missing path failure decisions'
    return None
