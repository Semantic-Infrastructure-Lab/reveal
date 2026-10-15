"""BACK-1691: overview's git-root lookup must not read a refused repo as "not in a repo".

``_resolve_git_root`` returned None for any ValueError, and GitAdapter raises ValueError
for a repository it cannot open (a libgit2 ``safe.directory`` / ownership refusal:
"Failed to open repository: ... not owned by current user ..."). The git-root-mismatch
warning was then skipped with nothing said. Only "not a repository"
(NotApplicableError) is a genuine None.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reveal.adapters.git import GitAdapter
from reveal.adapters.overview import OverviewAdapter, _resolve_git_root
from reveal.errors import NotApplicableError

REFUSAL = ("Failed to open repository: /srv/repo: repository path '/srv/repo/.git/' is not "
           "owned by current user\nThe repository belongs to another user. Mark it trusted "
           "with: git config --global --add safe.directory /srv/repo")
COMMITS = [{'hash': 'abc1234', 'message': 'x', 'author': 'a', 'date': '2026-01-01'}]


def _overview(tmp: str, metadata_effect) -> dict:
    """Overview of *tmp* with a non-empty git log and ``get_metadata`` misbehaving."""
    with patch('reveal.adapters.overview._run_git_log', return_value=list(COMMITS)), \
            patch.object(GitAdapter, 'get_metadata', **metadata_effect):
        return OverviewAdapter(tmp, 'no_imports=true').get_structure()


def _errors(result: dict) -> list:
    return (result.get('meta') or {}).get('errors') or []


class TestResolveGitRootDisclosure(unittest.TestCase):

    def test_open_refusal_is_disclosed_not_read_as_no_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _overview(tmp, {'side_effect': ValueError(REFUSAL)})
        messages = ' '.join(e['message'] for e in _errors(result))
        self.assertIn('safe.directory', messages)
        self.assertIn('not owned by current user', messages)
        self.assertLess(result['meta']['confidence'], 1.0)

    # Negative controls: a genuine "not a repository" stays a silent None.
    def test_not_a_repository_still_none_without_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _overview(tmp, {'side_effect': NotApplicableError('Not a git repository: x')})
        self.assertEqual(_errors(result), [])
        self.assertIsNone(result['git_foreign_root'])

    def test_metadata_without_path_still_none_without_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _overview(tmp, {'return_value': {'type': 'git_repository'}})
        self.assertEqual(_errors(result), [])
        self.assertIsNone(result['git_foreign_root'])

    def test_real_non_repo_directory_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            # A tmp dir may sit inside some enclosing repo on a dev box; only assert
            # that the call returns a Path-or-None without raising.
            root = _resolve_git_root(Path(tmp))
        self.assertTrue(root is None or isinstance(root, Path))


if __name__ == '__main__':
    unittest.main()
