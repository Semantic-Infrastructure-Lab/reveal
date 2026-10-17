"""Architecture comparisons require symmetric scope and complete snapshots."""
import json
from unittest.mock import patch

import pytest

pygit2 = pytest.importorskip('pygit2')

from reveal.adapters.ast import AstAdapter  # noqa: E402
from reveal.adapters.imports import ImportsAdapter  # noqa: E402
from reveal.diff import architecture_diff as diff  # noqa: E402
from reveal.utils.exclusions import exclusion_scope  # noqa: E402
from reveal.utils.gitignore import gitignore_scope  # noqa: E402

pytestmark = pytest.mark.component


@pytest.fixture
def tree(tmp_path):
    repo = pygit2.init_repository(str(tmp_path))
    src = tmp_path/'src'
    src.mkdir()
    for name, content in {'a.py': 'import os\n', 'b.py': 'import a\n'}.items():
        (src/name).write_text(content, encoding='utf-8')
        repo.index.add('src/'+name)
    repo.index.write()
    sig = pygit2.Signature('fixture', 'fixture@example.invalid')
    ref = str(repo.create_commit('HEAD', sig, sig, 'fixture', repo.index.write_tree(), []))
    return repo, src, ref


def _dirty(src):
    (src/'a.py').write_text('import os\n# behavior-neutral dirty tree\n', encoding='utf-8')


@pytest.mark.parametrize('relation,pattern', [('same', 'b.py'), ('ancestor', 'src/b.py'),
                                              ('descendant', '*.py'), ('disjoint', 'b.py')])
def test_dirty_but_equivalent_tree_has_no_false_scope_deltas(tree, relation, pattern):
    repo, src, ref = tree
    _dirty(src)
    active = {'same': src, 'ancestor': src.parent,
              'descendant': src/'nested', 'disjoint': src.parent/'other'}[relation]
    with exclusion_scope(active, [pattern]):
        result = diff.run_architecture_diff(src, ref)
    assert result['deltas'] == diff._empty_deltas(20)


@pytest.mark.parametrize('component', ['imports', 'complexity'])
@pytest.mark.parametrize('side', ['base', 'head'])
def test_required_component_exception_cannot_render_clean_deltas(tree, component, side, capsys):
    repo, src, ref = tree
    _dirty(src)
    owner, method = (ImportsAdapter, '_build_graph') if component == 'imports' else (AstAdapter, 'get_structure')
    original = getattr(owner, method)

    def injected(self, *args, **kwargs):
        is_head = self.path == str(src) if component == 'complexity' else args[0] == src
        if is_head == (side == 'head'):
            raise OSError('injected required '+component+' failure')
        return original(self, *args, **kwargs)

    with patch.object(owner, method, injected):
        result = diff.run_architecture_diff(src, ref)
    assert result['type'] == 'architecture_diff' and result['error']
    assert result['deltas'] is None
    assert result['analysis']['snapshots'][side][component] == 'failed'
    assert result['meta']['errors']
    assert all(e['component'] == component for e in result['meta']['errors'])
    serialized = json.dumps(result)
    assert 'reveal-archdiff-' not in serialized
    diff.render_diff_brief(result)
    text = capsys.readouterr().out
    assert 'comparison unavailable' in text.lower()
    assert 'Complexity centroid' not in text
    assert 'injected required '+component+' failure' in text


@pytest.mark.parametrize('kind', ['analysis_failed', 'parse_recovered'])
def test_explicit_ast_missing_evidence_is_incomplete(tree, kind):
    repo, src, ref = tree
    _dirty(src)
    child = {'results': [], 'meta': {'warnings': [{'type': kind, 'count': 1,
                                                  'message': 'injected missing evidence'}]}}
    with patch.object(AstAdapter, 'get_structure', return_value=child):
        result = diff.run_architecture_diff(src, ref)
    assert result['analysis']['snapshots']['base']['complexity'] == 'incomplete'
    assert result['error'] and result['deltas'] is None


def test_information_and_ranking_cuts_are_not_missing_evidence(tree):
    repo, src, ref = tree
    _dirty(src)
    child = {'results': [], 'meta': {'warnings': [
        {'type': 'complexity_is_unweighted', 'message': 'informational'},
        {'type': 'truncated', 'message': 'ranking cut', 'field': 'results',
         'shown': 2, 'total': 3, 'cause': 'limit'},
    ], 'confidence': 0.7}}
    with patch.object(AstAdapter, 'get_structure', return_value=child):
        result = diff.run_architecture_diff(src, ref)
    assert not result.get('error') and result['analysis']['complete']
    assert any(w['type'] == 'complexity_is_unweighted' for w in result['meta']['warnings'])
    assert result['meta']['confidence'] == 0.7


def test_complexity_helper_failure_is_canonical_and_visible(tree):
    from reveal.adapters import architecture

    repo, src, ref = tree
    _dirty(src)
    with patch.object(architecture, '_run_complex_functions', side_effect=OSError('injected helper I/O failure')):
        result = diff.run_architecture_diff(src, ref)
    assert result['error'] and result['deltas'] is None
    assert result['analysis']['snapshots']['base']['complexity'] == 'failed'
    assert result['meta']['errors'][0]['component'] == 'complexity'


def test_returned_complexity_error_is_a_required_failure(tree):
    repo, src, ref = tree
    _dirty(src)
    with patch.object(AstAdapter, 'get_structure', return_value={'error': 'injected returned failure'}):
        result = diff.run_architecture_diff(src, ref)
    assert result['error'] and result['deltas'] is None


@pytest.mark.parametrize('enabled', [True, False])
def test_ignored_untracked_fast_exit_respects_selected_head_policy(tree, enabled):
    repo, src, ref = tree
    (src.parent/'.gitignore').write_text('src/ignored.py\n', encoding='utf-8')
    repo.index.add('.gitignore')
    repo.index.write()
    sig = pygit2.Signature('fixture', 'fixture@example.invalid')
    ref = str(repo.create_commit('HEAD', sig, sig, 'ignore policy', repo.index.write_tree(), [repo.head.target]))
    (src/'ignored.py').write_text('import a\n', encoding='utf-8')
    with gitignore_scope(enabled):
        result = diff.run_architecture_diff(src, ref)
    assert bool(result['deltas']['fan_out']) is (not enabled)
    assert result['analysis']['basis'] == ('identical_tree' if enabled else 'snapshots')


@pytest.mark.parametrize('field', ['files_failed', 'files_lost'])
def test_importer_explicit_missing_inputs_are_incomplete(tree, field):
    repo, src, ref = tree
    _dirty(src)
    original = ImportsAdapter._build_graph

    def missing(self, root, **kwargs):
        original(self, root, **kwargs)
        getattr(self.analysis, field).append(root/'a.py')

    with patch.object(ImportsAdapter, '_build_graph', missing):
        result = diff.run_architecture_diff(src, ref)
    assert result['analysis']['snapshots']['base']['imports'] == 'incomplete'
    assert result['deltas'] is None and result['error']
    assert result['meta']['warnings']


@pytest.mark.parametrize('policy', ['config', 'environment'])
def test_live_ignore_policy_is_symmetric_for_subdirectory(tree, policy, monkeypatch):
    repo, src, ref = tree
    _dirty(src)
    if policy == 'config':
        (src.parent/'.reveal.yaml').write_text('root: true\nignore:\n  - src/b.py\n', encoding='utf-8')
    else:
        monkeypatch.setenv('REVEAL_IGNORE', 'src/b.py')
    result = diff.run_architecture_diff(src, ref)
    assert result['deltas'] == diff._empty_deltas(20)


def test_tracked_base_and_ignored_untracked_head_remain_distinct(tree):
    repo, src, ref = tree
    (src.parent/'.gitignore').write_text('src/b.py\nsrc/untracked.py\n', encoding='utf-8')
    (src/'untracked.py').write_text('import a\n', encoding='utf-8')
    result = diff.run_architecture_diff(src, ref)
    assert result['deltas'] == diff._empty_deltas(20)


def test_unsupported_language_scope_is_nonfatal(tree):
    repo, src, ref = tree
    _dirty(src)
    original = ImportsAdapter.get_metadata

    def metadata(self):
        result = original(self)
        result['unsupported_extensions'] = {'.unsupported': 1}
        return result

    with patch.object(ImportsAdapter, 'get_metadata', metadata):
        result = diff.run_architecture_diff(src, ref)
    assert result['analysis']['complete'] and not result.get('error')
