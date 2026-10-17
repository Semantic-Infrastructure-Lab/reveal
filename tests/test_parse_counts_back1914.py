"""A cold serial count gate must reject incomplete or misleading evidence."""
from copy import deepcopy
from dataclasses import asdict
import json
import os

import pytest

from reveal.utils.parse_audit import capture_parses, parse_attempt, parse_request
from scripts.check_parse_counts import (
    audit_snapshot, compare_snapshots, load_audit, qualify_snapshots,
    validate_command_output,
)


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
             'metadata': capture.metadata, 'events': [asdict(e) for e in capture.events]}
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
        audit['events'][1]['pid'] += 1
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
             'metadata': capture.metadata, 'events': [asdict(e) for e in capture.events]}
    report = audit_snapshot(audit, os.getpid(), tmp_path, targets)
    assert report['totals'] == {'request': 2, 'attempt': 1, 'artifact': 1,
                                'failure': 0, 'outcome': 2}
    assert report['coverage'] == ['first.ts', 'second.ts']


@pytest.mark.parametrize('source', ['x = 1', 'x = 1\n'])
def test_only_declared_source_transform_is_accepted(tmp_path, source):
    from scripts.check_parse_counts import _source_identity
    canonical = 'x = 1\n\n'
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
             'metadata': capture.metadata, 'events': [asdict(e) for e in capture.events]}
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
