"""BACK-1884: the issue count is file-local rules only: one definition for stats, overview, hotspots.

Before: every registered rule ran on every file to produce ``quality.check_issues``, so a file's
count and score moved with a scan cap, a sibling file or the project root, and the cap's
disclosure failed overview and hotspots with exit 3. After: only rules that declare
``RuleScope.FILE`` count (``quality.local_check_issues``), the result names the rule and the
rule set (``meta.issue_count``), and a cross-file scan cap no longer reaches scoring.
"""
import copy
import errno
import importlib
import json
import os
from pathlib import Path

import pytest

from conftest import _clear_module_caches, _run_reveal_direct as run, needs_forked_workers
from reveal.adapters.hotspots import HotspotsAdapter
from reveal.adapters.stats import MetricsAdapter
from reveal.rules import RuleRegistry
from reveal.rules.base import RuleScope

pytestmark = pytest.mark.component

LITERAL = 'ROUTE_KEYS = ["alpha", "beta", "gamma", "delta", "epsilon"]\n'
BARE_EXCEPTS = ''.join(
    f'def f{n}():\n    try:\n        return {n}\n    except:\n        return 0\n\n\n' for n in range(9))
COUNTING_RULE = 'file-local rules only'


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def project(root):
    """Local findings in risky.py; a cross-file finding in each other file.

    a.py <-> b.py import each other (I002 cycle); lit_*.py repeat one literal (D005).
    """
    write(root / 'pyproject.toml', '[project]\nname="probe"\nversion="0.0.0"\n')
    write(root / 'pkg' / '__init__.py', '')
    write(root / 'pkg' / 'a.py', 'from pkg import b\n\n\ndef fa():\n    return b.fb()\n')
    write(root / 'pkg' / 'b.py', 'from pkg import a\n\n\ndef fb():\n    return a.fa\n')
    for name in ('c', 'd', 'e'):
        write(root / 'pkg' / f'lit_{name}.py', LITERAL)
    write(root / 'pkg' / 'risky.py', BARE_EXCEPTS)
    return root


def stats_files(result):
    return {row['file']: row for row in result['files']}


def local_detections(path):
    """What the file-local rules find in one file, asked of the registry directly."""
    from reveal.registry import get_analyzer
    analyzer = get_analyzer(str(path))(str(path))
    return RuleRegistry.check_file(
        str(path), analyzer.get_structure(), analyzer.content,
        select=RuleRegistry.codes_in_scope(RuleScope.FILE))


def warning_types(result):
    return [w.get('type') for w in (result.get('meta') or {}).get('warnings', [])]


def test_stats_counts_the_file_local_rules_only(tmp_path):
    root = project(tmp_path)
    rows = stats_files(MetricsAdapter(str(root)).get_structure())
    risky = rows['pkg/risky.py']['quality']
    expected = len(local_detections(root / 'pkg' / 'risky.py'))
    assert expected >= 9, 'positive control: the nine bare excepts are file-local findings'
    assert risky['local_check_issues'] == expected
    assert risky['score'] < 70
    # I002 (import cycle) and D005 (repeated literal) are cross-file: they do not count.
    for name in ('a', 'b', 'lit_c', 'lit_d', 'lit_e'):
        assert rows[f'pkg/{name}.py']['quality']['local_check_issues'] == 0, name
        assert rows[f'pkg/{name}.py']['quality']['score'] == 100.0, name


def test_the_cross_file_rules_still_detect_under_check(tmp_path):
    """Negative control: the count leaves them out; the rules themselves are unchanged."""
    root = project(tmp_path)
    cycle = json.loads(run('check', str(root / 'pkg' / 'a.py'), '--select', 'I002', '--format', 'json').stdout)
    literal = json.loads(run('check', str(root / 'pkg' / 'lit_c.py'), '--select', 'D005', '--format', 'json').stdout)
    assert [d['rule_code'] for d in cycle['detections']] == ['I002']
    assert [d['rule_code'] for d in literal['detections']] == ['D005']


def test_stats_overview_and_hotspots_agree_on_one_file(tmp_path):
    root = project(tmp_path)
    stats = stats_files(json.loads(run(f'stats://{root}', '--format', 'json').stdout))['pkg/risky.py']
    overview = json.loads(run('overview', str(root), '--no-git', '--no-imports', '--format', 'json').stdout)
    hotspots = json.loads(run('hotspots', str(root), '--files-only', '--format', 'json').stdout)
    over = stats_files(overview['stats'])['pkg/risky.py']
    ranked = {row['file']: row for row in hotspots['file_hotspots']}['pkg/risky.py']
    assert stats['quality']['local_check_issues'] == over['quality']['local_check_issues'] > 0
    assert stats['quality']['score'] == over['quality']['score'] == ranked['quality_score']


@pytest.mark.parametrize('cap', ['REVEAL_D005_MAX_FILES', 'REVEAL_T006_MAX_FILES', 'REVEAL_I002_MAX_FILES'])
def test_the_count_does_not_move_with_a_cross_file_scan_cap(tmp_path, monkeypatch, cap):
    root = project(tmp_path)
    open_ended = MetricsAdapter(str(root)).get_structure()
    _clear_module_caches()  # a cap acts when an index is built: the first run's index must not serve the second
    monkeypatch.setenv(cap, '2')
    capped = MetricsAdapter(str(root)).get_structure()
    assert capped['files'] == open_ended['files'], 'a scan cap changed a count or a score'
    assert 'analysis_incomplete' not in warning_types(capped)


def deny_directory(monkeypatch, directory):
    """Make the stats walk fail on *directory* (an actual scandir error)."""
    from reveal.adapters.stats import adapter as stats_module
    real_find, real_scan = stats_module.find_analyzable_files, os.scandir
    active = []

    def find(*args, **kwargs):
        iterator = iter(real_find(*args, **kwargs))
        while True:
            active.append(1)
            try:
                path = next(iterator)
            except StopIteration:
                return
            finally:
                active.pop()
            yield path

    def scan(path):
        if active and Path(path) == directory:
            raise PermissionError(errno.EACCES, 'controlled traversal failure', str(path))
        return real_scan(path)

    monkeypatch.setattr(stats_module, 'find_analyzable_files', find)
    monkeypatch.setattr(os, 'scandir', scan)


COMMANDS = {
    'hotspots': ('hotspots', '{root}', '--format', 'json'),
    'overview': ('overview', '{root}', '--no-git', '--no-imports', '--format', 'json'),
}


def invoke(name, root):
    return run(*[part.format(root=root) for part in COMMANDS[name]])


# overview already dropped the notes that name I002 (its imports slice owns them, BACK-2018), so
# for the two I002 caps only hotspots changes; D005 and T006 notes reached both.
CAPS = [('REVEAL_D005_MAX_FILES', '3'), ('REVEAL_T006_MAX_FILES', '3'),
        ('REVEAL_I002_MAX_FILES', '3'), ('REVEAL_I002_CYCLE_LIMIT', '3')]


@pytest.mark.parametrize('command', sorted(COMMANDS))
@pytest.mark.parametrize('cap, limit', CAPS)
def test_a_scan_cap_alone_no_longer_fails_overview_or_hotspots(tmp_path, monkeypatch, command, cap, limit):
    """The cap note was the only cause of exit 3 here: nothing else is wrong with this tree."""
    root = project(tmp_path)
    assert invoke(command, root).returncode == 0, 'positive control: the tree is clean without the cap'
    _clear_module_caches()  # a cap acts when an index is built: the first run's index must not serve the second
    monkeypatch.setenv(cap, limit)
    capped = invoke(command, root)
    assert capped.returncode == 0, (capped.returncode, capped.stderr)
    result = json.loads(capped.stdout)
    assert 'analysis_incomplete' not in warning_types(result), result.get('meta')
    assert not (result.get('meta') or {}).get('errors')
    assert result['meta']['issue_count']['rule'] == COUNTING_RULE, 'the count still says what it counts'


@pytest.mark.parametrize('command', sorted(COMMANDS))
def test_a_traversal_failure_still_fails_overview_and_hotspots(tmp_path, monkeypatch, command):
    """Negative control: only the cross-file scan-cap note left scoring, not directory loss."""
    root = project(tmp_path)
    hidden = root / 'pkg' / 'hidden'
    write(hidden / 'inner.py', 'def inner():\n    return 1\n')
    deny_directory(monkeypatch, hidden)
    result_run = invoke(command, root)
    result = json.loads(result_run.stdout)
    lost = [w for w in result['meta']['warnings']
            if w.get('type') == 'analysis_incomplete' and w.get('unit') == 'directories']
    assert lost and lost[0]['count'] == 1
    assert result_run.returncode == 3, (result_run.returncode, result_run.stderr)


@pytest.mark.parametrize('command', sorted(COMMANDS))
def test_a_crashed_file_local_rule_still_fails_overview_and_hotspots(tmp_path, monkeypatch, command):
    """Negative control: a rule that could not run keeps its warning and exit code."""
    from reveal.rules.bugs.B001 import B001

    def crash(self, *args, **kwargs):
        raise RuntimeError('controlled rule crash')

    monkeypatch.setattr(B001, 'check', crash)
    root = project(tmp_path)
    result_run = invoke(command, root)
    result = json.loads(result_run.stdout)
    failed = [w for w in result['meta']['warnings'] if w.get('type') == 'check_rules_failed']
    assert failed and failed[0]['count'] >= 1
    assert result_run.returncode == 3, (result_run.returncode, result_run.stderr)


@pytest.mark.parametrize('command', ['architecture', 'deps'])
def test_siblings_that_never_read_stats_keep_their_exit_codes_under_a_cap(tmp_path, monkeypatch, command):
    """Sibling control: architecture and deps compose imports, not stats; the cap never reached them."""
    root = project(tmp_path)
    before = run(command, str(root), '--format', 'json')
    monkeypatch.setenv('REVEAL_D005_MAX_FILES', '3')
    after = run(command, str(root), '--format', 'json')
    assert (after.returncode, after.stdout) == (before.returncode, before.stdout)


def test_stats_builds_no_project_wide_index(tmp_path):
    """The shared indexes (I002 graph, D005 literals, M102 imports) belong to rules the count skips."""
    D005, I002, M102 = (importlib.import_module(f'reveal.rules.{name}') for name in
                        ('duplicates.D005', 'imports.I002', 'maintainability.M102'))
    root = project(tmp_path)
    MetricsAdapter(str(root)).get_structure()
    assert I002._graph_cache == {}
    assert D005._project_index == {}
    assert M102._import_cache == {}


@needs_forked_workers
@pytest.mark.real_worker_pool
def test_stats_pool_does_not_preload_the_indexes(tmp_path, monkeypatch):
    D005, I002 = (importlib.import_module(f'reveal.rules.{name}') for name in
                  ('duplicates.D005', 'imports.I002'))
    root = project(tmp_path)
    for number in range(25):
        write(root / 'pkg' / f'plain{number}.py', f'VALUE_{number} = {number}\n')
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '2')
    result = MetricsAdapter(str(root)).get_structure()
    assert result['summary']['total_files'] >= 30
    assert I002._graph_cache == {} and D005._project_index == {}, 'the parent preloaded an index'


def issue_count_meta(result):
    return result['meta']['issue_count']


def assert_states_the_rule(meta):
    codes = RuleRegistry.codes_in_scope(RuleScope.FILE)
    assert meta['rule'] == COUNTING_RULE
    assert meta['field'] == 'local_check_issues'
    assert meta['rule_count'] == len(codes) > 20
    assert meta['rules'] == codes
    assert isinstance(meta['rule_set_id'], str) and len(meta['rule_set_id']) == 8
    assert not {'I002', 'D005', 'M102', 'T006', 'I007', 'L001'} & set(meta['rules'])


def test_every_consumer_states_the_counting_rule_and_the_same_rule_set(tmp_path):
    root = project(tmp_path)
    stats = json.loads(run(f'stats://{root}', '--format', 'json').stdout)
    one = json.loads(run(f'stats://{root}/pkg/risky.py', '--format', 'json').stdout)
    overview = json.loads(run('overview', str(root), '--no-git', '--no-imports', '--format', 'json').stdout)
    hotspots = json.loads(run('hotspots', str(root), '--format', 'json').stdout)
    metas = [issue_count_meta(r) for r in (stats, one, overview, hotspots)]
    for meta in metas:
        assert_states_the_rule(meta)
    assert len({meta['rule_set_id'] for meta in metas}) == 1


@pytest.mark.parametrize('args', [
    ('stats://{root}',),
    ('stats://{root}/pkg/risky.py',),
    ('overview', '{root}', '--no-git', '--no-imports'),
    ('hotspots', '{root}'),
])
def test_the_text_footer_names_the_rule_and_the_rule_set(tmp_path, args):
    root = project(tmp_path)
    out = run(*[a.format(root=root) for a in args]).stdout
    meta = issue_count_meta(json.loads(run(*[a.format(root=root) for a in args], '--format', 'json').stdout))
    line, = [row for row in out.splitlines() if COUNTING_RULE in row]
    assert meta['rule_set_id'] in line and f"{meta['rule_count']} rules" in line
    assert 'local_check_issues' in line


def test_the_field_is_renamed_in_every_stats_view(tmp_path):
    root = project(tmp_path)
    directory = MetricsAdapter(str(root)).get_structure()
    single = MetricsAdapter(str(root / 'pkg' / 'risky.py')).get_structure()
    element = MetricsAdapter(str(root)).get_element('pkg/risky.py')
    for quality in (directory['files'][0]['quality'], single['files'][0]['quality'], element['quality']):
        assert 'local_check_issues' in quality and 'check_issues' not in quality
    schema = json.dumps(MetricsAdapter.get_schema())
    assert 'local_check_issues' in schema and '"check_issues"' not in schema


def config_project(tmp_path, text):
    root = project(tmp_path)
    write(root / '.reveal' / 'stats-quality.yaml', text)
    return root


def risky_score(root):
    return stats_files(MetricsAdapter(str(root)).get_structure())['pkg/risky.py']['quality']['score']


def test_penalty_config_key_is_renamed_and_the_old_spelling_still_applies_with_a_warning(tmp_path):
    base = risky_score(project(tmp_path / 'base'))
    new_root = config_project(tmp_path / 'new', 'penalties:\n  local_check_issues:\n    high: 0\n    max: 0\n')
    old_root = config_project(tmp_path / 'old', 'penalties:\n  check_issues:\n    high: 0\n    max: 0\n')
    assert risky_score(new_root) > base, 'the new key is read'
    assert 'deprecated_config_key' not in warning_types(MetricsAdapter(str(new_root)).get_structure())
    assert risky_score(old_root) == risky_score(new_root), 'the old key is an alias'
    old = MetricsAdapter(str(old_root)).get_structure()
    note, = [w for w in old['meta']['warnings'] if w.get('type') == 'deprecated_config_key']
    assert 'check_issues' in note['message'] and 'local_check_issues' in note['message']


def test_the_new_penalty_key_wins_over_the_old_one(tmp_path):
    both = config_project(tmp_path / 'both', 'penalties:\n  check_issues:\n    high: 0\n    max: 0\n'
                                              '  local_check_issues:\n    high: 5\n    max: 40\n')
    assert risky_score(both) == risky_score(project(tmp_path / 'default'))


def test_a_filter_on_the_old_field_name_is_honoured_and_says_it_is_deprecated(tmp_path):
    """A renamed field must not turn an existing filter into a silent empty answer."""
    root = project(tmp_path)
    new = MetricsAdapter(str(root), 'quality.local_check_issues>0').get_structure()
    old = MetricsAdapter(str(root), 'quality.check_issues>0').get_structure()
    assert [r['file'] for r in new['files']] == ['pkg/risky.py']
    assert [r['file'] for r in old['files']] == ['pkg/risky.py']
    assert 'deprecated_field' in warning_types(old)
    assert 'deprecated_field' not in warning_types(new)


def test_review_hotspot_rows_use_the_new_field(monkeypatch):
    from unittest.mock import patch
    from reveal.cli.commands.review import _run_hotspots
    row = {'files': [{'file': 'q60.py', 'quality': {'score': 60.0, 'local_check_issues': 4},
                      'complexity': {'average': 31, 'max': 31, 'min': 31}}]}
    with patch('reveal.adapters.stats.adapter.MetricsAdapter') as adapter:
        adapter.return_value.get_structure.return_value = row
        (found,) = _run_hotspots(None, files=[Path('a.py')])
    assert found['local_check_issues'] == 4 and 'check_issues' not in found


def run_with_every_rule(monkeypatch):
    """The pre-BACK-1884 behavior: check_file is asked for every registered rule."""
    real = RuleRegistry.check_file.__func__

    def all_rules(cls, *args, **kwargs):
        kwargs['ignore'] = None
        return real(cls, *args, **kwargs)

    monkeypatch.setattr(RuleRegistry, 'check_file', classmethod(all_rules))


def overview_json(root):
    result = json.loads(run('overview', str(root), '--no-git', '--no-imports', '--format', 'json').stdout)
    return result


def without_basis(result):
    result = copy.deepcopy(result)
    (result.get('meta') or {}).pop('issue_count', None)
    return result


def test_overview_is_unchanged_where_no_cross_file_rule_detects(tmp_path, monkeypatch):
    """Fixture twin of the celery-package check: a tree whose only findings are file-local gives
    the same overview whether every rule is counted or only the file-local ones."""
    root = write(tmp_path / 'pyproject.toml', '[project]\nname="local"\n').parent
    # Both modules are imported, so M102 (orphan module) has nothing to say about them.
    write(root / 'pkg' / '__init__.py', 'from pkg import ok, risky\n\n__all__ = ["ok", "risky"]\n')
    write(root / 'pkg' / 'risky.py', BARE_EXCEPTS)
    write(root / 'pkg' / 'ok.py', 'def ok():\n    return 1\n')
    cross_file = run('check', str(root), '--select', 'M102,I002,D005,T006,I007', '--format', 'json')
    assert json.loads(cross_file.stdout)['files'] == [], 'precondition: no cross-file rule detects here'
    local_only = overview_json(root)
    with monkeypatch.context() as patched:
        run_with_every_rule(patched)
        every_rule = overview_json(root)
    assert without_basis(local_only) == without_basis(every_rule)


def test_overview_differs_where_a_cross_file_rule_detects(tmp_path, monkeypatch):
    """Positive control for the twin above: the every-rule run does see the cycle."""
    root = project(tmp_path)
    local_only = overview_json(root)
    with monkeypatch.context() as patched:
        run_with_every_rule(patched)
        every_rule = overview_json(root)
    lo, ev = stats_files(local_only['stats']), stats_files(every_rule['stats'])
    assert lo['pkg/a.py']['quality']['local_check_issues'] == 0
    assert ev['pkg/a.py']['quality']['local_check_issues'] == 1, 'the I002 cycle counts when every rule runs'


def test_hotspots_adapter_states_the_rule_without_file_ranking(tmp_path):
    root = project(tmp_path)
    result = HotspotsAdapter(str(root), 'functions_only=true').get_structure()
    assert_states_the_rule(issue_count_meta(result))


def _plugin_rules():
    """Two plugin-style rules that flag line 1 of every file; one declares its scope."""
    from reveal.rules.base import BaseRule, RulePrefix, Severity

    class Declared(BaseRule):
        code = 'X8851'
        message = 'plugin rule that declares scope = "file"'
        category = RulePrefix.B
        severity = Severity.HIGH
        file_patterns = ['.py']
        scope = 'file'   # a plugin may write the string, as it may for severity

        def check(self, file_path, structure, content):
            return [self.create_detection(file_path, 1)]

    class Undeclared(Declared):
        code = 'X8852'
        message = 'plugin rule that declares no scope'
        scope = None

    return Declared, Undeclared


def test_a_plugin_rule_counts_only_when_it_declares_a_file_scope_and_the_count_lists_the_rest(
        tmp_path, monkeypatch):
    declared, undeclared = _plugin_rules()
    RuleRegistry.discover()
    monkeypatch.setattr(RuleRegistry, '_rules', [*RuleRegistry._rules, declared, undeclared])
    monkeypatch.setattr(RuleRegistry, '_rules_by_code',
                        {**RuleRegistry._rules_by_code, 'X8851': declared, 'X8852': undeclared})
    root = project(tmp_path)
    result = MetricsAdapter(str(root)).get_structure()
    ok = stats_files(result)['pkg/lit_c.py']['quality']
    # X8851 (HIGH) counts once per file; X8852 declares nothing, so it is not counted ...
    assert ok['local_check_issues'] == 1 and ok['score'] == 95.0
    basis = result['meta']['issue_count']
    assert 'X8851' in basis['rules'] and 'X8852' not in basis['rules']
    # ... and the count says it was left out, instead of dropping it silently.
    assert basis['undeclared'] == ['X8852']
    assert basis['rule_count'] == len(basis['rules'])


def test_review_is_no_longer_incomplete_for_a_cap_on_a_rule_it_did_not_run(tmp_path, monkeypatch):
    """review's hotspot step reads stats: the cap note of D005, a rule review's own quality pass
    does not select, used to make the whole review incomplete (exit 3)."""
    root = project(tmp_path)
    monkeypatch.setenv('REVEAL_D005_MAX_FILES', '3')
    review = run('review', str(root), '--select', 'B', '--format', 'json')
    report = json.loads(review.stdout)
    assert 'analysis_incomplete' not in warning_types(report), report.get('meta')
    assert report['overall_status'] != 'incomplete' and review.returncode != 3


def test_review_still_reports_a_cap_on_a_rule_its_own_quality_pass_runs(tmp_path, monkeypatch):
    """Negative control: with D005 selected review's check pass runs it, and check discloses the cap."""
    root = project(tmp_path)
    monkeypatch.setenv('REVEAL_D005_MAX_FILES', '3')
    review = run('review', str(root), '--select', 'D005', '--format', 'json')
    report = json.loads(review.stdout)
    assert any('D005' in note for note in report.get('scan_disclosures', [])), report.keys()
    assert (review.returncode, report['overall_status']) == (3, 'incomplete')


@pytest.mark.mcp
@pytest.mark.parametrize('scheme, query', [('hotspots', ''), ('overview', '?no_git=true&no_imports=true')])
def test_the_mcp_query_tool_adds_no_incomplete_note_for_a_scan_cap(tmp_path, monkeypatch, scheme, query):
    """mcp_server appends 'Required analysis is incomplete' to an INCOMPLETE answer; a cap alone is not one."""
    from reveal import mcp_server
    root = project(tmp_path)
    monkeypatch.setenv('REVEAL_D005_MAX_FILES', '3')
    answer = mcp_server.reveal_query(f'{scheme}://{root}{query}')
    assert 'Required analysis is incomplete' not in answer, answer
    assert COUNTING_RULE in answer, 'the answer still says what its count counts'
