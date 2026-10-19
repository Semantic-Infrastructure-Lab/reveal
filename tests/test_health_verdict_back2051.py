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


# --- aggregation: facts, never the numeric maximum of child codes --------------------------------

import io
import os
import subprocess
import sys
from argparse import Namespace
from contextlib import redirect_stdout


def _finding(code=1):
    return HealthResult(code, 'f', 'ok', verdict='finding')


_HEALTHY = HealthResult(0, 'h')
_NOT_APPLICABLE = HealthResult(1, 'n/a', 'not_applicable')
_UNAVAILABLE = HealthResult(1, 'gone', 'failed', verdict='unavailable')
_INCOMPLETE = HealthResult(1, 'partial', 'partial')
_FAILED = HealthResult(2, 'boom', 'failed')


def _run(results, fail_on=None):
    args = Namespace(targets=[f't{i}' for i in range(len(results))], health_all=False, format='text',
                     select=None, fail_on=fail_on)
    with patch.object(health, '_check_target', side_effect=results), redirect_stdout(io.StringIO()):
        with pytest.raises(SystemExit) as exit_info:
            health.run_health(args)
    return exit_info.value.code


@pytest.mark.parametrize('results, fail_on, expected', [
    ([_HEALTHY], None, 0),
    ([_finding(1)], None, 1),
    ([_finding(2)], None, 1),                       # a severe finding is a finding, not the usage code
    ([_finding(1), _finding(2)], 'findings', 1),
    ([_NOT_APPLICABLE], None, 0),                   # not applicable alone never fails a run
    ([_NOT_APPLICABLE, _HEALTHY], None, 0),
    ([_UNAVAILABLE], None, 3),
    ([_INCOMPLETE], None, 3),
    ([_FAILED], None, 3),
    ([_finding(2), _FAILED], None, 3),              # lost evidence beats a findings gate
    ([_finding(1), _INCOMPLETE], 'findings', 3),
    ([_finding(2)], 'none', 0),
    ([_finding(1), _HEALTHY], 'none', 0),
    ([_finding(1), _FAILED], 'none', 3),            # none never hides a failure
    ([_UNAVAILABLE], 'none', 3),
])
def test_overall_code_comes_from_verdicts(results, fail_on, expected):
    assert _run(results, fail_on) == expected


def test_one_target_raising_is_failed_and_does_not_end_the_others():
    code = _run([_finding(1), RuntimeError('x')])
    assert code == 3


def test_json_overall_exit_is_the_process_code_and_rows_carry_verdicts():
    args = Namespace(targets=['a', 'b'], health_all=False, format='json', select=None, fail_on=None)
    out = io.StringIO()
    with patch.object(health, '_check_target', side_effect=[_finding(2), _UNAVAILABLE]), redirect_stdout(out):
        with pytest.raises(SystemExit) as exit_info:
            health.run_health(args)
    data = json.loads(out.getvalue())
    assert data['overall_exit'] == exit_info.value.code == 3
    assert [r['verdict'] for r in data['results']] == ['finding', 'unavailable']


def _banner(rows):
    out = io.StringIO()
    with redirect_stdout(out):
        health._render_results(rows)
    return out.getvalue()


def test_banner_follows_verdicts():
    row = lambda r, t='x': {'target': t, **__import__('dataclasses').asdict(r)}  # noqa: E731
    assert 'Health: PASS' in _banner([row(_HEALTHY), row(_NOT_APPLICABLE)])
    assert 'Health: WARN' in _banner([row(_finding(1))])
    assert 'Health: FAIL' in _banner([row(_finding(2))])
    assert 'Health: INCOMPLETE' in _banner([row(_finding(1)), row(_INCOMPLETE)])
    assert 'Health: INCOMPLETE' in _banner([row(_UNAVAILABLE)])


def test_banner_still_reads_rows_without_a_verdict():
    assert 'Health: FAIL' in _banner([{'target': 'code', 'exit_code': 2, 'summary': 'code: 7 violations'}])
    assert 'Health: PASS' in _banner([{'target': 'code', 'exit_code': 0, 'summary': 'code: healthy'}])


def _cli(*args):
    env = {**os.environ, 'REVEAL_DISK_CACHE': '0'}
    return subprocess.run([sys.executable, '-m', 'reveal', *args], capture_output=True, text=True,
                          env=env, timeout=180, check=False, encoding='utf-8')


def test_real_cli_codes(tmp_path):
    clean = tmp_path / 'ok.py'
    clean.write_text('def f(x):\n    return x\n', encoding='utf-8')
    assert _cli('health', str(clean)).returncode == 0
    gone = _cli('health', str(tmp_path / 'missing'))
    assert gone.returncode == 3
    refused = _cli('health', 'ssl://127.0.0.1:9')
    assert refused.returncode == 1                  # a refused connection is a finding, not a crash
    assert _cli('health', 'ssl://127.0.0.1:9', '--fail-on', 'none').returncode == 0
    assert _cli('health', str(tmp_path / 'missing'), '--fail-on', 'none').returncode == 3
    assert _cli('health').returncode == 2           # no target: usage


_CAPABILITY_NOTE = 'W-CAP-2: I001 has no unused-import detection for these languages; 8 file(s) were not checked by it: .php (4)'


def _capability_report(issues):
    return {'summary': {'total_issues': issues, 'files_checked': 1, 'scan_disclosures': [_CAPABILITY_NOTE]},
            'files': [{'detections': [{'severity': 'medium'}] * issues}]}


def test_capability_note_alone_is_not_lost_evidence():
    # check keeps exit 0/1 for a language-capability note and exit 3 only for a capped or lost scan;
    # health follows the child, and still shows the note.
    clean = _code_result(_capability_report(0), 0, dict(_ACCOUNTING))
    assert (clean.verdict, clean.exit_code) == ('healthy', 0)
    assert 'W-CAP-2' in clean.summary
    found = _code_result(_capability_report(2), 1, dict(_ACCOUNTING))
    assert (found.verdict, found.exit_code) == ('finding', 1)
    assert 'W-CAP-2' in found.summary


def test_capped_scan_disclosure_with_child_exit_3_stays_incomplete():
    assert _code_result(_capability_report(0), 3, dict(_ACCOUNTING)).verdict == 'incomplete'
