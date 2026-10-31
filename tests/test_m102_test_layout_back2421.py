"""M102 exempts declared support files without filtering importer evidence."""
import importlib
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal import api
from reveal.cli import file_checker
from reveal.config import RevealConfig
from reveal.errors import TestLayoutValidationError
from reveal.rules import RuleRegistry
from reveal.utils.request_cache import host_request

owner = importlib.import_module('reveal.rules.maintainability.M102')
pytestmark = pytest.mark.component


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.delenv('REVEAL_CONFIG', raising=False)
    monkeypatch.delenv('REVEAL_NO_CONFIG', raising=False)
    root = tmp_path / 'repo'
    write(root / 'pyproject.toml', '[project]\nname="roles"\n')
    write(root / '.reveal.yaml', 'test_layout:\n  additional_paths: [helpers, pkg/support.py]\n')
    for name in ('helpers/fixture.py', 'helpersish/worker.py', 'pkg/support.py',
                 'pkg/orphan.py', 'tests/unit/helper.py'):
        write(root / name, 'VALUE=1\n')
    return root


def findings(answer):
    if 'files' in answer:
        return {row['file'] for row in answer['files']
                if any(d['rule_code'] == 'M102' for d in row['detections'])}
    return {d['file_path'] for d in answer.get('detections', []) if d['rule_code'] == 'M102'}


def checked(path, *flags):
    result = run('check', str(path), '--select', 'M102', '--format', 'json', *flags)
    return result, json.loads(result.stdout)


def test_native_and_api_exempt_helpers_and_keep_production_lookalikes(project):
    rule = owner.M102()
    for rel in ('helpers/fixture.py', 'pkg/support.py', 'tests/unit/helper.py'):
        path = project / rel
        assert rule.check(str(path), None, path.read_text(encoding='utf-8')) == []
        assert api.check(str(path), select=['M102']) == []
    for rel in ('helpersish/worker.py', 'pkg/orphan.py'):
        path = project / rel
        assert len(api.check(str(path), select=['M102'])) == 1


@pytest.mark.parametrize('workers', ['1', '2'])
def test_directory_child_file_and_parallel_select_same_project(project, monkeypatch, workers):
    monkeypatch.setenv('REVEAL_MAX_WORKERS', workers)
    response, answer = checked(project)
    assert response.returncode == 1
    assert findings(answer) == {'helpersish/worker.py', 'pkg/orphan.py'}
    for rel in ('helpers', 'helpers/fixture.py', 'pkg/support.py'):
        response, answer = checked(project / rel)
        assert response.returncode == 0 and not findings(answer)


@pytest.mark.parametrize('name', ['tests', 'specs'])
def test_checkout_ancestor_or_project_name_does_not_exempt_production(tmp_path, name):
    root = tmp_path / name / name
    write(root / 'pyproject.toml', '[project]\nname="production"\n')
    target = write(root / 'worker.py', 'VALUE=1\n')
    assert len(api.check(str(target), select=['M102'])) == 1
    response, answer = checked(root)
    assert response.returncode == 1 and findings(answer) == {'worker.py'}


def test_parent_check_uses_parent_policy_while_selected_nested_project_is_independent(project):
    nested = project / 'helpers' / 'nested'
    write(nested / 'pyproject.toml', '[project]\nname="nested"\n')
    write(nested / '.reveal.yaml', 'test_layout:\n  additional_paths: []\n')
    write(nested / 'worker.py', 'VALUE=1\n')
    _, parent = checked(project)
    assert 'helpers/nested/worker.py' not in findings(parent)
    response, child = checked(nested)
    assert response.returncode == 1 and findings(child) == {'worker.py'}


def test_imports_from_declared_helpers_still_prove_usage_and_reuse_same_cache(project):
    used = write(project / 'pkg/used.py', 'VALUE=1\n')
    write(project / 'helpers/fixture.py', 'from pkg import used\n')
    with host_request():
        assert RuleRegistry.check_file(str(used), None, used.read_text(encoding='utf-8'), select=['M102']) == []
        inventory = owner._import_cache[project]
        assert 'pkg.used' in inventory
        write(project / '.reveal.yaml', 'test_layout:\n  additional_paths: []\n')
        RevealConfig.reset_request_cache()
        assert RuleRegistry.check_file(str(used), None, used.read_text(encoding='utf-8'), select=['M102']) == []
        assert owner._import_cache[project] is inventory


def test_policy_edits_change_exemptions_in_fresh_requests(project):
    target = project / 'helpers/fixture.py'
    assert api.check(str(target), select=['M102']) == []
    write(project / '.reveal.yaml', 'test_layout:\n  additional_paths: []\n')
    assert len(api.check(str(target), select=['M102'])) == 1
    write(project / '.reveal.yaml', 'test_layout:\n  additional_paths: [helpers]\n')
    assert api.check(str(target), select=['M102']) == []


def test_invalid_selected_policy_rejects_only_active_m102(project):
    write(project / '.reveal.yaml', 'test_layout:\n  additional_paths: [../escape]\n')
    target = project / 'pkg/orphan.py'
    with pytest.raises(TestLayoutValidationError):
        api.check(str(target), select=['M102'])
    assert api.check(str(target), select=['E501']) == []
    for path in (project, target):
        result = run('check', str(path), '--select', 'M102', '--format', 'json')
        assert result.returncode == 2 and 'test_layout' in result.stderr
    write(project / '.reveal.yaml', 'rules:\n  disable: [M102]\ntest_layout:\n  additional_paths: [../escape]\n')
    assert not any(d.rule_code == 'M102' for d in api.check(str(target)))


def test_declared_support_only_preload_builds_no_import_inventory(project, monkeypatch):
    from reveal.rules.scan_caches import _m102_preload
    def forbidden(*args):
        raise AssertionError('exempt sources do not request importer evidence')
    monkeypatch.setattr(owner.M102, '_collect_all_imports', forbidden)
    assert _m102_preload(project, ['M102'], None, [project / 'helpers/fixture.py']) == {}


def test_direct_markerless_package_keeps_conventional_support_scope(tmp_path):
    root = tmp_path / 'package'
    write(root / '__init__.py', '')
    target = write(root / 'tests' / 'helper.py', 'VALUE=1\n')
    assert owner.M102().check(str(target), None, 'VALUE=1\n') == []


@pytest.mark.mcp
def test_registered_sdk_observes_policy_edits_and_reports_invalid_policy(project, tmp_path):
    from test_mcp_expected_errors_back1992 import _run, _text
    target = project / 'helpers/fixture.py'
    async def scenario(client):
        async def request():
            return await client.call_tool('reveal_check', {'path': str(target), 'select': 'M102'})
        healthy = await request()
        assert not healthy.is_error and 'No issues' in _text(healthy)
        write(project / '.reveal.yaml', 'test_layout:\n  additional_paths: []\n')
        changed = await request()
        assert not changed.is_error and '[M102]' in _text(changed)
        write(project / '.reveal.yaml', 'test_layout:\n  additional_paths: [../escape]\n')
        rejected = await request()
        assert rejected.is_error and 'test_layout' in _text(rejected)
    _run(tmp_path, scenario)
