"""Metrics ranking adopts one immutable project test/support selection (BACK-2402)."""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.api import query
from reveal.adapters.stats.adapter import MetricsAdapter, StatsAdapter
from reveal.errors import RequestValidationError
from reveal.utils.request_cache import host_request

# Positive hotspot scores from actual analysis, without changing quality configuration.
SOURCE = 'def work(value):\n' + ''.join(f'    if value == {n}:\n        return {n}\n' for n in range(15)) + '    return -1\n'
OPTIONS = 'hotspots=true&tests=exclude&churn=false&top=0&code_only=true'


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.delenv('REVEAL_NO_CONFIG', raising=False)
    monkeypatch.delenv('REVEAL_CONFIG', raising=False)
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    root = tmp_path / 'repo'
    write(root / 'pyproject.toml', '[project]\nname="metrics-policy"\n')
    write(root / '.reveal.yaml', 'test_layout:\n  additional_paths: [helpers, src/support.py]\n')
    for name in ('app.py', 'helpers/probe.py', 'helpersish/probe.py', 'src/support.py', 'src/supportive.py', 'tests/unit/helper.py'):
        write(root / name, SOURCE)
    return root


def ranked(result):
    return {row['file'] for row in result['hotspots']}


@pytest.mark.parametrize('adapter', [MetricsAdapter, StatsAdapter])
def test_configured_ranking_preserves_analyzed_population(project, adapter):
    included = adapter(str(project), OPTIONS.replace('exclude', 'include')).get_structure()
    excluded = adapter(str(project), OPTIONS).get_structure()
    assert ranked(excluded) == {'app.py', 'helpersish/probe.py', 'src/supportive.py'}
    assert len(ranked(included)) == 6
    assert excluded['files'] == included['files']
    assert excluded['summary'] == included['summary']
    scope = excluded['test_scope']
    assert scope['files_excluded'] == 3
    assert scope['additional_paths'] == ['helpers', 'src/support.py']
    assert scope['anchor'] == '.'
    assert scope['declaration']['layer'] == 'project'


def test_root_child_and_file_choose_same_policy(project):
    root = query(f'metrics://{project}?{OPTIONS}')
    child = query(f'metrics://{project / "tests" / "unit"}?{OPTIONS}')
    single = query(f'metrics://{project / "src" / "support.py"}?{OPTIONS}')
    assert 'tests/unit/helper.py' not in ranked(root)
    assert ranked(child) == ranked(single) == set()
    assert child['summary']['total_files'] == single['summary']['total_files'] == 1
    assert child['test_scope']['files_excluded'] == single['test_scope']['files_excluded'] == 1
    assert child['test_scope']['additional_paths'] == root['test_scope']['additional_paths']


def test_reused_adapter_rebinds_config_and_old_results_are_immutable(project):
    adapter = MetricsAdapter(str(project), OPTIONS)
    with host_request():
        first = adapter.get_structure()
    frozen = json.dumps(first, sort_keys=True)
    first_api = query(f'metrics://{project}?{OPTIONS}')
    write(project / '.reveal.yaml', 'test_layout:\n  additional_paths: [src/support.py, helpers]\n# changed source\n')
    with host_request():
        equal = adapter.get_structure()
    assert first['test_scope']['effective_policy'] == equal['test_scope']['effective_policy']
    assert first['test_scope']['declaration']['input_digest'] != equal['test_scope']['declaration']['input_digest']
    write(project / '.reveal.yaml', 'test_layout:\n  additional_paths: []\n')
    with host_request():
        latest = adapter.get_structure()
    assert query(f'metrics://{project}?{OPTIONS}')['test_scope']['files_excluded'] == 1
    assert first_api['test_scope']['files_excluded'] == 3
    assert latest['test_scope']['files_excluded'] == 1
    assert latest['test_scope']['additional_paths'] == []
    assert json.dumps(first, sort_keys=True) == frozen


def test_nested_project_and_markerless_scope(project, tmp_path):
    nested = project / 'helpers' / 'nested'
    write(nested / 'pyproject.toml', '[project]\nname="nested"\n')
    write(nested / 'ordinary.py', SOURCE)
    assert ranked(query(f'metrics://{nested}?{OPTIONS}')) == {'ordinary.py'}
    suite = tmp_path / 'markerless' / 'tests'
    write(suite / 'helper.py', SOURCE)
    result = query(f'metrics://{suite}?{OPTIONS}')
    assert not ranked(result)
    assert result['test_scope']['source'] == 'scan_root_fallback'


def test_invalid_policy_precedes_scan_but_unrelated_metrics_work(project, monkeypatch):
    write(project / '.reveal.yaml', 'test_layout:\n  additional_paths: [../outside]\n')
    assert query(f'metrics://{project}?code_only=true')['summary']['total_files'] == 6
    def forbidden(*args, **kwargs):
        raise AssertionError('policy validation must precede analysis')
    monkeypatch.setattr(MetricsAdapter, '_collect_filtered_stats', forbidden)
    with pytest.raises(RequestValidationError, match='test_layout'):
        query(f'metrics://{project}?{OPTIONS}')


def test_cli_uri_noun_and_text_state_selected_ranking(project):
    uri = _run_reveal_direct(f'metrics://{project}?{OPTIONS}', '--format', 'json')
    noun = _run_reveal_direct('metrics', str(project), '--hotspots', '--tests', 'exclude', '--no-churn', '--top', '0', '--code-only', '--format', 'json')
    assert uri.returncode == noun.returncode == 0, (uri.stderr, noun.stderr)
    assert ranked(json.loads(uri.stdout)) == ranked(json.loads(noun.stdout)) == {'app.py', 'helpersish/probe.py', 'src/supportive.py'}
    text = _run_reveal_direct(f'metrics://{project}?{OPTIONS}')
    assert text.returncode == 0
    assert 'ranking only' in text.stdout and 'declared additional paths' in text.stdout
    assert '3 files excluded' in text.stdout


def test_alias_selector_does_not_relabel_physical_target(project):
    alias = project / 'helpers' / 'linked'
    try:
        alias.symlink_to(project / 'helpersish', target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f'directory symlink unavailable: {error}')
    selected = query(f'metrics://{alias}?{OPTIONS}')
    physical = query(f'metrics://{project / "helpersish"}?{OPTIONS}')
    assert not ranked(selected)
    assert ranked(physical) == {'probe.py'}
