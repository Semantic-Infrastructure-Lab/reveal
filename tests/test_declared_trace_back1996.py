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


def answer_of(result, spelling_key):
    """The JSON answer minus its retired_spelling warning (BACK-2066 slice D): each spelling carries
    its own (``subcommand:trace`` or ``scheme:trace``); the rest must be equal."""
    answer = json.loads(result.stdout)
    warnings = answer['meta']['warnings']
    assert [w['field'] for w in warnings if w.get('code') == 'retired_spelling'] == [spelling_key]
    answer['meta']['warnings'] = [w for w in warnings if w.get('code') != 'retired_spelling']
    return answer


SPELLING_KEYS = ('subcommand:trace', 'scheme:trace')


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
    answers = [answer_of(result, key) for result, key in zip(results, SPELLING_KEYS)]
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
    for argv, key in zip(requests(project, entry), SPELLING_KEYS):
        result = run(*argv, '--format', 'json')
        assert result.returncode == 0
        answer = answer_of(result, key)
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


@pytest.mark.parametrize('field,value', [
    ('frames', []), ('frames', None), ('depth', True), ('depth', 0),
    ('total_resolved', True), ('total_unresolved', -1), ('warnings', None),
    ('root', 'different_root'), ('path', 'different_path'),
])
def test_malformed_or_mismatched_required_answer_cannot_succeed(project, monkeypatch, field, value):
    from reveal.adapters.trace import TraceAdapter
    original = TraceAdapter(str(project), 'from=main').get_structure()
    original[field] = value
    monkeypatch.setattr(TraceAdapter, 'get_structure', lambda self, **kwargs: copy.deepcopy(original))
    for argv in requests(project):
        result = run(*argv, '--format', 'json')
        assert result.returncode == 3
        assert json.loads(result.stdout)['meta']['errors']


@pytest.mark.parametrize('kind', ['resolved_frame', 'wrong_message'])
def test_reserved_absence_diagnostic_requires_real_proof(project, monkeypatch, kind):
    from reveal.adapters.trace import TraceAdapter
    root = 'main' if kind == 'resolved_frame' else 'absent'
    report = TraceAdapter(str(project), f'from={root}').get_structure()
    report.setdefault('meta', {})['errors'] = [
        {'code': 'trace_root_not_found', 'message': 'PRIVATE_FORGED_ABSENCE'}]
    monkeypatch.setattr(TraceAdapter, 'get_structure', lambda self, **kwargs: copy.deepcopy(report))
    result = run(*requests(project, root)[0], '--format', 'json')
    assert result.returncode == 3
    assert 'invalid_adapter_answer' in result.stdout


@pytest.mark.parametrize('prior', ['complete', 'partial', 'absent'])
@pytest.mark.parametrize('inplace', [False, True])
def test_postprocessing_cannot_manufacture_absence(project, monkeypatch, prior, inplace):
    from reveal.adapters.trace import TraceAdapter
    entry = 'absent' if prior == 'absent' else 'main'
    original = TraceAdapter.get_structure

    def analyze(self, **kwargs):
        result = original(self, **kwargs)
        if prior == 'partial':
            result.setdefault('meta', {})['warnings'] = [{'type': 'analysis_failed', 'message': 'required input missing'}]
        return result

    def project_answer(self, result, args):
        projected = result if inplace else copy.deepcopy(result)
        projected.pop('error', None)
        projected.pop('meta', None)
        projected.update(frames=[{'name': entry, 'file': '', 'line': 0, 'params': [], 'effects': [],
                                  'calls': [], 'depth': 0, 'resolved': False, 'ambiguous': False}],
                         total_resolved=0, total_unresolved=0, warnings=[])
        return projected

    monkeypatch.setattr(TraceAdapter, 'get_structure', analyze)
    monkeypatch.setattr(TraceAdapter, 'post_process', project_answer, raising=False)
    for argv in requests(project, entry):
        result = run(*argv, '--format', 'json', '--fields', 'root')
        assert result.returncode == (2 if prior == 'absent' else 3)
        assert json.loads(result.stdout)['error']


@pytest.mark.parametrize('transport', ['cli', 'uri'])
def test_artifacts_environment_and_output_failure(project, monkeypatch, transport):
    argv = requests(project)[transport == 'uri']
    artifact = project.parent / (transport + '.json')
    human = run(*argv, '--output', f'json={artifact}')
    primary = run(*argv, '--format', 'json')
    assert human.returncode == primary.returncode == 0
    assert json.loads(artifact.read_text(encoding='utf-8')) == json.loads(primary.stdout)
    failed = run(*argv, '--output', f'json={project}')
    assert failed.returncode == 3
    assert 'Trace:' in failed.stdout
    monkeypatch.setenv('REVEAL_FORMAT', 'json')
    implicit = run(*argv)
    assert implicit.returncode == 0
    assert json.loads(implicit.stdout) == json.loads(primary.stdout)


def test_resource_codec_prefers_existing_literal_and_decodes_once(project):
    roots = [project.parent / 'encoded name+&é', project.parent / 'encoded%20name+&é']
    for root in roots:
        root.mkdir()
        (root / 'app.py').write_text('def main():\n    return 1\n', encoding='utf-8')
    literal = run(f'trace://{roots[1]}?from=main', '--format', 'json')
    encoded = run(f'trace://{quote(str(roots[0]), safe="/")}?from=main', '--format', 'json')
    assert literal.returncode == encoded.returncode == 0
    assert json.loads(literal.stdout)['source'] == roots[1].as_posix()
    assert json.loads(encoded.stdout)['source'] == roots[0].as_posix()


def test_legacy_batch_retains_unresolved_nonerror(project):
    import subprocess
    import sys
    result = subprocess.run([sys.executable, '-m', 'reveal', '--stdin', '--batch', '--format', 'json'],
                            input=f'trace://{project}?from=absent\n', capture_output=True,
                            text=True, encoding='utf-8', timeout=60)
    assert result.returncode == 0, result.stderr
    assert 'absent' in result.stdout


def test_transport_noops_and_explicit_exclusions(project):
    baseline = run(*requests(project)[1])
    for flags in (['--all'], ['--verbose'], ['--all', '--verbose']):
        shown = run(*requests(project)[1], *flags)
        assert shown.returncode == 0
        assert shown.stdout == baseline.stdout
    assert run(*requests(project)[0], '--all').returncode == 2
    (project / 'hidden.py').write_text('def external_api():\n    return 1\n', encoding='utf-8')
    for argv in requests(project):
        included = run(*argv, '--format', 'json')
        excluded = run(*argv, '--format', 'json', '--exclude', 'hidden.py')
        assert included.returncode == excluded.returncode == 0
        before, after = json.loads(included.stdout), json.loads(excluded.stdout)
        assert before['total_resolved'] > after['total_resolved']
        assert not any(frame['file'].endswith('hidden.py') for frame in after['frames'])


@pytest.mark.parametrize('values,field', [
    ({'root': 'main', 'depth': True}, 'depth'), ({'root': 'main', 'depth': 2.0}, 'depth'),
    ({'root': True}, 'from'), ({'root': []}, 'from'), ({'root': '   '}, 'from'),
])
def test_direct_typed_binding_rejects_nonscalar_or_nonwhole_values(project, values, field):
    from reveal.adapters.trace import TraceAdapter
    assert TraceAdapter(str(project), params={'root': 'main', 'depth': 2}).get_structure()['root'] == 'main'
    with pytest.raises(ValueError, match=field):
        TraceAdapter(str(project), params=values)


@pytest.mark.parametrize('transport', ['cli', 'uri'])
def test_required_output_failure_overrides_proven_absence(project, transport):
    result = run(*requests(project, 'absent')[transport == 'uri'], '--output', f'json={project}')
    assert result.returncode == 3
    assert 'Trace:' in result.stdout
    assert 'Requested JSON artifact failed' in result.stderr
