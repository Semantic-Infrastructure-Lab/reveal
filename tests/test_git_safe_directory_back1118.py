"""BACK-1118: libgit2 refuses a repo owned by another UID; git:// says how to fix it.

Ownership can't be mismatched without root, so the refusal is simulated by making
pygit2.Repository raise libgit2's own message (CVE-2022-24765 check).
"""
import json

import pytest

pygit2 = pytest.importorskip('pygit2')

from conftest import _run_reveal_direct  # noqa: E402
from reveal.adapters.git.adapter import GitAdapter  # noqa: E402

pytestmark = pytest.mark.component


@pytest.fixture
def repo_dir(tmp_path):
    repo = pygit2.init_repository(str(tmp_path))
    (tmp_path / 'a.py').write_text('x = 1\n', encoding='utf-8')
    repo.index.add('a.py')
    repo.index.write()
    sig = pygit2.Signature('t', 't@example.com')
    repo.create_commit('HEAD', sig, sig, 'init', repo.index.write_tree(), [])
    return tmp_path


@pytest.fixture
def not_owned(monkeypatch):
    def refuse(path, *args, **kwargs):
        raise pygit2.GitError(f"repository path '{path}' is not owned by current user")

    monkeypatch.setattr(pygit2, 'Repository', refuse)


def test_adapter_names_the_safe_directory_fix(repo_dir, not_owned):
    with pytest.raises(ValueError) as exc:
        GitAdapter(str(repo_dir)).get_structure()
    message = str(exc.value)
    assert 'not owned by current user' in message
    assert 'git config --global --add safe.directory' in message
    assert repo_dir.name in message


@pytest.mark.parametrize('query', ['', '?type=history'])
def test_cli_fails_with_the_fix_and_no_empty_answer(repo_dir, not_owned, query):
    proc = _run_reveal_direct(f"git://{repo_dir}{query}", '--format', 'json')
    assert proc.returncode == 1
    data = json.loads(proc.stdout)
    assert 'safe.directory' in data['error']
    assert not data.get('history') and not data.get('commits')
    assert 'safe.directory' in proc.stderr


def test_other_open_failures_keep_their_cause(repo_dir, monkeypatch):
    """Negative control: a different libgit2 failure is not mislabelled as an ownership one."""
    def corrupt(path, *args, **kwargs):
        raise pygit2.GitError('corrupt object database')

    monkeypatch.setattr(pygit2, 'Repository', corrupt)
    with pytest.raises(ValueError) as exc:
        GitAdapter(str(repo_dir)).get_structure()
    assert 'corrupt object database' in str(exc.value)
    assert 'safe.directory' not in str(exc.value)
