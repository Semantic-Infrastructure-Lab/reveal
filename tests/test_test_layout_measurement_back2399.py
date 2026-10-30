"""Independent recall-gate controls for reported test-layout evidence."""
import copy

import pytest

from test_recall_gate import gate, test_import_corpus, _repo  # noqa: F401


pytestmark = pytest.mark.component


def test_gate_preserves_lexical_scope_without_changing_scoring(test_import_corpus):
    root, entry = test_import_corpus
    result = gate.measure(entry, root)
    for row in (result, *result['lazy'].values(), result['tests']['exclude']):
        scope = row['edge_rule']['test_scope']
        assert scope['anchor'] == '.'
        assert scope['source'] == 'explicit_root'
        assert scope['rule'] == 'is_test_path'
        assert scope['include_anchor_name'] is False
    assert result['hit_edges'] == result['oracle_edges'] == 4
    assert result['tests']['exclude']['hit_edges'] == 2


@pytest.mark.parametrize('damage', ['missing', 'empty', 'anchor', 'rule', 'flag'])
def test_gate_rejects_lost_or_malformed_lexical_scope(test_import_corpus, monkeypatch, damage):
    root, _ = test_import_corpus
    healthy = gate._importers_request(root, root, None)
    assert healthy['count'] if 'count' in healthy else healthy['total']
    broken = copy.deepcopy(healthy)
    scope = broken['edge_rule']['test_scope']
    if damage == 'missing':
        del broken['edge_rule']['test_scope']
    elif damage == 'empty':
        broken['edge_rule']['test_scope'] = {}
    elif damage == 'anchor':
        scope['anchor'] = None
    elif damage == 'rule':
        scope['rule'] = 'unknown-rule'
    else:
        scope['include_anchor_name'] = 'false'
    monkeypatch.setattr(gate, '_cli_json', lambda *args, **kwargs: broken)
    with pytest.raises(RuntimeError, match='test_scope'):
        gate._importers_request(root, root, None)


def test_gate_retained_scope_is_not_an_alias():
    scope = {'anchor': '.', 'source': 'project', 'rule': 'is_test_path',
             'include_anchor_name': False, 'basis': 'paths relative to the selected project'}
    original = {'edge_rule': {**gate.SCORED_RULE, 'test_scope': scope}}
    recorded = gate._edge_rule(original)
    assert recorded['test_scope'] == scope
    original['edge_rule']['test_scope']['anchor'] = 'changed'
    assert recorded['test_scope']['anchor'] == '.'


def test_external_policy_input_is_bounded_and_independent(tmp_path):
    policy = tmp_path / 'policy.yaml'
    policy.write_text('test_layout:\n  additional_paths: [t/./unit, "t\\\\unit", missing.py]\n', encoding='utf-8')
    selected = gate._read_test_policy(policy)
    assert selected['additional_paths'] == ['missing.py', 't/unit']
    assert selected['path'] == policy.resolve().as_posix()
    assert len(selected['file_sha256']) == len(selected['input_digest']) == 64
    assert 'raw' not in selected


@pytest.mark.parametrize('contents', [
    'test_layout: {additional_paths: []}\nignore: [pkg]\n',
    'test_layout: {additional_paths: [../escape]}\n',
    'test_layout: {additional_paths: [/absolute]}\n',
    'test_layout: {additional_paths: ["C:/drive"]}\n',
    'test_layout: {additional_paths: [true]}\n',
    'test_layout: {additional_paths: [], other: true}\n',
    'test_layout: {}\n',
])
def test_external_policy_rejects_unrecorded_or_unsafe_inputs(tmp_path, contents):
    policy = tmp_path / 'policy.yaml'
    policy.write_text(contents, encoding='utf-8')
    with pytest.raises(ValueError, match='policy'):
        gate._read_test_policy(policy)


@pytest.mark.parametrize('ambient', [None, 'prior.yaml'])
def test_explicit_policy_context_restores_environment_and_caches(tmp_path, monkeypatch, ambient):
    import os

    if ambient is None:
        monkeypatch.delenv('REVEAL_CONFIG', raising=False)
    else:
        monkeypatch.setenv('REVEAL_CONFIG', ambient)
    resets = []
    monkeypatch.setattr(gate, 'reset_request_caches', lambda: resets.append(True))
    policy = tmp_path / 'policy.yaml'
    with pytest.raises(RuntimeError, match='injected'):
        with gate._test_policy_config(policy):
            assert os.environ['REVEAL_CONFIG'] == policy.as_posix()
            raise RuntimeError('injected')
    assert os.environ.get('REVEAL_CONFIG') == ambient
    assert resets == [True, True]


def _configured_scope(policy):
    effective = {'classifier_version': 'project-test-layout-v1', 'anchor': '.',
                 'include_anchor_name': False, 'anchor_name': None,
                 'additional_paths': policy['additional_paths']}
    return {'anchor': '.', 'source': 'explicit_root', 'include_anchor_name': False,
            'rule': 'is_test_path', 'basis': 'paths relative to the selected project',
            'classifier_version': 'project-test-layout-v1',
            'additional_paths': policy['additional_paths'], 'whole_scope': False,
            'declaration': {'layer': 'custom', 'path': policy['path'],
                            'input_digest': policy['input_digest']},
            'effective_policy': effective}


@pytest.mark.parametrize('paths', [[], ['t/unit']])
def test_expected_policy_evidence_is_checked_independently(tmp_path, paths):
    import json

    path = tmp_path / 'policy.yaml'
    path.write_text(json.dumps({'test_layout': {'additional_paths': paths}}), encoding='utf-8')
    policy = gate._read_test_policy(path)
    scope = _configured_scope(policy)
    gate._validate_test_policy(scope, policy)
    for field in ('additional_paths', 'effective_policy', 'declaration', 'classifier_version'):
        damaged = copy.deepcopy(scope)
        del damaged[field]
        with pytest.raises(RuntimeError, match='policy'):
            gate._validate_test_policy(damaged, policy)
    for selector in ('changed',):
        damaged = copy.deepcopy(scope)
        damaged['additional_paths'] = [selector]
        with pytest.raises(RuntimeError, match='policy'):
            gate._validate_test_policy(damaged, policy)
    for container, field, value in [('declaration', 'input_digest', '0' * 64),
                                     ('effective_policy', 'anchor', '../wrong'),
                                     ('effective_policy', 'additional_paths', ['changed'])]:
        damaged = copy.deepcopy(scope)
        damaged[container][field] = value
        with pytest.raises(RuntimeError, match='policy'):
            gate._validate_test_policy(damaged, policy)


def test_policy_provenance_does_not_split_comparison_identity(tmp_path):
    path = tmp_path / 'policy.yaml'
    path.write_text('test_layout: {additional_paths: [t/unit]}\n', encoding='utf-8')
    policy = gate._read_test_policy(path)
    original = _configured_scope(policy)
    moved = copy.deepcopy(original)
    moved['declaration']['path'] = 'elsewhere/policy.yaml'
    assert gate._test_policy_identity(original) == gate._test_policy_identity(moved)
    moved['declaration']['input_digest'] = '0' * 64
    assert gate._test_policy_identity(original) != gate._test_policy_identity(moved)


@pytest.mark.parametrize('extra', [['--write-baseline'], ['--signal', 'calls']])
def test_configured_gate_cannot_overwrite_baseline_or_claim_calls(tmp_path, extra):
    with pytest.raises(SystemExit) as error:
        gate.main(['--corpus-root', str(tmp_path), '--output', str(tmp_path / 'report.json'),
                   '--test-policy', 'py=policy.yaml', *extra])
    assert error.value.code == 2


def test_configured_comparison_fails_missing_or_changed_policy_even_with_healthy_default(test_import_corpus, tmp_path):
    root, entry = test_import_corpus
    ordinary = gate.measure(entry, root)
    path = tmp_path / 'policy.yaml'
    path.write_text('test_layout: {additional_paths: [t/unit]}\n', encoding='utf-8')
    policy = gate._read_test_policy(path)
    configured = copy.deepcopy(ordinary['tests']['exclude'])
    configured['edge_rule']['test_scope'] = _configured_scope(policy)
    configured['policy_input'] = policy
    baseline = {**ordinary, 'configured_tests': {'exclude': configured}}
    assert gate.regressions({'py': baseline}, {'py': baseline}) == []
    for damage in ('missing', 'digest', 'selectors', 'input'):
        broken = copy.deepcopy(baseline)
        if damage == 'missing':
            del broken['configured_tests']
        elif damage == 'input':
            del broken['configured_tests']['exclude']['policy_input']
        elif damage == 'digest':
            broken['configured_tests']['exclude']['edge_rule']['test_scope']['declaration']['input_digest'] = '0' * 64
        else:
            broken['configured_tests']['exclude']['edge_rule']['test_scope']['effective_policy']['additional_paths'] = []
        assert gate.regressions({'py': broken}, {'py': baseline})
        assert broken['hit_edges'] == ordinary['hit_edges']


def test_lexical_policy_is_comparison_identity_with_legacy_baseline_disclosure(test_import_corpus):
    root, entry = test_import_corpus
    baseline = gate.measure(entry, root)
    changed = copy.deepcopy(baseline)
    changed['edge_rule']['test_scope']['anchor'] = '..'
    assert any('policy identity' in failure
               for failure in gate.regressions({'py': changed}, {'py': baseline}))
    legacy = copy.deepcopy(baseline)
    for row in (legacy, *legacy['lazy'].values(), legacy['tests']['exclude']):
        del row['edge_rule']['test_scope']
    notes = []
    assert gate.regressions({'py': baseline}, {'py': legacy}, notes) == []
    assert any('test_scope not compared' in note for note in notes)


@pytest.fixture
def nonstandard_corpus(tmp_path):
    root, entry = _repo(tmp_path / 'corpus', {
        'pyproject.toml': '[project]\nname = "pkg"\n',
        'pkg/__init__.py': '', 'pkg/a.py': '', 'pkg/only_helpers.py': '',
        'pkg/use.py': 'import pkg.a\nimport t.unit.helper\n',
        't/__init__.py': '', 't/unit/__init__.py': '',
        't/unit/helper.py': 'import pkg.a\nimport pkg.only_helpers\n',
        't/unitized/__init__.py': '', 't/unitized/prod.py': 'import pkg.a\n',
    }, {'oracle': 'python-ast', 'importer_dirs': ['.'], 'test_importer_dirs': ['t/unit']})
    path = tmp_path / 'policy.yaml'
    path.write_text('test_layout: {additional_paths: [t/unit]}\n', encoding='utf-8')
    policy = gate._read_test_policy(path)
    return root, entry, path, policy


def test_public_configured_row_removes_only_reviewed_importers(nonstandard_corpus):
    root, entry, _, policy = nonstandard_corpus
    measured = gate.measure(entry, root, policy=policy)
    assert measured['hit_edges'] == measured['oracle_edges'] == 5
    assert measured['extra_edges'] == 0
    assert measured['tests']['exclude']['hit_edges'] == 3
    assert measured['tests']['exclude']['extra_edges'] == 2
    configured = measured['configured_tests']['exclude']
    assert configured['hit_edges'] == configured['oracle_edges'] == 3
    assert configured['extra_edges'] == 0
    assert configured['targets'] == 2
    assert configured['policy_input'] == policy
    assert measured['lazy']['only']['oracle_edges'] == 0
    assert measured['lazy']['only']['recall'] is None


def test_ignored_configured_filter_cannot_hide_behind_healthy_default(nonstandard_corpus, monkeypatch):
    from reveal.analyzers.imports.types import ImportGraph

    root, entry, _, policy = nonstandard_corpus
    baseline = gate.measure(entry, root, policy=policy)
    monkeypatch.setattr(ImportGraph, 'without_test_importers', lambda self, layout: self)
    broken = gate.measure(entry, root, policy=policy)
    assert broken['hit_edges'] == baseline['hit_edges'] == 5
    assert broken['tests'] == baseline['tests']
    assert broken['lazy'] == baseline['lazy']
    configured = broken['configured_tests']['exclude']
    assert configured['differences'] == [
        {'target': 'pkg/a.py', 'missed': [], 'extra': ['t/unit/helper.py']},
        {'target': 'pkg/only_helpers.py', 'missed': [], 'extra': ['t/unit/helper.py']},
    ]
    failures = gate.regressions({'py': broken}, {'py': baseline})
    assert any('configured_tests=exclude extra-edge population changed' in item for item in failures)


def test_configured_empty_truth_keeps_unavailable_recall_and_extra_controls(nonstandard_corpus, monkeypatch):
    from reveal.analyzers.imports.types import ImportGraph

    root, entry, _, policy = nonstandard_corpus
    entry['recall']['importer_dirs'] = ['t/unit']
    baseline = gate.measure(entry, root, policy=policy)
    row = baseline['configured_tests']['exclude']
    assert row['oracle_edges'] == row['hit_edges'] == row['extra_edges'] == 0
    assert row['recall'] is row['precision'] is None
    monkeypatch.setattr(ImportGraph, 'without_test_importers', lambda self, layout: self)
    broken = gate.measure(entry, root, policy=policy)['configured_tests']['exclude']
    assert broken['oracle_edges'] == 0 and broken['recall'] is None
    assert broken['extra_edges'] == 2 and broken['precision'] == 0


def test_same_graph_two_inputs_and_equal_recipe_new_provenance(nonstandard_corpus, tmp_path):
    root, entry, path, policy = nonstandard_corpus
    baseline = gate.measure(entry, root, policy=policy)
    other_path = tmp_path / 'other.yaml'
    other_path.write_text('test_layout:\n  additional_paths: [t/unit]\n', encoding='utf-8')
    other = gate.measure(entry, root, policy=gate._read_test_policy(other_path))
    before = baseline['configured_tests']['exclude']['edge_rule']['test_scope']
    moved = other['configured_tests']['exclude']['edge_rule']['test_scope']
    assert before['declaration']['path'] != moved['declaration']['path']
    assert gate._test_policy_identity(before) == gate._test_policy_identity(moved)
    assert gate.regressions({'py': other}, {'py': baseline}) == []
    path.write_text('test_layout: {additional_paths: []}\n', encoding='utf-8')
    changed = gate.measure(entry, root, policy=gate._read_test_policy(path))
    assert changed['hit_edges'] == baseline['hit_edges'] == 5
    assert changed['configured_tests']['exclude']['extra_edges'] == 2
    assert baseline['configured_tests']['exclude']['extra_edges'] == 0
    assert before['additional_paths'] == ['t/unit']
    assert gate.regressions({'py': changed}, {'py': baseline})


@pytest.mark.parametrize('configured', [False, True])
@pytest.mark.parametrize('field,value', [('anchor', '..'), ('anchor', '/temporary/export'),
                                          ('source', 'project'), ('include_anchor_name', True)])
def test_request_boundary_is_independent_of_producer_metadata(test_import_corpus, tmp_path, monkeypatch,
                                                              configured, field, value):
    root, _ = test_import_corpus
    healthy = gate._importers_request(root, root, None)
    path = tmp_path / 'policy.yaml'
    path.write_text('test_layout: {additional_paths: []}\n', encoding='utf-8')
    policy = gate._read_test_policy(path) if configured else None
    broken = copy.deepcopy(healthy)
    scope = _configured_scope(policy) if policy else broken['edge_rule']['test_scope']
    scope[field] = value
    if configured and field in ('anchor', 'include_anchor_name'):
        scope['effective_policy'][field] = value
        if field == 'include_anchor_name':
            scope['effective_policy']['anchor_name'] = root.name
    broken['edge_rule']['test_scope'] = scope
    monkeypatch.setattr(gate, '_cli_json', lambda *args, **kwargs: broken)
    with pytest.raises(RuntimeError, match='test_scope|policy'):
        gate._importers_request(root, root, None, policy=policy)


def test_cli_records_separate_configured_candidate_without_rebaselining(nonstandard_corpus, tmp_path, monkeypatch):
    import json

    root, entry, path, _ = nonstandard_corpus
    ordinary = gate.measure(entry, root)
    baseline_path = tmp_path / 'baseline.json'
    baseline_bytes = json.dumps({'corpus': ordinary}).encode('utf-8')
    baseline_path.write_bytes(baseline_bytes)
    manifest = tmp_path / 'manifest.yaml'
    manifest.write_text(json.dumps({'corpora': [{'id': 'corpus', 'language': 'python', **entry}]}), encoding='utf-8')
    monkeypatch.setattr(gate, 'MANIFEST', manifest)
    output = tmp_path / 'report.json'
    code = gate.main(['--corpus-root', str(root.parent), '--output', str(output),
                      '--baseline', str(baseline_path), '--corpus', 'corpus',
                      '--test-policy', f'corpus={path}'])
    assert code == 1  # A new configured row requires review; ordinary baseline is never rewritten.
    report = json.loads(output.read_text(encoding='utf-8'))
    measured = report['measurements']['corpus']
    assert measured['tests'] == ordinary['tests']
    assert measured['lazy'] == ordinary['lazy']
    assert measured['configured_tests']['exclude']['extra_edges'] == 0
    assert report['failures'] == ['corpus: configured_tests=exclude baseline missing; review required']
    assert baseline_path.read_bytes() == baseline_bytes
    assert report['implementation']['head']


def test_public_configured_policy_sorts_deduplicates_and_keeps_missing_selectors(nonstandard_corpus):
    root, entry, path, _ = nonstandard_corpus
    path.write_text('test_layout: {additional_paths: [t/unit, missing.py, t/./unit]}\n', encoding='utf-8')
    policy = gate._read_test_policy(path)
    assert policy['additional_paths'] == ['missing.py', 't/unit']
    row = gate.measure(entry, root, policy=policy)['configured_tests']['exclude']
    scope = row['edge_rule']['test_scope']
    assert scope['additional_paths'] == ['missing.py', 't/unit']
    assert row['oracle_edges'] == row['hit_edges'] == 3
    assert row['extra_edges'] == 0


@pytest.mark.parametrize('damage', ['files_failed_count', 'files_lost_count'])
def test_configured_policy_does_not_mask_missing_loss_diagnostics(nonstandard_corpus, monkeypatch, damage):
    root, _, path, policy = nonstandard_corpus
    with gate._test_policy_config(path):
        healthy = gate._importers_request(root, root, None, tests='exclude', policy=policy)
    broken = copy.deepcopy(healthy)
    del broken['metadata'][damage]
    monkeypatch.setattr(gate, '_cli_json', lambda *args, **kwargs: broken)
    with pytest.raises(RuntimeError, match='files_failed_count/files_lost_count'):
        gate.rendered_reverse_graph(root, None, tests='exclude', policy=policy)


def test_conventional_rows_accept_valid_empty_declaration(nonstandard_corpus):
    root, entry, path, _ = nonstandard_corpus
    path.write_text('test_layout: {additional_paths: []}\n', encoding='utf-8')
    with gate._test_policy_config(path):
        measured = gate.measure(entry, root)
    assert measured['hit_edges'] == 5
    assert measured['tests']['exclude']['extra_edges'] == 2
    assert measured['edge_rule']['test_scope']['additional_paths'] == []


@pytest.mark.parametrize('damage', ['version', 'declaration', 'boolean'])
def test_conventional_rows_reject_unknown_empty_policy_evidence(nonstandard_corpus, monkeypatch, damage):
    root, _, path, _ = nonstandard_corpus
    path.write_text('test_layout: {additional_paths: []}\n', encoding='utf-8')
    with gate._test_policy_config(path):
        healthy = gate._importers_request(root, root, None)
    broken = copy.deepcopy(healthy)
    scope = broken['edge_rule']['test_scope']
    if damage == 'version':
        scope['classifier_version'] = 'unrecognized'
        scope['effective_policy']['classifier_version'] = 'unrecognized'
    elif damage == 'boolean':
        scope['effective_policy']['include_anchor_name'] = 0
    else:
        del scope['declaration']
    monkeypatch.setattr(gate, '_cli_json', lambda *args, **kwargs: broken)
    with pytest.raises(RuntimeError, match='policy'):
        gate._importers_request(root, root, None)
