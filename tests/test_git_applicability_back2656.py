"""Git applicability (COMMAND_MODEL "Applicability", BACK-2656 Step 2d).

Each control declares the answers that read it. Commits are walked by the repository overview, a ref's history, a file
or directory history and a timeline: they read the filter (``where``, ``since``, ``until``), ``sort``/``limit``/
``offset`` and the merge policy; ownership reads the row controls and ``merges`` but no filter; ``scan-limit`` is the
commit budget of ownership and a timeline; blame reads ``detail`` and ``ignore``, a diff ``context``, and the
element narrows a file's history, blame, diff and timeline. A file's content reads ``raw``/``detail=raw`` only. A
control on another answer is an invalid request with the one shared message, on the URI, the subcommand, the URI with
a flag and ``api.query``. Before, Git printed its own "has no effect" notes on stderr only (JSON mode too), the ledger
noted row controls on a file's content, blame and diff, several answered with no word at all (``context`` on a
repository diff, ``ignore`` on a repository blame, ``element`` on a ref's history, ``no_merges`` on a blame,
``raw`` on a repository), and ``scan-limit`` had its own message.

The merge policy is one on/off switch (COMMAND_MODEL "Switches"): the legacy numeric spelling ``merges=0``/``merges=1``
answers as ``merges=off``/``merges=on`` on every view. Before, it was read by ownership only and noted elsewhere, so
``merges=0`` on a history kept the merge commits that ``merges=off`` drops.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.errors import RequestValidationError

pygit2 = pytest.importorskip('pygit2')

UNREAD_WARNINGS = ('unused_query_param', 'unused_flag', 'unknown_query_param')


@pytest.fixture
def proj(tmp_path, monkeypatch):
    root = tmp_path / 'proj'
    (root / 'pkg').mkdir(parents=True)
    repo = pygit2.init_repository(str(root))
    parents = []
    for index, (author, when) in enumerate((('Ann', 1700000000), ('Bob', 1702000000), ('Ann', 1705000000))):
        (root / 'app.py').write_text(f'def serve(x):\n    return x + {index}\n\n\ndef other():\n    return {index}\n',
                                     encoding='utf-8')
        (root / 'pkg' / 'mod.py').write_text(f'X = {index}\n', encoding='utf-8')
        repo.index.add('app.py')
        repo.index.add('pkg/mod.py')
        repo.index.write()
        signature = pygit2.Signature(author, f'{author.lower()}@example.com', when, 0)
        parents = [repo.create_commit('HEAD', signature, signature, f'commit {index}', repo.index.write_tree(),
                                      parents)]
    monkeypatch.chdir(tmp_path)
    return root


@pytest.fixture
def merged(proj):
    """*proj* with a merge commit on top: the merge policy changes a history."""
    repo = pygit2.Repository(str(proj))
    head = repo.head.target
    signature = pygit2.Signature('Cy', 'cy@example.com', 1706000000, 0)
    side = repo.create_commit(None, signature, signature, 'side', repo.head.peel().tree.id, [head])
    repo.create_commit('HEAD', signature, signature, 'merge', repo.head.peel().tree.id, [head, side])
    return proj


def _run(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run, (json.loads(run.stdout) if run.stdout.strip().startswith('{') else {})


def _unread(doc):
    return [w for w in (doc.get('meta') or {}).get('warnings') or [] if (w.get('code') or w.get('type'))
            in UNREAD_WARNINGS]


_FILE, _BLAME, _DIFF = 'git_file_structure, default', 'git_file_blame, view, view=blame', 'git_file_diff, view, view=diff'


@pytest.mark.parametrize('argv,control,answer', [
    (('git://proj/app.py?limit=1',), 'limit', _FILE),                                       # the ledger's note before
    (('git://proj/app.py?view=blame&sort=-date',), 'sort', _BLAME),
    (('git://proj/app.py?view=diff&offset=1',), 'offset', _DIFF),
    (('git://proj?context=1',), 'context', 'git_repository, default'),                      # stderr-only note before
    (('git://proj/app.py?view=history&detail=full',), 'detail', 'git_file_history, view, view=history'),
    (('git://proj/app.py?view=diff&bucket=week',), 'bucket', _DIFF),
    (('git://proj?view=ownership&element=serve',), 'element', 'git_ownership, view, view=ownership'),
    (('git://proj?view=ownership&since=2023-11-01',), 'since', 'git_ownership, view, view=ownership'),
    (('git://proj/app.py?view=blame&until=2030-01-01',), 'until', _BLAME),
    (('git://proj?view=diff&context=1',), 'context', 'git_ref, view, view=diff'),             # silent before
    (('git://proj?view=history&element=serve',), 'element', 'git_ref, view, view=history'),   # silent before
    # legacy no_merges and raw are spellings of merges and detail (BACK-2616): the refusal names the control
    (('git://proj/app.py?view=blame&no_merges=1',), 'merges', _BLAME),                        # silent before
    (('git://proj?raw=1',), 'detail', 'git_repository, default'),                             # silent before
    # legacy ignore is ignore-commits, and ignore=off auto-ignore=off (BACK-2733): the refusal names the control
    (('git://proj/app.py?ignore=abc',), 'ignore-commits', _FILE),
    (('git://proj?view=blame&ignore=abc',), 'ignore-commits', 'git_ref, view, view=blame'),   # silent before 2656
    (('git://proj/app.py?ignore=off',), 'auto-ignore', _FILE),
    (('git://proj/app.py?ignore-commits=abc',), 'ignore-commits', _FILE),
    (('git', 'proj/app.py', '--auto-ignore', 'off'), 'auto-ignore', _FILE),
    (('git://proj/app.py?view=history&scan-limit=5',), 'scan-limit', 'git_file_history, view, view=history'),
    (('git', 'proj/app.py', '--view', 'blame', '--limit', '1'), 'limit', _BLAME),             # the subcommand
    (('git://proj/app.py?view=diff', '--limit', '1'), 'limit', _DIFF),                        # the URI and a flag
])
def test_git_refuses_a_control_its_answer_does_not_read(proj, argv, control, answer):
    run, _doc = _run(*argv)
    assert run.returncode == 2, (run.returncode, run.stdout[:300], run.stderr)
    assert f"control '{control}' is not read by this answer ({answer}" in run.stderr, run.stderr
    assert f'{control} is read by: ' in run.stderr, run.stderr


@pytest.mark.parametrize('uri,typed', [
    ('git://proj?view=ownership&author=Bob', 'author=Bob'),  # ownership aggregates unfiltered (stderr note before)
    ('git://proj/app.py?author=Bob', 'author=Bob'),          # a file's content reads no commit filter
])
def test_git_names_a_bare_filter_key_as_typed(proj, uri, typed):
    run, _doc = _run(uri)
    assert run.returncode == 2, (run.returncode, run.stderr)
    assert f"control 'where' ({typed}) is not read by this answer" in run.stderr, run.stderr


def test_git_element_on_a_repository_timeline_is_refused(proj):
    """A timeline is one answer type on a repository and on a path, and only a path's timeline reads the element:
    a repository has no element to narrow to (it answered the whole repository's timeline before, with no word)."""
    run, _doc = _run('git://proj?view=history&bucket=week&element=serve')
    assert run.returncode == 2, (run.returncode, run.stderr)
    assert 'element' in run.stderr and 'file' in run.stderr, run.stderr


def test_git_api_refuses_the_same_request(proj):
    from reveal import api
    with pytest.raises(RequestValidationError, match=r"control 'context' is not read by this answer \(git_ref"):
        api.query('git://proj?view=diff', context=1)


@pytest.mark.parametrize('uri', [
    'git://proj?author=Ann&since=2023-11-01&until=2030-01-01&sort=-date&limit=1&offset=0&merges=off',
    'git://proj?view=history&author=Ann&no_merges=1&limit=1',
    'git://proj/app.py?view=history&element=serve&author=Ann&since=2023-11-01&limit=1',
    'git://proj/pkg?view=history&limit=1',
    'git://proj/app.py?view=blame&detail=full&ignore=off&element=serve',
    'git://proj/app.py?view=diff&context=1&element=serve',
    'git://proj/app.py?raw=1',
    'git://proj?view=ownership&no_merges=1',  # merges=off, which ownership reads (BACK-2616 Q6; refused before)
    'git://proj/app.py?detail=raw',
    'git://proj?view=ownership&merges=on&scan-limit=5&sort=-commits&limit=1',
    'git://proj/app.py?view=history&bucket=week&element=serve&scan-limit=5&limit=1&author=Ann',
    'git://proj?view=history&bucket=month&scan-limit=5&until=2030-01-01',
    'markdown://proj?limit=1',  # a sibling noun's reading answer, unchanged
])
def test_git_answers_where_its_controls_are_read(proj, uri):
    run, doc = _run(uri)
    assert run.returncode == 0, (run.returncode, run.stderr)
    assert not _unread(doc), doc.get('meta')
    assert 'no effect' not in run.stderr, run.stderr


def _history(uri):
    run, doc = _run(uri)
    assert run.returncode == 0, (run.returncode, run.stderr)
    return [row['message'] for row in doc['history']]


@pytest.mark.parametrize('legacy,canonical', [('merges=0', 'merges=off'), ('merges=1', 'merges=on'),
                                              ('merges=false', 'merges=off')])
def test_git_legacy_merges_value_answers_as_its_switch_on_a_history(merged, legacy, canonical):
    assert _history(f'git://proj?view=history&{legacy}') == _history(f'git://proj?view=history&{canonical}')


def test_git_merge_policy_still_changes_a_history(merged):
    """Positive control: the fixture's merge commit is what merges=off drops."""
    assert 'merge' in _history('git://proj?view=history') and 'merge' not in _history('git://proj?view=history&merges=off')


def test_git_legacy_merges_beside_no_merges_is_a_conflicting_request(merged):
    """Both now set the one merge policy of a history, as the canonical switch beside no_merges already did."""
    run, _doc = _run('git://proj?view=history&merges=1&no_merges=1')
    assert run.returncode == 2, (run.returncode, run.stderr)
    assert 'merges' in run.stderr and 'no_merges' in run.stderr, run.stderr
