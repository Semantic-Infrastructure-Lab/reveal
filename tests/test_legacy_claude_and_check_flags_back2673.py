"""Claude --type/--name/--search and --check/--lint on Claude, Git and JSON (Scott 2026-11-19, BACK-2708 rulings 2 and
3; COMMAND_MODEL "Flags after a URI", BACK-2673). After a URI the main parser read them (Claude's readers filtered on
--type/--name; --check changed nothing and was noted unused) while the subcommand exited 2. They are now note-stage
legacy modifiers on both spellings, one RETIREMENTS row per flag per noun; an answer that does not read Claude's filters
exits 2. Codex keeps its old route until BACK-2618."""
import json

import pytest

import test_vocabulary_conformance_back2654 as C
from reveal.cli.invocation import Retirement
from legacy_modifier_fixture import rich, workspace  # noqa: F401  (fixtures)

# (URI, subcommand argv, flags typed after either): Claude answers that read the legacy filter
CLAUDE_READ = [
    ('claude://session/my-session/workflow', ['claude', 'session/my-session/workflow'], ['--type', 'Read']),
    ('claude://session/my-session/workflow', ['claude', 'session/my-session/workflow'], ['--name', 'read']),
    ('claude://session/my-session?view=workflow', ['claude', 'session/my-session', '--view', 'workflow'],
     ['--type', 'Bash', '--name', 'test']),
    ('claude://sessions', ['claude', 'sessions'], ['--name', 'my']),
    ('claude://sessions', ['claude', 'sessions'], ['--search', 'my']),
    ('claude://history', ['claude', 'history'], ['--name', 'review']),
]
CLAUDE_NOT_READ = [
    ('claude://session/my-session', ['claude', 'session/my-session'], ['--type', 'Read'], '--type'),
    ('claude://session/my-session?view=messages', ['claude', 'session/my-session', '--view', 'messages'],
     ['--name', 'x'], '--name'),
]
CHECKED = [('claude', 'claude://sessions', ['claude', 'sessions']),
           ('git', 'git://proj', ['git', 'proj']),
           ('git', 'git://proj/app.py', ['git', 'proj/app.py']),
           ('json', 'json://proj/data.json', ['json', 'proj/data.json'])]


def _notes(run, noun):
    doc = json.loads(run.out)
    return sorted(w['message'] for w in doc['meta'].get('warnings', [])
                  if w.get('code') == 'retired_spelling' and w['message'].startswith(f'{noun} --'))


def _flags(argv):
    return [token for token in argv if token.startswith('--')]


@pytest.mark.parametrize('uri,sub,typed', CLAUDE_READ, ids=[f'{u} {" ".join(t)}' for u, _, t in CLAUDE_READ])
def test_claude_filters_answer_alike_on_both_spellings_with_their_notes(rich, uri, sub, typed):  # noqa: F811
    after_uri = C._run(uri, *typed, '--format', 'json')
    on_sub = C._run(*sub, *typed, '--format', 'json')
    assert after_uri.rc == 0, after_uri.brief()
    assert on_sub.rc == 0, on_sub.brief()
    assert C._answer(on_sub, 'claude') == C._answer(after_uri, 'claude')
    wanted = sorted(f'claude {flag} is deprecated' for flag in _flags(typed))  # the stage clause after it is the row's
    for run in (after_uri, on_sub):
        assert [note[:len(prefix)] for note, prefix in zip(_notes(run, 'claude'), wanted)] == wanted, _notes(run, 'claude')


def test_the_filter_still_filters(rich):  # noqa: F811
    every = json.loads(C._run('claude://session/my-session/workflow', '--format', 'json').out)['workflow']
    read = json.loads(C._run('claude', 'session/my-session/workflow', '--type', 'Read', '--format', 'json').out)
    assert read['workflow'] == [step for step in every if (step.get('tool') or '').lower() == 'read']


@pytest.mark.parametrize('uri,sub,typed,control', CLAUDE_NOT_READ, ids=[u for u, *_ in CLAUDE_NOT_READ])
def test_a_claude_answer_that_does_not_read_the_filter_exits_2(rich, uri, sub, typed, control):  # noqa: F811
    for run in (C._run(uri, *typed, '--format', 'json'), C._run(*sub, *typed, '--format', 'json')):
        assert run.rc == 2, run.brief()
        assert f"control '{control}' is not read by this answer" in run.err + run.out


@pytest.mark.parametrize('flag', ['--check', '--lint'])
@pytest.mark.parametrize('noun,uri,sub', CHECKED, ids=[u for _, u, _ in CHECKED])
def test_check_answers_as_without_it_with_its_note(rich, noun, uri, sub, flag):  # noqa: F811
    plain = C._run(uri, '--format', 'json')
    for run in (C._run(uri, flag, '--format', 'json'), C._run(*sub, flag, '--format', 'json')):
        assert run.rc == 0, run.brief()
        assert C._answer(run, noun) == C._answer(plain, noun)
        assert _notes(run, noun) == [Retirement(f'{noun} {flag}', f'reveal check <path> to check files '
                                                f'(the flag never changed a {noun}:// answer)').text]
        assert not [w for w in json.loads(run.out)['meta'].get('warnings', []) if w.get('code') == 'unused_flag']


def test_codex_check_is_noted_like_every_declared_noun(rich):  # noqa: F811  (BACK-2598 ended the exemption)
    run = C._run('codex://', '--check', '--format', 'json')
    assert run.rc == 0, run.brief()
    assert _notes(run, 'codex') == ['codex --check is deprecated and works until 1.0; use reveal check <path> to check '
                                    'files (the flag never changed a codex:// answer).']
