"""Surface's two spellings share answers, diagnostics and D6 outcomes."""

import copy
import json
from urllib.parse import quote

import pytest

from conftest import _run_reveal_direct


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'app.py').write_text(
        "import os\nvalue = os.getenv('SERVICE_URL')\nother = os.environ['TOKEN']\n",
        encoding='utf-8',
    )
    tests = root / 'tests'
    tests.mkdir()
    (tests / 'test_app.py').write_text("import os\nvalue = os.getenv('TEST_ONLY')\n", encoding='utf-8')
    return root


def run(*args):
    return _run_reveal_direct(*args)


def assert_equal_answers(left, right):
    """Only actual invocation spelling may differ, never arbitrary metadata."""
    a, b = copy.deepcopy(left), copy.deepcopy(right)
    if 'execution' in a:
        assert a['execution']['command'].startswith('reveal surface ')
        assert b['execution']['command'].startswith('reveal surface://')
        del a['execution']['command']
        del b['execution']['command']
    assert a == b


@pytest.mark.parametrize('cli,query', [
    ([], ''),
    (['--type', 'env'], '?type=env'),
    (['--source-only'], '?source_only=true'),
    (['--by', 'dir', '--depth', '1'], '?by=dir&depth=1'),
    (['--by', 'dir', '--depth', '0'], '?by=dir&depth=0'),
    (['--top', '0'], '?top=0'),
])
@pytest.mark.parametrize('provenance', [False, True])
def test_parity(project, cli, query, provenance):
    extra = ['--provenance'] if provenance else []
    cli_argv = ['surface', 'proj', *cli, '--format', 'json', '--no-gitignore', *extra]
    uri_argv = ['surface://proj' + query, '--format', 'json', '--no-gitignore', *extra]
    a = run(*cli_argv)
    b = run(*uri_argv)
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    left, right = json.loads(a.stdout), json.loads(b.stdout)
    assert left['type'] == right['type'] == 'surface_scan'
    assert left['total'] > 0
    if provenance:
        assert left['execution']['command'] == ' '.join(['reveal', *cli_argv])
        assert right['execution']['command'] == ' '.join(['reveal', *uri_argv])
    assert_equal_answers(left, right)
    assert 'has no effect' not in a.stderr + b.stderr


def test_equivalence_guard_detects_lost_facts():
    result = {'total': 2, 'meta': {'warnings': [{'message': 'incomplete'}]}}
    changed = copy.deepcopy(result)
    changed['total'] = 1
    with pytest.raises(AssertionError):
        assert_equal_answers(result, changed)
    changed = copy.deepcopy(result)
    changed['meta']['warnings'].clear()
    with pytest.raises(AssertionError):
        assert_equal_answers(result, changed)


@pytest.mark.parametrize('spelling', ['surface', 'uri'])
def test_unparsed_input_is_incomplete(project, spelling):
    (project / 'broken.py').write_text('def broken(:\n', encoding='utf-8')
    argv = ['surface', 'proj'] if spelling == 'surface' else ['surface://proj']
    result = run(*argv, '--format', 'json', '--no-gitignore')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['type'] == 'surface_scan'
    assert answer['total'] > 0
    assert answer['unparsed_files']


@pytest.mark.parametrize('spelling', ['surface', 'uri'])
def test_missing_resource_is_structured_usage(project, spelling):
    argv = ['surface', 'absent'] if spelling == 'surface' else ['surface://absent']
    result = run(*argv, '--format', 'json')
    assert result.returncode == 2
    assert json.loads(result.stdout)['type'] == 'surface_scan'
    assert json.loads(result.stdout)['error']
    assert 'Traceback' not in result.stderr


@pytest.mark.parametrize('spelling', ['surface', 'uri'])
def test_human_primary_artifact(project, tmp_path, spelling):
    argv = ['surface', 'proj'] if spelling == 'surface' else ['surface://proj']
    artifact = tmp_path / (spelling + '.json')
    human = run(*argv, '--output', f'json={artifact}', '--no-gitignore')
    primary = run(*argv, '--format', 'json', '--no-gitignore')
    assert human.returncode == primary.returncode == 0
    assert 'Total surface entries:' in human.stdout
    assert json.loads(artifact.read_text(encoding='utf-8')) == json.loads(primary.stdout)


@pytest.mark.parametrize('spelling', ['surface', 'uri'])
def test_failed_requested_artifact_is_three(project, tmp_path, spelling):
    argv = ['surface', 'proj'] if spelling == 'surface' else ['surface://proj']
    result = run(*argv, '--also-json', str(tmp_path), '--no-gitignore')
    assert result.returncode == 3
    assert 'Total surface entries:' in result.stdout
    assert 'Traceback' not in result.stderr
    assert 'artifact' in result.stderr.lower()


def test_primary_json_retains_also_json_noop(project, tmp_path):
    artifact = tmp_path / 'redundant.json'
    result = run('surface', 'proj', '--format', 'json', '--also-json', str(artifact), '--no-gitignore')
    assert result.returncode == 0
    assert json.loads(result.stdout)['type'] == 'surface_scan'
    assert not artifact.exists()


@pytest.mark.parametrize('name', ['src & data,plus+%26', 'src?literal%26'])
def test_encoded_resource_and_literal_cli_path(project, name):
    if '?' in name:
        import sys
        if sys.platform == 'win32':
            pytest.skip('Windows filenames cannot contain question marks')
    renamed = project.rename(project.parent / name)
    a = run('surface', renamed.name, '--format', 'json', '--no-gitignore')
    b = run('surface://' + quote(renamed.name, safe=''), '--format', 'json', '--no-gitignore')
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    assert_equal_answers(json.loads(a.stdout), json.loads(b.stdout))


def test_unsupported_findings_gate_is_usage(project):
    result = run('surface', 'proj', '--fail-on', 'findings')
    assert result.returncode == 2
    assert 'findings' in result.stderr


def test_none_never_suppresses_incomplete(project):
    (project / 'broken.py').write_text('def broken(:\n', encoding='utf-8')
    result = run('--fail-on', 'none', 'surface', 'proj', '--format', 'json', '--no-gitignore')
    assert result.returncode == 3
    assert json.loads(result.stdout)['unparsed_files']


def test_sibling_uri_remains_unchanged(monkeypatch):
    monkeypatch.setenv('REVEAL_D6_CONTROL', 'present')
    result = run('env://REVEAL_D6_CONTROL', '--format', 'json')
    assert result.returncode == 0
    assert 'present' in result.stdout


@pytest.mark.parametrize('spelling', ['surface', 'uri'])
@pytest.mark.parametrize('kind', ['returned', 'raised', 'postprocess', 'malformed', 'postprocess_malformed', 'empty', 'bare_error', 'wrong_error_type', 'invalid_scope'])
def test_required_failure_preserves_identity(project, monkeypatch, spelling, kind):
    from reveal.adapters.surface import SurfaceAdapter
    from reveal.utils.results import ResultBuilder
    if kind == 'returned':
        monkeypatch.setattr(SurfaceAdapter, 'get_structure', lambda self, **kw:
                            ResultBuilder.create_error('surface_scan', 'proj', 'required input failed'))
    elif kind == 'raised':
        def fail(self, **kw):
            raise OSError('required input failed')
        monkeypatch.setattr(SurfaceAdapter, 'get_structure', fail)
    elif kind == 'postprocess':
        monkeypatch.setattr(SurfaceAdapter, 'post_process', staticmethod(lambda result, args:
                            ResultBuilder.create_error('surface_scan', 'proj', 'required input failed')),
                            raising=False)
    elif kind == 'invalid_scope':
        def invalid_scope(self, **kwargs):
            return {'contract_version': '1.1', 'type': 'surface_scan', 'source': 'proj',
                    'source_type': 'directory', 'scope': ['invalid']}
        monkeypatch.setattr(SurfaceAdapter, 'get_structure', invalid_scope)
    elif kind == 'empty':
        monkeypatch.setattr(SurfaceAdapter, 'get_structure', lambda self, **kw: {})
    elif kind == 'bare_error':
        monkeypatch.setattr(SurfaceAdapter, 'get_structure', lambda self, **kw: {'error': 'required input failed'})
    elif kind == 'wrong_error_type':
        monkeypatch.setattr(SurfaceAdapter, 'get_structure', lambda self, **kw:
                            ResultBuilder.create_error('wrong_operation', 'proj', 'required input failed'))
    elif kind == 'postprocess_malformed':
        monkeypatch.setattr(SurfaceAdapter, 'post_process', staticmethod(lambda result, args: None), raising=False)
    else:
        monkeypatch.setattr(SurfaceAdapter, 'get_structure', lambda self, **kw: None)
    argv = ['surface', 'proj'] if spelling == 'surface' else ['surface://proj']
    result = run(*argv, '--format', 'json', '--no-gitignore')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['type'] == 'surface_scan'
    assert answer['error']
    assert isinstance(answer.get('scope', {}), dict)
    assert 'Traceback' not in result.stderr


@pytest.mark.parametrize('spelling', ['surface', 'uri'])
def test_projection_cannot_hide_incompleteness(project, spelling):
    (project / 'broken.py').write_text('def broken(:\n', encoding='utf-8')
    argv = ['surface', 'proj'] if spelling == 'surface' else ['surface://proj']
    result = run(*argv, '--format', 'json', '--fields', 'total', '--no-gitignore')
    assert result.returncode == 3
    assert json.loads(result.stdout)['total'] > 0


@pytest.mark.parametrize('special', ['--rules', '--discover', '--stdin'])
def test_policy_cannot_be_smuggled_into_special_mode(project, special):
    result = run(special, 'surface://proj', '--fail-on', 'none')
    assert result.returncode == 2
    assert '--fail-on' in result.stderr


def test_uri_format_validation_precedes_analysis(project, monkeypatch):
    from reveal.adapters.surface import SurfaceAdapter
    def unexpected(self, **kwargs):
        pytest.fail('unsupported format reached analysis')
    monkeypatch.setattr(SurfaceAdapter, 'get_structure', unexpected)
    result = run('surface://proj', '--format', 'grep')
    assert result.returncode == 2
    assert result.stdout == ''


def test_render_output_failure_is_three(project, monkeypatch):
    from reveal.rendering.adapters.surface import SurfaceRenderer
    def fail(*args, **kwargs):
        raise OSError('requested output failed')
    monkeypatch.setattr(SurfaceRenderer, 'render_structure', fail)
    result = run('surface', 'proj', '--no-gitignore')
    assert result.returncode == 3
    assert 'requested output failed' in result.stderr
    assert 'Traceback' not in result.stderr


def test_runtime_artifact_failure_preserves_primary_json(project, monkeypatch):
    from reveal.utils import json_utils
    def fail(*args, **kwargs):
        raise OSError('injected artifact failure')
    # A boundary injection verifies preservation if the artifact writer fails;
    # the normal --format json no-op has a separate real CLI control above.
    monkeypatch.setattr(json_utils, 'write_also_json', fail)
    result = run('surface://proj', '--format', 'json', '--no-gitignore')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['total'] > 0
    assert answer['meta']['output_errors'][0]['code'] == 'artifact_write_failed'


def test_tilde_uri_uses_one_resolved_path(project, monkeypatch):
    monkeypatch.setenv('HOME', str(project.parent))
    monkeypatch.setenv('USERPROFILE', str(project.parent))
    a = run('surface://' + project.as_posix(), '--format', 'json', '--no-gitignore')
    b = run('surface://~/proj', '--format', 'json', '--no-gitignore')
    assert a.returncode == b.returncode == 0
    assert json.loads(a.stdout) == json.loads(b.stdout)


@pytest.mark.parametrize('incomplete,artifact_failure,expected', [
    (False, False, 0), (True, False, 3), (False, True, 3),
])
def test_closed_pipe_preserves_independent_failures(project, incomplete, artifact_failure, expected):
    import os
    import subprocess
    import sys
    if incomplete:
        (project / 'broken.py').write_text('def broken(:\n', encoding='utf-8')
    argv = [sys.executable, '-m', 'reveal', 'surface', 'proj', '--no-gitignore']
    if artifact_failure:
        argv.extend(['--also-json', str(project)])
    with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env=os.environ.copy()) as process:
        process.stdout.close()
        code = process.wait(timeout=30)
        errors = process.stderr.read().decode('utf-8', errors='replace')
    assert code == expected, errors
    assert 'Traceback' not in errors


@pytest.mark.parametrize('spelling', ['surface', 'uri'])
def test_legitimate_decline_is_complete(project, monkeypatch, spelling):
    from reveal.adapters.surface import SurfaceAdapter
    from reveal.errors import NotApplicableError
    def decline(self, **kwargs):
        raise NotApplicableError('fixture not applicable')
    monkeypatch.setattr(SurfaceAdapter, 'get_structure', decline)
    argv = ['surface', 'proj'] if spelling == 'surface' else ['surface://proj']
    result = run(*argv, '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    assert answer['type'] == 'surface_scan'
    assert answer['applicable'] is False
    assert answer['reason'] == 'fixture not applicable'


def test_informational_warning_is_not_incomplete(project, monkeypatch):
    from reveal.adapters.surface import SurfaceAdapter
    original = SurfaceAdapter.get_structure
    def warned(self, **kwargs):
        answer = original(self, **kwargs)
        answer['meta']['warnings'].append({'code': 'fixture_note', 'message': 'informational fixture note'})
        return answer
    monkeypatch.setattr(SurfaceAdapter, 'get_structure', warned)
    result = run('surface', 'proj', '--no-gitignore')
    assert result.returncode == 0
    assert result.stdout.count('informational fixture note') == 1
