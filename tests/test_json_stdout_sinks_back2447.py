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
    primary = json.loads(result.stdout)
    assert primary['type']
    assert primary['meta']['output_errors'][0]['code'] == 'artifact_write_failed'
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


@pytest.mark.parametrize('noun', NOUNS)
@pytest.mark.parametrize('spelling', ['cli', 'uri'])
def test_declared_text_destination_is_the_existing_primary_text_view(project, tmp_path, noun, spelling):
    separate = _run_reveal_direct(*argv_for(noun, spelling), '--format', 'text')
    destination = tmp_path / 'view.txt'
    result = _run_reveal_direct(*argv_for(noun, spelling), '--format', 'json',
                                '--output', f'text={destination}')
    assert result.returncode == separate.returncode
    assert json.loads(result.stdout)['type']
    assert destination.read_text(encoding='utf-8') == separate.stdout


def test_empty_directory_json_destination_is_a_completed_empty_answer(tmp_path):
    root = tmp_path / 'empty'
    root.mkdir()
    destination = tmp_path / 'empty.json'
    result = _run_reveal_direct('check', str(root), '--format', 'json', '--output', f'json={destination}')
    assert result.returncode == 0, result.stderr
    primary = json.loads(result.stdout)
    assert primary['summary']['files_checked'] == 0
    assert json.loads(destination.read_text(encoding='utf-8')) == primary


@pytest.mark.parametrize('legacy', [False, True])
def test_legacy_uri_failed_source_and_requested_write_failure_exits_three(tmp_path, monkeypatch, legacy):
    key = '__SHINING_TEST_ABSENT_KEY__'
    monkeypatch.delenv(key, raising=False)
    destination = tmp_path / 'missing' / 'out.json'
    sink = ['--also-json', str(destination)] if legacy else ['--output', f'json={destination}']
    result = _run_reveal_direct(f'env://{key}', '--format', 'json', *sink)
    assert result.returncode == 3, result.stderr
    primary = json.loads(result.stdout)
    assert primary['error']
    assert primary['meta']['output_errors'][0]['code'] == 'artifact_write_failed'
    assert result.stderr.count('Error (env://)') == 1
    assert result.stderr.count('Requested JSON artifact failed') == 1
    assert not destination.exists()


@pytest.mark.parametrize('with_sink', [False, True])
def test_legacy_uri_failed_source_keeps_existing_exit_when_no_write_fails(tmp_path, monkeypatch, with_sink):
    key = '__SHINING_TEST_ABSENT_KEY__'
    monkeypatch.delenv(key, raising=False)
    destination = tmp_path / 'out.json'
    sink = ['--output', f'json={destination}'] if with_sink else []
    result = _run_reveal_direct(f'env://{key}', '--format', 'json', *sink)
    # The source's own failure code (2 since BACK-2521: an element miss is an invalid request),
    # not a write failure's 3: a sink that wrote changes nothing.
    assert result.returncode == 2, result.stderr
    primary = json.loads(result.stdout)
    assert primary['error']
    assert 'output_errors' not in primary.get('meta', {})
    assert 'Requested JSON artifact failed' not in result.stderr
    if with_sink:
        assert json.loads(destination.read_text(encoding='utf-8')) == primary
