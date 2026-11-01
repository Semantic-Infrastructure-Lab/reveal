"""Observed public claims outside oracle target keys are disclosed without being scored."""
import copy
import json
import os

import pytest

from test_recall_gate import _repo, gate

pytestmark = pytest.mark.component


@pytest.fixture
def population_corpus(tmp_path, monkeypatch):
    root, entry = _repo(tmp_path / 'corpus', {
        'pkg/shared.py': '', 'pkg/unused.py': '',
        'pkg/module.py': 'import pkg.shared\n',
        'pkg/local.py': 'def f():\n    import pkg.shared\n',
        'tests/use.py': 'import pkg.shared\n', 'outside/hidden.py': '',
    }, {'oracle': 'python-ast', 'importer_dirs': ['pkg', 'tests'],
        'test_importer_dirs': ['tests']})
    calls, additions = [], {}

    def rendered(scan, cap, lazy='include', tests='include', *, policy=None):
        calls.append((lazy, tests, policy is not None))
        importers = {'pkg/module.py', 'pkg/local.py', 'tests/use.py'}
        if lazy != 'include':
            importers &= {'pkg/local.py'} if lazy == 'only' else {'pkg/module.py', 'tests/use.py'}
        if tests == 'exclude':
            importers -= {'tests/use.py'}
        graph = {root / 'pkg/shared.py': {root / name for name in importers}}
        for target, sources in additions.items():
            graph.setdefault(target, set()).update(sources)
        return {'by_target': graph, 'partial_files': 0,
                'edge_rule': {'lazy': lazy, 'tests': tests}}

    monkeypatch.setattr(gate, 'rendered_reverse_graph', rendered)
    return root, entry, additions, calls


def without_disclosure(row):
    if isinstance(row, dict):
        return {key: without_disclosure(value) for key, value in row.items() if key != 'target_population'}
    return copy.deepcopy(row)


def test_unknown_targets_are_disclosed_but_do_not_change_scores(population_corpus):
    root, entry, additions, calls = population_corpus
    before = gate.measure(entry, root)
    assert len(calls) == 4  # Default, two lazy views and test exclusion; no extra population query.
    additions.update({root / 'z.py': {root / 'pkg/module.py', root / 'outside/hidden.py'},
                      root / 'a.py': {root / 'pkg/local.py'},
                      root / 'ignored.py': {root / 'outside/hidden.py'}, root / 'empty.py': set()})
    calls.clear()
    after = gate.measure(entry, root)
    assert len(calls) == 4
    assert without_disclosure(after) == without_disclosure(before)
    assert gate.regressions({'py': after}, {'py': without_disclosure(before)}) == []
    scope = after['target_population']
    assert scope['status'] == 'observed'
    assert scope['oracle_targets'] == 1
    assert scope['observed_targets'] == 3
    assert scope['observed_pairs'] == 5 and scope['scored_pairs'] == 3
    assert scope['unscored_targets'] == scope['unscored_pairs'] == 2
    assert scope['unscored_target_paths'] == ['a.py', 'z.py']


def test_surplus_on_known_target_still_changes_existing_score(population_corpus):
    root, entry, additions, _ = population_corpus
    before = gate.measure(entry, root)
    additions[root / 'pkg/shared.py'] = {root / 'pkg/unused.py'}
    after = gate.measure(entry, root)
    assert after['extra_edges'] == 1 and before['extra_edges'] == 0
    assert any('extra-edge population changed' in failure
               for failure in gate.regressions({'py': after}, {'py': before}))
    assert after['target_population']['scored_pairs'] == 4
    assert after['target_population']['unscored_pairs'] == 0


def test_suffix_excluded_importer_does_not_create_an_observed_target(population_corpus):
    root, entry, additions, _ = population_corpus
    entry['recall']['exclude_importer_suffixes'] = ['unused.py']
    additions[root / 'unknown.py'] = {root / 'pkg/unused.py'}
    row = gate.measure(entry, root)
    assert row['hit_edges'] == row['oracle_edges'] == 3
    scope = row['target_population']
    assert scope['observed_targets'] == 1 and scope['observed_pairs'] == scope['scored_pairs'] == 3
    assert scope['unscored_targets'] == scope['unscored_pairs'] == 0


def test_no_eligible_public_pairs_is_observed_zero_with_known_empty_truth(population_corpus):
    root, entry, _, _ = population_corpus
    entry['recall']['importer_dirs'] = ['tests']
    row = gate.measure(entry, root)['lazy']['only']
    assert row['oracle_edges'] == 0 and row['recall'] is None
    scope = row['target_population']
    assert scope['status'] == 'observed' and scope['oracle_targets'] == 1
    assert scope['observed_targets'] == scope['observed_pairs'] == scope['scored_pairs'] == 0
    assert scope['unscored_targets'] == scope['unscored_pairs'] == 0


def test_all_parameter_rows_disclose_observed_claims_and_keep_empty_truth_keys(population_corpus, tmp_path):
    root, entry, additions, calls = population_corpus
    # Only the test importer has truth: exclusion leaves the known target empty but still scoreable.
    entry['recall']['importer_dirs'] = ['tests']
    additions[root / 'unknown.py'] = {root / 'tests/use.py'}
    policy_path = tmp_path / 'policy.yaml'
    policy_path.write_text('test_layout: {additional_paths: [tests]}\n', encoding='utf-8')
    measured = gate.measure(entry, root, policy=gate._read_test_policy(policy_path), test_lazy=True)
    rows = [measured, *measured['lazy'].values()]
    for dimension in ('tests', 'configured_tests'):
        row = measured[dimension]['exclude']
        assert row['targets'] == 0 and row['oracle_edges'] == 0
        rows.extend([row, *row['lazy'].values()])
    assert len(rows) == len(calls) == 9
    for row in rows:
        scope = row['target_population']
        assert scope['oracle_targets'] == 1
        assert scope['unscored_pairs'] == 1
        assert scope['unscored_target_paths'] == ['unknown.py']
    assert measured['tests']['exclude']['target_population']['scored_pairs'] == 0


def test_wrongly_retained_test_importer_remains_in_the_scored_population(population_corpus):
    root, entry, additions, _ = population_corpus
    additions[root / 'pkg/shared.py'] = {root / 'tests/use.py'}
    row = gate.measure(entry, root)['tests']['exclude']
    assert row['extra_edges'] == 1
    assert row['target_population']['scored_pairs'] == row['hit_edges'] + row['extra_edges'] == 3


def test_outside_root_target_has_relative_posix_identity(population_corpus):
    root, entry, additions, _ = population_corpus
    additions[root.parent / 'outside.py'] = {root / 'pkg/module.py'}
    scope = gate.measure(entry, root)['target_population']
    assert scope['unscored_target_paths'] == ['../outside.py']
    assert scope['unscored_target_paths_unavailable'] == 0


def test_cross_drive_identity_failure_does_not_hide_counts_or_leak_absolute_path(population_corpus, monkeypatch):
    root, entry, additions, _ = population_corpus
    target = root.parent / 'outside.py'
    additions[target] = {root / 'pkg/module.py'}
    relpath = os.path.relpath

    def different_drive(path, start):
        if path == target:
            raise ValueError('path is on another drive')
        return relpath(path, start)

    monkeypatch.setattr(gate.os.path, 'relpath', different_drive)
    scope = gate.measure(entry, root)['target_population']
    assert scope['unscored_targets'] == scope['unscored_pairs'] == 1
    assert scope['unscored_target_paths'] == []
    assert scope['unscored_target_paths_unavailable'] == 1
    assert scope['unscored_target_paths_reason']
    assert str(root.parent) not in json.dumps(scope)


def test_go_per_target_view_declines_observed_population(population_corpus, monkeypatch):
    root, entry, _, calls = population_corpus
    oracle = gate.ORACLES['python-ast']
    monkeypatch.setitem(gate.ORACLES, 'go-toolchain', oracle._replace(lazy_only=None))
    entry['recall'] = {**entry['recall'], 'oracle': 'go-toolchain'}
    del entry['recall']['test_importer_dirs']
    monkeypatch.setattr(gate, 'rendered_dependents', lambda *args: {
        'importers': {root / 'pkg/module.py', root / 'pkg/local.py', root / 'tests/use.py'},
        'partial_files': 0, 'edge_rule': {}})
    row = gate.measure(entry, root)
    assert row['recall'] == row['precision'] == 1
    assert calls == []
    scope = row['target_population']
    assert scope['status'] == 'unavailable' and scope['oracle_targets'] == 1
    assert 'per-target' in scope['reason']
    assert 'observed_pairs' not in scope and 'unscored_targets' not in scope
