"""BACK-1223: walkers over the user's target go through path_utils._walk_code_files.

A walker with its own os.walk applies whichever skip rules it copied. diff://'s directory
walk copied .gitignore and the skip-dir list but not REVEAL_IGNORE or --exclude; stats://
and ast:// copied their own sets. Each now filters the shared walk, so each honors every
rule. The boundary ratchet (scripts/check_boundaries.py, rule 'walker') keeps new copies out.
"""
from pathlib import Path

import pytest

from reveal.config import RevealConfig
from reveal.utils.exclusions import exclusion_scope


@pytest.fixture
def tree(tmp_path, monkeypatch):
    for rel in ('keep/a.py', 'skipme/b.py', 'build/lib/c.py'):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text('def f():\n    return 1\n', encoding='utf-8')
    monkeypatch.setattr(RevealConfig, '_cache', {})
    return tmp_path


def _names(files, root):
    return sorted(p.relative_to(root).as_posix() for p in files)


def _walkers():
    from reveal.adapters.ast.analysis import collect_structures
    from reveal.adapters.diff.resolution import find_analyzable_files as diff_walk
    from reveal.adapters.stats.analysis import find_analyzable_files as stats_walk

    def ast_walk(root):
        return sorted({Path(s['file']) if Path(s['file']).is_absolute() else root / s['file']
                       for s in collect_structures(str(root))})
    return {'ast': ast_walk, 'diff': diff_walk, 'stats': stats_walk}


@pytest.mark.parametrize('name', ['ast', 'diff', 'stats'])
def test_reveal_ignore_applies(tree, monkeypatch, name):
    monkeypatch.setenv('REVEAL_IGNORE', 'skipme/**')
    assert _names(_walkers()[name](tree), tree) == ['keep/a.py']


@pytest.mark.parametrize('name', ['ast', 'diff', 'stats'])
def test_the_active_exclude_scope_applies(tree, name):
    with exclusion_scope(tree, ['skipme/*']):
        assert _names(_walkers()[name](tree), tree) == ['keep/a.py']


@pytest.mark.parametrize('name', ['ast', 'diff', 'stats'])
def test_code_noise_dirs_are_pruned(tree, name):
    """build/ with no source at its top level is build output (BACK-552), for each."""
    assert _names(_walkers()[name](tree), tree) == ['keep/a.py', 'skipme/b.py']
