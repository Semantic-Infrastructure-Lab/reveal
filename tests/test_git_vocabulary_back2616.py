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


# --- discriminating REDs: each fails on 6f1c40d8 for the reason in its docstring ----------------------------------

def _notes(doc):
    return [w for w in _warnings(doc) if w.get('code') == 'retired_spelling']


def _without_notes(doc):
    import copy
    result = copy.deepcopy(doc)
    result['meta']['warnings'] = [w for w in _warnings(result) if w.get('code') != 'retired_spelling']
    return result


def _round_trip(repo, *argv):
    """The request's one note, and its replacement run as written: (legacy run, legacy doc, replacement, run, doc)."""
    run, doc = _json(repo, *argv)
    notes = _notes(doc)
    assert len(notes) == 1, (run.returncode, run.stderr[-400:], notes)
    replacement = notes[0]['replacement']
    canonical, canonical_doc = _json(repo, *shlex.split(replacement)[1:])
    return run, doc, replacement, canonical, canonical_doc


def _assert_same_answer(run, doc, canonical, canonical_doc, replacement):
    assert canonical.returncode == run.returncode, (replacement, run.returncode, canonical.returncode, canonical.stderr)
    assert not _notes(canonical_doc), replacement
    assert _without_notes(doc) == canonical_doc, replacement


# B1 / Q1 (A): the legacy aggregate limit is the input budget, so the note must name --scan-limit and answer alike.
@pytest.mark.parametrize('uri', ['git://.?type=ownership&limit=2', 'git://.?type=history&bucket=month&limit=2'])
def test_legacy_aggregate_limit_note_names_scan_limit_and_answers_alike(repo, uri):
    """RED: the note recommends --limit 2, a row cap over the whole history (exit 0), not the 2-commit window (exit 3)."""
    run, doc, replacement, canonical, canonical_doc = _round_trip(repo, uri)
    assert '--scan-limit 2' in replacement and '--limit' not in replacement.replace('--scan-limit', ''), replacement
    _assert_same_answer(run, doc, canonical, canonical_doc, replacement)


# B2 / Q1: one request, one answer on every transport (no override sniffing).
@pytest.mark.parametrize('uri,flags,typed', [
    ('git://.?type=ownership&limit=2', ['--sort', 'name'], {'sort': 'name'}),
    ('git://.?type=ownership', ['--limit', '2'], {'limit': 2}),
])
def test_legacy_aggregate_limit_answers_alike_on_cli_and_api(repo, monkeypatch, uri, flags, typed):
    """RED: a typed override flips the API to the row cap while the CLI keeps the input window, and the CLI's
    legacy path leaves --sort unread (the ledger's unused_flag warning, which must not fire on a declared noun)."""
    from reveal.api import query
    run, cli = _json(repo, uri, *flags)
    monkeypatch.chdir(repo)
    api = query(uri, **typed)
    unread = [w for w in _warnings(cli) + _warnings(api) if w.get('type') in ('unused_flag', 'unused_query_param')]
    assert not unread, unread
    assert _without_notes(cli) == _without_notes(api), (run.returncode, cli.get('total_commits'), api.get('total_commits'))


# Q1 (A): the legacy aggregate limit is a spelling of scan-limit, so scan-limit given too is one setting; its old zero
# (no input window) is scan-limit's zero.
def test_legacy_aggregate_limit_and_scan_limit_are_one_setting(repo):
    run, doc = _json(repo, 'git://.?type=ownership&limit=2&scan-limit=2')
    _, canonical = _json(repo, 'git://.', '--view', 'ownership', '--scan-limit', '2')
    assert run.returncode == 3 and _without_notes(doc) == canonical
    run, _ = _json(repo, 'git://.?type=ownership&limit=2&scan-limit=5')
    assert run.returncode == 2 and 'scan-limit: conflicting spellings: limit, scan-limit' in run.stderr, run.stderr
    run, doc, replacement, canonical, canonical_doc = _round_trip(repo, 'git://.?type=ownership&limit=0')
    assert '--scan-limit 0' in replacement and run.returncode == 0 and doc['total_commits'] == 7, replacement
    _assert_same_answer(run, doc, canonical, canonical_doc, replacement)


# B5 / BACK-2729: --all binds the value --limit 0 binds on git's commit lists, so the two are one setting; a different
# limit given with --all still names both. Git has no --all handling of its own.
@pytest.mark.parametrize('argv', [['git', '.', '--view', 'history'], ['git://.?view=history']])
def test_all_and_limit_zero_are_one_setting(repo, argv):
    _, uncapped = _json(repo, *argv, '--limit', '0')
    assert len(uncapped['history']) == 8
    for extra in (['--all'], ['--all', '--limit', '0']):
        run, doc = _json(repo, *argv, *extra)
        assert run.returncode == 0 and _without_notes(doc) == _without_notes(uncapped), (extra, run.stderr)
    run, _ = _json(repo, *argv, '--all', '--limit', '3')
    assert run.returncode == 2 and '--all' in run.stderr, run.stderr


# B3: since/until are settings (COMMAND_MODEL "Conflicting values"), on the typed API too.
def test_typed_since_list_with_two_values_is_refused(repo, monkeypatch):
    """RED: api.query answers with both bounds ANDed where the CLI and URI exit 2."""
    from reveal.api import query
    from reveal.errors import RequestValidationError
    monkeypatch.chdir(repo)
    with pytest.raises(RequestValidationError):
        query('git://.?view=history&limit=0', since=['2023-11-15', '2023-11-18'])


def test_typed_since_list_of_one_value_is_that_value(repo, monkeypatch):
    """RED: an equal list answers once, but its note renders since='D,D', which is not the request."""
    from reveal.api import query
    monkeypatch.chdir(repo)
    listed = query('git://.?view=history&limit=0', since=['2023-11-16', '2023-11-16'])
    single = query('git://.?view=history&limit=0', since='2023-11-16')
    assert _without_notes(listed) == _without_notes(single)
    replacements = [w['replacement'] for w in _notes(listed)]
    assert replacements and all("since='2023-11-16')" in r for r in replacements), replacements


# B6: a legacy spelling and its canonical control given with equal meaning are one setting.
def test_no_merges_and_merges_off_together_are_one_setting(repo):
    """RED: a hand-written check refuses them together (exit 2) though they agree."""
    run, doc = _json(repo, 'git://.?view=history&limit=0&no_merges=1&merges=off')
    _, canonical = _json(repo, 'git', '.', '--view', 'history', '--limit', '0', '--merges', 'off')
    assert run.returncode == 0, run.stderr
    assert _without_notes(doc)['history'] == canonical['history']


def test_raw_and_detail_raw_together_are_one_setting(repo):
    """RED: a hand-written check refuses them together (exit 2) though they agree."""
    run, doc = _json(repo, 'git://code.py?raw=1&detail=raw')
    _, canonical = _json(repo, 'git', 'code.py', '--detail', 'raw')
    assert run.returncode == 0, run.stderr
    assert _without_notes(doc) == canonical


# Q6: no_merges is merges=off on every answer merges reaches, ownership included.
def test_no_merges_on_ownership_answers_as_merges_off(repo):
    """RED: ownership refuses no_merges (exit 2, not read by this answer)."""
    run, doc = _json(repo, 'git://.?type=ownership&no_merges=1')
    _, canonical = _json(repo, 'git', '.', '--view', 'ownership', '--merges', 'off')
    assert run.returncode == 0, run.stderr
    assert _without_notes(doc) == canonical


# B7: a diff that did not run is not "no changes".
def test_a_failed_git_diff_is_a_failed_answer(repo, monkeypatch):
    """RED: get_file_diff ignores git's exit status and answers "(no changes ...)", exit 0."""
    import subprocess
    run, doc = _json(repo, 'git', 'pkg/app.py@HEAD~2', '--view', 'diff')
    assert run.returncode == 0 and 'return 3' in doc['diff_text']  # positive control: the real diff
    real = subprocess.run

    def failing_git_diff(cmd, *args, **kwargs):
        if isinstance(cmd, list) and cmd[:1] == ['git'] and 'diff' in cmd:
            return subprocess.CompletedProcess(cmd, 128, b'', b'fatal: simulated failure\n')
        return real(cmd, *args, **kwargs)
    monkeypatch.setattr(subprocess, 'run', failing_git_diff)
    run, doc = _json(repo, 'git', 'pkg/app.py@HEAD~2', '--view', 'diff')
    assert run.returncode == 3, (run.returncode, (doc or {}).get('diff_text'))


# B8 (BACK-2690) and B9 / Q8 (plan rule 9): a target that matches nothing exits 2 naming what was searched.
def test_an_element_on_a_directory_history_is_an_invalid_request(repo):
    """RED: exit 3, '_pygit2.Tree' object has no attribute 'data'."""
    run, _ = _json(repo, 'git', 'pkg', '--view', 'history', '--element', 'serve')
    assert run.returncode == 2, run.stderr


@pytest.mark.parametrize('target,flags', [
    ('pkg/app.py', ['--view', 'history', '--element', 'nosuch']),
    ('pkg/app.py@HEAD~2', ['--view', 'diff', '--element', 'nosuch']),
])
def test_an_unknown_element_exits_2_naming_it(repo, target, flags):
    """RED: history answers 0 commits and diff prints the whole diff, both exit 0 (blame already exits 2)."""
    run, _ = _json(repo, 'git', target, *flags)
    assert run.returncode == 2 and 'nosuch' in run.stderr, (run.returncode, run.stderr)


def test_an_unknown_element_controls(repo):
    """Controls for the RED above: blame already refuses, and a real element still answers."""
    blame, _ = _json(repo, 'git', 'pkg/app.py', '--view', 'blame', '--element', 'nosuch')
    assert blame.returncode == 2 and 'nosuch' in blame.stderr
    run, doc = _json(repo, 'git', 'pkg/app.py', '--view', 'history', '--element', 'serve')
    assert run.returncode == 0 and doc['commits']


def test_a_path_never_in_history_exits_2_naming_it(repo):
    """RED: exit 0 with count 0 (a deleted file, which history touched, keeps exit 0: preservation above)."""
    run, _ = _json(repo, 'git', 'nosuch.py', '--view', 'history')
    assert run.returncode == 2 and 'nosuch.py' in run.stderr, (run.returncode, run.stderr)


# Conformance cell 24 (BACK-2716 step 4) and B20: every legacy spelling notes, on every transport, and its replacement
# answers alike.
@pytest.mark.parametrize('uri,replacement', [
    ('git://.?view=history&limit=0&no_merges=true', '--merges off'),
    ('git://code.py?raw=true', '--detail raw'),
])
def test_legacy_no_merges_and_raw_note_their_flag_and_answer_alike(repo, uri, replacement):
    """RED: no flag spells them, so the request says no note (UnrenderableRequest) and would keep working at the cut."""
    run, doc, rendered, canonical, canonical_doc = _round_trip(repo, uri)
    assert replacement in rendered, rendered
    _assert_same_answer(run, doc, canonical, canonical_doc, rendered)


@pytest.mark.parametrize('uri,typed,word', [
    ('git://code.py', {'type': 'history'}, 'type'),
    ('git://.', {'view': 'history', 'no_merges': True}, 'no_merges'),
    ('git://code.py', {'raw': True}, 'raw'),
])
def test_typed_legacy_keywords_on_a_resource_uri_note(repo, monkeypatch, uri, typed, word):
    """RED: api.query accepts these keywords on a resource URI with no note."""
    from reveal.api import query
    monkeypatch.chdir(repo)
    notes = _notes(query(uri, **typed))
    assert any(word in str(n.get('old', '')) + str(n.get('message', '')) for n in notes), notes


def test_git_legacy_spellings_have_note_stage_rows():
    """RED: type, no_merges and raw have no RETIREMENTS row (type was D18-deferred; D20 adopts it), nor detail=summary."""
    from reveal.cli.invocation import RETIREMENTS
    keys = ('param:git.type', 'param:git.no_merges', 'param:git.raw', 'value:git.detail=summary')
    assert {key: RETIREMENTS[key].stage if key in RETIREMENTS else None for key in keys} == dict.fromkeys(keys, 'note')


# Q4: summary is a legacy value of detail.
def test_detail_summary_notes_detail_normal_and_answers_alike(repo):
    """RED: --detail summary is silently normal, with no note."""
    run, doc = _json(repo, 'git', 'code.py', '--view', 'blame', '--detail', 'summary')
    _, canonical = _json(repo, 'git', 'code.py', '--view', 'blame', '--detail', 'normal')
    assert run.returncode == 0, run.stderr
    assert any('--detail normal' in str(n.get('replacement')) for n in _notes(doc)), _notes(doc)
    assert _without_notes(doc) == canonical


# Q5: F@REF and --ref / ?ref= are one setting.
@pytest.mark.parametrize('argv', [('git', 'code.py@HEAD~1', '--ref', 'HEAD~2'), ('git://code.py@HEAD~1?ref=HEAD~2',)])
def test_a_different_ref_given_twice_exits_2_naming_both(repo, argv):
    """RED: --ref / ?ref= silently wins over @REF (exit 0 at HEAD~2)."""
    run, _ = _json(repo, *argv)
    assert run.returncode == 2 and 'HEAD~1' in run.stderr and 'HEAD~2' in run.stderr, (run.returncode, run.stderr)


# B11: hash compares the whole 7-character short hash; a prefix is a regex anchor, and the schema says so.
def test_hash_compares_the_whole_short_hash(repo):
    from reveal.adapters.git.params import COMMIT_FILTER_FIELDS
    head = str(pygit2.Repository(str(repo)).head.target)
    counts = []
    for term in (f'hash={head[:7]}', f'hash={head[:4]}', f'hash~=^{head[:4]}'):
        run, doc = _json(repo, 'git', '.', '--view', 'history', '--limit', '0', '--where', term)
        assert run.returncode == 0, run.stderr
        counts.append(len(_rows(doc, 'history')))
    assert counts == [1, 0, 1], counts
    assert '~=^PREFIX' in COMMIT_FILTER_FIELDS['hash'][1]


# B13: a repository's timeline names the repository, not "None".
def test_a_repository_timeline_header_names_the_repository(repo):
    run = _run_reveal_in(repo, 'git', '.', '--view', 'history', '--bucket', 'month')
    assert run.returncode == 0, run.stderr
    assert run.stdout.splitlines()[0].startswith('Timeline: repository @ HEAD'), run.stdout.splitlines()[:1]


# B14: a file structure's imports print as source lines, not Python dict reprs.
def test_file_structure_text_prints_imports_as_source_lines(capsys):
    from reveal.adapters.git.renderer import GitRenderer
    GitRenderer.render_structure({
        'type': 'git_file_structure', 'path': 'm.py', 'ref': 'HEAD', 'commit': 'abc1234', 'size': 10, 'lines': 1,
        'commit_info': {}, 'structure': {'imports': [{'line': 2, 'content': 'import os'}]}}, format='text')
    out = capsys.readouterr().out
    assert '  :2      import os' in out and "{'line'" not in out, out


# B15: the API docstrings' git examples answer (a file's structure reads no limit: the history view does).
def test_api_docstring_git_examples_answer(repo, monkeypatch):
    import re
    import reveal.api as api
    monkeypatch.chdir(repo)
    examples = re.findall(r'query\("git://[^"]+"([^)]*)\)', (api.__doc__ or '') + (api.query.__doc__ or ''))
    assert len(examples) == 3, examples
    for keywords in examples:
        controls = dict(re.findall(r'(\w+)=("[^"]*"|\d+)', keywords))
        api.query('git://code.py', **{k: (v.strip('"') if v.startswith('"') else int(v)) for k, v in controls.items()})


# B16: scan-limit declares the zero it reads (every commit), and ownership claims no unmeasured confidence.
def test_scan_limit_zero_is_declared_and_ownership_claims_no_confidence(repo):
    from reveal.adapters.git.params import SCAN_LIMIT
    assert SCAN_LIMIT.zero_uncaps and '20,000' in SCAN_LIMIT.description
    run, doc = _json(repo, 'git', '.', '--view', 'ownership', '--scan-limit', '0')
    assert run.returncode == 0 and doc['total_commits'] == 7
    assert 'confidence' not in doc['_meta'], doc['_meta']


# The request note of a retired value names the canonical value, never a spelling that itself retires.
@pytest.mark.parametrize('uri,replacement', [
    ('git://code.py?type=log', '--view history'),
    ('git://code.py?view=log', '--view history'),
    ('git://code.py?view=blame&detail=summary', '--detail normal'),
])
def test_a_retired_value_request_note_renders_its_canonical_value(repo, uri, replacement):
    run, doc, rendered, canonical, canonical_doc = _round_trip(repo, uri)
    assert replacement in rendered and '--view log' not in rendered and 'summary' not in rendered, rendered
    _assert_same_answer(run, doc, canonical, canonical_doc, rendered)
