"""BACK-1575: the walk seam -- purposes, on_hidden, sort, list_dir.

Every walker moves onto one predicate (``walk_filter``); a walk's purpose decides which skip
causes apply (internal-docs/design/WALKER_SEAM_2026-09-30.md).
"""
import pytest

from reveal.utils.exclusions import exclusion_scope
from reveal.utils.path_utils import (
    ANALYSIS, DOCS, EVIDENCE, WalkPurpose, _walk_code_files, list_dir, walk_filter, walk_tree,
)


@pytest.fixture
def tree(tmp_path):
    for rel in ('keep/a.py', 'tests/t.py', '.venv/lib/v.py', '.hg/h.py', '.github/c.py',
                'build/README.md', 'z/b.py', 'm/a.py'):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text('x = 1\n', encoding='utf-8')
    return tmp_path


def _rel(root, paths):
    return sorted(p.relative_to(root).as_posix() for p in paths)


def test_analysis_keeps_dot_dirs_and_prunes_noise(tree):
    # build/ holds no code at its top level, so it is build output (BACK-552).
    assert _rel(tree, _walk_code_files(tree, respect_gitignore=False)) == [
        '.github/c.py', 'keep/a.py', 'm/a.py', 'tests/t.py', 'z/b.py']


def test_hg_is_noise(tree):
    """VCS internals are noise like .git, not source to analyze or search."""
    assert '.hg/h.py' not in _rel(tree, _walk_code_files(tree, respect_gitignore=False))


def test_evidence_ignores_exclude_explicit_and_active_scope(tree):
    """Narrowing the report must not shrink the evidence that judges it (BACK-1259)."""
    explicit = _rel(tree, _walk_code_files(tree, ['tests'], False, purpose=EVIDENCE))
    with exclusion_scope(tree, ['tests']):
        scoped = _rel(tree, _walk_code_files(tree, respect_gitignore=False, purpose=EVIDENCE))
        analysis = _rel(tree, _walk_code_files(tree, respect_gitignore=False))
    assert 'tests/t.py' in explicit and 'tests/t.py' in scoped
    assert 'tests/t.py' not in analysis  # positive control: the scope is live


def test_docs_purpose_keeps_build_and_prunes_reserved_noise(tree):
    assert 'build/README.md' in _rel(tree, _walk_code_files(tree, respect_gitignore=False,
                                                            prune_noise=False))
    docs = _rel(tree, _walk_code_files(tree, respect_gitignore=False, purpose=DOCS))
    assert 'build/README.md' in docs
    assert not any(p.startswith(('.venv/', '.hg/')) for p in docs)


def test_on_hidden_reports_each_pruned_dir_once_with_its_cause(tree):
    seen = []
    list(_walk_code_files(tree, ['keep'], False,
                          on_hidden=lambda p, is_dir, cause: seen.append(
                              (p.relative_to(tree).as_posix(), is_dir, cause))))
    assert ('.venv', True, 'noise') in seen
    assert ('keep', True, 'exclude') in seen
    assert not any(path.startswith(('.venv/', 'keep/')) for path, _, _ in seen)


def test_sort_orders_dirs_and_files(tree):
    order = [p.relative_to(tree).as_posix()
             for p in _walk_code_files(tree, respect_gitignore=False, sort=True)]
    assert order == ['.github/c.py', 'keep/a.py', 'm/a.py', 'tests/t.py', 'z/b.py']


def test_walk_tree_dirs_stay_prunable(tree):
    seen = []
    for root, dirs, files in walk_tree(tree, ANALYSIS, respect_gitignore=False, sort=True):
        dirs[:] = [d for d in dirs if d != 'z']
        seen.extend(_rel(tree, [root / f for f in files]))
    assert 'z/b.py' not in seen and 'm/a.py' in seen


def test_hide_dot_purpose_names_the_cause(tree):
    display = WalkPurpose('display', hide_dot=True)
    hidden = walk_filter(tree, display, respect_gitignore=False)
    assert hidden(tree / '.github', True) == 'dot'
    assert hidden(tree / '.venv', True) == 'noise'  # noise wins, so the footer says why


def test_list_dir_filters_one_level(tree):
    causes = []
    kept = list_dir(tree, walk_filter(tree, ANALYSIS, respect_gitignore=False),
                    lambda p, is_dir, cause: causes.append((p.name, cause)))
    assert sorted(p.name for p, _ in kept) == ['.github', 'keep', 'm', 'tests', 'z']
    assert all(is_dir for _, is_dir in kept)
    assert sorted(causes) == [('.hg', 'noise'), ('.venv', 'noise'), ('build', 'noise')]


def test_list_dir_unreadable_is_none(tmp_path):
    assert list_dir(tmp_path / 'missing', walk_filter(tmp_path)) is None


def test_a_file_target_is_yielded_as_is(tree):
    assert list(_walk_code_files(tree / 'keep/a.py')) == [tree / 'keep/a.py']


def test_evidence_still_honors_reveal_ignore(tree, monkeypatch):
    """REVEAL_IGNORE declares what is not part of the project; --exclude narrows a view."""
    from reveal.config import RevealConfig
    monkeypatch.setenv('REVEAL_IGNORE', 'tests/**')
    monkeypatch.setattr(RevealConfig, '_cache', {})
    assert 'tests/t.py' not in _rel(tree, _walk_code_files(tree, respect_gitignore=False,
                                                           purpose=EVIDENCE))


@pytest.mark.parametrize('marker, is_venv', [
    ('pyvenv.cfg', True), ('conda-meta/', True), ('bin/activate', True),
    ('Scripts/activate', True), ('common/source.ts', False), ('README.md', False),
])
def test_env_is_noise_only_when_it_is_a_virtualenv(tmp_path, marker, is_venv):
    """BACK-1582: an env/ whose source sits in subdirectories is a package, not a venv."""
    from reveal.utils.path_utils import is_noise_dir
    for name in ('env', 'venv'):
        target = tmp_path / name / marker
        target.parent.mkdir(parents=True, exist_ok=True)
        if marker.endswith('/'):
            target.mkdir(exist_ok=True)
        else:
            target.write_text('x\n', encoding='utf-8')
        assert is_noise_dir(tmp_path, name) is is_venv


def test_build_without_top_level_code_is_still_noise(tmp_path):
    from reveal.utils.path_utils import is_noise_dir
    (tmp_path / 'build' / 'lib').mkdir(parents=True)
    (tmp_path / 'build' / 'lib' / 'x.py').write_text('x = 1\n', encoding='utf-8')
    assert is_noise_dir(tmp_path, 'build')
    (tmp_path / 'build' / 'main.py').write_text('x = 1\n', encoding='utf-8')
    assert not is_noise_dir(tmp_path, 'build')


def test_scope_matcher_agrees_with_the_per_path_checks_and_counts_as_consulted(tree):
    """BACK-1581: a walk resolves its root once; the answers must be the per-path ones."""
    from reveal.utils import exclusions
    with exclusion_scope(tree, ['tests', 'm/*.py']):
        match = exclusions.scope_matcher(tree)
        exclusions._CONSULTED = False
        for rel, is_dir in (('tests', True), ('tests/t.py', False), ('m/a.py', False),
                            ('keep/a.py', False), ('m', True)):
            per_path = (exclusions.dir_is_excluded if is_dir
                        else exclusions.path_is_excluded)(tree / rel)
            assert match(rel, is_dir) is per_path, rel
        assert exclusions.exclusions_consulted()
    assert exclusions.scope_matcher(tree) is None  # no scope, nothing to consult


def test_ignore_matcher_agrees_with_should_ignore(tree, monkeypatch):
    from reveal.config import RevealConfig
    (tree / '.git').mkdir()
    monkeypatch.setenv('REVEAL_IGNORE', 'tests/,*.py')
    monkeypatch.setattr(RevealConfig, '_cache', {})
    config = RevealConfig.get(start_path=tree / 'keep')
    match = config.ignore_matcher(tree / 'keep')
    assert match is not None
    assert match('a.py', False) is config.should_ignore(tree / 'keep' / 'a.py') is True
    assert match('README', False) is config.should_ignore(tree / 'keep' / 'README') is False


def test_scope_matcher_from_a_walk_root_above_the_scope(tree):
    """depends:// walks from the project root while the scope is its target below it: a
    path is judged relative to the scope root, and paths outside the scope never match."""
    from reveal.utils import exclusions
    with exclusion_scope(tree / 'keep', ['a.py']):
        above = exclusions.scope_matcher(tree)
        inside = exclusions.scope_matcher(tree / 'keep')
        assert above('keep/a.py', False) and inside('a.py', False)
        assert not above('m/a.py', False)        # outside the scope
        assert not above('keep', True)           # the scope root itself
    with exclusion_scope(tree / 'keep', ['a.py']):
        assert not exclusions.scope_matcher(tree / 'z')('b.py', False)  # disjoint
