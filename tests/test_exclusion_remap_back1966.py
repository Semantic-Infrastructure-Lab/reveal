"""Logical policy paths never redirect physical reads or gitignore."""
from pathlib import Path

import pytest

from reveal.config import RevealConfig
from reveal.utils import exclusions as scope
from reveal.utils.gitignore import gitignore_scope
from reveal.utils.path_utils import ANALYSIS, walk_tree

pytestmark = pytest.mark.component


@pytest.mark.parametrize('relation,pattern', [('same', 'skip.py'), ('ancestor', 'src/skip.py'),
                                              ('descendant', 'skip.py'), ('disjoint', 'skip.py')])
def test_policy_alias_preserves_scope_relationships_and_consultation(tmp_path, relation, pattern):
    source, physical = tmp_path/'source'/'src', tmp_path/'physical'
    source.mkdir(parents=True)
    physical.mkdir()
    active = {'same': source, 'ancestor': source.parent,
              'descendant': source/'pkg', 'disjoint': tmp_path/'elsewhere'}[relation]
    with scope.exclusion_scope(active, [pattern]):
        with scope.remapped_exclusion_scope(source, physical):
            matcher = scope.scope_matcher(physical)
            rel = 'pkg/skip.py' if relation == 'descendant' else 'skip.py'
            expected = relation != 'disjoint'
            assert matcher(rel, False) is expected
            assert scope.path_is_excluded(physical/rel) is expected
            assert scope.exclusions_consulted()
        assert scope.policy_path(physical/'skip.py') == (physical/'skip.py').resolve()


def test_nested_policy_alias_restores_after_exception_and_keeps_patterns(tmp_path):
    source, first, second = (tmp_path/name for name in ('source', 'first', 'second'))
    for path in (source, first, second):
        path.mkdir()
    with scope.exclusion_scope(source, ['*.py', '!keep.py']):
        before = scope.active_exclusions()
        with scope.remapped_exclusion_scope(source, first):
            assert scope.policy_path(first/'x.py') == source/'x.py'
            with pytest.raises(OSError):
                with scope.remapped_exclusion_scope(first, second):
                    assert scope.path_is_excluded(second/'x.py')
                    assert not scope.path_is_excluded(second/'keep.py')
                    raise OSError('injected nested failure')
            assert scope.policy_path(first/'x.py') == source/'x.py'
            assert scope.policy_path(second/'x.py') == second/'x.py'
        assert scope.active_exclusions() == before


def test_live_config_policy_maps_to_physical_walk_without_changing_reads(tmp_path):
    source, physical = tmp_path/'source', tmp_path/'physical'
    (source/'src').mkdir(parents=True)
    physical.mkdir()
    (source/'.reveal.yaml').write_text('root: true\nignore:\n  - src/skip.py\n', encoding='utf-8')
    (physical/'skip.py').write_text('PHYSICAL = True\n', encoding='utf-8')
    (physical/'keep.py').write_text('PHYSICAL = True\n', encoding='utf-8')
    with scope.remapped_exclusion_scope(source/'src', physical), gitignore_scope(False):
        files = [name for _, _, names in walk_tree(physical, ANALYSIS) for name in names]
        assert files == ['keep.py']
        assert (physical/'keep.py').read_text(encoding='utf-8') == 'PHYSICAL = True\n'
    assert set(name for _, _, names in walk_tree(physical, ANALYSIS) for name in names) == {'skip.py', 'keep.py'}


def test_mapping_is_not_applied_to_gitignore(tmp_path):
    source, physical = tmp_path/'source', tmp_path/'physical'
    source.mkdir()
    physical.mkdir()
    (source/'.gitignore').write_text('keep.py\n', encoding='utf-8')
    (physical/'keep.py').write_text('PHYSICAL = True\n', encoding='utf-8')
    with scope.remapped_exclusion_scope(source, physical), gitignore_scope(True):
        assert 'keep.py' in [name for _, _, names in walk_tree(physical, ANALYSIS) for name in names]
