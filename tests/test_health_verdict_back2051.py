"""Every health producer classifies into the closed verdict set (BACK-2051 slice 4).

``healthy`` | ``finding`` (a completed, negative domain verdict) | ``not_applicable`` |
``unavailable`` (the target could not be reached or read) | ``incomplete`` (usable but
partial or capped evidence) | ``failed`` (the check could not produce its answer). Numeric
child exit codes do not establish this: a child exiting 2 may carry a real domain verdict or
may have crashed.
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from reveal.cli.commands import health
from reveal.cli.commands.health import HEALTH_VERDICTS, HealthResult, _code_result, _uri_health_result

_CHECK_FAIL = {'type': 'ssl_check', 'status': 'failure', 'exit_code': 2,
               'checks': [{'name': 'connection', 'status': 'failure', 'severity': 'critical'}]}
_CHECK_WARN = {'type': 'domain_health_check', 'status': 'warning', 'exit_code': 1, 'checks': []}
_CHECK_PASS = {'type': 'domain_health_check', 'status': 'pass', 'exit_code': 0, 'checks': []}


def test_verdict_set_is_closed():
    assert set(HEALTH_VERDICTS) == {'healthy', 'finding', 'not_applicable', 'unavailable', 'incomplete', 'failed'}


@pytest.mark.parametrize('data, code, verdict, exit_code', [
    ({}, 0, 'healthy', 0),
    (_CHECK_PASS, 0, 'healthy', 0),
    ({}, 1, 'finding', 1),                                   # completed answer, child exit 1
    (_CHECK_WARN, 1, 'finding', 1),
    (_CHECK_FAIL, 2, 'finding', 2),                          # exit 2 carrying a real verdict is not a crash
    (_CHECK_FAIL, 0, 'finding', 2),                          # nor is a verdict the exit code did not carry
    ({'applicable': False}, 0, 'not_applicable', 1),
    ({'meta': {'warnings': [{'type': 'parse_degraded'}]}}, 0, 'incomplete', 1),
    ({'meta': {'errors': ['broken']}}, 0, 'incomplete', 1),
    ({'error': 'cannot answer'}, 1, 'failed', 1),
    ({}, 2, 'failed', 2),                                    # exit 2, no verdict: a crash or usage error
    ({}, -9, 'failed', 2),
    ([], 0, 'failed', 2),
])
def test_uri_children_classify_by_the_answer_not_the_exit_code(data, code, verdict, exit_code):
    result = _uri_health_result('ssl', code, json.dumps(data))
    assert (result.verdict, result.exit_code) == (verdict, exit_code)


def test_uri_child_that_printed_no_json_is_failed():
    result = _uri_health_result('ssl', 2, 'Traceback (most recent call last)', 'boom')
    assert (result.verdict, result.exit_code) == ('failed', 2)


_ACCOUNTING = {'total': 1, 'returned': 1, 'exact': True}


@pytest.mark.parametrize('data, code, verdict', [
    ({'total': 0, 'detections': []}, 0, 'healthy'),
    ({'total': 2, 'detections': [{'severity': 'medium'}, {'severity': 'low'}]}, 1, 'finding'),
    ({'total': 1, 'detections': [{'severity': 'high'}]}, 1, 'finding'),
    ({'total': 1, 'detections': [{'severity': 'critical'}]}, 1, 'finding'),
    ({'total': 0, 'detections': [], 'warning': 'parse incomplete'}, 3, 'incomplete'),
    ({'total': 0, 'detections': [], 'errors': [{'rule': 'I002', 'error': 'broken'}]}, 3, 'failed'),
    ({'total': 0, 'detections': []}, -9, 'failed'),
    ({'applicable': False}, 0, 'not_applicable'),
    ({'error': 'check blew up'}, 2, 'failed'),
    ({'summary': {'total_issues': 0, 'files_checked': 0}}, 0, 'not_applicable'),
    ({'summary': {'total_issues': 0, 'files_checked': 1, 'scan_disclosures': ['I002 skipped']}}, 3, 'incomplete'),
])
def test_code_results_classify_findings_apart_from_lost_analysis(data, code, verdict):
    assert _code_result(data, code, dict(_ACCOUNTING)).verdict == verdict


def test_skipped_oversized_directory_is_incomplete_not_healthy(tmp_path):
    (tmp_path / 'a.py').write_text('x = 1\n', encoding='utf-8')
    with patch.object(health, '_HEALTH_MAX_FILES', 0):
        result = health._check_code(tmp_path, type('A', (), {'select': None})())
    assert (result.outcome, result.verdict) == ('skipped', 'incomplete')


def test_missing_and_unreadable_targets_are_unavailable(tmp_path):
    args = type('A', (), {'select': None})()
    assert health._check_target(str(tmp_path / 'nope'), args).verdict == 'unavailable'
    conf = tmp_path / 'site.conf'
    conf.write_text('server {}\n', encoding='utf-8')
    with patch.object(Path, 'read_text', side_effect=OSError('denied')):
        assert health._check_target(str(conf), args).verdict == 'unavailable'


def test_nginx_findings_and_clean_config(tmp_path):
    args = type('A', (), {'select': None})()
    conf = tmp_path / 'site.conf'
    conf.write_text('server {\n}\n', encoding='utf-8')
    with patch('reveal.rules.RuleRegistry.check_file', return_value=[object()]):
        assert health._check_target(str(conf), args).verdict == 'finding'
    with patch('reveal.rules.RuleRegistry.check_file', return_value=[]):
        assert health._check_target(str(conf), args).verdict == 'healthy'


def test_legacy_construction_derives_a_safe_verdict():
    # Existing callers build HealthResult(code, summary[, outcome]); an unknown outcome never reads as clean.
    assert HealthResult(0, 'ok').verdict == 'healthy'
    assert HealthResult(1, 'warn').verdict == 'finding'
    assert HealthResult(2, 'x', 'failed').verdict == 'failed'
    assert HealthResult(0, 'x', 'mystery').verdict == 'failed'
