"""Git operation identity and evidence at the existing result boundary."""
import os
from typing import Any

from ...utils.query_parser import peek_query_items
from ...utils.results import (AnalysisCompleteness, FailureCause, ExecutionFacts,
                             result_execution_facts, note_warning, truncations_of)


def selected_type(parsed, params):
    values = dict(peek_query_items(params))
    view = values.get('view')
    subpath = parsed['subpath']
    if view == 'ownership':
        return 'git_ownership'
    if view in ('history', 'log') and values.get('bucket'):
        return 'git_timeline'
    if subpath:
        if view in ('history', 'log'):
            directory = not values.get('element') and os.path.isdir(os.path.join(parsed['path'], subpath))
            return 'git_directory_history' if directory else 'git_file_history'
        if view in ('blame', 'diff'):
            return 'git_file_blame' if view == 'blame' else 'git_file_diff'
        raw = values.get('detail') == 'raw' or str(values.get('raw')).lower() in ('true', 'yes', '1')
        return 'git_file' if raw else 'git_file_structure'
    return ('git_ref' if values.get('ref', parsed['ref']) != 'HEAD' or view
            else 'git_repository')


def _observations(result):
    kind = result.get('type')
    if kind == 'git_repository':
        return bool(result.get('head'))
    if kind == 'git_ref':
        return bool(result.get('history'))
    if kind in ('git_file_history', 'git_directory_history'):
        return bool(result.get('commits'))
    if kind in ('git_timeline', 'git_ownership'):
        return bool(result.get('commit_count') if kind == 'git_timeline' else result.get('total_commits'))
    if kind == 'git_file_structure':
        return any(isinstance(value, list) and value for value in result.get('structure', {}).values())
    if kind == 'git_file':
        return bool(result.get('content', '').replace('\ufffd', '').strip())
    return True



def text_evidence(loss):
    return {'blob_text': {'encoding': 'utf-8', 'decoding_loss': bool(loss)}}


def portable_repository_paths(result, spelling):
    from ...utils.path_utils import as_spelled
    path = result.get('path')
    if isinstance(path, str) and os.path.isabs(path):
        result['path'] = as_spelled(path, spelling)
    source = result.get('source')
    if isinstance(source, str):
        target, at, ref = source.rpartition('@') if '@' in source and result.get('type') != 'git_repository' else (source, '', '')
        if os.path.isabs(target):
            result['source'] = str(as_spelled(target, spelling)) + at + ref
    return result


def ref_sources(branches, tags):
    return {name: {'candidates': len(rows) + len(getattr(rows, 'failures', [])),
                   'analyzed': len(rows), 'failed': len(getattr(rows, 'failures', [])),
                   'failed_refs': list(getattr(rows, 'failures', []))}
            for name, rows in (('branches', branches), ('tags', tags))}


def _required_input_lost(result):
    if result.get('type') == 'git_timeline':
        return any(t.get('field') == 'commits' for t in truncations_of(result))
    if result.get('type') == 'git_ownership':
        return result.get('scope', {}).get('history_window', {}).get('complete') is False
    return False

def qualify_source_evidence(result: dict) -> dict:
    """Retain legacy disclosures and expose required loss through canonical diagnostics."""
    reasons = []
    if any(w.get('type') == 'content_search_unavailable' for w in result.get('warnings', [])):
        reasons.append('required changed-content search was unavailable')
    structure = result.get('structure', {})
    if isinstance(structure, dict) and structure.get('_has_errors'):
        reasons.append('structural analysis recovered from source errors')
    meta = result.get('meta', {})
    if any(proof.get('failed') for proof in meta.get('ref_sources', {}).values()):
        reasons.append('enumerated refs could not be analyzed')
    if meta.get('blob_text', {}).get('decoding_loss'):
        reasons.append('invalid UTF-8 was decoded with replacements')
    if _required_input_lost(result):
        reasons.append('a commit-input window omitted required history')
    if reasons:
        note_warning(result, {'type': 'analysis_incomplete', 'code': 'analysis_incomplete',
                              'message': 'Git answer is incomplete: ' + '; '.join(reasons) + '.'})
    if meta.get('blob_analysis', {}).get('available') is False:
        note_warning(result, {'type': 'not_applicable', 'code': 'not_applicable',
                              'message': 'No structural analyzer for this historical file; use detail=raw to read its text.'})
    return result


def execution_facts(result):
    warnings = result.get('meta', {}).get('warnings', []) if isinstance(result, dict) else []
    lost = any(w.get('code') == 'analysis_incomplete' for w in warnings)
    if lost:
        state = AnalysisCompleteness.INCOMPLETE if _observations(result) else AnalysisCompleteness.FAILED
        return ExecutionFacts(state, failures=frozenset({FailureCause.ANALYSIS}))
    state = AnalysisCompleteness.COMPLETE
    if result.get('meta', {}).get('blob_analysis', {}).get('available') is False:
        state = AnalysisCompleteness.NOT_APPLICABLE
    return result_execution_facts(result, completeness=state)


def _count(value):
    return type(value) is int and value >= 0



_REQUIREMENTS: dict[str, dict[str, Any]] = {
    'git_repository': {'head': dict, 'branches': dict, 'tags': dict, 'commits': dict},
    'git_ref': {'commit': dict, 'history': list},
    'git_file_structure': {'structure': dict, 'size': _count, 'lines': _count},
    'git_file': {'content': str, 'size': _count, 'lines': _count},
    'git_file_history': {'commits': list, 'count': _count},
    'git_directory_history': {'commits': list, 'count': _count},
    'git_file_blame': {'hunks': list, 'file_content': list, 'lines': _count},
    'git_file_diff': {'diff_text': str},
    'git_timeline': {'buckets': list, 'commit_count': _count, 'distinct_author_count': _count},
    'git_ownership': {'authors': list, 'total_commits': _count, 'contributor_count': _count},
}


def _valid_field(value, check):
    return isinstance(value, check) if isinstance(check, type) else check(value)


def _valid_text_proof(result):
    kind = result.get('type')
    if kind in ('git_file', 'git_file_structure', 'git_file_blame'):
        if type(result.get('meta', {}).get('blob_text', {}).get('decoding_loss')) is not bool:
            return False
    if kind == 'git_file_structure':
        return type(result.get('meta', {}).get('blob_analysis', {}).get('available')) is bool
    return True



def _valid_ref_proof(result):
    proofs = result.get('meta', {}).get('ref_sources', {})
    for name in ('branches', 'tags'):
        proof = proofs.get(name, {})
        counts = [proof.get(k) for k in ('candidates', 'analyzed', 'failed')]
        if not all(_count(n) for n in counts) or counts[0] != counts[1] + counts[2]:
            return False
        if not isinstance(proof.get('failed_refs'), list) or len(proof['failed_refs']) != counts[2]:
            return False
    return True

def answer_requirement_error(result, expected_type, prior_facts=None):
    if result.get('error') or result.get('applicable') is False:
        return None
    kind = result.get('type')
    fields = _REQUIREMENTS.get(kind)
    if not fields or not all(_valid_field(result.get(key), check) for key, check in fields.items()):
        return 'Git answer missing required view observations or counts'
    if (kind in ('git_file_history', 'git_directory_history')
            and result['count'] != len(result['commits'])
            and not _receipted_cut(result, ('commits',), len(result['commits']), result['count'])):
        return 'Git history count does not match its observations'
    if kind == 'git_repository' and not _valid_ref_proof(result):
        return 'Git repository answer missing ref-source decisions'
    if not _valid_text_proof(result):
        return 'Git answer missing source-text or analyzer evidence'
    return None


_OBSERVATION_FIELDS = {
    'git_repository': (('branches', 'recent'), ('tags', 'recent'), ('commits', 'recent')),
    'git_ref': (('history',),),
    'git_file_history': (('commits',),),
    'git_directory_history': (('commits',),),
    'git_timeline': (('buckets',),),
    'git_ownership': (('authors',),),
    'git_file_blame': (('hunks',), ('file_content',)),
    'git_file': (('content',),),
    'git_file_diff': (('diff_text',),),
}


def _field_at(result, path):
    value = result
    for part in path:
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def observation_counts(result):
    """Snapshot container kinds and sizes, without retaining or copying source rows."""
    paths = _OBSERVATION_FIELDS.get(result.get('type'), ())
    if result.get('type') == 'git_file_structure':
        paths = tuple(('structure', key) for key, value in result['structure'].items()
                      if isinstance(value, list))
    return {path: (type(value), len(value)) if isinstance(value, (list, str)) else None
            for path in paths for value in (_field_at(result, path),)}


def _receipted_cut(result, path, shown, previous):
    return any(receipt.get('field') == '.'.join(path)
               and receipt.get('shown') == shown
               and _count(receipt.get('total')) and receipt['total'] >= previous
               for receipt in truncations_of(result))


def presentation_observations_error(result, previous):
    current = observation_counts(result)
    for path, before in previous.items():
        after = current.get(path)
        if before is None or after is None or before[0] is not after[0]:
            return 'Git answer missing required observation containers'
        if after[1] > before[1]:
            return 'Git presentation cannot create new source observations'
        if after[1] < before[1] and not _receipted_cut(result, path, after[1], before[1]):
            return 'Git presentation removed observations without a matching truncation receipt'
    if any(value and value[1] for path, value in current.items() if path not in previous):
        return 'Git presentation cannot create new source observations'
    return None
