"""Selected policy failures keep their typed transport outcome."""
import pytest

from conftest import _run_reveal_direct
from reveal.api import query
from reveal.errors import RequestValidationError


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    monkeypatch.delenv('REVEAL_NO_CONFIG', raising=False)
    monkeypatch.delenv('REVEAL_CONFIG', raising=False)
    (tmp_path / 'pyproject.toml').write_text('[project]\nname="transport"\n', encoding='utf-8')
    (tmp_path / 'app.py').write_text('import os\n', encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('scheme', ['imports', 'overview', 'surface', 'patches', 'testability', 'stats'])
def test_malformed_selected_policy_is_invalid_request(project, scheme):
    (project / '.reveal.yaml').write_text('test_layout:\n  additional_paths: [../escape]\n', encoding='utf-8')
    params = {'surface': 'source_only=true', 'stats': 'hotspots=true&tests=exclude'}.get(scheme, '')
    uri = f'{scheme}://{project}?{params}'
    with pytest.raises(RequestValidationError, match='test_layout'):
        query(uri)
    result = _run_reveal_direct(uri, '--format', 'json')
    assert result.returncode == 2, result.stderr
    assert 'test_layout' in result.stderr


@pytest.mark.parametrize('scheme,params', [('imports', ''), ('overview', ''), ('stats', 'hotspots=true&tests=exclude')])
def test_required_config_syntax_failure_remains_operational(project, scheme, params):
    from reveal.errors import TestLayoutConfigError as ConfigFailure
    (project / '.reveal.yaml').write_text('test_layout: [\n', encoding='utf-8')
    uri = f'{scheme}://{project}?{params}'
    with pytest.raises(ConfigFailure, match='ParserError'):
        query(uri)
    result = _run_reveal_direct(uri, '--format', 'json')
    assert result.returncode == 3, result.stderr
    assert 'ParserError' in result.stderr


def test_registered_mcp_keeps_invalid_policy_and_unsupported_filter_diagnostics(project):
    import json
    pytest.importorskip('mcp')
    from test_mcp_expected_errors_back1992 import _run, _text
    (project / '.reveal.yaml').write_text('test_layout:\n  additional_paths: [helpers]\n', encoding='utf-8')

    async def scenario(session):
        for scheme, params in [('patches', ''), ('testability', '')]:
            rejected = await session.call_tool('reveal_query', {'uri': f'{scheme}://{project}?{params}'})
            assert rejected.is_error
            assert 'test_layout.additional_paths' in _text(rejected)
        for scheme, params in [('surface', 'source_only=true'), ('metrics', 'hotspots=true&tests=exclude&churn=false')]:
            supported = await session.call_tool('reveal_query', {'uri': f'{scheme}://{project}?{params}', 'provenance': True})
            assert not supported.is_error, _text(supported)
            payload = json.loads(_text(supported))
            assert payload['test_scope']['additional_paths'] == ['helpers']
        (project / '.reveal.yaml').write_text('test_layout:\n  additional_paths: [../escape]\n', encoding='utf-8')
        invalid = await session.call_tool('reveal_query', {'uri': f'imports://{project}', 'provenance': True})
        assert invalid.is_error and 'test_layout' in _text(invalid)
        (project / '.reveal.yaml').write_text('test_layout: [\n', encoding='utf-8')
        failed = await session.call_tool('reveal_query', {'uri': f'imports://{project}', 'provenance': True})
        assert failed.is_error and 'ParserError' in _text(failed)

    _run(project, scenario)


def test_configured_overview_map_counts_and_diagnostics_match_cli_api_mcp(project):
    import json
    pytest.importorskip('mcp')
    from test_mcp_expected_errors_back1992 import _run, _text
    (project / '.reveal.yaml').write_text('test_layout:\n  additional_paths: [helpers]\n', encoding='utf-8')
    (project / 'helpers').mkdir()
    (project / 'helpers' / 'worker.py').write_text('import core\n', encoding='utf-8')
    (project / 'core.py').write_text('VALUE=1\n', encoding='utf-8')
    (project / 'app.py').write_text('import core\n', encoding='utf-8')
    uri = f'overview://{project}'
    expected = query(uri)
    assert expected['map_status'] == 'complete'
    assert expected['map']['entrypoints']['rows'] == [{'file': 'app.py', 'fan_out': 1, 'is_test': False, 'test_only_importers': 0}]
    assert expected['map']['fan_in']['rows'] == [{'file': 'core.py', 'fan_in': 2, 'fan_out': 0}]
    scope = expected['map']['rules']['edge_rule']['test_scope']
    assert scope['observed']['scanned_files'] == 3
    assert scope['observed']['test_support_matches'] == 1
    cli = _run_reveal_direct(uri, '--format', 'json')
    assert cli.returncode == 0, cli.stderr
    assert json.loads(cli.stdout)['map'] == expected['map']

    async def scenario(session):
        result = await session.call_tool('reveal_query', {'uri': uri, 'provenance': True})
        assert not result.is_error, _text(result)
        payload = json.loads(_text(result))
        assert payload['map'] == expected['map']
        assert payload.get('meta', {}).get('warnings', []) == expected.get('meta', {}).get('warnings', [])
        assert payload.get('meta', {}).get('errors', []) == expected.get('meta', {}).get('errors', [])

    _run(project, scenario)
