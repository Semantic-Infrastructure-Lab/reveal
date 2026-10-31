"""Surface file selection and labels share the project test/support policy."""
from pathlib import Path

import pytest

from reveal.adapters.surface import SurfaceAdapter, _scan_surface

pytestmark = pytest.mark.component


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def env(root, name, key):
    return write(root, name, f'import os\nx = os.getenv("{key}")\n')


def names(result):
    return {row['name'] for row in result['surfaces']['env']}


def project(root):
    write(root, 'pyproject.toml', '[project]\nname="sample"\nversion="1"\n')


def test_direct_file_source_only_and_parent_scope(tmp_path):
    project(tmp_path)
    test = env(tmp_path, 'tests/helper.py', 'TEST')
    env(tmp_path, 'app.py', 'APP')
    assert names(_scan_surface(test, source_only=True)) == set()
    assert names(_scan_surface(test.parent, source_only=True)) == set()
    assert names(_scan_surface(tmp_path, source_only=True)) == {'APP'}
    assert names(_scan_surface(test)) == {'TEST'}


def test_canonical_production_lookalikes_are_retained(tmp_path):
    project(tmp_path)
    for directory in ('testimonials', 'testdata', 'testing'):
        env(tmp_path, directory + '/app.py', directory.upper())
    env(tmp_path, 'tests/helper.py', 'TEST')
    result = SurfaceAdapter(str(tmp_path), 'source_only=true').get_structure()
    assert names(result) == {'TESTIMONIALS', 'TESTDATA', 'TESTING'}
    assert result['scope']['total_code_files'] == 4


def test_configured_selection_labels_and_census(tmp_path):
    project(tmp_path)
    write(tmp_path, '.reveal.yaml', 'test_layout:\n  additional_paths: [helpers]\n')
    env(tmp_path, 'helpers/support.py', 'HELPER')
    env(tmp_path, 'helpers_extra/app.py', 'APP')
    write(tmp_path, 'helpers/routes.py', 'from flask import Flask\napp=Flask(__name__)\n@app.get("/helper")\ndef helper(): pass\n')
    included = SurfaceAdapter(str(tmp_path)).get_structure()
    assert included['surfaces']['http'][0]['test_origin'] is True
    filtered = SurfaceAdapter(str(tmp_path), 'source_only=true').get_structure()
    assert names(filtered) == {'APP'}
    assert filtered['scope'] == included['scope']
    assert filtered['test_scope']['additional_paths'] == ['helpers']
    assert included['test_scope'] == filtered['test_scope']


def test_labels_validate_selected_policy_even_without_filter(tmp_path):
    project(tmp_path)
    env(tmp_path, 'app.py', 'APP')
    write(tmp_path, '.reveal.yaml', 'test_layout:\n  additional_paths: [../escape]\n')
    assert names(SurfaceAdapter(str(tmp_path), 'type=env').get_structure()) == {'APP'}
    with pytest.raises(ValueError, match='relative paths'):
        SurfaceAdapter(str(tmp_path), 'type=http').get_structure()


@pytest.mark.parametrize('declaration,expected', [('', {'HELPER', 'APP'}), ('test_layout:\n  additional_paths: []\n', {'HELPER', 'APP'}), ('test_layout:\n  additional_paths: [helpers/support.py]\n', {'APP'})])
def test_omission_empty_and_precise_file_selection(tmp_path, declaration, expected):
    project(tmp_path)
    write(tmp_path, '.reveal.yaml', declaration)
    env(tmp_path, 'helpers/support.py', 'HELPER')
    env(tmp_path, 'helpers/app.py', 'APP')
    assert names(SurfaceAdapter(str(tmp_path), 'source_only=true').get_structure()) == expected


def test_api_repeat_config_edit_current_provenance_and_old_result(tmp_path):
    from reveal.api import query
    project(tmp_path)
    env(tmp_path, 'helpers/support.py', 'HELPER')
    env(tmp_path, 'app.py', 'APP')
    config = write(tmp_path, '.reveal.yaml', 'test_layout:\n  additional_paths: [helpers]\n')
    uri = f'surface://{tmp_path.as_posix()}?source_only=true'
    old = query(uri)
    config.write_text('test_layout:\n  additional_paths: [./helpers]\n', encoding='utf-8')
    equal = query(uri)
    assert old['test_scope']['effective_policy'] == equal['test_scope']['effective_policy']
    assert old['test_scope']['declaration'] != equal['test_scope']['declaration']
    config.write_text('test_layout:\n  additional_paths: []\n', encoding='utf-8')
    fresh = query(uri)
    assert names(fresh) == {'HELPER', 'APP'}
    assert names(old) == {'APP'}
    assert old['test_scope']['additional_paths'] == ['helpers']


def test_nested_and_markerless_anchors(tmp_path):
    from reveal.api import query
    project(tmp_path)
    write(tmp_path, '.reveal.yaml', 'test_layout:\n  additional_paths: [child/helpers]\n')
    env(tmp_path, 'child/helpers/support.py', 'HELPER')
    assert names(query(f'surface://{(tmp_path / "child").as_posix()}?source_only=true')) == set()
    project(tmp_path / 'child')
    assert names(query(f'surface://{(tmp_path / "child").as_posix()}?source_only=true')) == {'HELPER'}
    markerless = tmp_path / 'elsewhere' / 'tests'
    env(markerless, 'helper.py', 'TEST')
    # Explicit low-level context stays conventional and honors the selected project boundary.
    assert names(_scan_surface(markerless, source_only=True)) == set()


def test_cli_api_and_registered_mcp_match(tmp_path):
    import json
    from conftest import _run_reveal_direct
    from reveal.api import query
    project(tmp_path)
    write(tmp_path, '.reveal.yaml', 'test_layout:\n  additional_paths: [helpers]\n')
    env(tmp_path, 'helpers/support.py', 'HELPER')
    env(tmp_path, 'app.py', 'APP')
    uri = f'surface://{tmp_path.as_posix()}?source_only=true'
    expected = query(uri)
    response = _run_reveal_direct(uri, '--format', 'json')
    assert response.returncode == 0, response.stderr
    actual = json.loads(response.stdout)
    assert actual['surfaces'] == expected['surfaces']
    assert actual['test_scope'] == expected['test_scope']
    text = _run_reveal_direct('surface', str(tmp_path), '--source-only')
    assert text.returncode == 0, text.stderr
    assert 'declared additional paths' in text.stdout
    pytest.importorskip('mcp')
    from test_mcp_expected_errors_back1992 import _run, _text

    async def scenario(session):
        result = await session.call_tool('reveal_query', {'uri': uri, 'provenance': True})
        assert not result.is_error, _text(result)
        payload = json.loads(_text(result))
        assert payload['surfaces'] == expected['surfaces']
        assert payload['test_scope'] == expected['test_scope']

    _run(tmp_path, scenario)


@pytest.mark.parametrize('query', ['source_only=true', 'type=http'])
def test_required_configuration_read_failure_preserved(tmp_path, query):
    from reveal.errors import TestLayoutConfigError
    project(tmp_path)
    env(tmp_path, 'app.py', 'APP')
    write(tmp_path, '.reveal.yaml', 'test_layout: [\n')
    with pytest.raises(TestLayoutConfigError, match='ParserError'):
        SurfaceAdapter(str(tmp_path), query).get_structure()
    assert names(SurfaceAdapter(str(tmp_path), 'type=env').get_structure()) == {'APP'}
