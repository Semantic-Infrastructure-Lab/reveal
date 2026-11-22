"""``exclude`` is the walk control of every walking noun (COMMAND_MODEL "Walk exclusion", Scott 2026-11-22, BACK-2730).

Option B (manager ruling on S1): ``?exclude=P`` answers as ``--exclude P`` on every walking noun, through the one shared
declaration (``exclude_param``) and the one walk scope, on the subcommand, the URI, ``api.query`` and MCP, with the URI's
request note naming ``--exclude P``. Until the cut AST and Markdown (whose where fields come from the data) keep a bare
``?exclude=V`` as their field filter, the answer of ``?where=exclude=V``, with its note; ``--exclude`` and the keyword
stay the walk control there. A file target satisfies ``--exclude`` quietly (D-2730-2 (a)), and an empty pattern is an
invalid request on every transport (BACK-2736's shared rule, extended).

Before (measured at b5d4f5b0): ``?exclude=`` exited 2 "unsupported control 'exclude'" on Calls, Imports, Surface,
Contracts and Patches, where ``--exclude`` and ``exclude=`` walk-excluded; ``metrics://FILE?exclude=X`` and
``metrics://DIR?view=provenance&exclude=X`` exited 2 "not read by this answer" where the flag answered (``metrics FILE
--exclude X`` with an unused note, provenance excluding); ``ast``/``overview``/``surface``/``metrics FILE --exclude X``
printed "Input --exclude has no effect"; ``--exclude ''`` answered as no exclusion on every walking noun. Conformance
column 26 holds the rule per noun; this file holds the requests it does not reach and the siblings that must not change.
"""
import json

import pytest

from conftest import _run_reveal_direct


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """Two Python files and a Markdown file at the top, and a ``sub/`` directory with a Python file and a Markdown file
    whose front matter has ``exclude: yes`` (the field the where nouns filter on)."""
    (tmp_path / 'a.py').write_text('import os\n\n\ndef alpha():\n    return beta()\n\n\ndef beta():\n    return os.sep\n',
                                   encoding='utf-8')
    (tmp_path / 'b.py').write_text('from a import alpha\n\n\ndef gamma():\n    return alpha()\n', encoding='utf-8')
    (tmp_path / 'README.md').write_text('# Readme\n\nTop words.\n', encoding='utf-8')
    sub = tmp_path / 'sub'
    sub.mkdir()
    (sub / 'c.py').write_text('def delta():\n    return 1\n', encoding='utf-8')
    (sub / 'notes.md').write_text('---\nexclude: yes\n---\n# Notes\n\nSub words.\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _json(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    try:
        doc = json.loads(run.stdout)
    except ValueError:
        doc = {}
    return run, doc if isinstance(doc, dict) else {}


def _warnings(doc):
    return (doc.get('meta') or {}).get('warnings') or []


def _plain(doc):
    """The answer with its notes left out: a retirement note names the spelling used, which is the point of a URI."""
    doc = json.loads(json.dumps(doc))
    meta = doc.get('meta')
    if isinstance(meta, dict):
        meta['warnings'] = [w for w in meta.get('warnings') or [] if w.get('code') != 'retired_spelling']
    doc.pop('next_steps', None)
    return doc


def _unused(doc, run):
    """Whether the answer reports an input unused, in its JSON or on stderr."""
    return any(w.get('code') in ('unused_flag', 'unused_query_param') for w in _warnings(doc)) or \
        'has no effect' in run.stderr


def _error(run, doc):
    return doc.get('error') if isinstance(doc.get('error'), str) else run.stderr


# (URI, the subcommand request it is): the five nouns whose ?exclude= exited 2 "unsupported control 'exclude'".
WALK_URIS = [
    ('calls://.?callers=beta&exclude=sub', ('calls', '.', '--callers', 'beta', '--exclude', 'sub')),
    ('imports://.?exclude=sub', ('imports', '.', '--exclude', 'sub')),
    ('surface://.?exclude=sub', ('surface', '.', '--exclude', 'sub')),
    ('contracts://.?exclude=sub', ('contracts', '.', '--exclude', 'sub')),
    ('patches://.?exclude=sub', ('patches', '.', '--exclude', 'sub')),
]


@pytest.mark.parametrize('uri,sub', WALK_URIS)
def test_the_uri_key_is_the_walk_control(tree, uri, sub):
    run, doc = _json(uri)
    flag_run, flag_doc = _json(*sub)
    assert run.returncode == flag_run.returncode == 0, (run.stderr, flag_run.stderr)
    assert _plain(doc) == _plain(flag_doc)
    assert not _unused(doc, run), run.stderr


@pytest.mark.parametrize('uri,sub', WALK_URIS)
def test_the_uri_key_notes_its_flag(tree, uri, sub):
    """D-2730-3: the new key answers with its request note rendering ``--exclude P``, as ``metrics://.?exclude=`` did."""
    run, doc = _json(uri)
    notes = [w.get('message', '') for w in _warnings(doc) if w.get('code') == 'retired_spelling']
    assert any('--exclude sub' in note for note in notes), (notes, run.stderr)


def test_the_uri_key_excludes_on_imports(tree):
    """The key is applied, not only accepted: the excluded directory's file leaves the import graph."""
    plain = json.dumps(_json('imports://.')[1])
    excluded = json.dumps(_json('imports://.?exclude=sub')[1])
    assert 'c.py' in plain and 'c.py' not in excluded


def test_repeated_uri_keys_combine_as_repeated_flags(tree):
    run, doc = _json('surface://.?exclude=sub&exclude=b.py')
    flag_run, flag_doc = _json('surface', '.', '--exclude', 'sub', '--exclude', 'b.py')
    assert run.returncode == flag_run.returncode == 0, run.stderr
    assert _plain(doc) == _plain(flag_doc)


@pytest.mark.parametrize('uri,noun', [('imports://.?exclude=sub', 'imports'), ('surface://.?exclude=sub', 'surface'),
                                      ('contracts://.?exclude=sub', 'contracts')])
def test_the_typed_api_answers_the_uri_key_as_the_keyword(tree, uri, noun):
    from reveal import api
    assert _plain(api.query(uri)) == _plain(api.query(noun, '.', exclude='sub'))


def test_mcp_answers_the_uri_key(tree):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_run
    shown = reveal_run(['imports://.?exclude=sub', '--format', 'json'])
    assert _plain(json.loads(shown)) == _plain(_json('imports', '.', '--exclude', 'sub')[1])


# D-2730-2 (a): a file target satisfies exclude quietly, so metrics answers alike on the flag and the URI.
@pytest.mark.parametrize('excluded,plain', [
    (('metrics', 'a.py', '--exclude', 'sub'), ('metrics', 'a.py')),
    (('metrics://a.py?exclude=sub',), ('metrics://a.py',)),
    (('metrics://a.py', '--exclude', 'sub'), ('metrics://a.py',)),
    (('metrics://a.py?view=hotspots&exclude=sub',), ('metrics://a.py?view=hotspots',)),
    (('overview', 'a.py', '--exclude', 'sub'), ('overview', 'a.py')),
    (('ast', 'a.py', '--exclude', 'sub'), ('ast', 'a.py')),
    (('surface', 'a.py', '--exclude', 'sub'), ('surface', 'a.py')),
])
def test_a_file_target_satisfies_exclude_quietly(tree, excluded, plain):
    run, doc = _json(*excluded)
    base_run, base = _json(*plain)
    assert run.returncode == base_run.returncode == 0, (run.stderr, base_run.stderr)
    assert not _unused(doc, run), (_warnings(doc), run.stderr)
    assert _plain(doc) == _plain(base)


def test_metrics_provenance_reads_the_uri_key_as_the_flag(tree):
    """The provenance walk applied ``--exclude`` (7 -> 5 files) while ``?exclude=`` was refused as unread."""
    run, doc = _json('metrics://.?view=provenance&exclude=sub')
    flag_run, flag_doc = _json('metrics', '.', '--view', 'provenance', '--exclude', 'sub')
    assert run.returncode == flag_run.returncode == 0, run.stderr
    assert _plain(doc) == _plain(flag_doc)


def test_the_typed_api_satisfies_a_file_target_quietly(tree):
    from reveal import api
    assert _plain(api.query('metrics://a.py?exclude=sub')) == _plain(api.query('metrics://a.py'))


# An empty pattern is an invalid request on every walking noun and transport; the spelling is named as typed.
EMPTY = [
    (('ast', '.', '--exclude', ''), '--exclude'),
    (('markdown', '.', '--exclude', ''), '--exclude'),
    (('imports', '.', '--exclude', ''), '--exclude'),
    (('metrics', '.', '--exclude', ''), '--exclude'),
    (('overview', '.', '--exclude', ''), '--exclude'),
    (('pack', '.', '--exclude', ''), '--exclude'),
    (('surface', '.', '--exclude', ' '), '--exclude'),  # whitespace is no pattern, as it is no term
    (('calls', '.', '--callers', 'beta', '--exclude', 'sub', '--exclude', ''), '--exclude'),  # beside a real one
    (('ast://.', '--exclude', ''), '--exclude'),  # after a URI
    (('imports://.?exclude=',), 'exclude'),
    (('metrics://.?exclude=',), 'exclude'),
    (('metrics://.?exclude=sub&exclude=',), 'exclude'),
]


@pytest.mark.parametrize('argv,spelling', EMPTY)
def test_an_empty_pattern_is_an_invalid_request(tree, argv, spelling):
    run, doc = _json(*argv)
    assert run.returncode == 2, (run.returncode, run.stdout[:300])
    assert f'{spelling} needs a pattern: --exclude PATTERN' in _error(run, doc), _error(run, doc)


@pytest.mark.parametrize('call', [
    ('imports', '.', {'exclude': ''}),
    ('ast', '.', {'exclude': ''}),
    ('metrics://.?exclude=', None, {}),
    ('metrics://.', None, {'exclude': ''}),
])
def test_the_typed_api_refuses_an_empty_pattern(tree, call):
    from reveal import api
    from reveal.errors import RequestValidationError
    uri, target, keywords = call
    with pytest.raises(RequestValidationError, match='needs a pattern'):
        api.query(uri, target, **keywords) if target is not None else api.query(uri, **keywords)


def test_mcp_refuses_an_empty_pattern(tree):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_run
    try:
        shown = reveal_run(['imports', '.', '--exclude', '', '--format', 'json'])
    except Exception as exc:  # a tool error is the refusal on MCP
        shown = f'error: {exc}'
    assert 'rror' in shown and '--exclude needs a pattern' in shown, shown[:300]


# --- siblings that must not change ----------------------------------------------------------------------------------

@pytest.mark.parametrize('bare,where,rows', [
    ('ast://.?exclude=sub', 'ast://.?where=exclude=sub', 0),
    ('markdown://.?exclude=yes', 'markdown://.?where=exclude=yes', 1),  # notes.md's front matter: the field filter
])
def test_a_where_nouns_bare_key_keeps_its_field_filter_answer(tree, bare, where, rows):
    run, doc = _json(bare)
    where_run, where_doc = _json(where)
    assert run.returncode == where_run.returncode == 0, run.stderr
    assert len(doc.get('results') or []) == rows
    assert _plain(doc) == _plain(where_doc)
    assert any(w.get('code') == 'retired_spelling' for w in _warnings(doc)), _warnings(doc)


@pytest.mark.parametrize('argv,files', [
    (('ast', '.', '--exclude', 'sub'), 2),
    (('markdown', '.', '--exclude', 'sub'), 1),
    (('ast://.', '--exclude', 'sub'), 2),
])
def test_the_flag_stays_the_walk_control_on_a_where_noun(tree, argv, files):
    run, doc = _json(*argv)
    assert run.returncode == 0 and doc.get('total_files') == files, (run.stderr, doc.get('total_files'))


def test_metrics_directory_exclusion_is_unchanged(tree):
    run, doc = _json('metrics://.?exclude=sub')
    flag_run, flag_doc = _json('metrics', '.', '--exclude', 'sub')
    assert run.returncode == flag_run.returncode == 0
    assert _plain(doc) == _plain(flag_doc)
    assert all('sub' not in (row.get('file') or '') for row in doc.get('files') or [])


@pytest.mark.parametrize('argv', [
    ('json://data.json?exclude=yes',),  # JSON does not walk: its bare key is the legacy where term, noted
])
def test_a_non_walking_where_noun_keeps_its_legacy_where_term(tree, argv):
    (tree / 'data.json').write_text('[{"exclude": "yes"}, {"exclude": "no"}]', encoding='utf-8')
    run, doc = _json(*argv)
    assert run.returncode == 0, run.stderr
    assert any(w.get('code') == 'retired_spelling' for w in _warnings(doc))


@pytest.mark.parametrize('argv', [
    ('sqlite://app.db?exclude=sub',),
    ('sqlite', 'app.db', '--exclude', 'sub'),
])
def test_a_noun_that_walks_no_tree_still_refuses_exclude(tree, argv):
    import sqlite3
    from contextlib import closing
    with closing(sqlite3.connect(tree / 'app.db')) as connection, connection:
        connection.execute('CREATE TABLE t(id INTEGER)')
    run, doc = _json(*argv)
    assert run.returncode == 2 and 'exclude' in _error(run, doc), (run.returncode, _error(run, doc))
