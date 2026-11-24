"""Patches' trusted test roots are ``--test-paths PATHS`` (Scott 2026-11-23, D21, BACK-2774).

``--tests`` is the shared test/support policy (``include|exclude``) on every noun that declares it. The pressure view's
list of test roots, trusted as the suite, was also spelled ``--tests PATHS`` / ``?tests=``, so an agent taught
``--tests exclude`` by metrics or surface got "Test path not found: exclude". The roots are ``--test-paths``: one
answer on the subcommand, the URI, ``api.query`` and MCP. The old spelling answers as ``--test-paths`` with its
replaced-by note until the cut (note stage), on every transport and on the retired ``testability`` twin.

Also here (ruling S4 on the V1 inventory): testability's ``limit`` takes patches' shape, so ``--limit -1`` is an
invalid request (exit 2) as it is on patches, instead of reading a negative cap as uncapped.
"""
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run, without_request_notes, without_retirement_notes

PATCH = "from unittest import mock\n\n\ndef test_x():\n    with mock.patch('pkg.mod.target'):\n        pass\n"
BOUNDARY = ("import subprocess\nimport requests\n\n\n"
            "def target(url):\n"
            "    requests.get(url)\n"
            "    subprocess.run(['ls'])\n"
            "    return 1\n")
# The suite lives under a name the conventions do not find (qa/check_mod.py): only the named roots find its patch.
REPO, QA = 'repo', str(Path('repo', 'qa'))
NOTE = 'use --test-paths PATHS'


def _w(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _w(tmp_path / REPO / 'pkg' / 'mod.py', BOUNDARY)
    _w(tmp_path / REPO / 'qa' / 'check_mod.py', PATCH)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _doc(result):
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _retired(doc):
    return [w for w in (doc.get('meta') or {}).get('warnings', []) if w.get('code') == 'retired_spelling']


def _answer(doc):
    """The answer without its notes (the designed difference between spellings and transports) and without the
    echoed command line, which names the transport's own spelling."""
    doc = without_request_notes(without_retirement_notes(json.loads(json.dumps(doc, default=str))))
    meta = doc.get('meta') or {}
    meta.get('execution', {}).pop('command', None)
    return doc


def _cli(*spelling):
    return run('patches', REPO, '--view', 'pressure', *spelling, '--format', 'json')


def test_test_paths_names_the_trusted_suite(repo):
    doc = _doc(_cli('--test-paths', QA))
    assert doc['type'] == 'testability_report'
    assert [Path(p) for p in doc['tests']] == [Path(QA)]
    assert doc['summary']['total_patch_uses'] == 1  # the named root's patch, which the default policy never finds
    assert not _retired(doc)
    default = _doc(_cli())
    assert default['summary']['total_patch_uses'] == 0  # positive control: without the roots there is no patch


def test_test_paths_is_one_answer_on_every_transport(repo):
    from reveal import api
    expected = _answer(_doc(_cli('--test-paths', QA)))
    uri = f'patches://{REPO}?view=pressure&test-paths={QA}'
    answers = {
        'URI': _answer(_doc(run(uri, '--format', 'json'))),
        'api.query keyword': _answer(api.query('patches', REPO, view='pressure', test_paths=[QA])),
        'api.query URI': _answer(api.query(uri)),
    }
    try:
        from reveal.mcp_server import reveal_run
    except ImportError:  # the optional mcp extra
        reveal_run = None
    if reveal_run is not None:
        shown = reveal_run(['patches', REPO, '--view', 'pressure', '--test-paths', QA, '--format', 'json'])
        answers['MCP reveal_run'] = _answer(json.loads(shown))
    assert {name: answer == expected for name, answer in answers.items()} == {name: True for name in answers}


@pytest.mark.parametrize('noun', ['patches', 'testability'])
def test_the_old_spelling_answers_as_test_paths_with_its_note(repo, noun):
    head = ['patches', REPO, '--view', 'pressure'] if noun == 'patches' else ['testability', REPO]
    canonical = run(*head, '--test-paths', QA, '--format', 'json')
    legacy = run(*head, '--tests', QA, '--format', 'json')
    assert legacy.returncode == canonical.returncode == 0, legacy.stderr + canonical.stderr
    assert NOTE in legacy.stderr and NOTE not in canonical.stderr
    legacy_doc = json.loads(legacy.stdout)
    assert [w['field'] for w in _retired(legacy_doc) if NOTE in w['message']] == [f'param:{noun}.tests']
    assert _answer(legacy_doc) == _answer(json.loads(canonical.stdout))


def test_the_old_uri_key_and_keyword_answer_with_the_note(repo):
    from reveal import api
    expected = _answer(_doc(_cli('--test-paths', QA)))
    uri = run(f'patches://{REPO}?view=pressure&tests={QA}', '--format', 'json')
    assert uri.returncode == 0 and NOTE in uri.stderr, uri.stderr
    keyword = api.query('patches', REPO, view='pressure', tests=[QA])
    assert any(NOTE in w['message'] for w in _retired(keyword)), _retired(keyword)
    assert _answer(json.loads(uri.stdout)) == _answer(keyword) == expected


def test_the_old_and_new_spelling_with_different_roots_conflict(repo):
    both = _cli('--tests', REPO, '--test-paths', QA)
    assert both.returncode == 2 and '--tests' in both.stderr and '--test-paths' in both.stderr, both.stderr
    same = _cli('--tests', QA, '--test-paths', QA)
    assert same.returncode == 0, same.stderr
    assert _answer(json.loads(same.stdout)) == _answer(_doc(_cli('--test-paths', QA)))


def test_the_shared_tests_policy_keeps_its_meaning_on_its_nouns(repo):
    """Negative control: --tests include|exclude is the shared policy where it was; the rename touches patches only."""
    for noun in ('imports', 'surface'):
        result = run(noun, REPO, '--tests', 'exclude', '--format', 'json')
        assert result.returncode == 0 and 'test-paths' not in result.stderr, (noun, result.stderr)


def test_no_scannable_tests_teaches_test_paths(repo):
    """A tree with no test file the conventions find is declined, teaching the spelling that names the suite."""
    for request in (['patches', str(Path(REPO, 'pkg'))], ['patches', str(Path(REPO, 'pkg')), '--view', 'pressure']):
        result = run(*request)
        assert result.returncode == 0, result.stderr
        assert '--test-paths' in result.stdout + result.stderr and 'tests=<path>' not in result.stdout + result.stderr, \
            result.stdout + result.stderr


def test_the_test_scope_names_the_control_that_chose_the_files(repo):
    assert _doc(_cli('--test-paths', QA))['test_scope']['rule'] == 'test-paths'
    assert _doc(_cli())['test_scope']['rule'] == 'is_test_path'


@pytest.mark.parametrize('noun', ['patches', 'testability'])
def test_a_negative_limit_is_an_invalid_request(repo, noun):
    """S4: testability's cap takes patches' shape (minimum 0, zero is all); patches is the unaffected sibling."""
    head = ['patches', REPO, '--view', 'pressure'] if noun == 'patches' else ['testability', REPO]
    negative = run(*head, '--limit', '-1')
    assert negative.returncode == 2 and 'limit' in negative.stderr, (negative.returncode, negative.stderr)
    every = run(*head, '--limit', '0', '--format', 'json')
    assert every.returncode == 0, every.stderr
