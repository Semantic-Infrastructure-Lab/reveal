"""The base snapshot must see the same import-resolution inputs as the live tree (BACK-2436).

Go resolves local imports through go.mod, which has no analyzer, and the module
root may sit above the compared directory. A comment-only edit must give zero deltas.
"""
import pytest

pygit2 = pytest.importorskip('pygit2')

from reveal.diff import architecture_diff as diff  # noqa: E402

pytestmark = pytest.mark.component

FILES = {
    'go.mod': 'module example.com/m\n\ngo 1.21\n',
    'pkg/a/a.go': 'package a\n\nimport "example.com/m/pkg/b"\n\nfunc A() int { return b.B() }\n',
    'pkg/b/b.go': 'package b\n\nfunc B() int { return 1 }\n',
    'pkg/c/c.go': 'package c\n\nimport "example.com/m/pkg/b"\n\nfunc C() int { return b.B() }\n',
}


@pytest.fixture
def go_repo(tmp_path):
    repo = pygit2.init_repository(str(tmp_path))
    for rel, text in FILES.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
        repo.index.add(rel)
    repo.index.write()
    sig = pygit2.Signature('fixture', 'fixture@example.invalid')
    ref = str(repo.create_commit('HEAD', sig, sig, 'fixture', repo.index.write_tree(), []))
    (tmp_path / 'pkg/a/a.go').write_text('// comment only\n' + FILES['pkg/a/a.go'], encoding='utf-8')
    return tmp_path, ref


@pytest.mark.parametrize('scope', ['.', 'pkg', 'pkg/a'])
def test_comment_only_edit_has_zero_deltas_when_go_mod_is_at_or_above_scope(go_repo, scope):
    root, ref = go_repo
    result = diff.run_architecture_diff(root / scope, ref)
    deltas = result['deltas']
    assert deltas['fan_in'] == [] and deltas['fan_out'] == []
    assert deltas['entry_points'] == {'added': [], 'removed': []}
    assert deltas['circular_groups'] == {'introduced': [], 'resolved': []}


def test_materialized_base_keeps_scope_relative_paths(go_repo):
    root, ref = go_repo
    repo = diff._open_repo(root)
    with diff.materialize_ref(repo, ref, 'pkg') as tmp_root:
        assert (tmp_root / 'a' / 'a.go').exists()
        assert (tmp_root.parent / 'go.mod').exists()


def test_materialized_base_is_addressed_by_its_resolved_path(go_repo):
    """macOS reaches its temp dir through a /var -> /private/var symlink and Windows can spell it with
    8.3 short names; the resolvers work with resolved paths, so the base must be addressed by its
    resolved path or it resolves nothing (the macOS and Windows CI shards failed on this)."""
    root, ref = go_repo
    repo = diff._open_repo(root)
    with diff.materialize_ref(repo, ref, 'pkg') as tmp_root:
        assert tmp_root == tmp_root.resolve()


@pytest.mark.parametrize('scope', ['.', 'pkg'])
def test_symlinked_temp_dir_gives_the_same_zero_deltas(go_repo, tmp_path_factory, monkeypatch, scope):
    import tempfile
    real = tmp_path_factory.mktemp('real_tmp')
    link = tmp_path_factory.getbasetemp() / 'linked_tmp'
    try:
        link.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('symlinks are not available here')
    monkeypatch.setattr(tempfile, 'tempdir', str(link))
    root, ref = go_repo
    deltas = diff.run_architecture_diff(root / scope, ref)['deltas']
    assert deltas['fan_in'] == [] and deltas['fan_out'] == []
