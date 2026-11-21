"""Git vocabulary (BACK-2616, D20): what the package must keep, and what its spellings must become.

The fixture is a small repository with two authors, a side branch merged back (one merge commit), a deleted file and a
package directory, so merge policy, input windows, deleted-file history and element views have something to decide.
Every request runs from the repository root with relative targets, so no path spelling differs by platform.
"""
import json
import shlex

import pytest

from conftest import _run_reveal_in, without_covered_notes, without_request_notes

pygit2 = pytest.importorskip('pygit2')

_T0 = 1700000000  # 2023-11-14; one day per commit keeps every commit in one month bucket
APP_V1 = 'def serve():\n    return 1\n'
APP_V2 = 'def serve():\n    return 2\n'
APP_V3 = 'def serve():\n    return 3\n\n\ndef other():\n    return 0\n'


def _commit(repo, root, files, message, author, day, parents, ref='HEAD'):
    for name, text in files.items():
        path = root / name
        if text is None:
            path.unlink()
            repo.index.remove(name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
            repo.index.add(name)
    repo.index.write()
    sig = pygit2.Signature(author, f'{author.lower()}@example.com', _T0 + day * 86400, 0)
    return repo.create_commit(ref, sig, sig, message, repo.index.write_tree(), parents)


@pytest.fixture
def repo(tmp_path):
    """c1..c8 on the first-parent line plus side commit c5; c7 merges c5. 8 commits, 1 merge, 7 non-merge."""
    r = pygit2.init_repository(str(tmp_path))
    c1 = _commit(r, tmp_path, {'code.py': 'def answer():\n    return 1\n', 'pkg/app.py': APP_V1}, 'c1 start', 'Ada', 0, [])
    c2 = _commit(r, tmp_path, {'pkg/app.py': APP_V2}, 'c2 app', 'Bob', 1, [c1])
    c3 = _commit(r, tmp_path, {'gone.py': 'x = 1\n'}, 'c3 add gone', 'Ada', 2, [c2])
    c4 = _commit(r, tmp_path, {'gone.py': None}, 'c4 remove gone', 'Ada', 3, [c3])
    side_code = 'def answer():\n    return 5\n'
    c5 = _commit(r, tmp_path, {'code.py': side_code}, 'c5 side code', 'Bob', 4, [c4], ref=None)
    # back to the main line's code.py before the main-line commit, so c6 changes pkg/app.py only
    c6 = _commit(r, tmp_path, {'code.py': 'def answer():\n    return 1\n', 'pkg/app.py': APP_V3}, 'c6 app', 'Ada', 5, [c4])
    c7 = _commit(r, tmp_path, {'code.py': side_code}, 'c7 merge side', 'Ada', 6, [c6, c5])
    _commit(r, tmp_path, {'code.py': 'def answer():\n    return 8\n'}, 'c8 code', 'Ada', 7, [c7])
    return tmp_path


def _json(repo, *argv):
    run = _run_reveal_in(repo, *argv, '--format', 'json')
    try:
        doc = json.loads(run.stdout)
    except ValueError:
        doc = None
    return run, doc


def _warnings(doc):
    return (doc or {}).get('meta', {}).get('warnings', [])


def _rows(doc, field):
    value = doc[field]
    return value['recent'] if isinstance(value, dict) else value


# --- preservation pins: these hold before and after the package --------------------------------------------------

@pytest.mark.parametrize('target,flags,kind', [
    ('.', [], 'git_repository'),
    ('.@HEAD~1', [], 'git_ref'),
    ('code.py', [], 'git_file_structure'),
    ('code.py@HEAD~1', ['--detail', 'raw'], 'git_file'),
    ('code.py', ['--view', 'history'], 'git_file_history'),
    ('pkg', ['--view', 'history'], 'git_directory_history'),
    ('code.py', ['--view', 'blame'], 'git_file_blame'),
    ('pkg/app.py@HEAD~2', ['--view', 'diff'], 'git_file_diff'),
    ('.', ['--view', 'ownership'], 'git_ownership'),
    ('.', ['--view', 'history', '--bucket', 'month'], 'git_timeline'),
])
def test_default_views_answer_alike_on_the_subcommand_and_the_resource_uri(repo, target, flags, kind):
    cli, a = _json(repo, 'git', target, *flags)
    uri, b = _json(repo, f'git://{target}', *flags)
    assert cli.returncode == uri.returncode == 0, (cli.stderr, uri.stderr)
    assert a == b and a['type'] == kind
    assert not [w for w in _warnings(a) if w.get('code') == 'retired_spelling']


def test_a_resource_uri_at_a_ref_reads_that_revision_without_a_note(repo):
    run, doc = _json(repo, 'git://code.py@HEAD~1', '--detail', 'raw')
    assert run.returncode == 0, run.stderr
    assert doc['ref'] == 'HEAD~1' and 'return 5' in doc['content']  # HEAD~1 is the merge, which took the side's code.py
    assert not _warnings(doc)


def test_a_deleted_file_keeps_its_history(repo):
    """BACK-2545: a file absent at HEAD that history touched answers its commits, exit 0."""
    run, doc = _json(repo, 'git', 'gone.py', '--view', 'history')
    assert run.returncode == 0, run.stderr
    # Only the commits that held the file are asserted: whether the deleting commit is listed is not this package's.
    assert 'c3 add gone' in [c['message'] for c in doc['commits']]


def test_a_file_missing_at_the_ref_is_an_invalid_request(repo):
    run, _ = _json(repo, 'git', 'nosuch.py')
    assert run.returncode == 2 and 'nosuch.py' in run.stderr


def test_merges_are_on_for_commit_lists_and_off_for_ownership(repo):
    _, default = _json(repo, 'git', '.', '--view', 'history', '--limit', '0')
    _, off = _json(repo, 'git', '.', '--view', 'history', '--limit', '0', '--merges', 'off')
    assert len(default['history']) == 8 and len(off['history']) == 7
    assert 'c7 merge side' not in [c['message'] for c in off['history']]
    _, overview_off = _json(repo, 'git', '.', '--limit', '0', '--merges', 'off')
    assert len(_rows(overview_off, 'commits')) == 7
    _, owners = _json(repo, 'git', '.', '--view', 'ownership')
    _, owners_on = _json(repo, 'git', '.', '--view', 'ownership', '--merges', 'on')
    assert owners['total_commits'] == 7 and owners_on['total_commits'] == 8


def test_scan_limit_bounds_the_ownership_input_and_discloses_the_loss(repo):
    run, doc = _json(repo, 'git', '.', '--view', 'ownership', '--scan-limit', '2')
    assert run.returncode == 3, run.stderr
    assert doc['total_commits'] == 2 and doc['scope']['history_window'] == {'limit': 2, 'commits_counted': 2,
                                                                          'complete': False}
    assert any(w.get('code') == 'analysis_incomplete' for w in _warnings(doc))
    run, doc = _json(repo, 'git', '.', '--view', 'ownership', '--scan-limit', '0')
    assert run.returncode == 0 and doc['total_commits'] == 7


def test_limit_caps_the_ownership_rows_and_keeps_the_population(repo):
    run, doc = _json(repo, 'git', '.', '--view', 'ownership', '--limit', '1')
    assert run.returncode == 0, run.stderr
    assert doc['total_commits'] == 7 and len(doc['authors']) == 1 and doc['contributor_count'] == 2


def test_legacy_type_with_a_limit_keeps_its_input_window(repo):
    """The old aggregate limit was a commit-input window (exit 3 on loss); the package keeps that answer (Q1 A)."""
    run, doc = _json(repo, 'git://.?type=ownership&limit=2')
    assert run.returncode == 3, run.stderr
    assert doc['total_commits'] == 2 and doc['scope']['history_window']['limit'] == 2
    run, doc = _json(repo, 'git://.?type=history&bucket=month&limit=2')
    assert run.returncode == 3, run.stderr
    assert doc['commit_count'] == 2


def test_an_equal_ref_given_twice_is_one_setting(repo):
    plain, a = _json(repo, 'git', 'code.py@HEAD~1')
    twice, b = _json(repo, 'git', 'code.py@HEAD~1', '--ref', 'HEAD~1')
    assert plain.returncode == twice.returncode == 0, twice.stderr
    assert a == b
