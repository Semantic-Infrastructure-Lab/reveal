"""Overview retains component evidence without changing execution policy (BACK-1977)."""
import json
from concurrent.futures.process import BrokenProcessPool
from unittest.mock import patch

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.git import GitAdapter
from reveal.adapters.imports import ImportsAdapter, _lost_extraction
from reveal.adapters.overview import OverviewAdapter, _relativize_paths, _run_git_log, _run_imports_analysis
from reveal.adapters.stats import StatsAdapter
from reveal.errors import NotApplicableError
from reveal.rendering.adapters.overview import _render_quality_pulse


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path/'proj'
    root.mkdir()
    (root/'a.py').write_text('import os\n', encoding='utf-8')
    return root


def test_real_nonrepository_skips_history_without_composed_error(project):
    pygit2 = pytest.importorskip('pygit2')
    # Isolate from any enclosing developer checkout, without replacing the typed owner.
    with patch.object(pygit2, 'discover_repository', return_value=None), \
            patch('reveal.adapters.overview._run_git_log', wraps=_run_git_log) as history:
        result = OverviewAdapter(str(project)).get_structure()
    assert not result.get('meta', {}).get('errors')
    assert result['git_log'] == [] and result['git_foreign_root'] is None
    assert history.call_count == 0
    assert result['stats']['summary']['total_files'] == 1


@pytest.mark.parametrize('absent', ['typed', 'missing_path'])
def test_typed_absence_or_absent_root_precedes_history(project, absent):
    kwargs = {'side_effect': NotApplicableError('typed absent repository')} if absent == 'typed' else {'return_value': {'type': 'git_repository'}}
    with patch.object(GitAdapter, 'get_metadata', **kwargs), \
            patch('reveal.adapters.overview._run_git_log', return_value=[{'hash': 'abc'}]) as history:
        result = OverviewAdapter(str(project), 'no_imports=true').get_structure()
    assert history.call_count == 0
    assert result['git_log'] == []
    assert not result.get('meta', {}).get('errors')


@pytest.mark.parametrize('cause', [ImportError('Git dependency unavailable'),
                                   OSError('Git root I/O unavailable'), ValueError('Git root refused')])
def test_git_operational_failure_is_attributed_before_history(project, cause):
    with patch.object(GitAdapter, 'get_metadata', side_effect=cause), \
            patch('reveal.adapters.overview._run_git_log', return_value=[{'hash': 'abc'}]) as history:
        result = OverviewAdapter(str(project), 'no_imports=true').get_structure()
    error, = result.get('meta', {}).get('errors', [])
    assert error['code'] == 'E_COMPOSE' and str(cause) in error['message']
    assert history.call_count == 0
    assert result['stats']['summary']['total_files'] == 1


def test_no_git_skips_discovery_and_history(project):
    with patch.object(GitAdapter, 'get_metadata') as metadata, \
            patch('reveal.adapters.overview._run_git_log') as history:
        result = OverviewAdapter(str(project), 'no_git=true').get_structure()
    metadata.assert_not_called()
    history.assert_not_called()
    assert result['git_log'] == []


@pytest.mark.parametrize('top,count', [(0, 0), (2, 2), (5, 5)])
@pytest.mark.parametrize('foreign', [False, True])
def test_real_repository_and_foreign_history_preserve_population(project, top, count, foreign):
    pygit2 = pytest.importorskip('pygit2')
    repo = pygit2.init_repository(str(project))
    signature = pygit2.Signature('fixture', 'fixture@example.invalid')
    sub = project/'sub'
    sub.mkdir()
    for n in range(7):
        (sub/'change.py').write_text(f'VALUE = {n}\n', encoding='utf-8')
        repo.index.add_all()
        repo.index.write()
        parents = [] if n == 0 else [repo.head.target]
        repo.create_commit('HEAD', signature, signature, f'fixture {n}', repo.index.write_tree(), parents)
    target = sub if foreign else project
    result = OverviewAdapter(str(target), f'top={top}&no_imports=true').get_structure()
    assert len(result['git_log']) == count
    assert not result.get('meta', {}).get('errors')
    if foreign and count:
        assert result['git_foreign_root'] == project.as_posix()
    else:
        assert result['git_foreign_root'] is None


@pytest.mark.parametrize('spelling', ['absolute', 'relative'])
def test_import_loss_retains_exact_counts_paths_and_uncapped_causes(project, spelling):
    original = ImportsAdapter._build_graph
    def lost(self, path, **kwargs):
        original(self, path, **kwargs)
        for n in range(53):
            file = path/f'pending{n:02}.py'
            self.analysis.files_failed.append(file)
            self.analysis.files_lost.append(file)
            self.analysis.extractions[file] = _lost_extraction(
                BrokenProcessPool(f'exact controlled worker loss {n}'))
    # Controlled pending-input outcomes use the actual Imports failure artifact owner.
    target = str(project) if spelling == 'absolute' else 'proj'
    with patch.object(ImportsAdapter, '_build_graph', lost):
        result = OverviewAdapter(target, 'no_git=true').get_structure()
    metadata = result['architecture']['metadata']
    assert metadata['files_failed_count'] == metadata['files_lost_count'] == 53
    expected = [f'pending{n:02}.py' for n in range(50)]
    assert metadata['files_failed'] == metadata['files_lost'] == expected
    assert len(metadata['extraction_diagnostics']) == 53
    cause = metadata['extraction_diagnostics']['pending52.py']['parse']['reason']
    assert cause == 'BrokenProcessPool: exact controlled worker loss 52'
    cuts = [w for w in result['meta']['warnings'] if w.get('type') == 'truncated']
    for field in ('files_failed', 'files_lost'):
        cut, = [w for w in cuts if w['field'] == 'architecture.metadata.'+field]
        assert (cut['shown'], cut['total'], cut['exact'], cut['cause']) == (50, 53, True, 'auto_cap')
    warning, = [w for w in result['meta']['warnings'] if w.get('type') == 'worker_lost']
    assert warning['count'] == 53
    assert result['architecture']['unsupported_extensions'] == {}


def test_import_metadata_reuses_collector_read_without_fabricating_unknown_counts(project):
    adapter = OverviewAdapter(str(project), 'no_git=true')
    with patch.object(ImportsAdapter, 'get_metadata', return_value={'unsupported_extensions': {'.odd': 2}}) as read:
        result = _run_imports_analysis(adapter, project)
    # Four existing formatter reads plus the one collector read; no new read.
    assert read.call_count == 5
    assert result['unsupported_extensions'] == {'.odd': 2}
    assert 'files_failed_count' not in result.get('metadata', {})
    assert 'files_lost_count' not in result.get('metadata', {})


def test_existing_relativizer_handles_diagnostic_carrier_without_mutating_causes(project):
    cause = {'parse': {'status': 'unavailable', 'reason': 'OSError: exact cause'}}
    source = project/'nested'/'failed.py'
    result = {'metadata': {'files_failed': [str(source)], 'files_lost': [str(source)],
                           'files_failed_count': 1, 'files_lost_count': 1,
                           'extraction_diagnostics': {str(source): cause}}}
    _relativize_paths([], result, project)
    assert result['metadata']['files_failed'] == result['metadata']['files_lost'] == ['nested/failed.py']
    assert result['metadata']['extraction_diagnostics'] == {'nested/failed.py': cause}


def test_raw_optional_churn_warning_is_folded_once_and_visible(project):
    def unavailable(self, stats):
        self._churn_disclosure = 'exact optional churn unavailable'
        return None
    with patch.object(StatsAdapter, '_compute_churn_counts', unavailable):
        result = OverviewAdapter(str(project), 'no_git=true').get_structure()
        cli = run('overview', str(project), '--no-git')
    assert result['stats']['warnings'][0]['type'] == 'churn_unavailable'
    warning, = [w for w in result['meta']['warnings'] if w.get('type') == 'churn_unavailable']
    assert warning['message'] == 'exact optional churn unavailable'
    assert cli.returncode == 0 and cli.stdout.count('exact optional churn unavailable') == 1
    assert not result['meta']['errors']


@pytest.mark.parametrize('quality,phrase', [(60, '1 critical file(s) in shown ranking'),
                                            (80, '1 warning file(s) in shown ranking'),
                                            (100, 'no critical or warning files in shown ranking')])
def test_quality_pulse_scopes_rank_claim_but_preserves_population_average(quality, phrase):
    text = '\n'.join(_render_quality_pulse({'avg_quality_score': 84.5, 'avg_complexity': 12.5},
                                          [{'quality_score': quality}]))
    assert '84.5/100 avg quality' in text and 'avg complexity 12.5' in text
    assert phrase in text


def test_uri_query_exclusion_keeps_documented_ast_boundary(project):
    body = 'def hot(x):\n'+''.join(f'    if x == {n}: return {n}\n' for n in range(12))+'    return 0\n'
    (project/'hot.py').write_text(body, encoding='utf-8')
    query = run('overview://proj?no_git=true&exclude=hot.py', '--format', 'json')
    flag = run('overview://proj?no_git=true', '--exclude', 'hot.py', '--format', 'json')
    assert query.returncode == flag.returncode == 0
    left, right = json.loads(query.stdout), json.loads(flag.stdout)
    assert left['stats']['summary']['total_files'] == right['stats']['summary']['total_files'] == 1
    assert [fn['name'] for fn in left['complex_functions']] == ['hot']
    assert right['complex_functions'] == []


def test_reused_adapter_clears_failure_and_diagnostic_state(project):
    adapter = OverviewAdapter(str(project), 'no_git=true')
    with patch.object(ImportsAdapter, '_build_graph', side_effect=OSError('exact imports failure')):
        failed = adapter.get_structure()
    assert failed['meta']['errors']
    restored = adapter.get_structure()
    assert not restored['meta']['errors']
    assert restored['architecture']['metadata']['files_failed_count'] == 0
    assert restored['architecture']['metadata']['extraction_diagnostics'] == {}


@pytest.mark.parametrize('relative', ['proj', '../proj'])
@pytest.mark.parametrize('excluded', [False, True])
def test_architecture_matches_absolute_target_and_preserves_exclusions(project, monkeypatch, relative, excluded):
    (project/'b.py').write_text('import a\n', encoding='utf-8')
    if relative.startswith('..'):
        caller = project.parent/'caller'
        caller.mkdir()
        monkeypatch.chdir(caller)
    query = 'no_git=true'+('&exclude=b.py' if excluded else '')
    left = OverviewAdapter(relative, query).get_structure()
    right = OverviewAdapter(str(project), query).get_structure()
    assert left['source'] == left['path'] == relative
    assert left['architecture'] == right['architecture']
    assert sum(c['files'] for c in left['architecture']['components']) == (1 if excluded else 2)


def test_symlink_target_retains_architecture_and_original_resource(project):
    alias = project.parent/'alias'
    try:
        alias.symlink_to(project, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f'directory symlinks unavailable: {exc}')
    left = OverviewAdapter(str(alias), 'no_git=true').get_structure()
    right = OverviewAdapter(str(project), 'no_git=true').get_structure()
    assert left['source'] == left['path'] == str(alias)
    assert left['architecture'] == right['architecture']
