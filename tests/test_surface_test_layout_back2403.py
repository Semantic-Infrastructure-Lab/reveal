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
