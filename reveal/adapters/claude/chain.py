"""Qualified execution of the existing optional README continuation traversal."""
from pathlib import Path
from typing import Any, Dict, Optional
from ...utils.results import AnalysisCompleteness, note_warning, result_execution_facts
from .discovery import Failures, _diagnostics


class ChainTraversal:
    def __init__(self, root: Optional[Path], find_readme, parse_frontmatter):
        self.root, self.find_readme, self.parse_frontmatter = root, find_readme, parse_frontmatter
        self.failures: Failures = []
        self.entries: list[Dict[str, Any]] = []
        self.parsed = 0
        self.stop = 'end'

    def walk(self, current):
        seen = set()
        while current and current not in seen and len(self.entries) < 50:
            seen.add(current)
            current = self._step(current)
        if current:
            self.stop = 'cycle' if current in seen else 'limit'
        return self.entries

    def _step(self, name):
        before = len(self.failures)
        path = self.find_readme(name, self.root, self.failures)
        parse_before = len(self.failures)
        metadata = self.parse_frontmatter(path, self.failures) if path else {}
        self.parsed += bool(path) and len(self.failures) == parse_before
        self.entries.append(_chain_entry(name, path, metadata))
        following = metadata.get('continuing_from')
        if following and not isinstance(following, str):
            self.failures.append((path, ValueError('continuing_from must be a session-name string')))
            following = None
        if not following:
            self.stop = _terminal_reason(self.root, path, len(self.failures) > before)
        return following

    def attach(self, result: Dict[str, Any]) -> Dict[str, Any]:
        proof = {
            'visited_sessions': len(self.entries),
            'readmes_found': sum(row['readme'] is not None for row in self.entries),
            'parsed_readmes': self.parsed, 'failed_operations': len(self.failures),
            'stop_reason': self.stop, 'failures': _diagnostics(self.failures),
            'count_rule': 'Optional latest README per visited session; missing README or unconfigured source retains one terminal null entry; traversal capped at 50 unique sessions',
        }
        result.setdefault('meta', {})['chain_analysis'] = proof
        if self.failures or self.stop == 'limit':
            note_warning(result, {'type': 'analysis_incomplete', 'code': 'analysis_incomplete',
                                  'field': 'chain_analysis',
                                  'message': 'Required continuation metadata was lost or the source traversal cap was reached. Decisions: JSON meta.chain_analysis.'})
        return result


def _terminal_reason(root, path, failed):
    if failed:
        return 'required-loss'
    if root is None:
        return 'unconfigured'
    return 'end' if path else 'missing-readme'


def _chain_entry(name, path, metadata):
    return {'session': name, 'readme': str(path) if path else None,
            'date': metadata.get('date') or metadata.get('session_date'),
            **{key: metadata.get(key) for key in ('badge', 'continuing_from', 'tests_start', 'tests_end', 'commits')}}


def chain_execution_facts(result):
    proof = result.get('meta', {}).get('chain_analysis', {})
    state = AnalysisCompleteness.COMPLETE
    if proof.get('failed_operations') or proof.get('stop_reason') == 'limit':
        state = AnalysisCompleteness.INCOMPLETE if proof.get('parsed_readmes') else AnalysisCompleteness.FAILED
    return result_execution_facts(result, completeness=state)


def chain_requirement_error(adapter, result, prior_facts):
    from copy import deepcopy
    proof = result.get('meta', {}).get('chain_analysis')
    error = _proof_error(proof, result)
    if error:
        return error
    if prior_facts is None:
        adapter._chain_proof = deepcopy(proof)
    if proof != adapter._chain_proof:
        return 'Claude presentation cannot change continuation source decisions'
    return None


def _proof_error(proof, result):
    if not isinstance(proof, dict):
        return 'Claude chain answer missing source decisions'
    counts = ('visited_sessions', 'readmes_found', 'parsed_readmes', 'failed_operations')
    if not all(type(proof.get(k)) is int and proof[k] >= 0 for k in counts):
        return 'Claude chain answer missing nonnegative source counts'
    error = _chain_observation_error(proof, result)
    return error or _decision_error(proof)


def _chain_observation_error(proof, result):
    from ...utils.observations import has_truncation_receipt
    rows = result.get('chain')
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        return 'Claude chain answer missing session observations'
    total = proof['visited_sessions']
    if result.get('chain_length') != total or proof['readmes_found'] > total:
        return 'Claude chain count disagrees with observed sessions'
    if total != len(rows) and not has_truncation_receipt(result, ('chain',), len(rows), total):
        return 'Claude chain display cut missing its source count receipt'
    visible_readmes = sum(row.get('readme') is not None for row in rows)
    if proof['readmes_found'] < visible_readmes or (total == len(rows) and proof['readmes_found'] != visible_readmes):
        return 'Claude chain count disagrees with observed READMEs'
    return None


def _decision_error(proof):
    if proof['parsed_readmes'] > proof['readmes_found']:
        return 'Claude chain parsed count exceeds selected READMEs'
    failures = proof.get('failures')
    if not isinstance(failures, list) or len(failures) != proof['failed_operations']:
        return 'Claude chain missing source failure decisions'
    if proof.get('stop_reason') not in ('end', 'cycle', 'limit', 'unconfigured', 'missing-readme', 'required-loss'):
        return 'Claude chain missing traversal termination decision'
    return None
