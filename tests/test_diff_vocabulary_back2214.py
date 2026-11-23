"""diff is a declared noun (BACK-2214): ``reveal diff LEFT RIGHT[/ELEMENT]`` is generated from the declaration
diff:// binds through, with the same answer and exit as ``diff://LEFT:RIGHT[/ELEMENT]`` on the CLI, the API and MCP.

Before: ``reveal diff a.py b.py`` was read as the file ``diff`` ("unrecognized arguments: b.py"); diff:// read no
control, so an unknown key or API keyword was a warning and the comparison ran; ``DiffAdapter`` took ``(left, right)``
where every declared noun takes ``(resource, query)`` and typed ``params=``; a side that does not exist and has no
analyzer for its name (``absent``) answered "No analyzer found" as a failed analysis (exit 3).

Now: the pair is the resource (one word per side on the subcommand, or ``LEFT:RIGHT`` as the URI spells it); the one
control is the walk's ``exclude`` (a directory pair walks both sides, and the walk policy applies); anything else exits
2 naming the supported controls; an absent side, or an element neither side has (its names listed), exits 2.
"""
import json
import os
import shutil

import pytest

from conftest import _run_reveal_direct, without_request_notes
from reveal import api
from reveal.errors import MissingResourceError, RequestValidationError, UnsupportedOverrideError

pytestmark = [pytest.mark.component]


def _json(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run.returncode, (json.loads(run.stdout) if run.stdout.strip() else None), run.stderr


@pytest.fixture
def pair(tmp_path, monkeypatch):
    """Two files that differ in one function, named relative to the cwd (no drive-letter colon in the pair)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'a.py').write_text('def ok():\n    return 1\n\n\ndef only_left():\n    pass\n', encoding='utf-8')
    (tmp_path / 'b.py').write_text('def ok():\n    x = 2\n    return x\n', encoding='utf-8')
    return tmp_path


@pytest.fixture
def trees(tmp_path, monkeypatch):
    """A repository with two directory sides; left/ignored.py is git-ignored and left/sub/ holds a function."""
    pygit2 = pytest.importorskip('pygit2')
    monkeypatch.chdir(tmp_path)
    for side in ('left', 'right'):
        (tmp_path / side).mkdir()
        (tmp_path / side / 'app.py').write_text('def main():\n    return 0\n', encoding='utf-8')
    (tmp_path / 'left' / 'sub').mkdir()
    (tmp_path / 'left' / 'sub' / 'extra.py').write_text('def extra():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'left' / 'ignored.py').write_text('def hidden():\n    return 2\n', encoding='utf-8')
    (tmp_path / '.gitignore').write_text('left/ignored.py\n', encoding='utf-8')
    repo = pygit2.init_repository(str(tmp_path))
    for file in ('.gitignore', 'left/app.py', 'left/sub/extra.py', 'right/app.py'):
        repo.index.add(file)
    repo.index.write()
    sig = pygit2.Signature('Fixture', 'fixture@example.com', 1700000000, 0)
    repo.create_commit('HEAD', sig, sig, 'fixture', repo.index.write_tree(), [])
    return tmp_path


def _names(doc):
    return sorted(f['name'] for f in doc['diff']['functions'])


# --- the generated subcommand: the same answer and exit as the URI -------------------------------------------------

@pytest.mark.parametrize('cli,uri', [
    (('a.py', 'b.py'), 'diff://a.py:b.py'),
    (('a.py', 'b.py/ok'), 'diff://a.py:b.py/ok'),
    (('a.py:b.py',), 'diff://a.py:b.py'),  # one word: the pair as the URI spells it
], ids=['pair', 'element', 'one-word'])
def test_the_subcommand_answers_as_the_uri(pair, cli, uri):
    code, doc, stderr = _json('diff', *cli)
    uri_code, uri_doc, _ = _json(uri)
    assert code == uri_code == 0, stderr
    assert doc['type'] == ('diff_element' if '/ok' in uri else 'diff_comparison')
    assert doc == uri_doc
    text, uri_text = _run_reveal_direct('diff', *cli), _run_reveal_direct(uri)
    assert text.returncode == 0 and text.stdout == uri_text.stdout and text.stdout.strip()


def test_the_subcommand_needs_a_pair(pair):
    run = _run_reveal_direct('diff')
    assert run.returncode == 2 and 'LEFT' in run.stderr, run.stderr


def test_the_element_the_resource_names_answers_its_diff(pair):
    code, doc, _ = _json('diff', 'a.py', 'b.py/only_left')
    assert code == 0 and doc['type'] == 'diff_element' and doc['change'] == 'removed'
    assert doc['source'] == 'diff://a.py:b.py/only_left'


# --- the declaration: unknown controls exit 2 naming the supported ones --------------------------------------------

@pytest.mark.parametrize('argv,named', [
    (('diff://a.py:b.py?bogus=1',), "'bogus'"),
    (('diff://a.py:b.py?limit=1',), "'limit'"),  # a result-control key: diff declares no cap
    (('diff', 'a.py', 'b.py', '--bogus', '1'), "'--bogus'"),
    (('diff', 'a.py', 'b.py', '--sort', 'name'), "'--sort'"),
    (('diff://a.py:b.py', '--verbose'), "'detail'"),  # --verbose is --detail full: diff declares no detail
], ids=['uri-key', 'result-control-key', 'flag', 'sort', 'verbose'])
def test_an_unsupported_control_exits_2_naming_the_supported_controls(pair, argv, named):
    code, doc, stderr = _json(*argv)
    assert code == 2, stderr
    assert named in stderr and 'supported controls: exclude' in stderr, stderr
    assert doc is not None and doc['meta']['errors'], doc  # the invalid-request document, not empty stdout


def test_the_api_refuses_an_unknown_key_or_keyword(pair):
    with pytest.raises(RequestValidationError, match="unsupported control 'bogus'"):
        api.query('diff://a.py:b.py?bogus=1')
    with pytest.raises(UnsupportedOverrideError, match="unsupported control 'bogus_kw'"):
        api.query('diff://a.py:b.py', bogus_kw=1)
    with pytest.raises(RequestValidationError, match="unsupported control 'bogus'"):
        api.query('diff', 'a.py:b.py', bogus=1)  # the noun form: the subcommand's parser refuses --bogus


def test_mcp_refuses_an_unknown_key(pair):
    from reveal.mcp_server import reveal_query, _ToolFailure
    answer = reveal_query('diff://a.py:b.py?bogus=1')
    assert isinstance(answer, _ToolFailure) and "unsupported control 'bogus'" in str(answer), str(answer)[:300]
    assert not isinstance(reveal_query('diff://a.py:b.py'), _ToolFailure)  # control: the pair still answers


# --- the typed binding: api.query's noun form and the (resource, query, params=) construction ----------------------

def test_the_noun_form_is_the_subcommand(pair):
    _, expected, _ = _json('diff', 'a.py', 'b.py')
    assert api.query('diff', 'a.py:b.py') == expected
    assert api.query('diff://a.py:b.py')['type'] == 'diff_comparison'


def test_diff_constructs_as_every_declared_noun_does(pair):
    from reveal.adapters.diff import DiffAdapter
    adapter = DiffAdapter('a.py:b.py', params={'exclude': 'sub'})
    assert (adapter.left_uri, adapter.right_uri) == ('a.py', 'b.py')
    assert adapter.query_params['exclude'] == 'sub'
    assert DiffAdapter('a.py:b.py/ok', '').embedded_element == 'ok'
    with pytest.raises(RequestValidationError, match="unsupported control 'bogus'"):
        DiffAdapter('a.py:b.py', 'bogus=1')
    with pytest.raises(RequestValidationError, match="unsupported control 'b.py'"):
        DiffAdapter('a.py', 'b.py')  # the old two-argument spelling: the second argument is the query


# --- execution facts (D6) --------------------------------------------------------------------------------------------

@pytest.mark.parametrize('argv', [('diff', 'absent', 'b.py'), ('diff://absent:b.py',), ('diff', 'a.py', 'nosuch.py')],
                         ids=['subcommand-no-extension', 'uri-no-extension', 'subcommand-missing-file'])
def test_a_side_that_does_not_exist_is_an_invalid_request(pair, argv):
    code, doc, stderr = _json(*argv)
    assert code == 2, stderr
    assert 'File not found' in doc['error'], doc


def test_two_words_are_the_sides_as_typed_even_holding_a_colon(pair):
    """reveal diff LEFT RIGHT reads each word as a side; it joined them with ':' and re-split the text, so a side holding a
    colon (a drive-letter path beside a POSIX-style one, a filename with a colon) was 'requires left:right format', exit 3."""
    if os.name == 'nt':
        right = str(pair / 'b.py')  # C:\...\b.py beside the relative a.py
    else:
        shutil.copy(pair / 'b.py', pair / 'side:b.py')
        right = 'side:b.py'
    code, doc, stderr = _json('diff', 'a.py', right)
    assert code == 0, stderr
    assert doc['type'] == 'diff_comparison' and 'error' not in doc, doc
    code, doc, stderr = _json('diff', '/nonexistent/path', 'C:\\Users\\x')
    assert code == 2, stderr
    assert 'File not found: /nonexistent/path' in doc['error'], doc  # noqa: win-path (a side as typed)


def test_the_api_raises_the_missing_side(pair):
    with pytest.raises(MissingResourceError, match='File not found: absent'):
        api.query('diff://absent:b.py')


def test_an_element_neither_side_has_exits_2_listing_both_sides_names(pair):
    code, doc, stderr = _json('diff', 'a.py', 'b.py/nope')
    assert code == 2, stderr
    assert doc['error'] == "Element 'nope' not found"
    assert doc['available_elements'] == ['ok', 'only_left']
    text = _run_reveal_direct('diff', 'a.py', 'b.py/nope')
    assert text.returncode == 2 and 'Available elements: ok, only_left' in text.stderr


# --- the walk: a directory pair walks both sides --------------------------------------------------------------------

def test_exclude_prunes_both_sides_alike_on_every_spelling(trees):
    _, whole, _ = _json('diff', 'left', 'right')
    assert 'extra' in _names(whole)
    _, flagged, _ = _json('diff', 'left', 'right', '--exclude', 'sub')
    _, keyed, _ = _json('diff://left:right?exclude=sub')
    assert 'extra' not in _names(flagged)
    assert flagged == without_request_notes(keyed)  # a URI query string is a retiring request: its one note
    assert api.query('diff', 'left:right', exclude='sub') == flagged


def test_the_walk_policy_reaches_a_directory_pair(trees):
    _, default, _ = _json('diff', 'left', 'right')
    _, unignored, stderr = _json('diff', 'left', 'right', '--respect-gitignore', 'off')
    assert 'hidden' not in _names(default)
    assert 'hidden' in _names(unignored), stderr
