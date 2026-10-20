"""BACK-2114: the effective rule set for a (select, ignore) pair is resolved once, not
five to seven times per file by get_scan_disclosures.

stats:// and overview:// call get_scan_disclosures once per analyzed file (each file's
worker asks which scan-capped rules ran), and every rule_will_run inside it re-filtered
the whole rule registry. The red tests count RuleRegistry.get_rules calls that carry a
non-empty ``select`` -- the disclosure path passes the codes that ran; the per-file rule
pass itself (check_file) always passes select=None, so it is not in the count.
"""
import json
from pathlib import Path

import pytest

from reveal.adapters.stats.adapter import StatsAdapter
from reveal.rules import RuleRegistry
from reveal.rules import scan_caches
from reveal.utils.request_cache import reset_request_caches
from reveal.rules.base import BaseRule, RulePrefix, Severity
from reveal.rules.scan_caches import (
    get_scan_budgets, get_scan_disclosures, preload_scan_caches, rule_will_run,
)

pytestmark = pytest.mark.component

SELECT_IGNORE = [
    (None, None),
    (['I002'], None),
    (['C901'], None),
    (['I'], None),
    (['D005', 'T006', 'M102', 'I007'], None),
    (None, ['I002']),
    (None, ['I', 'D']),
    (['I', 'D', 'T', 'M'], ['I002']),
    (['NOPE999'], None),
    (['I002', 'I007'], ['I007']),
]
INDEX_CODES = ('I002', 'I007', 'D005', 'T006', 'M102')


def _reference_will_run(code, select, ignore):
    """The pre-BACK-2114 definition, verbatim: one registry filter per question."""
    return any(r.code == code for r in RuleRegistry.get_rules(select=select, ignore=ignore))


@pytest.fixture
def get_rules_calls(monkeypatch):
    """Record the select argument of every RuleRegistry.get_rules call."""
    seen = []
    real = RuleRegistry.get_rules.__func__

    def counted(cls, select=None, ignore=None):
        seen.append(None if select is None else tuple(select))
        return real(cls, select=select, ignore=ignore)

    monkeypatch.setattr(RuleRegistry, 'get_rules', classmethod(counted))
    return seen


def _disclosure_questions(seen):
    """Calls made to answer 'did this rule run' -- those with a non-empty select."""
    return [s for s in seen if s]


def _write_py_files(directory: Path, count: int):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'pyproject.toml').write_text('[project]\nname="sample"\n', encoding='utf-8')
    for i in range(count):
        (directory / f'mod{i}.py').write_text(
            f'def f{i}(a, b):\n    return a + b + {i}\n', encoding='utf-8')
    return sorted(directory.glob('mod*.py'))


def test_scan_disclosure_resolution_does_not_grow_with_files(tmp_path, get_rules_calls):
    """Red: one get_scan_disclosures call per analyzed file, as stats does, repeated N
    times for the same selected codes. Old code filtered the registry 5-7 times per call
    (so N=3 and N=30 differ by 27 x 5+); the effective set is the same every time."""
    files = _write_py_files(tmp_path, 30)
    eligible = ['B001', 'D005', 'I001', 'I002', 'I007', 'M102', 'T006']

    def questions_for(n):
        reset_request_caches()  # each measurement is its own request: cold start
        get_rules_calls.clear()
        for path in files[:n]:
            get_scan_disclosures([path], eligible, None)
        return len(_disclosure_questions(get_rules_calls))

    few, many = questions_for(3), questions_for(30)
    assert many == few, (
        f'effective rule set re-resolved per call: {few} registry filters for 3 files, '
        f'{many} for 30 (want equal: O(1) in files)')
    assert many <= 1, f'one distinct (select, ignore) should resolve at most once, got {many}'


def test_stats_directory_resolves_rule_set_once_for_all_files(tmp_path, get_rules_calls):
    """Red, through the real caller: stats:// over a directory (serial, as the suite sets
    REVEAL_MAX_WORKERS=1) must not filter the registry per file for its disclosures."""
    def questions_for(directory, n):
        _write_py_files(directory, n)
        reset_request_caches()
        get_rules_calls.clear()
        StatsAdapter(str(directory)).get_structure()
        return len(_disclosure_questions(get_rules_calls))

    few = questions_for(tmp_path / 'few', 3)
    many = questions_for(tmp_path / 'many', 12)
    assert many == few, f'{few} disclosure registry filters for 3 files, {many} for 12'
    assert many <= 3, f'stats over 12 files resolved the rule set {many} times'


@pytest.mark.parametrize('select,ignore', SELECT_IGNORE)
def test_rule_will_run_equals_registry_definition(select, ignore):
    """Output equality: every combination answers exactly as one fresh registry filter."""
    for code in INDEX_CODES + ('C901', 'B001', 'ZZZ999'):
        assert rule_will_run(code, select, ignore) == _reference_will_run(code, select, ignore), \
            (code, select, ignore)
    # Asked twice, the second answer cannot differ (a memo must not change a result).
    for code in INDEX_CODES:
        assert rule_will_run(code, select, ignore) == _reference_will_run(code, select, ignore)


@pytest.mark.parametrize('select,ignore', SELECT_IGNORE)
def test_scan_disclosures_and_budgets_identical_for_every_filter(tmp_path, monkeypatch, select, ignore):
    """Output equality of the two consumers: a failed preload for each index rule is
    reported exactly when that rule is in the effective set, for each filter."""
    files = _write_py_files(tmp_path, 2)
    monkeypatch.setattr(scan_caches, '_preload_failures',
                        {code: 'OSError: injected' for code in INDEX_CODES})
    expected = [code for code in sorted(INDEX_CODES) if _reference_will_run(code, select, ignore)]
    got = get_scan_disclosures(files, select, ignore)
    failed = [m.split(':', 1)[0] for m in got if 'shared-index preload failed' in m]
    assert failed == expected
    budgets = get_scan_budgets(files, select, ignore)
    assert [r for r in budgets] == get_scan_budgets(files, select, ignore)
    if not any(_reference_will_run(c, select, ignore) for c in ('I002', 'D005')):
        assert budgets == []


def test_rule_disabled_by_config_is_reported_as_before(tmp_path, monkeypatch):
    """A rule a .reveal.yaml disables is still in the registry's effective set (config is
    applied per file by check_file, not by the registry); the answer must not change."""
    (tmp_path / '.reveal.yaml').write_text(
        'root: true\nrules:\n  disable: ' + json.dumps(['I002', 'D005']) + '\n', encoding='utf-8')
    files = _write_py_files(tmp_path, 2)
    monkeypatch.setattr(scan_caches, '_preload_failures', {'I002': 'OSError: injected'})
    for select, ignore in SELECT_IGNORE:
        want = _reference_will_run('I002', select, ignore)
        got = [m for m in get_scan_disclosures(files, select, ignore) if m.startswith('I002:')]
        assert bool(got) == want, (select, ignore)


class _LateRule(BaseRule):
    code = 'ZQ901'
    message = 'registered between two requests'
    category = RulePrefix.B
    severity = Severity.LOW
    file_patterns = ['*.py']

    def check(self, file_path, structure, content):
        return []


def test_rule_added_between_requests_is_honoured(monkeypatch):
    """A plugin rule registered after the first answer (project/user rule discovery, a
    forced rediscovery) must show up in the next answer for the same select/ignore."""
    RuleRegistry.discover()
    monkeypatch.setattr(RuleRegistry, '_rules', list(RuleRegistry._rules))
    monkeypatch.setattr(RuleRegistry, '_rules_by_code', dict(RuleRegistry._rules_by_code))
    assert rule_will_run('ZQ901', ['ZQ'], None) is False
    assert rule_will_run('ZQ901', None, None) is False
    RuleRegistry._register_rule_in_registry(_LateRule)
    assert rule_will_run('ZQ901', ['ZQ'], None) is True
    assert rule_will_run('ZQ901', None, None) is True
    assert rule_will_run('ZQ901', None, ['ZQ']) is False


def test_forced_rediscovery_drops_a_removed_rule(monkeypatch):
    """Rediscovery replaces the rule list; an answer taken from the old list is stale."""
    RuleRegistry.discover()
    assert rule_will_run('I002', None, None) is True
    monkeypatch.setattr(RuleRegistry, '_rules',
                        [r for r in RuleRegistry._rules if r.code != 'I002'])
    assert rule_will_run('I002', None, None) is False


def _spy_builders(monkeypatch):
    """Replace every shared-index builder with a recorder; return the call log."""
    import reveal.rules.duplicates.D005 as d005
    import reveal.rules.imports._dep_reconciliation as dep
    import reveal.rules.imports.I002 as i002
    import reveal.rules.maintainability.M102 as m102
    import reveal.rules.types.T006 as t006
    calls = []

    def spy(name, result):
        def _spy(*args, **kwargs):
            calls.append(name)
            return result
        return _spy

    monkeypatch.setattr(i002.I002, '_build_import_graph', spy('I002', None))
    monkeypatch.setattr(d005, '_build_index', spy('D005', {}))
    monkeypatch.setattr(t006, '_build_index', spy('T006', {}))
    monkeypatch.setattr(m102.M102, '_collect_all_imports', spy('M102', None))
    monkeypatch.setattr(dep, '_preload_project_imports', spy('I007', {}))
    return calls


def test_select_c901_builds_no_project_index(tmp_path, monkeypatch):
    """Negative control (BACK-338): --select C901 must not trigger any index build."""
    calls = _spy_builders(monkeypatch)
    files = _write_py_files(tmp_path, 3)
    caches = preload_scan_caches(files, tmp_path, ['C901'], None)
    assert calls == []
    assert caches == {code: {} for code in INDEX_CODES}


def test_default_selection_still_builds_every_index(tmp_path, monkeypatch):
    """Positive control for the negative one: the spy does see a build when selected."""
    calls = _spy_builders(monkeypatch)
    files = _write_py_files(tmp_path, 3)
    preload_scan_caches(files, tmp_path, None, None)
    assert {'I002', 'D005', 'T006', 'M102', 'I007'} <= set(calls)


def test_ignore_one_index_skips_only_that_build(tmp_path, monkeypatch):
    """Sibling control: --ignore I002 skips I002's build and leaves the others."""
    calls = _spy_builders(monkeypatch)
    files = _write_py_files(tmp_path, 3)
    preload_scan_caches(files, tmp_path, None, ['I002'])
    assert 'I002' not in calls and {'D005', 'T006', 'M102', 'I007'} <= set(calls)
