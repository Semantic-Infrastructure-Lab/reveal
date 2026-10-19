"""Every reached project and every skipped scan must remain visible."""
import json
import pytest
from reveal.rules.scan_caches import _i002_preload, _d005_preload, get_scan_budgets, get_scan_disclosures

pytestmark = pytest.mark.component


def projects(tmp_path):
    files = []
    for name, size in [('p1', 6), ('p2', 7)]:
        root = tmp_path / name
        (root / 'pkg').mkdir(parents=True)
        (root / 'pyproject.toml').touch()
        (root / 'pkg' / '__init__.py').touch()
        for i in range(size):
            p = root / 'pkg' / f'm{i}.py'
            p.write_text(f'from pkg import m{(i + 1) % size}\n' if name == 'p2'
                         else 'NAMES = ["a", "b", "c", "d", "e"]\n', encoding='utf-8')
        files.extend(sorted((root / 'pkg').glob('*.py')))
    return files


@pytest.mark.parametrize('rule,preload,env', [
    ('I002', _i002_preload, 'REVEAL_I002_MAX_FILES'),
    ('D005', _d005_preload, 'REVEAL_D005_MAX_FILES'),
])
def test_preload_accounts_for_every_root(tmp_path, monkeypatch, rule, preload, env):
    files = projects(tmp_path)
    monkeypatch.setenv(env, '6')
    caches = preload(tmp_path, [rule], None, files)
    assert set(caches) == {tmp_path / 'p1', tmp_path / 'p2'}
    rows = get_scan_budgets(files, [rule], None)
    assert len(rows) == 2 and all(row['skipped'] for row in rows)
    disclosures = get_scan_disclosures()
    assert all(any(str(tmp_path / p) in d for d in disclosures) for p in ('p1', 'p2'))


def test_multi_project_cap_is_partial_with_cycle_positive_control(tmp_path, monkeypatch):
    from conftest import _run_reveal_direct
    projects(tmp_path)
    monkeypatch.setenv('REVEAL_I002_MAX_FILES', '7')
    result = _run_reveal_direct('check', str(tmp_path), '--select', 'I002', '--format', 'json')
    data = json.loads(result.stdout)
    assert len(data['summary']['scan_budgets']) == 2
    assert any('p2' in d for d in data['summary']['scan_disclosures'])
    assert data['summary']['exit_code'] == result.returncode == 3
    text = _run_reveal_direct('check', str(tmp_path), '--select', 'I002')
    assert text.returncode == 3 and 'No issues found' not in text.stdout
    monkeypatch.setenv('REVEAL_I002_MAX_FILES', '100000')  # 0 would mean the default, not uncapped
    # CLI invocations are separate processes; the in-process helper needs a cold cache.
    from reveal.rules.imports.I002 import _graph_cache
    _graph_cache.clear()
    control = _run_reveal_direct('check', str(tmp_path), '--select', 'I002', '--format', 'json')
    assert json.loads(control.stdout)['summary']['total_issues'] == 7
    assert control.returncode == 1


@pytest.mark.disk_cache
def test_i002_disk_cache_includes_active_limits(tmp_path, monkeypatch):
    from reveal.rules.imports.I002 import I002, _graph_cache, _tree_fingerprint
    projects(tmp_path)
    root = tmp_path / 'p2'
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_I002_MAX_FILES', '20000')
    first = _tree_fingerprint(root)
    assert I002()._build_import_graph(root).scan_budget['limit'] == 20000
    _graph_cache.clear()
    monkeypatch.setenv('REVEAL_I002_MAX_FILES', '5000')
    assert _tree_fingerprint(root) != first
    assert I002()._build_import_graph(root).scan_budget['limit'] == 5000


def test_d005_multi_root_cap_and_duplicate_positive_control(tmp_path, monkeypatch):
    from conftest import _run_reveal_direct
    from reveal.rules.duplicates.D005 import _clear_index
    projects(tmp_path)
    monkeypatch.setenv('REVEAL_D005_MAX_FILES', '6')
    for fmt in ('text', 'json'):
        result = _run_reveal_direct('check', str(tmp_path), '--select', 'D005', '--format', fmt)
        assert result.returncode == 3
        if fmt == 'json':
            summary = json.loads(result.stdout)['summary']
            assert len(summary['scan_budgets']) == 2 and len(summary['scan_disclosures']) == 2
        else:
            assert 'No issues found' not in result.stdout
            assert all(p in result.stdout for p in ('p1', 'p2'))
    monkeypatch.delenv('REVEAL_D005_MAX_FILES')
    _clear_index()
    control = _run_reveal_direct('check', str(tmp_path), '--select', 'D005', '--format', 'json')
    assert json.loads(control.stdout)['summary']['total_issues'] > 0
    assert control.returncode == 1


def test_capped_single_file_and_exit_zero(tmp_path, monkeypatch):
    from conftest import _run_reveal_direct
    files = projects(tmp_path)
    monkeypatch.setenv('REVEAL_I002_MAX_FILES', '1')
    for target in (str(files[-1]), str(tmp_path)):
        result = _run_reveal_direct('check', target, '--select', 'I002')
        assert result.returncode == 3 and 'No issues found' not in result.stdout
        override = _run_reveal_direct('check', target, '--select', 'I002', '--exit-zero')
        assert override.returncode == 0 and 'skipping circular-dependency' in override.stdout


def test_project_parse_loss_is_disclosed_for_an_individually_clean_file(tmp_path):
    from conftest import _run_reveal_direct
    (tmp_path / 'pyproject.toml').touch()
    clean = tmp_path / 'clean.py'; clean.write_text('import broken\n', encoding='utf-8')
    (tmp_path / 'broken.py').write_text('def broken(\n', encoding='utf-8')
    result = _run_reveal_direct('check', str(clean), '--select', 'I002', '--format', 'json')
    assert result.returncode == 3
    assert any('parsed with errors' in d for d in json.loads(result.stdout)['scan_disclosures'])


# BACK-1823: the suite runs serially (conftest sets REVEAL_MAX_WORKERS=1), where every index is
# built in the main process. These rows run reveal's own pool, where only a preload keeps a capped
# second project's skip reason visible to the process that renders the verdict.

def _clear_rule_caches():
    from reveal.rules.duplicates.D005 import _clear_index as clear_d005
    from reveal.rules.imports.I002 import _graph_cache
    from reveal.rules.types.T006 import _clear_index as clear_t006
    clear_d005(); clear_t006(); _graph_cache.clear()


def test_t006_preload_accounts_for_every_root(tmp_path, monkeypatch):
    from reveal.rules.scan_caches import _t006_preload
    files = projects(tmp_path)
    monkeypatch.setenv('REVEAL_T006_MAX_FILES', '6')
    caches = _t006_preload(tmp_path, ['T006'], None, files)
    assert set(caches) == {tmp_path / 'p1', tmp_path / 'p2'}
    disclosures = get_scan_disclosures(files, ['T006'], None)
    assert all(any(str(tmp_path / p) in d for d in disclosures) for p in ('p1', 'p2'))


def test_m102_preload_builds_every_reached_root(tmp_path):
    from reveal.rules.scan_caches import _m102_preload
    files = projects(tmp_path)
    caches = _m102_preload(tmp_path, ['M102'], None, files)
    assert {tmp_path / 'p1', tmp_path / 'p2'} <= set(caches)


@pytest.mark.real_worker_pool
@pytest.mark.parametrize('rule,env', [('I002', 'REVEAL_I002_MAX_FILES'),
                                      ('D005', 'REVEAL_D005_MAX_FILES'),
                                      ('T006', 'REVEAL_T006_MAX_FILES')])
def test_parallel_cap_on_second_project_is_incomplete(tmp_path, monkeypatch, rule, env):
    from conftest import _run_reveal_direct
    projects(tmp_path)
    monkeypatch.setenv(env, '6')
    _clear_rule_caches()
    capped = _run_reveal_direct('check', str(tmp_path), '--select', rule, '--format', 'json')
    summary = json.loads(capped.stdout)['summary']
    assert capped.returncode == 3, capped.stdout
    assert any('p2' in d for d in summary['scan_disclosures'])
    monkeypatch.setenv(env, '0')
    _clear_rule_caches()
    control = _run_reveal_direct('check', str(tmp_path), '--select', rule, '--format', 'json')
    assert not json.loads(control.stdout)['summary'].get('scan_disclosures')
    assert control.returncode != 3


# BACK-1824: a capped scan is not a clean review.

def _review(tmp_path, *args):
    from conftest import _run_reveal_direct
    return _run_reveal_direct('review', str(tmp_path), '--select', 'I002', *args)


def test_capped_review_is_incomplete_in_text_and_json(tmp_path, monkeypatch):
    projects(tmp_path)
    monkeypatch.setenv('REVEAL_I002_MAX_FILES', '7')
    _clear_rule_caches()
    text = _review(tmp_path)
    assert text.returncode == 3
    assert 'Ready for review' not in text.stdout and 'No violations found ✅' not in text.stdout
    assert 'Review incomplete' in text.stdout
    _clear_rule_caches()
    report = json.loads(_review(tmp_path, '--format', 'json').stdout)
    assert (report['overall_status'], report['exit_code']) == ('incomplete', 3)
    assert report['scan_disclosures']
    monkeypatch.setenv('REVEAL_I002_MAX_FILES', '0')
    _clear_rule_caches()
    control = _review(tmp_path)
    assert control.returncode == 1          # the 7 high I002 cycle findings are visible uncapped (a finding, not usage 2)
    assert 'Review incomplete' not in control.stdout


def test_capped_mcp_review_is_not_ready(tmp_path, monkeypatch):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_review
    projects(tmp_path)
    monkeypatch.setenv('REVEAL_I002_MAX_FILES', '7')
    _clear_rule_caches()
    out = reveal_review(str(tmp_path), select='I002')
    assert 'Ready for review' not in out and 'incomplete' in out.lower()
