"""Health interprets actual check envelopes; a plausible zero cannot hide failure."""
from argparse import Namespace
from dataclasses import asdict
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch
import json
import pytest
from reveal.cli.commands.health import _check_code, _code_result

pytestmark = pytest.mark.component


def accounting():
    return {'scope': 'scan', 'total': 3, 'returned': 3, 'exact': True, 'limit': 5000,
            'analyzed_files': 0, 'skipped': False}


@pytest.mark.parametrize('data,code,expected', [
    ({'error': 'query failed'}, 1, 'failed'),
    ({'applicable': False}, 0, 'not_applicable'),
    ({'summary': {'total_issues': 0, 'files_checked': 3, 'files_errored': 1}}, 3, 'failed'),
    ({'summary': {'total_issues': 0, 'files_checked': 3, 'files_degraded': 1}}, 3, 'partial'),
    ({'summary': {'total_issues': 0, 'files_checked': 3, 'scan_disclosures': ['D005 skipped']}}, 3, 'partial'),  # a capped scan makes check exit 3
    ({'summary': {'total_issues': 0, 'files_checked': 0}}, 0, 'not_applicable'),
    ({'total': 0, 'detections': []}, 1, 'failed'),
    ({'total': 0, 'detections': []}, 0, 'ok'),
])
def test_explicit_outcomes(data, code, expected):
    budget = accounting()
    if 'summary' not in data:
        budget.update(total=1, returned=1)
    result = _code_result(data, code, budget)
    assert result.outcome == expected
    assert ('healthy' in result.summary) == (expected == 'ok')
    assert result.scan_budget['total'] == budget['total']


@pytest.mark.parametrize('data', [{}, [], {'total': '0', 'detections': []},
                                  {'total': 0, 'detections': None}])
def test_malformed_success_is_unknown_not_healthy(tmp_path, data):
    file = tmp_path / 'demo.py'; file.write_text('value=1\n', encoding='utf-8')
    with patch('subprocess.run', return_value=CompletedProcess([], 0, json.dumps(data), '')):
        result = _check_code(file, Namespace(select=None))
    assert result.exit_code == 2 and result.outcome == 'failed'


def test_real_check_violation_is_not_reported_healthy(tmp_path):
    file = tmp_path / 'demo.py'
    file.write_text('def work(x):\n'+''.join(f'    if x == {i}:\n        x += {i}\n' for i in range(25))+'    return x\n', encoding='utf-8')
    result = _check_code(file, Namespace(select='C901'))
    assert result.exit_code == 1 and '1 violations' in result.summary
    assert result.scan_budget['analyzed_files'] == 1
    assert 'healthy' not in result.summary


def test_directory_budget_is_numeric_in_real_json_and_text(tmp_path):
    from conftest import _run_reveal_direct
    (tmp_path / 'demo.py').write_text('value = 1\n', encoding='utf-8')
    answer = _run_reveal_direct('health', str(tmp_path), '--select', 'C901', '--format', 'json')
    result = json.loads(answer.stdout)['results'][0]
    assert result['scan_budget']['total'] == 1
    assert result['scan_budget']['analyzed_files'] == 1
    assert result['scan_budget']['exact']
    text = _run_reveal_direct('health', str(tmp_path), '--select', 'C901')
    assert '1 candidate files, 1 analyzed' in text.stdout



def test_population_change_cannot_claim_exact_or_clean_accounting(capsys):
    result = _code_result({'summary': {'total_issues': 0, 'files_checked': 4}}, 0, accounting())
    assert result.outcome == 'partial' and result.exit_code == 1
    assert result.scan_budget['preflight_files'] == 3
    assert result.scan_budget['total'] == 4 and result.scan_budget['analyzed_files'] == 4
    assert result.scan_budget['exact'] is False
    assert 'population changed' in result.summary
    from reveal.cli.commands.health import _render_results
    _render_results([{'target': '.', **asdict(result)}])
    assert 'at least 4 candidate files' in capsys.readouterr().out
