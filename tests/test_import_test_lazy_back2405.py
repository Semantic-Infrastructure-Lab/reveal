"""Independent test-role and function-scope facts qualify combined public views."""
import copy
import json

import pytest

from test_recall_gate import _repo, gate

pytestmark = pytest.mark.component


@pytest.fixture
def combined(tmp_path, monkeypatch):
    monkeypatch.delenv('REVEAL_CONFIG', raising=False)
    monkeypatch.delenv('REVEAL_NO_CONFIG', raising=False)
    root, entry = _repo(tmp_path / 'corpus', {
        'pyproject.toml': '[project]\nname="pkg"\n',
        'pkg/__init__.py': '', 'pkg/shared.py': '', 'pkg/only_tests.py': '',
        'pkg/module.py': ('import pkg.shared\ndef f():\n    import pkg.shared\n'
                          'from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import pkg.only_tests\n'),
        'pkg/local.py': 'def f():\n    import pkg.shared\n    import tests.helper\n',
        'pkg/use_helper.py': 'import tests.helper\n',
        'tests/__init__.py': '', 'tests/helper.py': 'import pkg.shared\n',
        'tests/boot.py': 'import pkg.shared\nimport pkg.only_tests\n',
        'tests/local.py': 'def f():\n    import pkg.shared\n',
        't/unit/helper.py': 'import pkg.shared\n',
        't/unit/local_helper.py': 'def f():\n    import pkg.shared\n',
    }, {'oracle': 'python-ast', 'importer_dirs': ['.'], 'test_importer_dirs': ['tests', 't/unit']})
    policy_file = tmp_path / 'policy.yaml'
    policy_file.write_text('test_layout: {additional_paths: [t/unit]}\n', encoding='utf-8')
    return root, entry, gate._read_test_policy(policy_file)


def measure(combined, configured=False):
    root, entry, policy = combined
    return gate.measure(entry, root, policy=policy if configured else None, test_lazy=True)


def modes(row, configured=False):
    return row['configured_tests' if configured else 'tests']['exclude']['lazy']


def test_public_crossed_modes_use_independent_partition_and_retain_helper_targets(combined):
    row = measure(combined, configured=True)
    assert row['oracle_edges'] == row['hit_edges'] == 10
    assert row['lazy']['exclude']['oracle_edges'] == 6
    assert row['lazy']['only']['oracle_edges'] == 4
    assert row['tests']['exclude']['oracle_edges'] == 4
    conventional, configured = modes(row), modes(row, True)
    for mode, helper in [('exclude', 't/unit/helper.py'), ('only', 't/unit/local_helper.py')]:
        assert conventional[mode]['oracle_edges'] == conventional[mode]['hit_edges'] == 2
        assert conventional[mode]['extra_edges'] == 1
        assert conventional[mode]['differences'] == [{'target': 'pkg/shared.py', 'missed': [], 'extra': [helper]}]
        selected = configured[mode]
        assert selected['oracle_edges'] == selected['hit_edges'] == 2
        assert selected['extra_edges'] == 0 and selected['recall'] == selected['precision'] == 1
        assert selected['targets'] == 2  # Production imports of tests/helper.py survive both modes.
        assert selected['edge_rule']['lazy'] == mode
        assert selected['edge_rule']['tests'] == 'importers_not_counted'
        assert selected['policy_input'] == combined[2]
    assert configured['exclude']['test_population']['edges'] == 4
    assert configured['only']['test_population']['edges'] == 2


def test_default_results_are_unchanged_and_new_rows_require_review(combined):
    root, entry, policy = combined
    ordinary = gate.measure(entry, root, policy=policy)
    crossed = measure(combined, configured=True)
    legacy = copy.deepcopy(crossed)
    for dimension in ('tests', 'configured_tests'):
        del legacy[dimension]['exclude']['lazy']
    assert legacy == ordinary
    failures = gate.regressions({'py': crossed}, {'py': ordinary})
    assert len(failures) == 4 and all('baseline missing; review required' in f for f in failures)
    missing = gate.regressions({'py': ordinary}, {'py': crossed})
    assert len(missing) == 4 and all('measurement missing' in f for f in missing)


def test_ignored_combined_filter_is_seen_while_existing_rows_stay_healthy(combined, monkeypatch):
    baseline = measure(combined, configured=True)
    real = gate.rendered_reverse_graph
    def ignored(scan, cap, lazy='include', tests='include', *, policy=None):
        if tests == 'exclude' and lazy == 'only':
            result = real(scan, cap, lazy, tests='include', policy=policy)
            # The strongest negative control: a producer claims to have applied the filter.
            result['edge_rule']['tests'] = 'importers_not_counted'
            return result
        return real(scan, cap, lazy, tests, policy=policy)
    monkeypatch.setattr(gate, 'rendered_reverse_graph', ignored)
    broken = measure(combined, configured=True)
    for field in ('oracle_edges', 'hit_edges', 'extra_edges', 'lazy'):
        assert broken[field] == baseline[field]
    for dimension in ('tests', 'configured_tests'):
        now, before = copy.deepcopy(broken[dimension]), copy.deepcopy(baseline[dimension])
        del now['exclude']['lazy']
        del before['exclude']['lazy']
        assert now == before
    assert modes(broken, True)['only']['extra_edges'] == 2
    assert any('lazy=only extra-edge population changed' in f
               for f in gate.regressions({'py': broken}, {'py': baseline}))


@pytest.mark.parametrize('configured', [False, True])
def test_crossed_empty_truth_is_unavailable_and_still_scores_extras(combined, monkeypatch, configured):
    root, entry, policy = combined
    entry['recall']['importer_dirs'] = ['tests']
    baseline = measure(combined, configured=configured)
    for row in modes(baseline, configured).values():
        assert row['oracle_edges'] == row['hit_edges'] == row['extra_edges'] == 0
        assert row['recall'] is row['precision'] is None
    real = gate.rendered_reverse_graph
    def ignored(scan, cap, lazy='include', tests='include', *, policy=None):
        result = real(scan, cap, lazy, tests, policy=policy)
        if tests == 'exclude' and lazy == 'only':
            result['by_target'][root / 'pkg/only_tests.py'] = {root / 'tests/local.py'}
        return result
    monkeypatch.setattr(gate, 'rendered_reverse_graph', ignored)
    broken = measure(combined, configured=configured)
    row = modes(broken, configured)['only']
    assert row['recall'] is None and row['precision'] == 0
    assert row['differences'] == [{'target': 'pkg/only_tests.py', 'missed': [], 'extra': ['tests/local.py']}]
    assert gate.regressions({'py': broken}, {'py': baseline})


@pytest.mark.parametrize('configured', [False, True])
def test_crossed_policy_and_loss_identity_cannot_disappear(combined, configured):
    baseline = measure(combined, configured=configured)
    broken = copy.deepcopy(baseline)
    del modes(broken, configured)['only']['edge_rule']['test_scope']
    assert any('policy identity' in f for f in gate.regressions({'py': broken}, {'py': baseline}))
    broken = copy.deepcopy(baseline)
    modes(broken, configured)['only']['partial_files'] += 1
    assert any('partial_files rose' in f for f in gate.regressions({'py': broken}, {'py': baseline}))
    if configured:
        broken = copy.deepcopy(baseline)
        del modes(broken, True)['only']['policy_input']
        assert gate.regressions({'py': broken}, {'py': baseline})


def test_combined_request_without_independent_labels_declines(combined):
    root, entry, _ = combined
    del entry['recall']['test_importer_dirs']
    with pytest.raises(RuntimeError, match='requires.*test.*labels'):
        gate.measure(entry, root, test_lazy=True)


@pytest.mark.parametrize('arguments', [[], ['--signal', 'calls'], ['--write-baseline']])
def test_combined_cli_option_is_explicit_and_cannot_rebaseline(tmp_path, arguments):
    if not arguments:
        pytest.skip('positive CLI scenario is qualified with the pinned corpus')
    with pytest.raises(SystemExit) as error:
        gate.main(['--corpus-root', str(tmp_path), '--output', str(tmp_path / 'report.json'),
                   '--test-lazy', *arguments])
    assert error.value.code == 2
