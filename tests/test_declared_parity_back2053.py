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

from conftest import _run_reveal_direct
from reveal.cli.invocation import COMMANDS, RETIREMENTS
from reveal.cli.routing.declared import declared_adapter_class

# noun -> (CLI argv after the noun, URI suffix after `noun://proj`)
CASES = {
    'architecture': ([], ''),
    'calls': (['--callers', 'serve'], '?callers=serve'),
    'contracts': ([], ''),
    'deps': ([], ''),
    'hotspots': ([], ''),
    'imports': ([], ''),
    'metrics': ([], ''),
    'overview': ([], ''),
    'pack': ([], ''),
    'patches': ([], ''),
    'surface': ([], ''),
    'testability': ([], ''),
    'trace': (['--from', 'serve'], '?from=serve'),
}
NOUNS = sorted(CASES)
# A noun whose default answer is not a findings view gates the view that is (imports: BACK-1054 S4).
FINDINGS_VIEWS = {'imports': (['--unused'], '?unused')}

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
                     'subcommand:deps', 'scheme:deps')


@pytest.fixture
def project(tmp_path, monkeypatch):
    for key in RETIRED_NOUN_ROWS:
        monkeypatch.delitem(RETIREMENTS, key)
    monkeypatch.chdir(tmp_path)
    root = tmp_path / 'proj'
    (root / 'tests').mkdir(parents=True)
    (root / 'app.py').write_text(APP, encoding='utf-8')
    (root / 'tests' / 'test_app.py').write_text(
        'from app import serve\n\n\ndef test_serve():\n    assert serve("") is None\n', encoding='utf-8')
    return root


def argv_for(noun, spelling, resource='proj'):
    cli, query = CASES[noun]
    if spelling == 'cli':
        return [noun, resource, *cli]
    return [f'{noun}://{resource}{query}']


def run(noun, spelling, *extra, resource='proj'):
    return _run_reveal_direct(*argv_for(noun, spelling, resource), '--no-gitignore', *extra)


def architecture_retirement(spelling):
    key = f'{"subcommand" if spelling == "cli" else "scheme"}:architecture'
    entry = RETIREMENTS[key]
    return {'type': 'retired_spelling', 'code': 'retired_spelling', 'message': entry.text,
            'field': key, 'old': entry.old, 'replacement': entry.replacement, 'stage': entry.stage}


def without_architecture_note(noun, answer, spelling):
    """Validate the one central transport record before removing exactly that record."""
    result = copy.deepcopy(answer)
    if noun == 'architecture':
        warnings = result['meta']['warnings']
        records = [warning for warning in warnings
                   if warning.get('code') == 'retired_spelling' or warning.get('type') == 'retired_spelling']
        expected = architecture_retirement(spelling)
        assert records == [expected]
        warnings.remove(expected)
    return result


def parity_stderr(noun, stderr, spelling, *, noted=True):
    if noun != 'architecture':
        return stderr
    line = f"note: {architecture_retirement(spelling)['message']}\n"
    assert stderr.count(line) == int(noted)
    return stderr.replace(line, '', 1) if noted else stderr


def assert_equal_stdout(noun, left, right):
    if noun == 'architecture' and left.strip().startswith('{'):
        assert_equal_answers(noun, json.loads(left), json.loads(right))
    else:
        assert left == right


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
    assert parity_stderr(noun, a.stderr, 'cli') == parity_stderr(noun, b.stderr, 'uri')


@pytest.mark.parametrize('noun', NOUNS)
def test_text_output_matches(project, noun):
    a, b = run(noun, 'cli'), run(noun, 'uri')
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    assert a.stdout.strip()
    assert_equal_stdout(noun, a.stdout, b.stdout)
    assert parity_stderr(noun, a.stderr, 'cli') == parity_stderr(noun, b.stderr, 'uri')


@pytest.mark.parametrize('noun', NOUNS)
def test_requested_artifact_equals_the_primary_json(project, tmp_path, noun):
    docs = {}
    for spelling in ('cli', 'uri'):
        artifact = tmp_path / f'{spelling}.json'
        result = run(noun, spelling, '--output', f'json={artifact}')
        assert result.returncode == 0, result.stderr
        parity_stderr(noun, result.stderr, spelling)
        docs[spelling] = json.loads(artifact.read_text(encoding='utf-8'))
        primary = run(noun, spelling, '--format', 'json')
        assert primary.returncode == 0, primary.stderr
        parity_stderr(noun, primary.stderr, spelling)
        assert docs[spelling] == json.loads(primary.stdout)
    assert_equal_answers(noun, docs['cli'], docs['uri'])


@pytest.mark.parametrize('noun', NOUNS)
def test_failed_artifact_write_keeps_the_answer_and_exits_three(project, tmp_path, noun):
    # A directory cannot be written as a file on any platform.
    a = run(noun, 'cli', '--also-json', str(tmp_path))
    b = run(noun, 'uri', '--also-json', str(tmp_path))
    assert a.returncode == b.returncode == 3, (a.stderr, b.stderr)
    assert a.stdout == b.stdout and a.stdout.strip()
    assert parity_stderr(noun, a.stderr, 'cli') == parity_stderr(noun, b.stderr, 'uri')
    assert 'artifact' in a.stderr.lower()
    assert 'Traceback' not in a.stderr


@pytest.mark.parametrize('fmt', ['text', 'json'])
@pytest.mark.parametrize('noun', NOUNS)
def test_missing_resource_is_rejected_alike(project, noun, fmt):
    a = run(noun, 'cli', '--format', fmt, resource='absent')
    b = run(noun, 'uri', '--format', fmt, resource='absent')
    assert a.returncode == b.returncode == 2, (a.stderr, b.stderr)
    assert_equal_stdout(noun, a.stdout, b.stdout)
    assert parity_stderr(noun, a.stderr, 'cli') == parity_stderr(noun, b.stderr, 'uri')


@pytest.mark.parametrize('gate', ['findings', 'none'])
@pytest.mark.parametrize('noun', NOUNS)
def test_fail_on_means_the_same_before_after_and_on_a_uri(project, noun, gate):
    """The project carries an unused import and a branchy function, so a declared gate has something to match."""
    cli, query = FINDINGS_VIEWS.get(noun, CASES[noun])
    spellings = {
        'after': [noun, 'proj', *cli, '--fail-on', gate],
        'before': ['--fail-on', gate, noun, 'proj', *cli],
        'uri': [f'{noun}://proj{query}', '--fail-on', gate],
    }
    runs = {k: _run_reveal_direct(*v, '--format', 'json', '--no-gitignore') for k, v in spellings.items()}
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
        assert parity_stderr(noun, runs['after'].stderr, 'cli') == parity_stderr(
            noun, runs['uri'].stderr, 'uri', noted=noun != 'architecture')
    else:
        assert parity_stderr(noun, runs['after'].stderr, 'cli') == parity_stderr(noun, runs['uri'].stderr, 'uri')
    if expected == 2:
        assert 'not supported' in runs['uri'].stderr


VALUE_CASES = [
    ['--max-items', '0'], ['--max-items', '1'], ['--max-items', '-1'], ['--max-items', 'abc'],
    ['--max-snippet-chars', '0'], ['--max-snippet-chars', '-3'], ['--fields', 'nope'], ['--verbose'],
    ['--format', 'json', '--max-items', '0'], ['--format', 'json', '--fields', 'type'], ['--format', 'bogus'],
]


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
        # parser-level rejection: no answer, a usage message in both spellings
        assert not a.stdout and 'usage:' in a.stderr and 'usage:' in b.stderr
    else:
        assert a.returncode == 0 and a.stdout.strip()
        if noun == 'architecture':
            parity_stderr(noun, a.stderr, 'cli')
            parity_stderr(noun, b.stderr, 'uri')


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
        else:
            assert answers[-1]['meta']['warnings'][-1]['message'] == 'harmless observation'
    assert len(calls) == 2, 'the patched entry point was not the one the noun runs'
    assert_equal_answers(noun, *answers)


@pytest.mark.parametrize('noun', ['trace', 'testability', 'deps'])
def test_a_retired_nouns_spellings_differ_only_by_their_own_note(project, monkeypatch, noun):
    """trace (BACK-2066 slice D), testability (BACK-2160) and deps (BACK-1054 S4): each spelling carries its own
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
