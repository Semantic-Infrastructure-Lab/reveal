"""Acquisition of named workspace-list entries, before content filtering."""
import stat
from pathlib import Path
from typing import Any, Dict

from ...utils.results import (AnalysisCompleteness, ExecutionFacts, FailureCause,
                              note_warning, result_execution_facts)


class WorkspaceScan:
    def __init__(self, *, legacy_discovery_error=False):
        self.candidates: set[str] = set()
        self.completed: set[str] = set()
        self.filtered: set[str] = set()
        self.recovered: set[str] = set()
        self.entry_errors: list[tuple[Path, BaseException]] = []
        self.ordering_errors: list[tuple[Path, BaseException]] = []
        self.discovery_errors: list[tuple[Path, BaseException]] = []
        self.legacy_errors: list[tuple[Path, BaseException]] = []
        self.request_rejected = False
        self.root_error = ''
        self.legacy_discovery_error = legacy_discovery_error

    def directory(self, path, *, required=False):
        try:
            directory = stat.S_ISDIR(path.stat().st_mode)
            if required and not directory:
                raise NotADirectoryError(str(path))
            return directory
        except (FileNotFoundError, NotADirectoryError) as exc:
            if required:
                self.request_rejected = True
                self.root_error = str(exc)
            return False
        except OSError as exc:
            self.discovery_errors.append((path, exc))
            if self.legacy_discovery_error:
                self.legacy_errors.append((path, exc))
            self.root_error = str(exc)
            return False

    def entries(self, path, *, legacy_error=False):
        entries = []
        try:
            for entry in path.iterdir():
                entries.append(entry)
        except OSError as exc:
            self.discovery_errors.append((path, exc))
            if legacy_error:
                self.legacy_errors.append((path, exc))
        return entries

    def markdown(self, path):
        entries = [p for p in self.entries(path) if p.match('*.md')]
        self.candidates.update(str(p) for p in entries)
        return entries

    def read_text(self, path):
        text = path.read_text(encoding='utf-8', errors='surrogateescape')
        repaired = text.encode('utf-8', errors='surrogateescape').decode('utf-8', errors='replace')
        if repaired != text:
            self.recovered.add(str(path))
        return repaired

    def complete(self, path, *, filtered=False):
        self.completed.add(str(path))
        if filtered:
            self.filtered.add(str(path))

    def count_directory(self, path):
        return sum(1 for _ in path.iterdir())

    def attach(self, result: Dict[str, Any]) -> Dict[str, Any]:
        required_order = [(p, e) for p, e in self.ordering_errors if str(p) not in self.filtered]
        failures = [('discovery', p, e) for p, e in self.discovery_errors]
        failures += [('entry', p, e) for p, e in self.entry_errors]
        failures += [('ordering', p, e) for p, e in required_order]
        proof = {
            'candidate_entries': len(self.candidates), 'analyzed_entries': len(self.completed),
            'failed_entries': len(self.candidates - self.completed),
            'discovery_failures': len(self.discovery_errors), 'failed_operations': len(failures),
            'recovered_entries': len(self.recovered),
            'advisory_ordering_failures': len(self.ordering_errors) - len(required_order),
            'request_rejected': self.request_rejected,
            'failures': [{'phase': phase, 'source': str(p), 'cause': type(e).__name__, 'message': str(e)}
                         for phase, p, e in failures],
            'count_rule': 'Named entries after project scope and before content/display filters; analyzed plus failed equals candidates; required ordering/discovery failures count separately; aliases remain separate entries',
        }
        result.setdefault('meta', {})['workspace_analysis'] = proof
        if self.request_rejected:
            result['meta'].setdefault('errors', []).append({'code': 'invalid_request', 'message': result['error']})
        if self.legacy_errors and not result.get('error'):
            result['error'] = str(self.legacy_errors[0][1])
        if failures or self.recovered:
            note_warning(result, {'type': 'analysis_incomplete', 'code': 'analysis_incomplete',
                                  'field': 'workspace_analysis',
                                  'message': 'Required workspace input was lost or repaired. Decisions: JSON meta.workspace_analysis.'})
        return result


LIST_FIELDS = {'claude_plans': 'plans', 'claude_agents': 'agents',
               'claude_memory': 'memories', 'claude_hooks': 'hooks'}


def workspace_listing_type(resource):
    path = resource.partition('?')[0]
    noun, _, name = path.partition('/')
    if noun == 'memory' and '/chain' not in path:
        return 'claude_memory'
    if not name.strip():
        return {'plans': 'claude_plans', 'agents': 'claude_agents', 'hooks': 'claude_hooks'}.get(noun)
    return None


def workspace_execution_facts(result):
    meta = result.get('meta', {})
    if any(e.get('code') == 'invalid_adapter_answer' for e in meta.get('errors', ())):
        return result_execution_facts(result, completeness=AnalysisCompleteness.FAILED)
    proof = meta.get('workspace_analysis', {})
    if proof.get('request_rejected'):
        return result_execution_facts(result, completeness=AnalysisCompleteness.COMPLETE,
                                      failure_cause=FailureCause.INVALID_REQUEST)
    if proof.get('failed_operations') or proof.get('recovered_entries'):
        if proof.get('analyzed_entries'):
            return ExecutionFacts(AnalysisCompleteness.INCOMPLETE)
        return result_execution_facts(result, completeness=AnalysisCompleteness.FAILED)
    return result_execution_facts(result, completeness=AnalysisCompleteness.COMPLETE)


def workspace_requirement_error(adapter, result, expected_type, prior_facts):
    from copy import deepcopy
    proof = result.get('meta', {}).get('workspace_analysis')
    error = _proof_error(proof)
    if error:
        return error
    if prior_facts is None:
        adapter._workspace_proof = deepcopy(proof)
    if proof != adapter._workspace_proof:
        return 'Claude presentation cannot change workspace acquisition decisions'
    field = LIST_FIELDS[expected_type]
    if not isinstance(result.get(field), list):
        return 'Claude workspace answer missing entry observations'
    count = result.get('displayed' if expected_type in ('claude_plans', 'claude_agents') else 'total')
    if result.get('error') and not result[field]:
        return None
    if type(count) is not int or count != len(result[field]):
        return 'Claude workspace entry count disagrees with observations'
    return None


def _proof_error(proof):
    if not isinstance(proof, dict):
        return 'Claude workspace answer missing source decisions'
    keys = ('candidate_entries', 'analyzed_entries', 'failed_entries', 'discovery_failures',
            'failed_operations', 'recovered_entries', 'advisory_ordering_failures')
    if not all(type(proof.get(k)) is int and proof[k] >= 0 for k in keys):
        return 'Claude workspace answer missing nonnegative source counts'
    if proof['candidate_entries'] != proof['analyzed_entries'] + proof['failed_entries']:
        return 'Claude workspace entry counts are inconsistent'
    if proof['recovered_entries'] > proof['candidate_entries']:
        return 'Claude workspace recovery count exceeds candidates'
    failures = proof.get('failures')
    if not isinstance(failures, list) or len(failures) != proof['failed_operations']:
        return 'Claude workspace answer missing failure decisions'
    if type(proof.get('request_rejected')) is not bool:
        return 'Claude workspace answer missing request state'
    return None
