"""Explicit JSON destinations are written even when JSON is also stdout."""
import json
from argparse import Namespace

import pytest

from conftest import _run_reveal_direct
from reveal.utils.json_utils import write_also_json
from test_declared_parity_back2053 import NOUNS, argv_for, project

pytestmark = pytest.mark.contract


def test_owner_writes_explicit_json_destination_beside_json_stdout(tmp_path):
    destination = tmp_path / 'result.json'
    write_also_json({'type': 'fixture', 'answer': 7},
                    Namespace(format='json', output=[f'json={destination}'], also_json=None))
    assert destination.is_file(), 'an explicit destination must not silently disappear'
    assert json.loads(destination.read_text(encoding='utf-8')) == {'type': 'fixture', 'answer': 7}


@pytest.mark.parametrize('noun', NOUNS)
@pytest.mark.parametrize('spelling', ['cli', 'uri'])
@pytest.mark.parametrize('provenance', [False, True])
def test_declared_json_destination_equals_primary_document(project, tmp_path, noun, spelling, provenance):
    destination = tmp_path / 'mirror.json'
    extra = ['--provenance'] if provenance else []
    result = _run_reveal_direct(*argv_for(noun, spelling), '--format', 'json',
                                '--output', f'json={destination}', *extra)
    assert result.returncode in (0, 1), result.stderr
    primary = json.loads(result.stdout)
    assert primary['type']
    assert destination.is_file(), 'the requested JSON sink was not written'
    assert json.loads(destination.read_text(encoding='utf-8')) == primary
    if provenance:
        assert primary['execution']


@pytest.mark.parametrize('route', ['declared', 'uri', 'check-file', 'check-directory'])
@pytest.mark.parametrize('legacy', [False, True])
def test_failed_json_destination_keeps_primary_and_exits_three(project, tmp_path, route, legacy):
    argv = {'declared': ['metrics', 'proj'], 'uri': ['ast://proj?type=function'],
            'check-file': ['check', 'proj/app.py'], 'check-directory': ['check', 'proj']}[route]
    destination = tmp_path / 'missing' / 'mirror.json'
    sink = ['--also-json', str(destination)] if legacy else ['--output', f'json={destination}']
    result = _run_reveal_direct(*argv, '--format', 'json', *sink)
    assert result.returncode == 3, result.stderr
    assert json.loads(result.stdout)['type']
    assert result.stderr.count('Requested JSON artifact failed') == 1
    assert 'Traceback' not in result.stderr


@pytest.mark.parametrize('target', ['proj/app.py', 'proj'])
def test_unsupported_view_rejects_json_destination_even_with_json_stdout(project, tmp_path, target):
    destination = tmp_path / 'mirror.json'
    result = _run_reveal_direct(target, '--format', 'json', '--output', f'json={destination}')
    assert result.returncode == 2, result.stderr
    assert result.stdout == ''
    assert 'not supported' in result.stderr
    assert not destination.exists()


def test_no_file_sink_keeps_json_stdout_unchanged(project):
    result = _run_reveal_direct('metrics', 'proj', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['type'] == 'stats_summary'
