"""Git blame's ``ignore`` becomes ``--ignore-commits`` and the switch ``--auto-ignore`` (Scott 2026-11-22, BACK-2733).

One scalar carried two meanings: ``ignore=off`` turned off auto-ignore (``.git-blame-ignore-revs`` and the noise
heuristic), and ``ignore=SHAS`` named commits to suppress *plus* auto-ignore, so explicit commits without auto-ignore
could not be asked for. Now ``--ignore-commits`` (alias ``ignore_commits``; repeatable, commas join) names the commits and
``--auto-ignore on|off`` (alias ``auto_ignore``; the shared switch codec) is the switch, on the subcommand, the URI,
``api.query`` and MCP. The old word stays a note-stage legacy spelling (``param:git.ignore``) declared on
``ignore-commits`` whose value decides its target (``LegacySpelling.sets_when``): ``ignore=off`` is ``auto-ignore=off``,
``ignore=SHAS`` is ``ignore-commits=SHAS``; its answers are the same as before, and its conflicts are generated. Both
controls are read by blame only, as ``ignore`` was. ``--ignore`` the global/check rule-ignore flag is another control and
is untouched.

Before (measured at 22e443e0): ``--ignore-commits``, ``--auto-ignore``, ``?ignore-commits=`` and the keywords exited 2
"unsupported control"; the blame text said "--ignore off includes them"; ``git -h`` listed ``--ignore``.
"""
import json
import re

import pytest

from conftest import _run_reveal_direct

pygit2 = pytest.importorskip('pygit2')

A_V1 = 'def alpha(x):\n    return x\n\n\ndef beta(y):\n    return y\n'
A_V2 = 'def alpha(x):\n    return  x\n\n\ndef beta(y):\n    return  y\n'  # a reformat touching lines 2 and 6
A_V3 = 'def alpha(x):\n    return  x + 1\n\n\ndef beta(y):\n    return  y\n'


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """``a.py`` in three commits: ``one`` writes it, ``style: reformat`` respaces lines 2 and 6 and is listed in
    ``.git-blame-ignore-revs`` (auto-ignored), ``three`` changes line 2. Returns the short hashes (one, reformat, three)."""
    repository = pygit2.init_repository(str(tmp_path))
    parents, hashes = [], []
    for index, (text, message) in enumerate(((A_V1, 'one'), (A_V2, 'style: reformat'), (A_V3, 'three'))):
        (tmp_path / 'a.py').write_text(text, encoding='utf-8')
        repository.index.add('a.py')
        repository.index.write()
        signature = pygit2.Signature('Fixture', 'fixture@example.com', 1700000000 + index * 86400, 0)
        oid = repository.create_commit('HEAD', signature, signature, message, repository.index.write_tree(), parents)
        parents = [oid]
        hashes.append(str(oid)[:7])
    (tmp_path / '.git-blame-ignore-revs').write_text(hashes[1] + '\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tuple(hashes)


BLAME = ('git', 'a.py', '--view', 'blame')


def _json(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    try:
        doc = json.loads(run.stdout)
    except ValueError:
        doc = {}
    return run, doc if isinstance(doc, dict) else {}


def _notes(doc):
    return [w for w in (doc.get('meta') or {}).get('warnings') or [] if w.get('code') == 'retired_spelling']


def _plain(doc):
    """The answer without its retirement notes and next steps (a note names the spelling used)."""
    doc = json.loads(json.dumps(doc))
    meta = doc.get('meta')
    if isinstance(meta, dict):
        meta['warnings'] = [w for w in meta.get('warnings') or [] if w.get('code') != 'retired_spelling']
    doc.pop('next_steps', None)
    return doc


def _ignored(doc):
    return sorted((entry['hash'], entry['source']) for entry in doc.get('ignored') or [])


def _owners(doc):
    return sorted(hunk['commit']['hash'] for hunk in doc.get('hunks') or [])


def _error(run, doc):
    return doc.get('error') if isinstance(doc.get('error'), str) else run.stderr


# --- the new spellings answer -----------------------------------------------------------------------------------------

def test_ignore_commits_suppresses_the_commits_beside_auto_ignore(repo):
    one, reformat, three = repo
    run, doc = _json(*BLAME, '--ignore-commits', three)
    assert run.returncode == 0, run.stderr
    assert _ignored(doc) == sorted([(three, 'explicit'), (reformat, 'ignore-revs')])
    assert three not in _owners(doc)


def test_auto_ignore_off_shows_the_raw_blame(repo):
    one, reformat, three = repo
    run, doc = _json(*BLAME, '--auto-ignore', 'off')
    assert run.returncode == 0, run.stderr
    assert _ignored(doc) == [] and reformat in _owners(doc)


def test_explicit_commits_without_auto_ignore_are_expressible(repo):
    """The request the one scalar could not spell: suppress a commit and keep auto-ignore off."""
    one, reformat, three = repo
    run, doc = _json(*BLAME, '--ignore-commits', three, '--auto-ignore', 'off')
    assert run.returncode == 0, run.stderr
    assert _ignored(doc) == [(three, 'explicit')]
    assert reformat in _owners(doc) and three not in _owners(doc)


def test_auto_ignore_on_is_the_default(repo):
    assert _plain(_json(*BLAME, '--auto-ignore', 'on')[1]) == _plain(_json(*BLAME)[1])


@pytest.mark.parametrize('spellings', [
    ('--ignore-commits', '{three},{one}'),
    ('--ignore-commits', '{three}', '--ignore-commits', '{one}'),
])
def test_ignore_commits_repeats_and_commas_join(repo, spellings):
    one, reformat, three = repo
    argv = [part.format(one=one, three=three) for part in spellings]
    run, doc = _json(*BLAME, *argv)
    assert run.returncode == 0, run.stderr
    assert _ignored(doc) == sorted([(one, 'explicit'), (three, 'explicit'), (reformat, 'ignore-revs')])


@pytest.mark.parametrize('query,flags', [
    ('ignore-commits={three}', ('--ignore-commits', '{three}')),
    ('ignore_commits={three}', ('--ignore-commits', '{three}')),
    ('ignore-commits={three}&ignore-commits={one}', ('--ignore-commits', '{three}', '--ignore-commits', '{one}')),
    ('auto-ignore=off', ('--auto-ignore', 'off')),
    ('auto_ignore=off', ('--auto-ignore', 'off')),
    ('ignore-commits={three}&auto-ignore=off', ('--ignore-commits', '{three}', '--auto-ignore', 'off')),
])
def test_the_uri_answers_as_the_flags(repo, query, flags):
    one, reformat, three = repo
    uri = 'git://a.py?view=blame&' + query.format(one=one, three=three)
    run, doc = _json(uri)
    flag_run, flag_doc = _json(*BLAME, *(part.format(one=one, three=three) for part in flags))
    assert run.returncode == flag_run.returncode == 0, (run.stderr, flag_run.stderr)
    assert _plain(doc) == _plain(flag_doc)


@pytest.mark.parametrize('query,rendered', [
    ('ignore-commits={three}', '--ignore-commits {three}'),
    ('auto-ignore=off', '--auto-ignore off'),
])
def test_the_uri_request_note_renders_the_new_flags(repo, query, rendered):
    one, reformat, three = repo
    run, doc = _json('git://a.py?view=blame&' + query.format(three=three))
    messages = [note['message'] for note in _notes(doc)]
    assert any(rendered.format(three=three) in message for message in messages), messages


@pytest.mark.parametrize('keywords,flags', [
    ({'ignore_commits': '{three}'}, ('--ignore-commits', '{three}')),
    ({'ignore_commits': ['{three}', '{one}']}, ('--ignore-commits', '{three}', '--ignore-commits', '{one}')),
    ({'auto_ignore': 'off'}, ('--auto-ignore', 'off')),
    ({'auto_ignore': False}, ('--auto-ignore', 'off')),
    ({'ignore_commits': '{three}', 'auto_ignore': 'off'}, ('--ignore-commits', '{three}', '--auto-ignore', 'off')),
])
def test_the_typed_api_answers_as_the_flags(repo, keywords, flags):
    from reveal import api
    one, reformat, three = repo
    fill = {'one': one, 'three': three}
    typed = {key: [item.format(**fill) for item in value] if isinstance(value, list)
             else value.format(**fill) if isinstance(value, str) else value for key, value in keywords.items()}
    answer = api.query('git', 'a.py', view='blame', **typed)
    assert _plain(answer) == _plain(_json(*BLAME, *(part.format(**fill) for part in flags))[1])
    assert _plain(api.query('git://a.py?view=blame', **typed)) == _plain(answer)


@pytest.mark.parametrize('argv', [
    ('--ignore-commits', '{three}', '--auto-ignore', 'off'),
    ('--auto-ignore', 'off'),
])
def test_mcp_answers_as_the_subcommand(repo, argv):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_run
    one, reformat, three = repo
    filled = [part.format(three=three) for part in argv]
    shown = reveal_run([*BLAME, *filled, '--format', 'json'])
    assert _plain(json.loads(shown)) == _plain(_json(*BLAME, *filled)[1])


# --- the legacy word answers as before, with its note -------------------------------------------------------------------

@pytest.mark.parametrize('legacy,canonical', [
    (('--ignore', 'off'), ('--auto-ignore', 'off')),
    (('--ignore', '{three}'), ('--ignore-commits', '{three}')),
    (('--ignore', '{three},{one}'), ('--ignore-commits', '{three},{one}')),
    (('git://a.py?view=blame&ignore=off',), ('--auto-ignore', 'off')),
    (('git://a.py?view=blame&ignore=OFF',), ('--auto-ignore', 'off')),
    (('git://a.py?view=blame&ignore={three}',), ('--ignore-commits', '{three}')),
])
def test_the_legacy_word_answers_as_its_replacement(repo, legacy, canonical):
    one, reformat, three = repo
    fill = {'one': one, 'three': three}
    legacy = tuple(part.format(**fill) for part in legacy)
    request = legacy if legacy[0].startswith('git://') else (*BLAME, *legacy)
    run, doc = _json(*request)
    canonical_run, canonical_doc = _json(*BLAME, *(part.format(**fill) for part in canonical))
    assert run.returncode == canonical_run.returncode == 0, (run.stderr, canonical_run.stderr)
    assert _plain(doc) == _plain(canonical_doc)


def test_the_legacy_answers_are_the_old_ones(repo):
    """Positive controls (they pass at the base): what ``ignore=off`` and ``ignore=SHA`` answered before."""
    one, reformat, three = repo
    assert _ignored(_json(*BLAME, '--ignore', 'off')[1]) == []
    assert _ignored(_json(*BLAME, '--ignore', three)[1]) == sorted([(three, 'explicit'), (reformat, 'ignore-revs')])
    assert _ignored(_json('git://a.py?view=blame&ignore=off')[1]) == []
    from reveal import api
    assert _ignored(api.query('git', 'a.py', view='blame', ignore='off')) == []
    assert _ignored(api.query('git', 'a.py', view='blame', ignore=three)) == \
        sorted([(three, 'explicit'), (reformat, 'ignore-revs')])


@pytest.mark.parametrize('legacy', [('--ignore', 'off'), ('--ignore', 'abc1234')])
def test_the_legacy_flag_notes_its_row(repo, legacy):
    run, doc = _json(*BLAME, *legacy)
    notes = _notes(doc)
    assert [note.get('field') for note in notes] == ['param:git.ignore'], notes
    assert '--ignore-commits' in notes[0]['message'] and '--auto-ignore off' in notes[0]['message']


@pytest.mark.parametrize('query,rendered', [
    ('ignore=off', '--auto-ignore off'),
    ('ignore={three}', '--ignore-commits {three}'),
])
def test_the_legacy_uri_request_note_renders_the_replacement(repo, query, rendered):
    one, reformat, three = repo
    run, doc = _json('git://a.py?view=blame&' + query.format(three=three))
    messages = [note['message'] for note in _notes(doc)]
    assert len(messages) == 1 and rendered.format(three=three) in messages[0], messages
    assert '--ignore ' not in messages[0]


def test_the_legacy_keyword_notes_its_row(repo):
    from reveal import api
    answer = api.query('git', 'a.py', view='blame', ignore='off')
    assert 'param:git.ignore' in [note.get('field') for note in _notes(answer)]


# --- conflicts and refusals ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize('request_argv,names', [
    ((*BLAME, '--ignore', 'off', '--auto-ignore', 'on'), ('--ignore', '--auto-ignore')),
    ((*BLAME, '--auto-ignore', 'on', '--ignore', 'off'), ('--ignore', '--auto-ignore')),
    (('git://a.py?view=blame&ignore=off&auto-ignore=on',), ('ignore', 'auto-ignore')),
    (('git://a.py?view=blame&ignore=off', '--auto-ignore', 'on'), ('ignore', '--auto-ignore')),
    ((*BLAME, '--auto-ignore', 'off', '--auto-ignore', 'on'), ('--auto-ignore off', '--auto-ignore on')),
])
def test_a_conflict_exits_2_naming_both_spellings(repo, request_argv, names):
    run, doc = _json(*request_argv)
    assert run.returncode == 2, (run.stdout[:300], run.stderr)
    message = _error(run, doc)
    assert 'conflicting spellings' in message or 'given twice' in message, message
    assert all(name in message for name in names), message


def test_the_legacy_word_and_the_new_control_combine(repo):
    """``ignore-commits`` filters, so it repeats and combines (COMMAND_MODEL "Conflicting values"), and so does its
    legacy word: ``--ignore A --ignore-commits B`` suppresses both, the generated join of one control's spellings."""
    one, reformat, three = repo
    run, doc = _json(*BLAME, '--ignore', three, '--ignore-commits', one)
    assert run.returncode == 0, run.stderr
    assert _ignored(doc) == sorted([(one, 'explicit'), (three, 'explicit'), (reformat, 'ignore-revs')])
    off_run, off_doc = _json(*BLAME, '--ignore', 'off', '--ignore-commits', three)
    assert off_run.returncode == 0, off_run.stderr
    assert _ignored(off_doc) == [(three, 'explicit')]


@pytest.mark.parametrize('argv', [('--ignore-commits', 'abc1234'), ('--auto-ignore', 'off'),
                                  ('--ignore', 'abc1234'), ('--ignore', 'off')])
def test_blame_alone_reads_them(repo, argv):
    """Applicability is unchanged: history does not read them (``--ignore SHA`` on history still refuses)."""
    run, doc = _json('git', 'a.py', '--view', 'history', *argv)
    assert run.returncode == 2, run.stderr
    assert 'not read by this answer' in _error(run, doc)


@pytest.mark.parametrize('argv,typed', [
    (('--ignore-commits', ''), '--ignore-commits'),
    (('--ignore', ''), '--ignore'),
    (('--auto-ignore', 'maybe'), '--auto-ignore'),
])
def test_an_empty_or_invalid_value_exits_2(repo, argv, typed):
    run, doc = _json(*BLAME, *argv)
    assert run.returncode == 2, run.stderr
    message = _error(run, doc)
    assert typed.lstrip('-') in message and 'unsupported control' not in message, message


# --- help and text ------------------------------------------------------------------------------------------------------

def test_git_help_teaches_the_new_flags_and_hides_the_old_one(repo):
    run = _run_reveal_direct('git', '--help')
    assert run.returncode == 0
    assert '--ignore-commits' in run.stdout and '--auto-ignore' in run.stdout
    assert not re.search(r'--ignore(?![-\w])', run.stdout), run.stdout


def test_the_blame_text_names_the_switch(repo):
    run = _run_reveal_direct(*BLAME)
    assert run.returncode == 0, run.stderr
    assert '--auto-ignore off includes them' in run.stdout
    assert '--ignore off' not in run.stdout


def test_the_global_rule_ignore_flag_is_untouched(repo):
    """Negative control: ``check --ignore RULES`` is another control (the rule filter) and still answers."""
    run = _run_reveal_direct('check', 'a.py', '--ignore', 'E501', '--format', 'json')
    assert run.returncode in (0, 1), run.stderr
    assert 'unsupported control' not in run.stderr
