"""``reveal diff DIR_A DIR_B/NAME`` (and ``reveal diff://DIR_A:DIR_B NAME``) compares element NAME across two directories
(BACK-2812).

The element is spelled after the right side (``RIGHT/NAME``, the spelling the ``target:diff.element`` row names), and
diff split it off only when ``RIGHT`` named a file. A directory pair, a git tree pair and a ``file://`` right side kept
``dB/h`` whole, so the answer was "File not found: dB/h", exit 2 (3 for a git tree: "Path not found in HEAD"). Before
the positional element became a join (D4) these answered the element, exit 0.

The rule now (ruling A2 on the diff F1 inventory): ``RIGHT/NAME`` is an element when ``RIGHT/NAME`` does not exist and
``RIGHT`` is a file, or a directory with a directory on the left (a local directory, or a tree at a git ref); a
``file://`` side splits as a local path does. Accepted costs: a missing child of a directory pair answers "Element
'NAME' not found" (still exit 2), and a file left with a directory right is not spellable (it stays "File not found").

The API's own element route (``api.query(URI, ELEMENT)``) answers through ``get_element`` beside the CLI's owner; its
answer equals the CLI's only once BACK-2813 moves it onto the CLI's join, held as a strict xfail here.
"""
import json
import os
import shutil

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.errors import MissingResourceError

pytestmark = [pytest.mark.component]

ROW = 'target:diff.element'
H_OLD = 'def h():\n    return 1\n'
H_NEW = 'def h(x, y):\n    return 3\n'


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    """dA and dB: m.py's f differs in its body, skip.py's h in its signature; a.py and b.py: f differs in its body."""
    monkeypatch.chdir(tmp_path)
    for side, f_body, h_text in (('dA', '1', H_OLD), ('dB', '2', H_NEW)):
        (tmp_path / side).mkdir()
        (tmp_path / side / 'm.py').write_text(f'def f():\n    return {f_body}\n', encoding='utf-8')
        (tmp_path / side / 'skip.py').write_text(h_text, encoding='utf-8')
    (tmp_path / 'a.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'b.py').write_text('def f():\n    return 2\n', encoding='utf-8')
    return tmp_path


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A repository whose pkg/skip.py has ``def h()`` at HEAD~1 and ``def h(x, y)`` at HEAD (and in the work tree)."""
    pygit2 = pytest.importorskip('pygit2')
    root = tmp_path / 'repo'
    (root / 'pkg').mkdir(parents=True)
    git = pygit2.init_repository(str(root))
    sig = pygit2.Signature('fixture', 'fixture@example.invalid')
    parents = []
    for text in (H_OLD, H_NEW):
        (root / 'pkg' / 'skip.py').write_text(text, encoding='utf-8')
        git.index.add('pkg/skip.py')
        git.index.write()
        parents = [git.create_commit('HEAD', sig, sig, 'fixture', git.index.write_tree(), parents)]
    monkeypatch.chdir(root)
    return root


def _run(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run.returncode, (json.loads(run.stdout) if run.stdout.strip() else None), run.stderr


def _element(doc, name='h'):
    assert doc['type'] == 'diff_element', doc.get('error', doc)
    assert (doc['name'], doc['change']) == (name, 'modified'), doc
    return doc


def _noted(doc):
    return [w.get('field') for w in (doc.get('meta') or {}).get('warnings') or [] if w.get('code') == 'retired_spelling']


# --- a directory pair ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize('argv,noted', [
    (('diff', 'dA', 'dB/h'), []),
    (('diff://dA:dB/h',), []),
    (('diff://dA:dB', 'h'), [ROW]),
    (('diff://dA/:dB/', 'h'), [ROW]),
], ids=['subcommand', 'uri-embedded', 'uri-positional', 'uri-positional-trailing-slashes'])
def test_cli_element_of_a_directory_pair(dirs, argv, noted):
    code, doc, stderr = _run(*argv)
    assert code == 0, (stderr, doc)
    assert 'signature' in _element(doc)['changes'], doc
    assert _noted(doc) == noted, doc


@pytest.mark.mcp
def test_mcp_element_of_a_directory_pair(dirs):
    pytest.importorskip('mcp')
    from reveal.mcp_server import _ToolFailure, reveal_run
    shown = reveal_run(['diff', 'dA', 'dB/h', '--format', 'json'])
    assert not isinstance(shown, _ToolFailure), shown[:400]
    _element(json.loads(shown))


@pytest.mark.parametrize('call', [('diff', 'dA:dB/h'), ('diff://dA:dB/h',)], ids=['noun-form', 'uri-embedded'])
def test_api_element_of_a_directory_pair(dirs, call):
    _element(api.query(*call))


def test_cli_exclude_applies_to_a_directory_pair_element(dirs):
    """h is only in skip.py: with skip.py excluded neither side has it, as the comparison itself shows."""
    code, doc, stderr = _run('diff', 'dA', 'dB/h', '--exclude', 'skip.py')
    assert code == 2, (stderr, doc)
    assert doc['error'] == "Element 'h' not found", doc
    code, doc, stderr = _run('diff', 'dA', 'dB', '--exclude', 'skip.py')  # sibling: the comparison already excluded it
    assert code == 0, stderr
    assert doc['type'] == 'diff_comparison' and doc['diff']['functions'] == [], doc


def test_a_missing_child_of_a_directory_pair_is_an_element_miss(dirs):
    """The accepted cost of the rule: ``dB/nosuch`` is read as the element, still an invalid request (exit 2)."""
    code, doc, stderr = _run('diff', 'dA', 'dB/nosuch')
    assert code == 2, (stderr, doc)
    assert doc['error'] == "Element 'nosuch' not found", doc


@pytest.mark.xfail(strict=True, reason="BACK-2813: api.query(URI, ELEMENT) answers through get_element beside the CLI's "
                                       "owner (no contract_version, source or source_type)")
def test_api_positional_element_equals_the_cli(dirs):
    code, cli, stderr = _run('diff://dA:dB', 'h')
    assert code == 0, stderr
    assert api.query('diff://dA:dB', 'h') == cli


# --- other sides: a git tree, a file:// side -----------------------------------------------------------------------

@pytest.mark.parametrize('argv,noted', [
    (('diff', 'git://HEAD~1/pkg', 'pkg/h'), []),
    (('diff', 'git://HEAD~1/pkg', 'git://HEAD/pkg/h'), []),
    (('diff://git://HEAD~1/pkg:git://HEAD/pkg', 'h'), [ROW]),
    (('diff://git://HEAD~1/pkg:git://HEAD/pkg/h',), []),
], ids=['tree-and-work-tree', 'two-trees', 'uri-positional', 'uri-embedded'])
def test_cli_element_of_a_git_tree_pair(tree, argv, noted):
    code, doc, stderr = _run(*argv)
    assert code == 0, (stderr, doc)
    _element(doc)
    assert _noted(doc) == noted, doc


@pytest.mark.parametrize('argv', [('diff://a.py:file://b.py', 'f'), ('diff', 'a.py', 'file://b.py/f'),
                                  ('diff://file://dA:file://dB/h',)],
                         ids=['uri-positional', 'subcommand', 'directories'])
def test_cli_element_after_a_file_uri_side(dirs, argv):
    code, doc, stderr = _run(*argv)
    assert code == 0, (stderr, doc)
    _element(doc, 'h' if argv[0].endswith('/h') else 'f')


# --- colons and drive letters (d080af4f): two words are the sides as typed ----------------------------------------

def test_a_side_holding_a_colon_or_drive_letter_keeps_its_element(dirs):
    """A drive-letter path on Windows, a directory or file named with a colon elsewhere: the element still splits off."""
    if os.name == 'nt':
        right_dir, right_file = os.fspath(dirs / 'dB'), os.fspath(dirs / 'b.py')  # C:\...\dB beside the relative dA
    else:
        shutil.copytree(dirs / 'dB', dirs / 'side:dB')
        shutil.copy(dirs / 'b.py', dirs / 'side:b.py')
        right_dir, right_file = 'side:dB', 'side:b.py'
    code, doc, stderr = _run('diff', 'a.py', right_file + '/f')  # sibling: a file side already split
    assert code == 0, stderr
    _element(doc, 'f')
    code, doc, stderr = _run('diff', 'dA', right_dir + '/h')
    assert code == 0, (stderr, doc)
    _element(doc)


# --- negative controls: what must not change -----------------------------------------------------------------------

def test_a_file_left_never_splits_a_directory_child(dirs):
    """A file left with a directory right is not spellable (ruling A2): the child is read as a file, as before."""
    code, doc, stderr = _run('diff', 'a.py', 'dB/missing.py')
    assert code == 2, stderr
    assert doc['error'] == 'File not found: dB/missing.py', doc
    with pytest.raises(MissingResourceError, match='File not found: dB/missing.py'):
        api.query('diff://a.py:dB/missing.py')


def test_whole_directory_and_file_sides_still_compare(dirs):
    for argv in (('diff', 'dA', 'dB'), ('diff', 'dA/m.py', 'dB/m.py'), ('diff://dA:dB',)):
        code, doc, stderr = _run(*argv)
        assert code == 0, (argv, stderr)
        assert doc['type'] == 'diff_comparison', (argv, doc)
