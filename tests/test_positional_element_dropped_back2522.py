"""A positional element the chosen view never reads exits 2 instead of being dropped (BACK-2522).

``reveal sqlite://x.db users``, ``reveal json://f.json key`` and ``reveal ast://src foo`` printed the
whole resource, exit 0, even for a name that exists: those adapters have no element view, and the
router went to the structure without a word. The bare-path forms did the same: ``reveal DIR NAME``
printed the tree, and ``reveal FILE NAME`` with ``--name``/``--type``/``--sort`` (rerouted to an
``ast://`` query) or ``--grep`` answered for the whole file. Declared nouns already refused an
element (``calls does not support element selection``, exit 2); now the legacy URI path and the bare
path do too, and each says what to type instead.
"""
import json
import sqlite3

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component


@pytest.fixture
def tree(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    conn = sqlite3.connect(str(tmp_path / 'x.db'))
    conn.execute('CREATE TABLE users (id INTEGER)')
    conn.commit()
    conn.close()
    (tmp_path / 'f.json').write_text('{"a": {"b": 1}}', encoding='utf-8')
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src' / 'a.py').write_text('def foo():\n    return 1\n\n\ndef bar():\n    return 2\n',
                                           encoding='utf-8')
    (tmp_path / 'd.md').write_text('# T\n\n## Sec\n\nbody\n', encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('uri,element,syntax', [
    ('sqlite://x.db', 'users', 'sqlite:///path/to/db.db[/table]'),
    ('sqlite://x.db', 'nope', 'sqlite:///path/to/db.db[/table]'),
    ('json://f.json', 'a', 'json://<file>[/path/to/key][?query]'),
    ('ast://src', 'foo', 'ast://<path>?'),
])
def test_a_uri_element_the_adapter_has_no_view_for_exits_2(tree, uri, element, syntax):
    response = _run_reveal_direct(uri, element, '--format', 'json')
    assert response.returncode == 2, response.stdout + response.stderr
    result = json.loads(response.stdout)
    assert [e['code'] for e in result['meta']['errors']] == ['invalid_request']
    assert f"'{element}'" in result['error'] and syntax in result['error']
    text = _run_reveal_direct(uri, element)
    assert text.returncode == 2 and f"'{element}'" in text.stderr


@pytest.mark.parametrize('argv,says', [
    (('src', 'foo'), 'src/'),
    (('src', 'foo', '--name', 'bar'), 'src/'),
    (('src/a.py', 'foo', '--sort', 'name'), '--sort'),
    (('src/a.py', 'foo', '--type', 'function'), '--type'),
    (('src/a.py', 'foo', '--name', 'bar'), '--name'),
    (('src/a.py', 'foo', '--grep', 'return'), '--grep'),
])
def test_a_bare_path_element_its_view_never_reads_exits_2(tree, argv, says):
    response = _run_reveal_direct(*argv)
    assert response.returncode == 2, response.stdout + response.stderr
    assert "'foo'" in response.stderr and says in response.stderr
    assert response.stdout == ''


@pytest.mark.parametrize('argv,shows', [
    (('sqlite://x.db/users',), 'users'),
    (('json://f.json/a',), 'b'),
    (('ast://src?name=foo',), 'foo'),
    (('env://', 'PATH'), 'PATH'),
    (('src/a.py', 'foo'), 'return 1'),
    (('src/a.py', '--sort', 'name'), 'bar'),
    (('src/a.py', '--grep', 'return'), 'return 2'),
    (('src', '--name', 'bar'), 'bar'),
    (('src',), 'a.py'),
])
def test_the_spellings_that_name_the_element_still_answer(tree, argv, shows):
    response = _run_reveal_direct(*argv)
    assert response.returncode == 0, response.stdout + response.stderr
    assert shows in response.stdout


def test_an_element_view_still_reports_a_miss_as_its_own_error(tree):
    response = _run_reveal_direct('env://', 'NO_SUCH_VARIABLE_BACK2522', '--format', 'json')
    assert response.returncode == 2
    assert [e['code'] for e in json.loads(response.stdout)['meta']['errors']] == ['element_not_found']


@pytest.mark.parametrize('uri,syntax', [('calls://src', 'calls://'), ('imports://src', 'imports://')])
def test_a_declared_noun_refuses_an_element_with_the_same_envelope(tree, uri, syntax):
    """It printed one stderr line and wrote nothing on stdout, so --format json had no answer (BACK-2526)."""
    response = _run_reveal_direct(uri, 'foo', '--format', 'json')
    assert response.returncode == 2, response.stdout + response.stderr
    result = json.loads(response.stdout)
    assert [e['code'] for e in result['meta']['errors']] == ['invalid_request']
    assert "takes no positional element ('foo')" in result['error'] and syntax in result['error']
    text = _run_reveal_direct(uri, 'foo')
    assert text.returncode == 2 and text.stderr.count("('foo')") == 1 and text.stdout == ''
