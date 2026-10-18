"""Trace's canonical binding preserves evidence across both public spellings."""
import copy
import json
from urllib.parse import quote

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.ast.analysis import StructureList


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / 'project'
    root.mkdir()
    (root / 'app.py').write_text(
        'def main():\n    helper()\n    external_api()\n\ndef helper():\n    return 1\n\ndef true():\n    return 2\n', encoding='utf-8')
    return root


def requests(root, entry='main', depth=None):
    cli = ['trace', str(root), '--from', entry]
    uri = [f'trace://{root}?from={quote(entry, safe="")}']
    if depth is not None:
        cli += ['--depth', depth]
        uri[0] += '&depth=' + depth
    return cli, uri


@pytest.mark.parametrize('depth', [None, '-2', '+2', '0', '8'])
@pytest.mark.parametrize('provenance', [False, True])
def test_canonical_parity(project, depth, provenance):
    options = ['--format', 'json', '--no-gitignore'] + (['--provenance'] if provenance else [])
    results = [run(*argv, *options) for argv in requests(project, depth=depth)]
    assert [result.returncode for result in results] == [0, 0]
    answers = [json.loads(result.stdout) for result in results]
    assert answers[0]['type'] == 'trace'
    assert answers[0]['frames'][0]['resolved']
    if provenance:
        for answer, argv in zip(answers, requests(project, depth=depth)):
            assert answer['execution']['command'] == ' '.join(['reveal', *argv, *options])
            answer['execution'].pop('command')
    assert answers[0] == answers[1]


@pytest.mark.parametrize('entry', ['true', '0', 'false'])
def test_scalar_selector_is_not_coerced(project, entry):
    expected = 0 if entry == 'true' else 2
    for argv in requests(project, entry):
        result = run(*argv, '--format', 'json')
        assert result.returncode == expected
        assert json.loads(result.stdout)['root'] == entry


def test_once_percent_selector_and_literal_resource(project):
    source = project / 'name%20+&é.py'
    source.write_text('def entrée():\n    return 1\n', encoding='utf-8')
    entry = source.name + ':entrée'
    answers = []
    for argv in requests(project, entry):
        result = run(*argv, '--format', 'json')
        assert result.returncode == 0
        answer = json.loads(result.stdout)
        assert answer['root'] == entry
        assert answer['frames'][0]['resolved']
        answers.append(answer)
    assert answers[0] == answers[1]


@pytest.mark.parametrize('depth', ['1.5', 'true', 'NaN', '1e2', ''])
def test_invalid_depth_is_structured_usage(project, depth):
    for argv in requests(project, depth=depth):
        result = run(*argv, '--format', 'json')
        assert result.returncode == 2
        assert json.loads(result.stdout)['type'] == 'trace'
        assert 'depth' in result.stderr


@pytest.mark.parametrize('transport', ['cli', 'uri'])
def test_absent_root_is_usage_with_canonical_answer(project, transport):
    argv = requests(project, 'absent')[transport == 'uri']
    result = run(*argv, '--format', 'json')
    assert result.returncode == 2
    answer = json.loads(result.stdout)
    assert answer['type'] == 'trace'
    assert answer['error'] and 'absent' in answer['error']
    assert answer['frames'][0]['resolved'] is False


@pytest.mark.parametrize('transport', ['cli', 'uri'])
def test_incomplete_collection_beats_absence(project, monkeypatch, transport):
    structures = StructureList()
    structures.skipped = [(str(project / 'unavailable.py'), 'PermissionError: unavailable')]
    monkeypatch.setattr('reveal.adapters.ast.analysis.collect_structures', lambda path: structures)
    result = run(*requests(project, 'absent')[transport == 'uri'], '--format', 'json')
    assert result.returncode == 3
    assert json.loads(result.stdout)['meta']['warnings'][0]['type'] == 'analysis_failed'
