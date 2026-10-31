"""A source file is a valid pressure target and keeps its module-qualified identity."""
import pytest

from conftest import _run_reveal_direct as run
from reveal import api
from reveal.testability.boundaries import module_name_from_file


@pytest.mark.parametrize('name,expected', [('service.py', 'service'), ('__init__.py', 'package')])
def test_file_source_root_retains_its_module_name(tmp_path, name, expected):
    package = tmp_path / 'package'
    package.mkdir()
    source = package / name
    source.write_text('def target():\n    return 1\n', encoding='utf-8')
    assert module_name_from_file(str(source), str(source)) == expected
    if name == 'service.py':
        assert module_name_from_file(str(source), str(package)) == expected


@pytest.mark.parametrize('scheme', ['patches', 'testability'])
def test_file_pressure_retains_boundary_and_explicit_patch_evidence(tmp_path, scheme):
    source = tmp_path / 'service.py'
    source.write_text('def target():\n    return open("data.txt").read()\n', encoding='utf-8')
    tests = tmp_path / 'chosen'
    tests.mkdir()
    (tests / 'helper.py').write_text(
        'from unittest.mock import patch\n'
        'def setup():\n    patch("service.target")\n', encoding='utf-8')
    view = 'view=pressure&' if scheme == 'patches' else ''
    query = f'{scheme}://{source}?{view}tests={tests}&min_patches=1&min_categories=1'
    answer = api.query(query)
    assert answer['summary']['total_patch_uses'] == 1
    assert answer['summary']['total_boundary_profiles'] == 1
    assert answer['patch_hotspots'][0]['key'] == 'service.target'
    assert answer['patch_hotspots'][0]['related_profiles'][0]['function'] == 'target'
    cli = run(query, '--format', 'json')
    assert cli.returncode == 0, cli.stderr


def test_directory_module_identity_is_unchanged(tmp_path):
    package = tmp_path / 'package'
    package.mkdir()
    source = package / 'service.py'
    source.write_text('def target():\n    return 1\n', encoding='utf-8')
    assert module_name_from_file(str(source), str(package)) == 'service'
    init = package / '__init__.py'
    init.write_text('', encoding='utf-8')
    assert module_name_from_file(str(init), str(package)) == 'package'
