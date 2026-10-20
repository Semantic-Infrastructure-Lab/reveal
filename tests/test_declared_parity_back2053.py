"""Phase 1 exit audit (BACK-2053): the nine declared nouns answer alike in both spellings.

One table drives every noun through `reveal NOUN ...` and `reveal NOUN://...`: parsed JSON equal except
the command spelling, same exits and visible diagnostics, provenance off/on, text, requested JSON
artifacts (success and failed write), and a rejected resource. Per-noun depth lives in the
test_declared_<noun>_* files; this file is the cross-noun gate and fails if a noun is added to
COMMANDS without a row here.
"""
import copy
import json

import pytest

from conftest import _run_reveal_direct
from reveal.cli.invocation import COMMANDS
from reveal.cli.routing.declared import declared_adapter_class

# noun -> (CLI argv after the noun, URI suffix after `noun://proj`)
CASES = {
    'architecture': ([], ''),
    'calls': (['--target', 'serve'], '?target=serve'),
    'contracts': ([], ''),
    'deps': ([], ''),
    'hotspots': ([], ''),
    'overview': ([], ''),
    'pack': ([], ''),
    'surface': ([], ''),
    'testability': ([], ''),
    'trace': (['--from', 'serve'], '?from=serve'),
}
NOUNS = sorted(CASES)

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


@pytest.fixture
def project(tmp_path, monkeypatch):
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


def assert_equal_answers(noun, left, right):
    """Only the command spelling may differ; a changed count or a dropped diagnostic must not pass."""
    a, b = copy.deepcopy(left), copy.deepcopy(right)
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
    assert a.stderr == b.stderr


@pytest.mark.parametrize('noun', NOUNS)
def test_text_output_matches(project, noun):
    a, b = run(noun, 'cli'), run(noun, 'uri')
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    assert a.stdout.strip()
    assert a.stdout == b.stdout
    assert a.stderr == b.stderr


@pytest.mark.parametrize('noun', NOUNS)
def test_requested_artifact_equals_the_primary_json(project, tmp_path, noun):
    docs = {}
    for spelling in ('cli', 'uri'):
        artifact = tmp_path / f'{spelling}.json'
        result = run(noun, spelling, '--also-json', str(artifact))
        assert result.returncode == 0, result.stderr
        docs[spelling] = json.loads(artifact.read_text(encoding='utf-8'))
    primary = json.loads(run(noun, 'cli', '--format', 'json').stdout)
    assert docs['cli'] == primary == docs['uri']


@pytest.mark.parametrize('noun', NOUNS)
def test_failed_artifact_write_keeps_the_answer_and_exits_three(project, tmp_path, noun):
    # A directory cannot be written as a file on any platform.
    a = run(noun, 'cli', '--also-json', str(tmp_path))
    b = run(noun, 'uri', '--also-json', str(tmp_path))
    assert a.returncode == b.returncode == 3, (a.stderr, b.stderr)
    assert a.stdout == b.stdout and a.stdout.strip()
    assert a.stderr == b.stderr
    assert 'artifact' in a.stderr.lower()
    assert 'Traceback' not in a.stderr


@pytest.mark.parametrize('fmt', ['text', 'json'])
@pytest.mark.parametrize('noun', NOUNS)
def test_missing_resource_is_rejected_alike(project, noun, fmt):
    a = run(noun, 'cli', '--format', fmt, resource='absent')
    b = run(noun, 'uri', '--format', fmt, resource='absent')
    assert a.returncode == b.returncode == 2, (a.stderr, b.stderr)
    assert a.stdout == b.stdout
    assert a.stderr == b.stderr


@pytest.mark.parametrize('gate', ['findings', 'none'])
@pytest.mark.parametrize('noun', NOUNS)
def test_fail_on_means_the_same_before_after_and_on_a_uri(project, noun, gate):
    """The project carries an unused import and a branchy function, so a declared gate has something to match."""
    cli, query = CASES[noun]
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
    assert len({r.stdout for r in runs.values()}) == 1
    if expected == 2:
        assert len({r.stderr for r in runs.values()}) == 1
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
    assert a.stdout == b.stdout
    assert ignored_flags(a.stderr) == ignored_flags(b.stderr)
    if a.returncode == 2:
        # parser-level rejection: no answer, a usage message in both spellings
        assert not a.stdout and 'usage:' in a.stderr and 'usage:' in b.stderr
    else:
        assert a.returncode == 0 and a.stdout.strip()


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
        assert answers[-1]['meta']['warnings'][-1]['message'] == 'harmless observation'
    assert len(calls) == 2, 'the patched entry point was not the one the noun runs'
    assert_equal_answers(noun, *answers)


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
