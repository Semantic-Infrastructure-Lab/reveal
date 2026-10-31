"""Independent public-consumer controls for contextual suite selection."""
import json
from pathlib import Path
from urllib.parse import quote

import pytest

from conftest import _run_reveal_direct as run
from reveal.api import query
from reveal.config import RevealConfig
from reveal.errors import NotApplicableError, RequestValidationError, TestLayoutConfigError as ConfigFailure


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def _patch(name):
    return f'from unittest.mock import patch\ndef setup():\n    patch("{name}")\n'


def _policy(root, paths):
    return _write(root / '.reveal.yaml', 'test_layout:\n  additional_paths: ' + json.dumps(paths) + '\n')


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    monkeypatch.delenv('REVEAL_NO_CONFIG', raising=False)
    monkeypatch.delenv('REVEAL_CONFIG', raising=False)
    monkeypatch.setattr(RevealConfig, '_get_user_config_path', staticmethod(lambda: tmp_path / 'absent-user.yaml'))
    # An inherited tests/ ancestor must not turn this entire checkout into a suite.
    root = tmp_path / 'tests' / 'checkout'
    _write(root / 'pyproject.toml', '[project]\nname="suite-consumer"\n')
    _write(root / 'src' / 'app.py', 'def target():\n    return open("data.txt").read()\n')
    _write(root / 'suite' / 'helper.py', _patch('app.target'))
    _write(root / 'suite' / 'helper.ts', 'vi.mock("remote");\n')
    _write(root / 'suite' / 'unit.test.ts', 'vi.mock("remote.test");\n')
    _write(root / 'tests' / 'support.py', _patch('app.target'))
    _write(root / 'suiteish' / 'plain.py', _patch('decoy.target'))
    _write(root / 'other' / 'plain.py', _patch('other.target'))
    _policy(root, ['suite'])
    return root.resolve()


def _pressure(root, scheme='patches', extra=''):
    controls = 'min_patches=1&min_categories=1&include_unresolved=true'
    if scheme == 'patches':
        controls = 'view=pressure&' + controls
    return f'{scheme}://{root}?{controls}' + ('&' + extra if extra else '')


def _facts(answer):
    return {key: answer[key] for key in ('type', 'summary', 'tests', 'test_scope', 'patch_hotspots', 'boundary_hotspots')}


def test_raw_membership_is_hand_labelled_and_cuts_do_not_change_observations(project):
    answer = query(f'patches://{project}?limit=1')
    names = {Path(use['test_file']).relative_to(project).as_posix() for use in answer['uses']}
    assert names == {'suite/helper.py', 'suite/helper.ts', 'suite/unit.test.ts', 'tests/support.py'}
    assert answer['total_uses'] == answer['test_scope']['files_scanned'] == 4
    assert answer['total_targets'] == 3
    assert len(answer['groups']) == 1
    assert any(w['type'] == 'truncated' for w in answer['meta']['warnings'])
    assert answer['test_scope']['additional_paths'] == ['suite']
    assert answer['test_scope']['source'] == 'project'
    assert answer['test_scope']['include_anchor_name'] is False


@pytest.mark.parametrize('scheme', ['patches', 'testability'])
def test_pressure_child_adds_declared_suite_without_expanding_boundary_population(project, scheme):
    answer = query(_pressure(project / 'src', scheme))
    assert answer['summary']['total_patch_uses'] == 4
    assert answer['summary']['total_boundary_profiles'] == 1
    assert answer['test_scope']['files_scanned'] == 4
    assert {row['key'] for row in answer['patch_hotspots']} == {'app.target', 'remote', 'remote.test'}
    assert [(row['function'], row['categories']) for row in answer['boundary_hotspots']] == [('target', ['filesystem'])]
    root = query(_pressure(project, scheme))
    # Existing profiles include suite/support functions as well as source functions.
    assert root['summary']['total_boundary_profiles'] == 5


def test_raw_narrowing_uses_project_context_and_does_not_expand_to_declared_siblings(project):
    assert query(f'patches://{project / "suite"}')['total_uses'] == 3
    with pytest.raises(NotApplicableError):
        query(f'patches://{project / "src"}')
    with pytest.raises(NotApplicableError):
        query(f'patches://{project / "other" / "plain.py"}')
    # A selected test directory remains selected when narrowed below its own name.
    nested = _write(project / 'tests' / 'nested' / 'helper.py', _patch('nested.target'))
    assert query(f'patches://{nested.parent}')['total_uses'] == 1


def test_file_selectors_are_literal_and_support_non_test_named_typescript(project):
    _policy(project, ['suite/helper.ts', 'missing.py'])
    raw = query(f'patches://{project}')
    assert raw['total_uses'] == raw['test_scope']['files_scanned'] == 3
    assert query(f'patches://{project / "suite" / "helper.ts"}')['total_uses'] == 1
    assert {row['key'] for row in query(_pressure(project / 'src'))['patch_hotspots']} == {'app.target', 'remote'}
    assert raw['test_scope']['additional_paths'] == ['missing.py', 'suite/helper.ts']


def test_whole_project_selector_is_disclosed_and_deduplicates_overlapping_roots(project):
    _policy(project, ['.', 'suite', 'missing'])
    answer = query(_pressure(project / 'src'))
    assert answer['summary']['total_patch_uses'] == 6
    assert answer['test_scope']['files_scanned'] == 7
    assert answer['summary']['total_boundary_profiles'] == 1
    assert answer['test_scope']['whole_scope'] is True


@pytest.mark.parametrize('scheme', ['patches', 'testability'])
def test_trusted_external_roots_override_policy_with_existing_python_and_ts_meaning(project, tmp_path, scheme):
    external = tmp_path / 'external'
    _write(external / 'helper.py', _patch('external.target'))
    _write(external / 'helper.ts', 'vi.mock("ignored");\n')
    _write(external / 'named.test.ts', 'vi.mock("external.ts");\n')
    _policy(project, ['../invalid'])
    uri = _pressure(project / 'src', scheme, 'tests=' + quote(external.as_posix(), safe=''))
    answer = query(uri)
    assert answer['summary']['total_patch_uses'] == answer['test_scope']['files_scanned'] == 2
    assert answer['summary']['total_boundary_profiles'] == 1
    assert answer['test_scope']['rule'] == 'tests='
    assert {row['key'] for row in answer['patch_hotspots']} == {'external.target', 'external.ts'}
    cli = run(uri, '--format', 'json')
    assert cli.returncode == 0, cli.stderr
    assert _facts(json.loads(cli.stdout)) == _facts(answer)


def test_child_root_order_and_new_requests_see_policy_edits_without_mutating_old_answers(project):
    child = query(_pressure(project / 'src'))
    retained = json.loads(json.dumps(child))
    assert query(_pressure(project))['summary']['total_patch_uses'] == 4
    _policy(project, [])
    changed = query(_pressure(project / 'src'))
    assert changed['summary']['total_patch_uses'] == 1
    assert changed['test_scope']['additional_paths'] == []
    assert child == retained
    _policy(project, ['suite'])
    assert query(_pressure(project / 'src'))['summary']['total_patch_uses'] == 4


def test_existing_outside_project_sibling_uses_conventions_without_its_invalid_policy(project):
    outside = project.parent / 'tests'
    _write(outside / 'helper.py', _patch('outside.target'))
    _policy(outside, ['../invalid'])
    answer = query(_pressure(project))
    assert answer['summary']['total_patch_uses'] == 5
    assert answer['summary']['total_boundary_profiles'] == 5
    assert any(row['key'] == 'outside.target' for row in answer['patch_hotspots'])
    assert 'outside_anchor_roots' in answer['test_scope']


def test_alias_selector_does_not_relabel_physical_target(project):
    alias = project / 'alias'
    try:
        alias.symlink_to(project / 'other', target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('directory symlinks unavailable')
    _policy(project, ['alias'])
    raw = query(f'patches://{project}')
    assert raw['total_uses'] == 2  # the root walk does not follow the alias
    pressure = query(_pressure(project / 'src'))
    assert pressure['summary']['total_patch_uses'] == 2  # sibling tests plus explicit alias root
    files = [name for row in pressure['patch_hotspots'] for name in row['test_files']]
    assert any(Path(name).parent.name == 'alias' for name in files)
    assert not any(Path(name).parent.name == 'other' for name in files)


def test_nested_project_and_explicit_root_marker_choose_one_policy(project):
    nested = project / 'nested'
    _write(nested / 'pyproject.toml', '[project]\nname="nested-suite"\n')
    _write(nested / 'custom' / 'helper.py', _patch('nested.target'))
    _write(nested / 'other' / 'helper.py', _patch('nested.other'))
    _policy(nested, ['other'])
    _policy(project, ['nested/custom'])
    answer = query(_pressure(nested))
    assert {row['key'] for row in answer['patch_hotspots']} == {'nested.other'}
    _write(project / '.reveal.yaml', 'root: true\ntest_layout:\n  additional_paths: [nested/custom]\n')
    answer = query(_pressure(nested))
    assert {row['key'] for row in answer['patch_hotspots']} == {'nested.target'}
    assert answer['test_scope']['additional_paths'] == ['nested/custom']


def test_markerless_fallback_keeps_suite_name_and_discloses_unknown_project(tmp_path, monkeypatch):
    monkeypatch.delenv('REVEAL_CONFIG', raising=False)
    monkeypatch.delenv('REVEAL_NO_CONFIG', raising=False)
    suite = tmp_path / 'tests'
    _write(suite / 'helper.py', _patch('fallback.target'))
    answer = query(f'patches://{suite}')
    assert answer['total_uses'] == 1
    assert answer['test_scope']['source'] == 'scan_root_fallback'
    assert answer['test_scope']['include_anchor_name'] is True


@pytest.mark.parametrize('contents,error,exit_code', [
    ('test_layout: {additional_paths: [../bad]}\n', RequestValidationError, 2),
    ('test_layout: [\n', ConfigFailure, 3),
])
def test_selected_policy_failures_keep_cli_and_api_outcomes(project, contents, error, exit_code):
    _write(project / '.reveal.yaml', contents)
    for uri in (f'patches://{project}', _pressure(project / 'src'), _pressure(project / 'src', 'testability')):
        with pytest.raises(error):
            query(uri)
        cli = run(uri, '--format', 'json')
        assert cli.returncode == exit_code, cli.stderr


def test_registered_sdk_matches_cli_api_and_refreshes_policy_in_one_session(project):
    pytest.importorskip('mcp')
    from test_mcp_expected_errors_back1992 import _run, _text

    expected = {scheme: query(_pressure(project / 'src', scheme)) for scheme in ('patches', 'testability')}
    for scheme, answer in expected.items():
        cli = run(_pressure(project / 'src', scheme), '--format', 'json')
        assert cli.returncode == 0, cli.stderr
        assert _facts(json.loads(cli.stdout)) == _facts(answer)

    async def scenario(session):
        for scheme, answer in expected.items():
            result = await session.call_tool('reveal_query', {'uri': _pressure(project / 'src', scheme), 'provenance': True})
            assert not result.is_error, _text(result)
            assert _facts(json.loads(_text(result))) == _facts(answer)
        _policy(project, [])
        result = await session.call_tool('reveal_query', {'uri': _pressure(project / 'src'), 'provenance': True})
        assert not result.is_error, _text(result)
        assert json.loads(_text(result))['summary']['total_patch_uses'] == 1
        _policy(project, ['../invalid'])
        rejected = await session.call_tool('reveal_query', {'uri': _pressure(project / 'src'), 'provenance': True})
        assert rejected.is_error and 'test_layout' in _text(rejected)

    _run(project, scenario)
