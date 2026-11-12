"""Measured full-record acquisition for existing Codex message substring search."""
from pathlib import Path
from typing import Any

from ...utils.jsonl_records import TranscriptRecords, valid_record_proof
from ...utils.results import AnalysisCompleteness, FailureCause, note_warning, result_execution_facts
from .catalog import answer_requirement_error as catalog_error
from .rollout import ROLLOUT_RULE, unavailable_rollout, rollout_lost

CONTENT_RULE = 'Required catalog rows after date scope; consume every nonblank JSONL record before message substring matching and per-session snippet caps; object decoding does not validate every event payload'


def scan_rollout(row, term, cap, snippet_of):
    raw = row.get('rollout_path')
    if not isinstance(raw, str) or not raw or '\x00' in raw:
        return [], 0, {**unavailable_rollout(raw), 'session_id': row['id']}
    read = TranscriptRecords(Path(raw), replace_decode=True, opener=open)
    snippets: list[dict[str, Any]] = []
    found = 0
    try:
        for record in read.records():
            snippet = snippet_of(record, term)
            if snippet:
                found += 1
                if cap <= 0 or len(snippets) < cap:
                    snippets.append(snippet)
    except (OSError, UnicodeDecodeError):
        pass  # The shared reader retains the consumed prefix and precise failure.
    proof = {**read.receipt(), 'opened': read.opened, 'count_rule': ROLLOUT_RULE, 'session_id': row['id']}
    return snippets, found, proof


def _usable_source(source):
    return bool(source['analyzed_records']) or (source['opened'] and not rollout_lost(source))


def attach_content_evidence(result, sources):
    proof = {
        'selected_sessions': len(sources), 'rollouts': sources,
        'failed_sources': sum(rollout_lost(source) for source in sources),
        'usable_sources': sum(_usable_source(source)
                              for source in sources),
        'count_rule': CONTENT_RULE,
    }
    result.setdefault('meta', {'warnings': [], 'errors': []})['content_analysis'] = proof
    if proof['failed_sources']:
        note_warning(result, {'type': 'analysis_incomplete', 'code': 'analysis_incomplete', 'field': 'content_analysis',
                              'message': 'Codex search lost or repaired required rollout input; acquired matches retained. See JSON meta.content_analysis.'})
    return result


def execution_facts(result):
    meta = result.get('meta', {})
    catalog, content = meta.get('session_catalog', {}), meta.get('content_analysis', {})
    if catalog.get('source_present') is False:
        return result_execution_facts(result, completeness=AnalysisCompleteness.COMPLETE,
                                      failure_cause=FailureCause.INVALID_REQUEST)
    loss = catalog.get('failed_operations') or content.get('failed_sources')
    state = AnalysisCompleteness.COMPLETE
    if loss:
        usable = content.get('usable_sources') or (not content.get('selected_sessions') and catalog.get('query_complete'))
        state = AnalysisCompleteness.INCOMPLETE if usable else AnalysisCompleteness.FAILED
    return result_execution_facts(result, completeness=state)


def _match_error(result, expected):
    originals = {row['id']: row for row in expected['sessions']}
    seen: set[str] = set()
    for row in result['sessions']:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str):
            return 'Codex search missing its matched session identity'
        if row['id'] not in originals or row['id'] in seen:
            return 'Codex search changed its matched session identities'
        seen.add(row['id'])
        original = originals[row['id']]
        if (type(row.get('match_count')) is not int or row['match_count'] != original['match_count']
                or not isinstance(row.get('matches'), list) or len(row['matches']) != len(original['matches'])):
            return 'Codex search changed its acquired snippets or match counts'
    return None


def _valid_source(source):
    return (valid_record_proof(source) and type(source.get('recovered_records')) is int
            and 0 <= source['recovered_records'] <= source['candidate_records']
            and isinstance(source.get('failures'), list) and type(source.get('opened')) is bool
            and isinstance(source.get('source'), str) and isinstance(source.get('session_id'), str)
            and source.get('decision') in ('exhausted', 'interrupted', 'unavailable')
            and source.get('count_rule') == ROLLOUT_RULE)


def _proof_error(proof):
    if not isinstance(proof, dict) or not isinstance(proof.get('rollouts'), list):
        return 'Codex search missing required rollout decisions'
    sources = proof['rollouts']
    counts = ('selected_sessions', 'failed_sources', 'usable_sources')
    if not all(type(proof.get(key)) is int and proof[key] >= 0 for key in counts):
        return 'Codex search missing nonnegative acquisition counts'
    if proof['selected_sessions'] != len(sources) or not all(_valid_source(source) for source in sources):
        return 'Codex search source counts disagree with its required rollouts'
    failed = sum(rollout_lost(source) for source in sources)
    usable = sum(_usable_source(source) for source in sources)
    if proof['failed_sources'] != failed or proof['usable_sources'] != usable or proof.get('count_rule') != CONTENT_RULE:
        return 'Codex search source counts disagree with its acquisition decisions'
    return None


def answer_requirement_error(adapter, result, prior_facts):
    error = catalog_error(adapter, result, prior_facts)
    if error:
        return error
    expected = adapter._catalog_answer
    error = _proof_error(result.get('meta', {}).get('content_analysis'))
    if error:
        return error
    if result.get('meta', {}).get('content_analysis') != expected['meta']['content_analysis']:
        return 'Codex search changed its required rollout acquisition decisions'
    if result.get('query') != expected['query']:
        return 'Codex search changed its applied query'
    return _match_error(result, expected)
