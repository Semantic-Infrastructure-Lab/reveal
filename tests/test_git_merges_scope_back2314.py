"""Ownership-only merges controls do not filter unrelated views (BACK-2314)."""
import json

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.git.adapter import GitAdapter
from test_git_filter_answers_back2312 import history_repo

pygit2 = pytest.importorskip('pygit2')


@pytest.mark.parametrize('target,query', [('repo', ''), ('repo', 'type=history'),
                                        ('repo', 'type=history&bucket=month'),
                                        ('file', 'type=history'),
                                        ('file', 'type=history&bucket=month')])
@pytest.mark.parametrize('entry', ['api', 'cli'])
def test_merges_is_inert_outside_ownership(history_repo, target, query, entry, capsys):
    path = history_repo / 'sample.py' if target == 'file' else history_repo
    with_merges = query + ('&' if query else '') + 'merges=1'
    if entry == 'cli':
        baseline = run(f'git://{path}?{query}', '--format', 'json')
        modified = run(f'git://{path}?{with_merges}', '--format', 'json')
        assert baseline.returncode == modified.returncode == 0
        assert json.loads(modified.stdout) == json.loads(baseline.stdout)
        warning = modified.stderr
    else:
        baseline = GitAdapter(str(path), query).get_structure()
        modified = GitAdapter(str(path), with_merges).get_structure()
        assert modified == baseline
        warning = capsys.readouterr().err
    assert "'merges' has no effect" in warning
    assert 'only applies to ?type=ownership' in warning


def test_merges_still_changes_ownership_on_a_real_merge(history_repo):
    repo = pygit2.Repository(str(history_repo))
    head = repo.head.target
    signature = pygit2.Signature('Reviewer', 'reviewer@example.com', 1700000010, 0)
    (history_repo / 'sample.py').write_text('value = 4\n', encoding='utf-8')
    repo.index.add('sample.py')
    side = repo.create_commit(None, signature, signature, 'side', repo.index.write_tree(), [head])
    (history_repo / 'sample.py').write_text('value = 5\n', encoding='utf-8')
    repo.index.add('sample.py')
    repo.create_commit('HEAD', signature, signature, 'merge', repo.index.write_tree(), [head, side])
    ordinary = GitAdapter(str(history_repo), 'type=ownership').get_structure()
    merged = GitAdapter(str(history_repo), 'type=ownership&merges=1').get_structure()
    assert merged['total_commits'] == ordinary['total_commits'] + 1
