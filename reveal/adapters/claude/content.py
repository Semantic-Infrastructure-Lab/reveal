"""Acquisition receipts for cross-session content decisions, before display cuts."""
from typing import Any, Dict
from ...utils.results import AnalysisCompleteness, note_warning, result_execution_facts
from .analysis.records import TranscriptRecords, valid_record_proof


def degraded(source):
    return bool(source['failed_records'] or source['recovered_records'] or source['failures']
                or source['decision'] not in ('exhausted', 'matched-prefix'))


class ContentScans:
    def __init__(self, candidates):
        self.candidates = candidates
        self.reads: list[TranscriptRecords] = []

    def attach(self, result: Dict[str, Any]) -> Dict[str, Any]:
        sources = [read.receipt() for read in self.reads]
        proof = {
            'candidate_sessions': self.candidates, 'scanned_sessions': len(sources),
            'degraded_sessions': sum(degraded(s) for s in sources),
            'usable_sessions': sum(bool(s['analyzed_records']) or not degraded(s) for s in sources),
            'count_rule': 'Required sessions after declared date scope (none for an empty search term); nonblank records consumed until first content match or EOF; file tracking consumes all records',
            'sources': sources,
        }
        result.setdefault('meta', {})['session_content'] = proof
        if proof['degraded_sessions'] or proof['candidate_sessions'] != proof['scanned_sessions']:
            note_warning(result, {'type': 'analysis_incomplete', 'code': 'analysis_incomplete',
                                  'field': 'session_content',
                                  'message': 'Required session content was lost or repaired. Decisions: JSON meta.session_content.'})
        return result


def content_execution_facts(result):
    meta = result.get('meta', {})
    catalog, content = meta.get('session_catalog', {}), meta.get('session_content', {})
    loss = (catalog.get('failed_entries') or catalog.get('discovery_failures')
            or content.get('degraded_sessions') or content.get('candidate_sessions') != content.get('scanned_sessions'))
    state = AnalysisCompleteness.COMPLETE
    if loss:
        state = AnalysisCompleteness.INCOMPLETE if content.get('usable_sessions') else AnalysisCompleteness.FAILED
    return result_execution_facts(result, completeness=state)


def content_requirement_error(adapter, result, prior_facts):
    from copy import deepcopy
    from .catalog import catalog_proof_error
    error = catalog_proof_error(adapter, result, prior_facts)
    if error:
        return error
    proof = result.get('meta', {}).get('session_content')
    error = _content_proof_error(proof)
    if error:
        return error
    if prior_facts is None:
        adapter._content_proof = deepcopy(proof)
    if proof != adapter._content_proof:
        return 'Claude presentation cannot change content scan decisions'
    return _match_count_error(result)


def _content_proof_error(proof):
    if not isinstance(proof, dict) or not isinstance(proof.get('sources'), list):
        return 'Claude content answer missing scan decisions'
    sources = proof['sources']
    keys = ('candidate_sessions', 'scanned_sessions', 'degraded_sessions', 'usable_sessions')
    if not all(type(proof.get(k)) is int and proof[k] >= 0 for k in keys):
        return 'Claude content answer missing nonnegative scan counts'
    if proof['candidate_sessions'] != proof['scanned_sessions'] or proof['scanned_sessions'] != len(sources):
        return 'Claude content scan count disagrees with required sessions'
    if not all(_valid_source(s) for s in sources):
        return 'Claude content record decisions are inconsistent'
    if proof['degraded_sessions'] != sum(degraded(s) for s in sources):
        return 'Claude content loss count disagrees with source decisions'
    if proof['usable_sessions'] != sum(bool(s['analyzed_records']) or not degraded(s) for s in sources):
        return 'Claude content usable count disagrees with source decisions'
    return None


def _valid_source(source):
    return (valid_record_proof(source) and type(source.get('recovered_records')) is int
            and 0 <= source['recovered_records'] <= source['candidate_records']
            and isinstance(source.get('failures'), list)
            and isinstance(source.get('source'), str)
            and source.get('decision') in ('exhausted', 'matched-prefix', 'interrupted'))


def _match_count_error(result):
    from ...utils.observations import has_truncation_receipt
    field = 'matches' if result.get('type') == 'claude_cross_session_search' else 'sessions'
    rows, count = result.get(field), result.get('match_count')
    if not isinstance(rows, list) or type(count) is not int or count < 0:
        return 'Claude content answer missing observations and count'
    if count != len(rows) and not has_truncation_receipt(result, (field,), len(rows), count):
        return 'Claude content count disagrees with display observations'
    return None
