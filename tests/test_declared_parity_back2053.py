"""Phase 1 exit audit (BACK-2053): the nine declared nouns answer alike in both spellings.

One table drives every noun through `reveal NOUN ...` and `reveal NOUN://...`: parsed JSON equal except
the command spelling and validated central architecture retirement note, same exits and visible
diagnostics, provenance off/on, text, requested JSON
artifacts (success and failed write), and a rejected resource. Per-noun depth lives in the
test_declared_<noun>_* files; this file is the cross-noun gate and fails if a noun is added to
COMMANDS without a row here.
"""
import copy
import json

import pytest

from conftest import _run_reveal_direct, without_request_note_lines, without_request_notes
from reveal.cli.invocation import COMMANDS, RETIREMENTS
from reveal.cli.routing.declared import declared_adapter_class

# noun -> (CLI argv after the noun, URI suffix after `noun://proj`)
CASES = {
    'ast': ([], ''),
    'architecture': ([], ''),
    'calls': (['--callers', 'serve'], '?callers=serve'),
    'claude': ([], ''),
    'codex': ([], ''),
    'contracts': ([], ''),
    'deps': ([], ''),
    'diff': ([], ''),
    'env': ([], ''),
    'hotspots': ([], ''),
    'imports': ([], ''),
    'git': ([], ''),
    'json': ([], ''),
    'markdown': ([], ''),
    'metrics': ([], ''),
    'overview': ([], ''),
    'pack': ([], ''),
    'patches': ([], ''),
    'sqlite': ([], ''),
    'xlsx': ([], ''),
    'surface': ([], ''),
    'testability': ([], ''),
    'trace': (['--from', 'serve'], '?from=serve'),
}
NOUNS = sorted(CASES)
# env's resource: a variable the fixture sets, never one the host owns (V042, BACK-2678).
ENV_VARIABLE = 'REVEAL_PARITY_VARIABLE'
# diff's resource: a pair of the project's directories that differ, so it walks as the other walking nouns' targets do
# (BACK-2214). One word on the subcommand, as its URI spells it (``reveal diff LEFT:RIGHT``);
# test_diff_vocabulary_back2214 holds the two-word ``reveal diff LEFT RIGHT`` and a file pair to it.
DIFF_PAIR = 'proj:proj/tests'
# A noun whose default answer is not a findings view gates the view that is (imports: BACK-1054 S4;
# metrics: the hotspots ranking, BACK-2149).
FINDINGS_VIEWS = {'imports': (['--unused'], '?unused'), 'metrics': (['--hotspots'], '?hotspots=true'),
                  'sqlite': (['--view', 'health'], '?view=health')}  # the fixture database has an orphan foreign key

APP = '''\
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass


class Store(ABC):
    @abstractmethod
    def get(self, key):
        ...


@dataclass
class Item:
    name: str


def load(key):
    return os.getenv(key)


def serve(key):
    if key:
        return load(key)
    return None


def branchy(x):
    if x == 0:
        return 0
    if x == 1:
        return 1
    if x == 2:
        return 2
    if x == 3:
        return 3
    if x == 4:
        return 4
    if x == 5:
        return 5
    if x == 6:
        return 6
    if x == 7:
        return 7
    if x == 8:
        return 8
    if x == 9:
        return 9
    if x == 10:
        return 10
    if x == 11:
        return 11
    if x == 12:
        return 12
    if x == 13:
        return 13
    if x == 14:
        return 14
    if x == 15:
        return 15
    if x == 16:
        return 16
    if x == 17:
        return 17
    if x == 18:
        return 18
    if x == 19:
        return 19
    if x == 20:
        return 20
    if x == 21:
        return 21
    if x == 22:
        return 22
    if x == 23:
        return 23
    if x == 24:
        return 24
    return -1
'''


# A retired noun's note names the spelling used (``reveal trace`` vs ``trace://``), so it differs
# between the two spellings by design. The rows are lifted here so the rest of the answer is
# compared byte for byte; test_a_retired_nouns_spellings_differ_only_by_their_own_note puts them back.
RETIRED_NOUN_ROWS = ('subcommand:trace', 'scheme:trace', 'subcommand:testability', 'scheme:testability',
                     'subcommand:deps', 'scheme:deps', 'subcommand:hotspots', 'scheme:hotspots')


@pytest.fixture
def project(tmp_path, monkeypatch):
    for key in RETIRED_NOUN_ROWS:
        monkeypatch.delitem(RETIREMENTS, key)
    monkeypatch.chdir(tmp_path)
    from claude_session_fixture import build_claude_home
    # Environment tests can reload the implementation and replace the registry class.
    ClaudeAdapter = declared_adapter_class('claude')
    claude = build_claude_home(tmp_path / 'home')
    monkeypatch.setattr(ClaudeAdapter, 'CLAUDE_HOME', claude)
    monkeypatch.setattr(ClaudeAdapter, 'CONVERSATION_BASE', claude / 'projects')
    from codex_session_fixture import build_codex_home
    CodexAdapter = declared_adapter_class('codex')
    codex = build_codex_home(tmp_path / 'codex-home')
    monkeypatch.setattr(CodexAdapter, 'CODEX_HOME', codex)
    monkeypatch.setattr(CodexAdapter, 'CODEX_DB', codex / 'state_5.sqlite')
    import sqlite3
    from contextlib import closing
    with closing(sqlite3.connect(tmp_path / 'app.db')) as connection, connection:  # sqlite's resource, beside proj
        connection.executescript('CREATE TABLE users(id INTEGER PRIMARY KEY);'
                                 'CREATE TABLE posts(id INTEGER, user_id INTEGER REFERENCES users(id));'
                                 'INSERT INTO posts VALUES (1, 9);')
    from test_retirements_back2066 import sample_workbook
    sample_workbook(tmp_path)  # xlsx's resource, beside proj (BACK-2626)
    monkeypatch.setenv(ENV_VARIABLE, 'parity-value')  # env's resource (BACK-2626)
    root = tmp_path / 'proj'
    (root / 'tests').mkdir(parents=True)
    (root / 'app.py').write_text(APP, encoding='utf-8')
    (root / 'data.json').write_text('{"items": [1, 2]}', encoding='utf-8')
    (root / 'tests' / 'test_app.py').write_text(
        'from app import serve\n\n\ndef test_serve():\n    assert serve("") is None\n', encoding='utf-8')
    import pygit2
    repo = pygit2.init_repository(str(root))
    for file in ('app.py', 'data.json', 'tests/test_app.py'):
        repo.index.add(file)
    repo.index.write()
    sig = pygit2.Signature('Fixture', 'fixture@example.com', 1700000000, 0)
    repo.create_commit('HEAD', sig, sig, 'fixture', repo.index.write_tree(), [])
    return root


def argv_for(noun, spelling, resource='proj'):
    cli, query = CASES[noun]
    if noun in ('claude', 'codex') and resource == 'proj':
        resource = 'sessions'
    if noun == 'sqlite' and resource == 'proj':
        resource = 'app.db'
    if noun == 'xlsx' and resource == 'proj':
        resource = 'book.xlsx'
    if noun == 'env' and resource == 'proj':
        resource = ENV_VARIABLE
    if noun == 'diff':
        resource = DIFF_PAIR if resource == 'proj' else f'{resource}:{resource}'
    if noun == 'json':
        resource += '/data.json'
    if spelling == 'cli':
        return [noun, resource, *cli]
    return [f'{noun}://{resource}{query}']


def run(noun, spelling, *extra, resource='proj'):
    walk_flags = ['--respect-gitignore=off'] if declared_adapter_class(noun).RESOURCE_SPEC.walks else []
    return _run_reveal_direct(*argv_for(noun, spelling, resource), *walk_flags, *extra)


def architecture_retirement(spelling):
    key = f'{"subcommand" if spelling == "cli" else "scheme"}:architecture'
    entry = RETIREMENTS[key]
    return {'type': 'retired_spelling', 'code': 'retired_spelling', 'message': entry.text,
            'field': key, 'old': entry.old, 'replacement': entry.replacement, 'stage': entry.stage}


def without_architecture_note(noun, answer, spelling):
    """Validate the one central transport record before removing exactly that record."""
    result = without_request_notes(copy.deepcopy(answer))  # the URI request's own note (BACK-2716)
    if noun == 'architecture':
        warnings = result['meta']['warnings']
        records = [warning for warning in warnings
                   if warning.get('code') == 'retired_spelling' or warning.get('type') == 'retired_spelling']
        expected = architecture_retirement(spelling)
        assert records == [expected]
        warnings.remove(expected)
    return result


def _carries_retirement(stdout):
    """A JSON answer that carries the retired_spelling entry: then the note is not also on stderr (BACK-2659)."""
    try:
        document = json.loads(stdout)
    except ValueError:
        return False
    warnings = (document.get('meta') or {}).get('warnings') or [] if isinstance(document, dict) else []
    return any(isinstance(w, dict) and w.get('code') == 'retired_spelling' for w in warnings)


def parity_stderr(noun, stderr, spelling, *, noted=True, stdout=''):
    stderr = without_request_note_lines(stderr)
    if noun != 'architecture':
        return stderr
    line = f"note: {architecture_retirement(spelling)['message']}\n"
    on_stderr = noted and not _carries_retirement(stdout)
    assert stderr.count(line) == int(on_stderr)
    return stderr.replace(line, '', 1) if on_stderr else stderr


def assert_equal_stdout(noun, left, right):
    if left.strip().startswith('{'):
        assert_equal_answers(noun, json.loads(left), json.loads(right))
    else:
        assert without_request_note_lines(left) == without_request_note_lines(right)


def assert_equal_answers(noun, left, right):
    """Only proven transport spelling facts may differ; all analysis and diagnostics stay exact."""
    a = without_architecture_note(noun, left, "cli")
    b = without_architecture_note(noun, right, "uri")
    if 'execution' in a:
        assert a['execution']['command'].startswith(f'reveal {noun} ')
        assert b['execution']['command'].startswith(f'reveal {noun}://')
        del a['execution']['command']
        del b['execution']['command']
    assert a == b


def test_every_declared_noun_has_a_row():
    declared = sorted(n for n, spec in COMMANDS.items() if spec.declared_adapter)
    assert declared == NOUNS


@pytest.mark.parametrize('provenance', [False, True])
@pytest.mark.parametrize('noun', NOUNS)
def test_json_answers_match(project, noun, provenance):
    extra = ['--format', 'json'] + (['--provenance'] if provenance else [])
    a, b = run(noun, 'cli', *extra), run(noun, 'uri', *extra)
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    left, right = json.loads(a.stdout), json.loads(b.stdout)
    assert left.get('type'), 'an empty answer would compare equal vacuously'
    if provenance:
        assert left['execution']['command'].startswith(f'reveal {noun} ')
        assert right['execution']['command'].startswith(f'reveal {noun}://')
    assert_equal_answers(noun, left, right)
    assert parity_stderr(noun, a.stderr, 'cli', stdout=a.stdout) == parity_stderr(noun, b.stderr, 'uri', stdout=b.stdout)


@pytest.mark.parametrize('noun', NOUNS)
def test_text_output_matches(project, noun):
    a, b = run(noun, 'cli'), run(noun, 'uri')
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    assert a.stdout.strip()
    assert_equal_stdout(noun, a.stdout, b.stdout)
    assert parity_stderr(noun, a.stderr, 'cli', stdout=a.stdout) == parity_stderr(noun, b.stderr, 'uri', stdout=b.stdout)


@pytest.mark.parametrize('noun', NOUNS)
def test_requested_artifact_equals_the_primary_json(project, tmp_path, noun):
    docs = {}
    for spelling in ('cli', 'uri'):
        artifact = tmp_path / f'{spelling}.json'
        result = run(noun, spelling, '--output', f'json={artifact}')
        assert result.returncode == 0, result.stderr
        parity_stderr(noun, result.stderr, spelling, stdout=result.stdout)
        docs[spelling] = json.loads(artifact.read_text(encoding='utf-8'))
        primary = run(noun, spelling, '--format', 'json')
        assert primary.returncode == 0, primary.stderr
        parity_stderr(noun, primary.stderr, spelling, stdout=primary.stdout)
        assert docs[spelling] == json.loads(primary.stdout)
    assert_equal_answers(noun, docs['cli'], docs['uri'])


@pytest.mark.parametrize('noun', NOUNS)
def test_failed_artifact_write_keeps_the_answer_and_exits_three(project, tmp_path, noun):
    # A directory cannot be written as a file on any platform.
    a = run(noun, 'cli', '--also-json', str(tmp_path))
    b = run(noun, 'uri', '--also-json', str(tmp_path))
    assert a.returncode == b.returncode == 3, (a.stderr, b.stderr)
    assert a.stdout == b.stdout and a.stdout.strip()
    assert parity_stderr(noun, a.stderr, 'cli', stdout=a.stdout) == parity_stderr(noun, b.stderr, 'uri', stdout=b.stdout)
    assert 'artifact' in a.stderr.lower()
    assert 'Traceback' not in a.stderr


@pytest.mark.parametrize('fmt', ['text', 'json'])
@pytest.mark.parametrize('noun', NOUNS)
def test_missing_resource_is_rejected_alike(project, noun, fmt):
    resource = 'proj/absent.py' if noun == 'git' else 'absent'
    a = run(noun, 'cli', '--format', fmt, resource=resource)
    b = run(noun, 'uri', '--format', fmt, resource=resource)
    assert a.returncode == b.returncode == 2, (a.stderr, b.stderr)
    assert_equal_stdout(noun, a.stdout, b.stdout)
    assert parity_stderr(noun, a.stderr, 'cli', stdout=a.stdout) == parity_stderr(noun, b.stderr, 'uri', stdout=b.stdout)


@pytest.mark.parametrize('gate', ['findings', 'none'])
@pytest.mark.parametrize('noun', NOUNS)
def test_fail_on_means_the_same_before_after_and_on_a_uri(project, noun, gate):
    """The project carries an unused import and a branchy function, so a declared gate has something to match."""
    cli, query = FINDINGS_VIEWS.get(noun, CASES[noun])
    target = {'json': 'proj/data.json', 'claude': 'sessions', 'codex': 'sessions', 'sqlite': 'app.db', 'env': ENV_VARIABLE,
              'xlsx': 'book.xlsx', 'diff': DIFF_PAIR}.get(noun, 'proj')
    walk_flags = ['--respect-gitignore=off'] if declared_adapter_class(noun).RESOURCE_SPEC.walks else []
    spellings = {
        'after': [noun, target, *cli, '--fail-on', gate],
        'before': ['--fail-on', gate, noun, target, *cli],
        'uri': [f'{noun}://{target}{query}', '--fail-on', gate],
    }
    runs = {k: _run_reveal_direct(*v, '--format', 'json', *walk_flags) for k, v in spellings.items()}
    if gate == 'none':
        expected = 0
    elif 'findings' in declared_adapter_class(noun).FINDINGS_POLICIES:
        expected = 1
    else:
        expected = 2
    for name, result in runs.items():
        assert result.returncode == expected, (name, result.stderr)
    assert runs['after'].stdout == runs['before'].stdout
    assert_equal_stdout(noun, runs['after'].stdout, runs['uri'].stdout)
    if expected == 2:
        assert runs['after'].stderr == runs['before'].stderr
        assert parity_stderr(noun, runs['after'].stderr, 'cli', stdout=runs['after'].stdout) == parity_stderr(
            noun, runs['uri'].stderr, 'uri', noted=noun != 'architecture', stdout=runs['uri'].stdout)
    else:
        assert parity_stderr(noun, runs['after'].stderr, 'cli', stdout=runs['after'].stdout) == parity_stderr(
            noun, runs['uri'].stderr, 'uri', stdout=runs['uri'].stdout)
    if expected == 2:
        assert 'not supported' in runs['uri'].stderr


VALUE_CASES = [
    ['--max-items', '0'], ['--max-items', '1'], ['--max-items', '-1'], ['--max-items', 'abc'],
    ['--max-snippet-chars', '0'], ['--max-snippet-chars', '-3'], ['--fields', 'nope'], ['--verbose'],
    ['--format', 'json', '--max-items', '0'], ['--format', 'json', '--fields', 'type'], ['--format', 'bogus'],
    # the global --all reaches a noun's subcommand as it reaches its URI (BACK-2654 item 1c)
    ['--all'], ['--format', 'json', '--all'],
]


def rejection(stderr):
    """The request's error lines, which a typed command and its URI answer alike."""
    return [line for line in stderr.splitlines() if line.startswith('Error')]


def ignored_flags(stderr):
    """The flags a 'has no effect' note names; the sentence names the spelling, so compare the flags."""
    return sorted(line.split()[2] for line in stderr.splitlines() if line.startswith('Note: ') and 'has no effect' in line)


@pytest.mark.parametrize('flags', VALUE_CASES, ids=' '.join)
@pytest.mark.parametrize('noun', NOUNS)
def test_option_values_are_read_alike(project, noun, flags):
    """Zero, negative, malformed and unused values: same exit, same stdout, same ignored-flag notes."""
    a, b = run(noun, 'cli', *flags), run(noun, 'uri', *flags)
    assert a.returncode == b.returncode, (a.stderr, b.stderr)
    assert_equal_stdout(noun, a.stdout, b.stdout)
    assert ignored_flags(a.stderr) == ignored_flags(b.stderr)
    if a.returncode == 2:
        # no answer: a parser-level rejection (a usage message) in both spellings, or the same request rejection
        # (rule 4: --verbose is --detail full, which the request lacks; BACK-2654)
        assert not a.stdout and not b.stdout
        assert ('usage:' in a.stderr and 'usage:' in b.stderr) or rejection(a.stderr) == rejection(b.stderr) != []
    else:
        assert a.returncode == 0 and a.stdout.strip()
        if noun == 'architecture':
            parity_stderr(noun, a.stderr, 'cli', stdout=a.stdout)
            parity_stderr(noun, b.stderr, 'uri', stdout=b.stdout)


# (noun, CLI argv, URI suffix) where --all lifts a cap the wider tree exceeds (default 10 ranked files/functions)
ALL_LIFTS = [('metrics', ['--hotspots'], '?hotspots=true'), ('metrics', ['--view', 'hotspots'], '?view=hotspots'),
             ('hotspots', [], '')]


@pytest.mark.parametrize('noun, cli, query', ALL_LIFTS, ids=['metrics-legacy-hotspots', 'metrics-view', 'hotspots'])
def test_all_lifts_the_same_cap_on_both_forms(project, noun, cli, query):
    """BACK-2654 item 1c: `reveal NOUN PATH --all` answers as `NOUN://PATH --all` (the subcommand used to exit 2
    "unsupported control '--all'"), and the cap it lifts is the one the selected answer reads."""
    branches = ''.join(f'    if x == {i}:\n        return {i}\n' for i in range(12))
    for n in range(14):
        (project / f'hot_{n}.py').write_text(f'def hot_{n}(x):\n{branches}    return -1\n', encoding='utf-8')

    def answer(*flags):
        a = _run_reveal_direct(noun, 'proj', *cli, '--no-gitignore', '--format', 'json', *flags)
        b = _run_reveal_direct(f'{noun}://proj{query}', '--no-gitignore', '--format', 'json', *flags)
        assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
        left, right = json.loads(a.stdout), json.loads(b.stdout)
        assert_equal_answers(noun, left, right)
        return left

    def ranked(result):
        return len(result.get('hotspots') or result.get('file_hotspots') or [])

    capped, lifted = answer(), answer('--all')
    assert ranked(capped) == 10 and ranked(lifted) > 10, (ranked(capped), ranked(lifted))


@pytest.mark.parametrize('noun', ['ast', 'calls', 'git', 'metrics'])
def test_all_beside_a_different_limit_is_one_invalid_request_on_both_forms(project, noun):
    """--all sets the noun's limit, so beside --limit 1 it names both flags and exits 2 on both forms (rule 1). It
    sets the cap of an answer that reads it: calls' ranking (its callers answer has none, BACK-2656)."""
    ranking = {'calls': ['--sort=-callers']}.get(noun)
    if ranking:
        walk = ['--respect-gitignore=off']
        a = _run_reveal_direct(noun, 'proj', *ranking, *walk, '--all', '--limit', '1')
        b = _run_reveal_direct(f'{noun}://proj?sort=-callers', *walk, '--all', '--limit', '1')
    else:
        a, b = run(noun, 'cli', '--all', '--limit', '1'), run(noun, 'uri', '--all', '--limit', '1')
    assert a.returncode == b.returncode == 2, (a.stderr, b.stderr)
    assert rejection(a.stderr) == rejection(b.stderr) == [
        f'Error ({noun}://): --limit conflicts with --all: both set limit with different values; give one']


@pytest.mark.parametrize('noun', NOUNS)
def test_a_harmless_warning_is_shown_and_never_makes_a_complete_answer_fail(project, monkeypatch, noun):
    adapter = declared_adapter_class(noun)
    original = adapter.get_structure
    calls = []

    def observed(self, **kwargs):
        calls.append(noun)
        result = original(self, **kwargs)
        result.setdefault('meta', {}).setdefault('warnings', []).append(
            {'type': 'informational', 'message': 'harmless observation'})
        return result

    monkeypatch.setattr(adapter, 'get_structure', observed)
    answers = []
    for spelling in ('cli', 'uri'):
        result = run(noun, spelling, '--format', 'json')
        assert result.returncode == 0, (spelling, result.stderr)
        answers.append(json.loads(result.stdout))
        if noun == 'architecture':
            assert answers[-1]['meta']['warnings'].count(
                {'type': 'informational', 'message': 'harmless observation'}) == 1
        else:  # the URI request's own note rides beside it (BACK-2716)
            assert [w for w in without_request_notes(answers[-1])['meta']['warnings']][-1]['message'] == 'harmless observation'
    assert len(calls) == 2, 'the patched entry point was not the one the noun runs'
    assert_equal_answers(noun, *answers)


@pytest.mark.parametrize('noun', ['trace', 'testability', 'deps', 'hotspots'])
def test_a_retired_nouns_spellings_differ_only_by_their_own_note(project, monkeypatch, noun):
    """trace (BACK-2066 slice D), testability (BACK-2160), deps (BACK-1054 S4) and hotspots (BACK-2149): each spelling carries its own
    retired_spelling warning and note; without them the two answers are equal."""
    monkeypatch.undo()
    monkeypatch.chdir(project.parent)
    a, b = run(noun, 'cli', '--format', 'json'), run(noun, 'uri', '--format', 'json')
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    left, right = json.loads(a.stdout), json.loads(b.stdout)
    fields = []
    for doc in (left, right):
        warnings = doc['meta']['warnings']
        fields.append([w['field'] for w in warnings if w.get('code') == 'retired_spelling'])
        doc['meta']['warnings'] = [w for w in warnings if w.get('code') != 'retired_spelling']
    assert fields == [[f'subcommand:{noun}'], [f'scheme:{noun}']]
    assert_equal_answers(noun, left, right)
    # The JSON answers carry the notes (fields above), so neither is also on stderr (BACK-2659); text prints each.
    assert [[line for line in r.stderr.splitlines() if 'deprecated' in line] for r in (a, b)] == [[], []]
    a, b = run(noun, 'cli'), run(noun, 'uri')
    notes = [[line for line in r.stderr.splitlines() if 'deprecated' in line] for r in (a, b)]
    assert notes == [[f'note: {RETIREMENTS[f"subcommand:{noun}"].text}'], [f'note: {RETIREMENTS[f"scheme:{noun}"].text}']]


def test_the_comparison_fails_on_a_changed_count_or_dropped_diagnostic():
    answer = {'type': 'x', 'total': 2, 'meta': {'warnings': [{'message': 'incomplete'}]}}
    changed = copy.deepcopy(answer)
    changed['total'] = 1
    with pytest.raises(AssertionError):
        assert_equal_answers('x', answer, changed)
    changed = copy.deepcopy(answer)
    changed['meta']['warnings'].clear()
    with pytest.raises(AssertionError):
        assert_equal_answers('x', answer, changed)


@pytest.mark.parametrize('field', ['type', 'code', 'message', 'field', 'old', 'replacement', 'stage'])
@pytest.mark.parametrize('mutation', ['missing', 'changed'])
def test_architecture_note_must_match_the_complete_central_record(field, mutation):
    warning = architecture_retirement('cli')
    if mutation == 'missing':
        del warning[field]
    else:
        warning[field] = 'corrupted'
    answer = {'meta': {'warnings': [warning]}}
    with pytest.raises(AssertionError):
        without_architecture_note('architecture', answer, 'cli')


@pytest.mark.parametrize('copies', [0, 2])
def test_architecture_note_must_appear_exactly_once(copies):
    answer = {'meta': {'warnings': [architecture_retirement('cli')] * copies}}
    with pytest.raises(AssertionError):
        without_architecture_note('architecture', answer, 'cli')


@pytest.mark.parametrize('change', ['count', 'diagnostic'])
def test_architecture_comparison_still_rejects_analysis_and_diagnostic_loss(change):
    left = {'type': 'overview', 'total': 2, 'meta': {'warnings': [
        architecture_retirement('cli'), {'type': 'informational', 'message': 'keep me'}]}}
    right = copy.deepcopy(left)
    right['meta']['warnings'][0] = architecture_retirement('uri')
    assert_equal_answers('architecture', left, right)
    if change == 'count':
        right['total'] = 1
    else:
        right['meta']['warnings'].pop()
    with pytest.raises(AssertionError):
        assert_equal_answers('architecture', left, right)


@pytest.mark.parametrize('copies', [0, 2])
def test_architecture_stderr_note_must_appear_exactly_once(copies):
    line = f"note: {architecture_retirement('cli')['message']}\n"
    with pytest.raises(AssertionError):
        parity_stderr('architecture', line * copies, 'cli')


def test_architecture_stderr_normalization_preserves_every_other_line():
    line = f"note: {architecture_retirement('cli')['message']}\n"
    assert parity_stderr('architecture', 'first\n' + line + 'last\n', 'cli') == 'first\nlast\n'
    with pytest.raises(AssertionError):
        parity_stderr('architecture', line, 'uri')
    assert parity_stderr('overview', line, 'cli') == line
