"""Measured session-entry acquisition shared by listing, search and file tracking."""
from reveal.utils.path_utils import to_posix
import stat
from pathlib import Path
from typing import Any, Callable, Dict, Mapping

from ...utils.results import note_warning
from .discovery import Failures


class SessionEntries(list):
    def __init__(self):
        super().__init__()
        self.candidate_entries = 0
        self.metadata_failures: Failures = []
        self.discovery_failures: Failures = []

    def merge(self, other: 'SessionEntries') -> None:
        self.extend(other)
        self.candidate_entries += other.candidate_entries
        self.metadata_failures.extend(other.metadata_failures)
        self.discovery_failures.extend(other.discovery_failures)

    def receipt(self) -> dict:
        return {
            'candidate_entries': self.candidate_entries, 'analyzed_entries': len(self),
            'failed_entries': len(self.metadata_failures), 'discovery_failures': len(self.discovery_failures),
            'count_rule': 'Non-agent JSONL-named entries before name/date/content filtering; analyzed metadata plus failed entries equals candidates; discovery failures count directory/stat events',
            'failures': [{'source': to_posix(path), 'cause': type(exc).__name__, 'message': str(exc)}
                         for path, exc in (*self.metadata_failures, *self.discovery_failures)],
        }


def collect_session_entries(base: Path, collect: Callable[[Path], SessionEntries]) -> SessionEntries:
    entries = SessionEntries()
    try:
        for directory in base.iterdir():
            try:
                is_directory = stat.S_ISDIR(directory.stat().st_mode)
            except OSError as exc:
                entries.discovery_failures.append((directory, exc))
                continue
            if is_directory:
                entries.merge(collect(directory))
    except OSError as exc:
        entries.discovery_failures.append((base, exc))
    return entries


def attach_catalog_evidence(result: Mapping[str, Any], entries: SessionEntries) -> dict:
    result = dict(result)
    result.setdefault('meta', {})['session_catalog'] = entries.receipt()
    failures = len(entries.metadata_failures) + len(entries.discovery_failures)
    if failures:
        note_warning(result, {
            'type': 'analysis_incomplete', 'code': 'analysis_incomplete', 'field': 'session_catalog',
            'message': (f'{failures} required session-entry acquisition operation(s) failed; '
                        'known entries are retained. Decisions: JSON meta.session_catalog.'),
        })
        if not entries:
            result['error'] = str((entries.metadata_failures or entries.discovery_failures)[0][1])
    return result


def catalog_execution_facts(result):
    from ...utils.results import AnalysisCompleteness, result_execution_facts
    proof = result.get('meta', {}).get('session_catalog', {})
    state = AnalysisCompleteness.COMPLETE
    if proof.get('failed_entries') or proof.get('discovery_failures'):
        state = AnalysisCompleteness.INCOMPLETE if proof.get('analyzed_entries') else AnalysisCompleteness.FAILED
    return result_execution_facts(result, completeness=state)


def _valid_catalog_proof(proof):
    if not isinstance(proof, dict):
        return False
    keys = ('candidate_entries', 'analyzed_entries', 'failed_entries', 'discovery_failures')
    if not all(type(proof.get(key)) is int and proof[key] >= 0 for key in keys):
        return False
    if proof['candidate_entries'] != proof['analyzed_entries'] + proof['failed_entries']:
        return False
    return isinstance(proof.get('failures'), list) and len(proof['failures']) == proof['failed_entries'] + proof['discovery_failures']


def catalog_proof_error(adapter, result, prior_facts):
    from copy import deepcopy
    proof = result.get('meta', {}).get('session_catalog')
    if not _valid_catalog_proof(proof):
        return 'Claude listing missing consistent session-entry acquisition decisions'
    if prior_facts is None:
        adapter._catalog_proof = deepcopy(proof)
    if proof != adapter._catalog_proof:
        return 'Claude presentation cannot change session-entry acquisition decisions'
    return None


def catalog_requirement_error(adapter, result, prior_facts):
    from ...utils.observations import has_truncation_receipt
    error = catalog_proof_error(adapter, result, prior_facts)
    if error:
        return error
    rows, count = result.get('recent_sessions'), result.get('session_count')
    if not isinstance(rows, list) or type(count) is not int or count < 0:
        return 'Claude listing missing session observations and count'
    if count != len(rows) and not has_truncation_receipt(result, ('recent_sessions',), len(rows), count):
        return 'Claude listing count disagrees with its display observations'
    return None
