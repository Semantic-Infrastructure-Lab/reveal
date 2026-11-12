"""Display thresholds never define the population used by Check's exit gate."""
import json

import pytest

from conftest import _run_reveal_in


@pytest.fixture
def tree(tmp_path):
    (tmp_path / 'Dockerfile').write_text('FROM python:latest\n# ' + 'x' * 150 + '\n', encoding='utf-8')
    (tmp_path / 'a.py').write_text('try:\n    pass\nexcept:\n    pass\n', encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('target', ['Dockerfile', '.'])
@pytest.mark.parametrize('policy,expected', [(None, 0), ('none', 0), ('low', 1), ('medium', 1), ('high', 0), ('findings', 1)])
def test_medium_displays_but_only_high_gates_by_default(tree, target, policy, expected):
    flags = ['--fail-on', policy] if policy else []
    run = _run_reveal_in(tree, 'check', target, '--select', 'S701,E501', '--format', 'json', *flags)
    assert run.returncode == expected, run.stderr
    answer = json.loads(run.stdout)
    assert answer['summary']['exit_code'] == expected
    rows = [d for f in answer['files'] for d in f['detections']]
    assert [d['rule_code'] for d in rows] == ['S701']
    assert answer['summary']['low_count'] == 1
    assert answer['summary']['severity_counts'] == {'low': 1, 'medium': 1, 'high': 0, 'critical': 0}


@pytest.mark.parametrize('target', ['a.py', '.'])
@pytest.mark.parametrize('flags', [[], ['--max-items', '0'], ['--severity', 'critical']])
def test_high_gate_survives_display_cuts_and_thresholds(tree, target, flags):
    run = _run_reveal_in(tree, 'check', target, '--select', 'B001', '--format', 'json', *flags)
    assert run.returncode == 1, run.stderr
    assert json.loads(run.stdout)['summary']['severity_counts']['high'] == 1


@pytest.mark.parametrize('target', ['Dockerfile', '.'])
def test_low_count_prints_once_and_low_can_be_requested(tree, target):
    run = _run_reveal_in(tree, 'check', target, '--select', 'E501')
    assert run.returncode == 0, run.stderr
    assert run.stdout.count('Low findings: 1') == 1
    run = _run_reveal_in(tree, 'check', target, '--select', 'E501', '--severity', 'low', '--format', 'json')
    assert run.returncode == 0
    assert any(f['detections'] for f in json.loads(run.stdout)['files'])


def test_non_check_commands_reject_severity_policy(tree):
    run = _run_reveal_in(tree, 'overview', '.', '--fail-on', 'high')
    assert run.returncode == 2
    assert 'not supported' in run.stderr


def test_mcp_uses_the_same_display_threshold_and_low_count(tree):
    from reveal.mcp_server import reveal_check
    answer = reveal_check(str(tree / 'Dockerfile'), select='E501,S701')
    assert '[S701]' in answer and '[E501]' not in answer
    assert answer.count('Low findings: 1') == 1
    answer = reveal_check(str(tree / 'Dockerfile'), severity='low', select='E501')
    assert '[E501]' in answer


@pytest.mark.parametrize('policy', ['none', 'low', 'medium', 'high', 'findings'])
def test_incomplete_analysis_beats_every_severity_gate(tree, policy):
    (tree / 'bad.py').write_text('def broken(:\n', encoding='utf-8')
    result = _run_reveal_in(tree, 'check', 'bad.py', '--select', 'B001', '--fail-on', policy,
                            '--severity', 'critical', '--format', 'json')
    assert result.returncode == 3
    assert json.loads(result.stdout)['summary']['exit_code'] == 3


@pytest.mark.parametrize('target', ['Dockerfile', '.'])
def test_text_sidecar_matches_json_with_hidden_lows(tree, target):
    artifact = tree.parent / (tree.name + '-answer.json')
    text = _run_reveal_in(tree, 'check', target, '--select', 'E501,S701', '--output', f'json={artifact}')
    direct = _run_reveal_in(tree, 'check', target, '--select', 'E501,S701', '--format', 'json')
    assert text.returncode == direct.returncode == 0
    assert json.loads(artifact.read_text(encoding='utf-8')) == json.loads(direct.stdout)
