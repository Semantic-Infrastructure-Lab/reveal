"""M102 exempts declared support files without filtering importer evidence."""
import importlib
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal import api
from reveal.config import RevealConfig
from reveal.errors import TestLayoutValidationError as LayoutValidationError, TestLayoutConfigError as LayoutConfigError
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
    result = run('check', str(path), '--select', 'M102', '--fail-on', 'medium', '--format', 'json', *flags)
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
    with pytest.raises(LayoutValidationError):
        api.check(str(target), select=['M102'])
    assert api.check(str(target), select=['E501']) == []
    for path in (project, target):
        result = run('check', str(path), '--select', 'M102', '--format', 'json')
        assert result.returncode == 2 and 'test_layout' in result.stderr
    write(project / '.reveal.yaml', 'rules:\n  disable: [M102]\ntest_layout:\n  additional_paths: [../escape]\n')
    assert not any(d.rule_code == 'M102' for d in api.check(str(target)))


def test_declared_support_only_preload_builds_no_import_inventory(project, monkeypatch):
    from reveal.rules.scan_caches import _m102_preload
    builds = []
    monkeypatch.setattr(owner.M102, '_collect_all_imports', lambda *args: builds.append(args))  # noqa: V036 parent-only preload; no worker is launched
    assert _m102_preload(project, ['M102'], None, [project / 'helpers/fixture.py']) == {}
    assert builds == [], 'exempt sources do not request importer evidence'


@pytest.mark.parametrize('selectors', ['[.]', '[missing, pkg/support.py]', '[]'])
def test_literal_whole_optional_and_precise_paths(project, selectors):
    write(project / '.reveal.yaml', f'test_layout:\n  additional_paths: {selectors}\n')
    response, answer = checked(project)
    expected = set() if selectors == '[.]' else {'helpers/fixture.py', 'helpersish/worker.py', 'pkg/orphan.py'}
    if selectors == '[]':
        expected.add('pkg/support.py')
    assert findings(answer) == expected
    assert response.returncode == int(bool(expected))
    if selectors == '[.]':
        row = next(r for r in answer['coverage']['rules'] if r['rule'] == 'M102')
        assert row['subjects']['skipped'] == 5
        assert 'WHOLE SCOPE' in row['reason']


def test_discovery_disclosure_uses_same_exemption_policy_as_rule_and_preload(project, monkeypatch):
    import os
    from reveal.rules.scan_caches import get_scan_disclosures
    blocked = project / 'blocked'
    write(blocked / 'main.py', 'import pkg.orphan\n')
    original = os.scandir
    def scandir(path):
        if Path(path) == blocked:
            raise PermissionError(13, 'PUBLIC_IMPORT_DISCOVERY_DENIED', str(path))
        return original(path)
    with monkeypatch.context() as context:
        context.setattr(os, 'scandir', scandir)
        inventory = owner.M102()._collect_all_imports(project)
    assert inventory.traversal_failures
    assert get_scan_disclosures([project / 'helpers/fixture.py'], ['M102'], directory=project) == []
    notes = get_scan_disclosures([project / 'pkg/orphan.py'], ['M102'], directory=project)
    assert len(notes) == 1 and 'PUBLIC_IMPORT_DISCOVERY_DENIED' in notes[0]
    assert owner._import_cache[project] is inventory


def test_custom_policy_is_project_relative_and_no_config_uses_conventions(project, tmp_path, monkeypatch):
    custom = write(tmp_path / 'policy.yaml', 'test_layout:\n  additional_paths: [helpersish]\n')
    monkeypatch.setenv('REVEAL_CONFIG', str(custom))
    response, answer = checked(project)
    assert response.returncode == 1
    assert findings(answer) == {'helpers/fixture.py', 'pkg/support.py', 'pkg/orphan.py'}
    monkeypatch.setenv('REVEAL_NO_CONFIG', '1')
    RevealConfig.reset_request_cache()
    response, answer = checked(project)
    assert response.returncode == 1
    assert findings(answer) == {'helpers/fixture.py', 'helpersish/worker.py', 'pkg/support.py', 'pkg/orphan.py'}


def test_required_policy_read_failure_is_operational_not_clean(project, monkeypatch):
    import builtins
    config_path = project / '.reveal.yaml'
    original = builtins.open
    def read(path, *args, **kwargs):
        if Path(path) == config_path:
            raise PermissionError(13, 'PUBLIC_POLICY_DENIED', str(path))
        return original(path, *args, **kwargs)
    monkeypatch.setattr(builtins, 'open', read)
    with pytest.raises(LayoutConfigError):
        api.check(str(project / 'pkg/orphan.py'), select=['M102'])
    for path in (project, project / 'pkg/orphan.py'):
        result = run('check', str(path), '--select', 'M102')
        assert result.returncode == 3 and 'PUBLIC_POLICY_DENIED' in result.stderr


def test_declared_symlink_does_not_reclassify_physical_production(project):
    alias = project / 'helpers/linked.py'
    try:
        alias.symlink_to(project / 'pkg/orphan.py')
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f'file symlink unavailable: {exc}')
    assert len(api.check(str(alias), select=['M102'])) == 1


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
