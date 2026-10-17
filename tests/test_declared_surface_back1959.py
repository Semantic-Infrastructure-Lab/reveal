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
    return _run_reveal_direct(*args, '--no-breadcrumbs')


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
    a = run('surface', 'proj', *cli, '--format', 'json', '--no-gitignore', *extra)
    b = run('surface://proj' + query, '--format', 'json', '--no-gitignore', *extra)
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    left, right = json.loads(a.stdout), json.loads(b.stdout)
    assert left['type'] == right['type'] == 'surface_scan'
    assert left['total'] > 0
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
    human = run(*argv, '--also-json', str(artifact), '--no-gitignore')
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
@pytest.mark.parametrize('kind', ['returned', 'raised', 'postprocess', 'malformed'])
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
    else:
        monkeypatch.setattr(SurfaceAdapter, 'get_structure', lambda self, **kw: None)
    argv = ['surface', 'proj'] if spelling == 'surface' else ['surface://proj']
    result = run(*argv, '--format', 'json', '--no-gitignore')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['type'] == 'surface_scan'
    assert answer['error']
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
