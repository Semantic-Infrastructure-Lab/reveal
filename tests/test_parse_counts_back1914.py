"""A cold serial count gate must reject incomplete or misleading evidence."""
from copy import deepcopy
from dataclasses import asdict
import json
import os
import platform
import sys

import pytest

from reveal.utils.parse_audit import capture_parses, parse_attempt, parse_request
from scripts.check_parse_counts import (
    audit_snapshot, compare_snapshots, load_audit, qualify_snapshots,
    validate_command_output,
)


def _metadata(capture):
    return {**capture.metadata, 'runtime': {
        'platform': sys.platform, 'implementation': platform.python_implementation()}}


@pytest.fixture
def ledger(tmp_path):
    source = 'x = 1\n'
    path = tmp_path / 'config.py'
    path.write_text(source, encoding='utf-8')
    with capture_parses(tmp_path, targets=['config.py']) as capture:
        with parse_request('python.ast', source, path, 'fullsource'):
            with parse_attempt(source, 'original'):
                pass
    request = capture.events[0]
    targets = {'config.py': {'parsers': ['python.ast'], 'sha256': request.source_hash,
                              'bytes': request.source_length}}
    audit = {'schema_version': 1, 'complete': True, 'exit_code': 0,
             'metadata': _metadata(capture), 'events': [asdict(e) for e in capture.events]}
    return audit, tmp_path, targets


def snapshot(ledger):
    audit, root, targets = ledger
    return audit_snapshot(audit, os.getpid(), root, targets)


def test_valid_audit_retains_separate_requests_attempts_and_artifacts(ledger):
    report = snapshot(ledger)
    assert report['totals'] == {'request': 1, 'attempt': 1, 'artifact': 1,
                                'failure': 0, 'outcome': 1}
    assert report['coverage'] == ['config.py']
    assert compare_snapshots(report, deepcopy(report)) == []


def test_duplicate_physical_build_is_a_regression(ledger):
    baseline = snapshot(ledger)
    audit = ledger[0]
    attempt, artifact = deepcopy(audit['events'][1:3])
    attempt['attempt_id'] = artifact['attempt_id'] = 2
    audit['events'][3:3] = [attempt, artifact]
    current = snapshot(ledger)
    regressions = compare_snapshots(baseline, current)
    assert len(regressions) == 2
    assert any('artifact' in error for error in regressions)
    assert any('attempt' in error for error in regressions)


@pytest.mark.parametrize('fault', ['incomplete', 'worker', 'missing_outcome', 'unknown_target',
                                   'wrong_hash', 'wrong_parser', 'missing_target', 'failed_outcome'])
def test_unqualified_evidence_is_rejected(ledger, fault):
    audit, root, targets = ledger
    if fault == 'incomplete':
        audit['complete'] = False
    elif fault == 'worker':
        for event in audit['events']:
            event['pid'] += 1
    elif fault == 'missing_outcome':
        audit['events'].pop()
    elif fault == 'unknown_target':
        for event in audit['events']:
            event.update(filename=None, scope='unattributed')
    elif fault == 'wrong_hash':
        for event in audit['events']:
            event['source_hash'] = '0' * 64
    elif fault == 'wrong_parser':
        for event in audit['events']:
            event['parser'] = 'treesitter:javascript'
    elif fault == 'missing_target':
        targets['unseen.py'] = deepcopy(targets['config.py'])
    elif fault == 'failed_outcome':
        audit['events'][-1]['outcome'] = 'failed'
    with pytest.raises(ValueError):
        snapshot(ledger)


def test_missing_audit_cannot_look_like_zero_parses(tmp_path):
    with pytest.raises(ValueError, match='audit'):
        load_audit(tmp_path / 'absent.json')


def test_command_failure_or_empty_json_cannot_pass():
    spec = {'exit_code': 0, 'type': 'check'}
    valid = {'type': 'check', 'summary': {'files_checked': 3, 'total_issues': 0,
             'files_errored': 0, 'files_degraded': 0, 'exit_code': 0}}
    assert validate_command_output(0, json.dumps(valid), spec, 3)['files_checked'] == 3
    with pytest.raises(ValueError, match='exit'):
        validate_command_output(1, json.dumps(valid), spec, 3)
    with pytest.raises(ValueError):
        validate_command_output(0, '{}', spec, 3)
    valid['summary']['files_checked'] = 0
    with pytest.raises(ValueError, match='files_checked'):
        validate_command_output(0, json.dumps(valid), spec, 3)


def test_five_fresh_runs_must_have_exact_vectors(ledger):
    report = snapshot(ledger)
    assert qualify_snapshots([deepcopy(report) for _ in range(5)]) == report
    with pytest.raises(ValueError, match='five'):
        qualify_snapshots([report] * 4)
    changed = deepcopy(report)
    changed['totals']['request'] += 1
    with pytest.raises(ValueError, match='repeat'):
        qualify_snapshots([report] * 4 + [changed])


def test_equal_content_target_requests_can_share_one_ts_artifact(tmp_path):
    source = 'const x = 1;\n'
    for name in ('first.ts', 'second.ts'):
        (tmp_path / name).write_text(source, encoding='utf-8')
    with capture_parses(tmp_path, targets=['first.ts', 'second.ts']) as capture:
        with parse_request('treesitter:typescript', source, tmp_path / 'first.ts', 'fullsource'):
            with parse_attempt(source, 'native'):
                pass
        with parse_request('treesitter:typescript', source, tmp_path / 'second.ts', 'fullsource'):
            pass
    request = capture.events[0]
    targets = {name: {'parsers': ['treesitter:typescript'], 'sha256': request.source_hash,
                      'bytes': request.source_length} for name in ('first.ts', 'second.ts')}
    audit = {'schema_version': 1, 'complete': True, 'exit_code': 0,
             'metadata': _metadata(capture), 'events': [asdict(e) for e in capture.events]}
    report = audit_snapshot(audit, os.getpid(), tmp_path, targets)
    assert report['totals'] == {'request': 2, 'attempt': 1, 'artifact': 1,
                                'failure': 0, 'outcome': 2}
    assert report['coverage'] == ['first.ts', 'second.ts']


@pytest.mark.parametrize('operation', ['drop-two-LF', 'drop-one-LF', 'strip'])
def test_only_declared_source_transform_is_accepted(tmp_path, operation):
    from scripts.check_parse_counts import _source_identity
    canonical = 'x = 1  \n\n'
    source = {'drop-two-LF': canonical[:-2], 'drop-one-LF': canonical[:-1],
              'strip': canonical.strip()}[operation]
    path = tmp_path / 'config.py'
    path.write_text(canonical, encoding='utf-8')
    identity = _source_identity(canonical)
    targets = {'config.py': {**identity, 'parsers': ['python.ast'], 'variants': {
        'canonical': identity, 'analyzer-content': _source_identity(canonical[:-1])}}}
    with capture_parses(tmp_path, targets=['config.py']) as capture:
        with parse_request('python.ast', source, path, 'fullsource'):
            with parse_attempt(source, 'original'):
                pass
    audit = {'schema_version': 1, 'complete': True, 'exit_code': 0,
             'metadata': _metadata(capture), 'events': [asdict(e) for e in capture.events]}
    if source == canonical[:-1]:
        report = audit_snapshot(audit, os.getpid(), tmp_path, targets)
        assert {json.loads(key)['source_variant'] for key in report['counts']} == {'analyzer-content'}
        assert {json.loads(key)['original_source_hash'] for key in report['counts']} == {identity['sha256']}
    else:
        with pytest.raises(ValueError, match='declared variants'):
            audit_snapshot(audit, os.getpid(), tmp_path, targets)


def test_manifest_hashes_and_variants_must_match_real_text(ledger):
    from scripts.check_parse_counts import _verify_corpus
    _, root, targets = ledger
    _verify_corpus(root, targets)
    targets['config.py']['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='sha256'):
        _verify_corpus(root, targets)


@pytest.mark.parametrize('kind', ['overview', 'hotspots'])
@pytest.mark.parametrize('failure', ['parse_degraded', 'check_rules_failed', 'analysis_failed', 'truncated'])
def test_partial_command_results_cannot_qualify(kind, failure):
    result = {'type': kind, 'summary': {'total_files': 3, 'excluded': 0},
              'stats': {'summary': {'total_files': 3, 'excluded': 0}},
              'scope': {'total_code_files': 3},
              'meta': {'warnings': [{'type': failure, 'message': 'partial analysis'}]}}
    with pytest.raises(ValueError, match='warning'):
        validate_command_output(0, json.dumps(result), {'type': kind, 'exit_code': 0}, 3)


def test_nested_child_errors_and_unexpected_rule_exclusions_reject():
    result = {'type': 'overview', 'stats': {'summary': {'total_files': 3},
              'meta': {'errors': [{'message': 'child scan failed'}]}}, 'meta': {}}
    with pytest.raises(ValueError, match='errors'):
        validate_command_output(0, json.dumps(result), {'type': 'overview', 'exit_code': 0}, 3)
    result = {'type': 'check', 'summary': {'files_checked': 3, 'total_issues': 0,
              'files_errored': 0, 'files_degraded': 0, 'exit_code': 0,
              'scan_disclosures': ['rule unavailable']}}
    with pytest.raises(ValueError, match='scan_disclosures'):
        validate_command_output(0, json.dumps(result), {'type': 'check', 'exit_code': 0}, 3)


def test_unknown_non_target_domain_is_not_silently_excluded(ledger):
    audit, root, _ = ledger
    added = deepcopy(audit['events'])
    for event in added:
        event.update(request_id=2, scope='external', domain='mystery',
                     filename=(root.parent / 'outside.py').as_posix())
    audit['events'].extend(added)
    with pytest.raises(ValueError, match='domain'):
        snapshot(ledger)


def test_subprocess_failure_preserves_stderr(ledger, monkeypatch):
    from scripts import check_parse_counts as gate
    _, root, targets = ledger
    run = root / 'run'
    run.mkdir()

    class FailedProcess:
        returncode = 1
        pid = os.getpid()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def communicate(self, timeout):
            return '{}', 'original failure'

    monkeypatch.setattr(gate.subprocess, 'Popen', lambda *args, **kwargs: FailedProcess())
    with pytest.raises(ValueError, match='original failure'):
        gate.run_once({'args': ['check', '{corpus}'], 'type': 'check', 'exit_code': 0},
                      root, targets, run)


def test_capture_environment_overrides_user_scan_controls(tmp_path, monkeypatch):
    from scripts.check_parse_counts import _environment
    monkeypatch.setenv('REVEAL_IGNORE', '*.py')
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '8')
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')
    environment = _environment(tmp_path)
    assert environment['REVEAL_MAX_WORKERS'] == '1'
    assert environment['REVEAL_DISK_CACHE'] == '0'
    assert environment['XDG_CONFIG_HOME'] == str(tmp_path)
    assert 'REVEAL_IGNORE' not in environment


def test_historical_runtime_versions_are_provenance_not_count_ceilings(ledger):
    current = snapshot(ledger)
    historical = deepcopy(current)
    historical['parser_versions']['python.ast'] = '3.12.1'
    historical['runtime'] = {'platform': 'another-platform', 'implementation': 'another-python'}
    assert compare_snapshots(historical, current) == []
    with pytest.raises(ValueError, match='repeat'):
        qualify_snapshots([current] * 4 + [historical])


@pytest.mark.parametrize('field', ['runtime', 'parser_versions'])
def test_missing_child_runtime_metadata_rejects(ledger, field):
    ledger[0]['metadata'].pop(field)
    with pytest.raises(ValueError, match='metadata'):
        snapshot(ledger)


def test_cold_cached_requests_require_prior_observed_artifact(tmp_path):
    source = 'x = 1\n'
    path = tmp_path / 'config.py'
    path.write_text(source, encoding='utf-8')
    with capture_parses(tmp_path, targets=['config.py']) as capture:
        with parse_request('python.ast', source, path, 'fullsource'):
            with parse_attempt(source, 'original'):
                pass
        for _ in range(3):
            with parse_request('python.ast', source, path, 'fullsource'):
                pass
    request = capture.events[0]
    targets = {'config.py': {'parsers': ['python.ast'], 'sha256': request.source_hash,
                              'bytes': request.source_length}}
    audit = {'schema_version': 1, 'complete': True, 'exit_code': 0,
             'metadata': _metadata(capture), 'events': [asdict(e) for e in capture.events]}
    baseline = audit_snapshot(audit, os.getpid(), tmp_path, targets)
    # A genuine reduction may remove a complete cached request while retaining
    # the physical artifact that backs remaining warm requests.
    reduced = deepcopy(audit)
    reduced['events'] = reduced['events'][:-2]
    assert compare_snapshots(baseline, audit_snapshot(reduced, os.getpid(), tmp_path, targets)) == []
    audit['events'] = audit['events'][4:]
    with pytest.raises(ValueError, match='cached'):
        audit_snapshot(audit, os.getpid(), tmp_path, targets)


def test_unqualified_physical_input_hash_cannot_hide_behind_request_identity(ledger):
    for event in ledger[0]['events']:
        if event['event'] in ('attempt', 'artifact'):
            event['parsed_hash'] = '0' * 64
    with pytest.raises(ValueError, match='physical'):
        snapshot(ledger)


def test_full_command_result_changes_cannot_hide_behind_equal_totals(ledger):
    spec = {'type': 'surface', 'exit_code': 0}
    result = {'type': 'surface', 'scope': {'total_code_files': 1}, 'total': 1,
              'surfaces': {'env': [{'name': 'CORRECT'}]}}
    first = validate_command_output(0, json.dumps(result), spec, 1)
    result['surfaces']['env'][0]['name'] = 'WRONG'
    second = validate_command_output(0, json.dumps(result), spec, 1)
    assert first != second
    report = snapshot(ledger)
    report['command_outcome'] = first
    changed = deepcopy(report)
    changed['command_outcome'] = second
    with pytest.raises(ValueError, match='repeat'):
        qualify_snapshots([report] * 4 + [changed])


@pytest.mark.parametrize('parser', ['python.ast', 'tree-sitter', 'tree-sitter-language-pack'])
def test_parser_versions_must_be_nonempty_strings(ledger, parser):
    ledger[0]['metadata']['parser_versions'][parser] = None
    with pytest.raises(ValueError, match='metadata'):
        snapshot(ledger)
