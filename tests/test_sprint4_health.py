"""Outcome table: completed, failed, partial, unavailable and malformed answers."""
from argparse import Namespace
import json
import pytest
from reveal.cli.commands.health import _uri_health_result, _code_result

pytestmark = pytest.mark.component


@pytest.mark.parametrize('data,code,expected', [
    ({}, 0, 'ok'),
    ({'error': 'cannot answer'}, 1, 'failed'),
    ({'applicable': False}, 0, 'not_applicable'),
    ({'meta': {'warnings': [{'type': 'parse_degraded'}]}}, 0, 'partial'),
    ({'meta': {'errors': ['broken']}}, 0, 'partial'),
    ({}, -9, 'failed'),
    ({}, 2, 'failed'),
    ([], 0, 'failed'),
])
def test_uri_outcome_table(data, code, expected):
    result = _uri_health_result('stats', code, json.dumps(data))
    assert result.outcome == expected
    assert (result.exit_code == 0) == (expected == 'ok')


@pytest.mark.parametrize('directory', [False, True])
@pytest.mark.parametrize('status,code,expected', [
    ('clean', 0, 'ok'), ('degraded', 3, 'partial'), ('failed', 3, 'failed'),
    ('killed', -9, 'failed'), ('unavailable', 0, 'not_applicable'),
])
def test_file_and_directory_outcome_table(directory, status, code, expected):
    data = {'total': 0, 'detections': []}
    if directory:
        data = {'summary': {'total_issues': 0, 'files_checked': 1}}
    if status == 'degraded':
        if directory:
            data['summary']['files_degraded'] = 1
        else:
            data['warning'] = 'parse incomplete'
    if status == 'failed':
        if directory:
            data['summary']['files_errored'] = 1
        else:
            data['errors'] = [{'rule': 'I002', 'error': 'broken'}]
    if status == 'unavailable':
        data = {'applicable': False}
    result = _code_result(data, code, {'total': 1, 'returned': 1, 'exact': True})
    assert result.outcome == expected
    assert (result.exit_code == 0) == (expected == 'ok')


def test_high_is_not_counted_as_critical():
    result = _code_result({'total': 1, 'detections': [{'severity': 'high'}]}, 1,
                          {'total': 1, 'returned': 1, 'exact': True})
    assert result.exit_code == 2
    assert '(1 high, 0 critical)' in result.summary


def test_real_degraded_file_directory_and_stats_agree(tmp_path):
    from conftest import _run_reveal_direct
    bad = tmp_path / 'bad.py'
    bad.write_text('def broken(\n', encoding='utf-8')
    for target in (str(bad), str(tmp_path), 'stats://' + str(tmp_path)):
        result = _run_reveal_direct('health', target, '--select', 'C901', '--format', 'json')
        assert result.returncode == 1
        assert json.loads(result.stdout)['results'][0]['outcome'] == 'partial'
    bad.write_text('value = 1\n', encoding='utf-8')
    for target in (str(bad), str(tmp_path), 'stats://' + str(tmp_path)):
        result = _run_reveal_direct('health', target, '--select', 'C901', '--format', 'json')
        assert result.returncode == 0
        assert json.loads(result.stdout)['results'][0]['outcome'] == 'ok'
