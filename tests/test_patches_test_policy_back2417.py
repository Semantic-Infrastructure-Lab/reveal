"""Project-context suite selection; explicit suites retain their established trust."""
from pathlib import Path
import os

import pytest

from reveal.adapters.patches import PatchesAdapter
from reveal.adapters.testability import TestabilityAdapter as PressureAdapter
from reveal.errors import NotApplicableError
from reveal.utils.request_cache import host_request


PATCH = 'from unittest.mock import patch\npatch("pkg.service.call")\n'


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.delenv('REVEAL_CONFIG', raising=False)
    monkeypatch.delenv('REVEAL_NO_CONFIG', raising=False)
    write(tmp_path / 'pyproject.toml', '[project]\nname="policy"\n')
    return tmp_path


def configure(root, selectors):
    import json
    write(root / '.reveal.yaml', 'test_layout:\n  additional_paths: ' + json.dumps(selectors) + '\n')


def test_default_raw_selection_keeps_project_context_when_narrowed(project):
    helper = project / 'tests' / 'nested' / 'helper.py'
    write(helper, PATCH)
    for target in (project, project / 'tests', helper.parent, helper):
        result = PatchesAdapter(str(target)).get_structure()
        assert result['total_uses'] == 1
    assert result['test_scope']['source'] == 'project'
    assert result['test_scope']['basis'] == 'paths relative to the selected project'
    source = project / 'src' / 'plain.py'
    write(source, PATCH)
    with pytest.raises(NotApplicableError):
        PatchesAdapter(str(source)).get_structure()


def test_raw_declarations_select_literal_files_and_subtrees_inside_target_only(project):
    configure(project, ['checks/unit', 'src/helper.ts'])
    for name in ('checks/unit/helper.py', 'checks/unitized/helper.py', 'src/plain.py', 'elsewhere/test_extra.py'):
        write(project / name, PATCH)
    write(project / 'src/helper.ts', 'jest.mock("pkg.service");\n')
    raw = PatchesAdapter(str(project)).get_structure()
    assert raw['total_uses'] == 3
    assert {Path(row['test_file']).relative_to(project).as_posix() for row in raw['uses']} == {
        'checks/unit/helper.py', 'src/helper.ts', 'elsewhere/test_extra.py'}
    narrow = PatchesAdapter(str(project / 'src')).get_structure()
    assert narrow['total_uses'] == 1
    direct = PatchesAdapter(str(project / 'src/helper.ts')).get_structure()
    assert direct['total_uses'] == 1


def test_pressure_adds_declared_project_roots_without_changing_boundary_population(project):
    configure(project, ['checks', 'precise/helper.ts', 'missing'])
    write(project / 'src/app.py', 'def app():\n    return 1\n')
    write(project / 'src/test_app.py', 'def test_app():\n    return 2\n')
    write(project / 'checks/helper.py', PATCH)
    write(project / 'precise/helper.ts', 'vi.mock("pkg.service");\n')
    write(project / 'precise/neighbor.py', PATCH)
    result = PressureAdapter(str(project / 'src')).get_structure()
    assert result['summary']['total_patch_uses'] == 2
    assert result['summary']['total_boundary_profiles'] == 2
    assert {Path(p).relative_to(project).as_posix() for p in result['tests']} == {
        'src', 'checks', 'precise/helper.ts', 'missing'}


def test_explicit_tests_bypass_invalid_policy_and_keep_js_filename_semantics(project):
    configure(project, ['../invalid'])
    write(project / 'src/app.py', 'def app():\n    return 1\n')
    write(project / 'chosen/helper.py', PATCH)
    write(project / 'chosen/helper.ts', 'vi.mock("pkg.service");\n')
    result = PressureAdapter(str(project / 'src'), f'tests={project / "chosen"}').get_structure()
    assert result['summary']['total_patch_uses'] == 1
    assert result['test_scope'] == {'rule': 'tests=', 'files_scanned': 1}


def test_context_is_selected_once_and_reused_adapters_do_not_retain_policy(project):
    configure(project, ['checks'])
    configure(project / 'nested', ['support'])
    write(project / 'nested/pyproject.toml', '[project]\nname="nested"\n')
    write(project / 'checks/helper.py', PATCH)
    write(project / 'nested/support/helper.py', PATCH)
    write(project / 'nested/test_control.py', PATCH)
    adapter = PatchesAdapter(str(project))
    with host_request():
        old = adapter.get_structure()
    assert old['total_uses'] == 2
    child = PatchesAdapter(str(project / 'nested')).get_structure()
    assert child['total_uses'] == 2
    configure(project, [])
    with host_request():
        fresh = adapter.get_structure()
    assert fresh['total_uses'] == 1
    assert old['total_uses'] == 2
    assert old['test_scope']['additional_paths'] == ['checks']
    assert fresh['test_scope']['additional_paths'] == []


def test_overlapping_declared_roots_count_unsupported_files_once(project):
    configure(project, ['checks', 'checks/other.go'])
    write(project / 'checks/helper.py', PATCH)
    write(project / 'checks/other.go', 'package checks\n')
    write(project / 'checks/more.go', 'package checks\n')
    report = PressureAdapter(str(project)).get_structure()
    assert report['test_scope']['files_scanned'] == 1
    assert report['test_scope']['unscanned'] == {'Go': 2}
    warning, = [w for w in report['meta']['warnings'] if w['type'] == 'language_not_scanned']
    assert warning['languages'] == {'Go': 2}


def test_default_discovery_loss_is_failed_analysis_not_absent_suite(project, monkeypatch):
    write(project / 'tests/test_case.py', PATCH)
    adapter = PressureAdapter(str(project))
    real = os.scandir

    def denied(path):
        if Path(path) == project / 'tests':
            raise PermissionError(13, 'controlled suite enumeration failure', str(path))
        return real(path)

    with monkeypatch.context() as context:
        context.setattr(os, 'scandir', denied)
        result = adapter.get_structure()
    assert adapter.execution_facts(result).completeness.value == 'failed'
    warning, = [w for w in result['meta']['warnings'] if w['type'] == 'analysis_incomplete']
    assert warning['count'] == 1
    assert result['summary']['total_patch_uses'] == 0
    clean = adapter.get_structure()
    assert clean['summary']['total_patch_uses'] == 1
    assert not any(w['type'] == 'analysis_incomplete' for w in clean['meta']['warnings'])


@pytest.mark.parametrize('unsupported', [False, True])
def test_explicit_empty_and_unsupported_suites_remain_valid(project, unsupported):
    suite = project / 'chosen'
    suite.mkdir()
    if unsupported:
        write(suite / 'helper.go', 'package chosen\n')
    result = PressureAdapter(str(project), f'tests={suite}').get_structure()
    assert result['summary']['total_patch_uses'] == 0
    assert result['test_scope'] == {'rule': 'tests=', 'files_scanned': 0}


@pytest.mark.parametrize('declared', [False, True])
def test_selected_suite_stat_loss_is_reported_before_absence(project, monkeypatch, declared):
    suite = project / ('checks' if declared else 'tests')
    if declared:
        configure(project, ['checks', 'optional_missing'])
    write(project / 'src/app.py', 'VALUE = 1\n')
    write(suite / 'helper.py', PATCH)
    real = os.stat
    real_path_stat = Path.stat

    def denied(path, *args, **kwargs):
        if not isinstance(path, int) and Path(path) == suite:
            raise PermissionError(13, 'controlled suite stat failure', str(path))
        return real(path, *args, **kwargs)

    def denied_path_stat(path, *args, **kwargs):
        if path == suite:
            raise PermissionError(13, 'controlled suite stat failure', str(path))
        return real_path_stat(path, *args, **kwargs)

    adapter = PressureAdapter(str(project / 'src'))
    with monkeypatch.context() as context:
        context.setattr(os, 'stat', denied)
        context.setattr(Path, 'stat', denied_path_stat)
        result = adapter.get_structure()
    assert adapter.execution_facts(result).completeness.value == 'failed'
    warning, = [w for w in result['meta']['warnings'] if w['type'] == 'analysis_incomplete']
    assert warning['count'] == 1
    assert 'PermissionError' in warning['message']
    assert result['summary']['total_patch_uses'] == 0
    clean = adapter.get_structure()
    assert clean['summary']['total_patch_uses'] == 1
    assert not any(w['type'] == 'analysis_incomplete' for w in clean['meta']['warnings'])
