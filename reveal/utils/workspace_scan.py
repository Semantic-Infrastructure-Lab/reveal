"""Acquisition of named workspace-list entries, before content filtering (Claude and Codex workspace lists)."""
from reveal.utils.path_utils import failure_of, to_posix
import stat
from pathlib import Path
from typing import Any, Dict

from .results import (AnalysisCompleteness, ExecutionFacts, FailureCause,
                      note_warning, result_execution_facts)


# The receipt's counting rule unless the caller names its own (Codex's lists have no project scope).
CLAUDE_COUNT_RULE = ('Named entries after project scope and before content/display filters; analyzed plus failed '
                     'equals candidates; required ordering/discovery failures count separately; aliases remain '
                     'separate entries')


class WorkspaceScan:
    def __init__(self, *, legacy_discovery_error=False, count_rule=CLAUDE_COUNT_RULE):
        self.count_rule = count_rule
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
                raise NotADirectoryError(to_posix(path))
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
        self.candidates.update(to_posix(p) for p in entries)
        return entries

    def read_text(self, path):
        text = path.read_text(encoding='utf-8', errors='surrogateescape')
        repaired = text.encode('utf-8', errors='surrogateescape').decode('utf-8', errors='replace')
        if repaired != text:
            self.recovered.add(to_posix(path))
        return repaired

    def complete(self, path, *, filtered=False):
        self.completed.add(to_posix(path))
        if filtered:
            self.filtered.add(to_posix(path))

    def count_directory(self, path):
        return sum(1 for _ in path.iterdir())

    def attach(self, result: Dict[str, Any]) -> Dict[str, Any]:
        required_order = [(p, e) for p, e in self.ordering_errors if to_posix(p) not in self.filtered]
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
            # The cause without the path (``source`` carries it): str(OSError) embeds the filename (BACK-2249).
            'failures': [{'phase': phase, 'source': to_posix(p), 'cause': type(e).__name__,
                          'message': failure_of(e).cause} for phase, p, e in failures],
            'count_rule': self.count_rule,
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


def workspace_list_error(adapter, result, field, prior_facts, *, count_key='total', label='Workspace'):
    """A workspace list answer keeps its acquisition decisions and its entry count through presentation."""
    from copy import deepcopy
    proof = result.get('meta', {}).get('workspace_analysis')
    error = workspace_proof_error(proof, label=label)
    if error:
        return error
    if prior_facts is None:
        adapter._workspace_proof = deepcopy(proof)
    if proof != adapter._workspace_proof:
        return f'{label} presentation cannot change workspace acquisition decisions'
    if not isinstance(result.get(field), list):
        return f'{label} workspace answer missing entry observations'
    count = result.get(count_key)
    if result.get('error') and not result[field]:
        return None
    from .observations import has_truncation_receipt
    if type(count) is not int or count < 0 or (count != len(result[field])
            and not has_truncation_receipt(result, (field,), len(result[field]), count)):
        return f'{label} workspace entry count disagrees with observations'
    return None


def workspace_proof_error(proof, *, label='Workspace'):
    if not isinstance(proof, dict):
        return f'{label} workspace answer missing source decisions'
    keys = ('candidate_entries', 'analyzed_entries', 'failed_entries', 'discovery_failures',
            'failed_operations', 'recovered_entries', 'advisory_ordering_failures')
    if not all(type(proof.get(k)) is int and proof[k] >= 0 for k in keys):
        return f'{label} workspace answer missing nonnegative source counts'
    if proof['candidate_entries'] != proof['analyzed_entries'] + proof['failed_entries']:
        return f'{label} workspace entry counts are inconsistent'
    if proof['recovered_entries'] > proof['candidate_entries']:
        return f'{label} workspace recovery count exceeds candidates'
    failures = proof.get('failures')
    if not isinstance(failures, list) or len(failures) != proof['failed_operations']:
        return f'{label} workspace answer missing failure decisions'
    if type(proof.get('request_rejected')) is not bool:
        return f'{label} workspace answer missing request state'
    return None
