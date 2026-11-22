"""The walk scope (BACK-2730), the shared owners' unit test (``cli/routing/declared.py``, ``ledger.py``, ``uri.py``).

``exclude`` is one walk control however a request spells it: the walk scope joins the ``--exclude`` flags and the
declared ``exclude`` of a URI or keyword (peeked, so binding is not reading), a file target satisfies it quietly in the
flag ledger (no unused note for the flag or the key; D-2730-2 (a)), and a walking noun refuses an empty flag pattern
before it binds, declared or not (the walk-policy check). A noun that walks no tree keeps refusing ``--exclude``.
"""
import argparse
from types import SimpleNamespace

import pytest

from reveal.cli.routing.declared import _validate_walk_policy, _walk_scope
from reveal.cli.routing.ledger import FlagLedger, satisfy_walk_exclusion
from reveal.errors import RequestValidationError
from reveal.utils.exclusions import clear_active_exclusions
from reveal.utils.query_parser import QueryParams

WALKING = SimpleNamespace(RESOURCE_SPEC=SimpleNamespace(walks=True))
FILE_ONLY = SimpleNamespace(RESOURCE_SPEC=SimpleNamespace(walks=False))


@pytest.fixture
def tree(tmp_path, monkeypatch):
    (tmp_path / 'sub').mkdir()
    (tmp_path / 'app.py').write_text('x = 1\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('REVEAL_IGNORE', raising=False)
    clear_active_exclusions()  # the scope is process-wide: an earlier test's walk may have consulted one
    yield tmp_path
    clear_active_exclusions()


def _ledgered(**flags):
    parser = argparse.ArgumentParser()
    parser.add_argument('--exclude', action='append')
    given = argparse.Namespace(**{'exclude': None, **flags})
    ledger = FlagLedger(given, parser=parser)
    return ledger, ledger.track(given)


def test_the_scope_joins_the_flags_and_the_declared_key(tree):
    _ledger, args = _ledgered(exclude=['sub'])
    params = QueryParams({'exclude': ['vendor,a%2Cb', 'sub']})  # a repeated URI key, one with an escaped comma
    params._reads = set()  # the ledger's read log: binding is not reading
    root, patterns = _walk_scope(WALKING, str(tree), args, params)
    assert root == tree and patterns == ['sub', 'vendor', 'a,b']
    assert params._reads == set()  # peeked, never read


def test_the_scope_takes_the_key_alone_and_the_flags_alone(tree):
    _ledger, args = _ledgered()
    assert _walk_scope(WALKING, str(tree), args, QueryParams({'exclude': 'build'}))[1] == ['build']
    _ledger, args = _ledgered(exclude=['build'])
    assert _walk_scope(WALKING, str(tree), args, None)[1] == ['build']


def test_a_noun_that_walks_no_tree_has_no_scope(tree):
    _ledger, args = _ledgered(exclude=['sub'])
    assert _walk_scope(FILE_ONLY, str(tree), args, QueryParams({'exclude': 'sub'})) == (None, [])


def test_a_file_target_satisfies_the_walk_control(tree):
    ledger, args = _ledgered(exclude=['sub'])
    ledger.query_keys = ['exclude']
    assert 'exclude' in ledger.unused_flags() and 'exclude' in ledger.unused_query_keys()  # the old note's facts
    _walk_scope(WALKING, str(tree / 'app.py'), args, None)
    assert ledger.exclusion_satisfied
    assert 'exclude' not in ledger.unused_flags() and 'exclude' not in ledger.unused_query_keys()


def test_a_directory_target_is_not_satisfied_without_a_walk(tree):
    """Negative control: only a file target, or a walk that consulted the scope, counts the control applied."""
    ledger, args = _ledgered(exclude=['sub'])
    _walk_scope(WALKING, str(tree), args, None)
    assert not ledger.exclusion_satisfied and 'exclude' in ledger.unused_flags()


def test_satisfying_without_a_ledger_is_a_no_op():
    satisfy_walk_exclusion(argparse.Namespace(exclude=['x']))  # a library call outside a dispatch: nothing to count


@pytest.mark.parametrize('patterns', [[''], [' '], ['sub', '']])
def test_a_walking_noun_refuses_an_empty_flag_pattern(patterns):
    with pytest.raises(RequestValidationError, match='--exclude needs a pattern: --exclude PATTERN'):
        _validate_walk_policy(WALKING, argparse.Namespace(exclude=patterns, respect_gitignore=True), None)


def test_real_patterns_and_no_flag_pass_the_walk_policy():
    _validate_walk_policy(WALKING, argparse.Namespace(exclude=['sub'], respect_gitignore=True), None)
    _validate_walk_policy(WALKING, argparse.Namespace(exclude=None, respect_gitignore=True), None)


def test_a_noun_that_walks_no_tree_still_refuses_the_flag():
    with pytest.raises(ValueError, match='--exclude requires a directory-walking operation'):
        _validate_walk_policy(FILE_ONLY, argparse.Namespace(exclude=['sub'], respect_gitignore=True), None)


def test_the_uri_key_is_carried_once_the_walk_applied_it(tree):
    """A URI route clears the scope before it reports; the walk's use recorded during the dispatch carries the key."""
    ledger, _args = _ledgered()
    ledger.query_keys = ['exclude']
    assert ledger.unused_query_keys() == ['exclude']
    ledger.used.add('exclude')  # what dispatching() records when a walk consulted the scope
    assert ledger.unused_query_keys() == []


def test_the_uri_route_reads_exclude_from_the_declaration():
    """The legacy URI route's scheme table is gone: a scheme that declares exclude takes the flag into its query, and
    its URI key joins the walk scope."""
    from reveal.cli.routing.uri import _declares_exclude, _uri_exclude_patterns
    from reveal.utils.query_parser import exclude_param
    assert _declares_exclude(SimpleNamespace(PARAM_SPECS=(exclude_param(),)))
    assert not _declares_exclude(SimpleNamespace(PARAM_SPECS=())) and not _declares_exclude(None)
    assert _uri_exclude_patterns('src?exclude=a%2Cb,c&sort=name&exclude=c') == ['a,b', 'c']
    assert _uri_exclude_patterns('src?sort=name') == []


def test_the_typed_api_route_publishes_the_bound_exclude(tree):
    """``api.query(URI)`` builds the adapter itself (no CLI route): the exclude it bound, from the URI or a keyword, is
    its walk scope too; a request naming none, or a noun that walks no tree, publishes none (as before)."""
    from reveal import api
    from reveal.utils.query_parser import ResourceSpec
    walking = SimpleNamespace(RESOURCE_SPEC=ResourceSpec(), PARAM_SPECS=())
    root, patterns = api._walk_scope(walking, '.?exclude=sub', SimpleNamespace(query_params=QueryParams(
        {'exclude': 'sub,a%2Cb'})))
    assert root.resolve() == tree.resolve() and patterns == ['sub', 'a,b']
    assert api._walk_scope(walking, '.', SimpleNamespace(query_params=QueryParams())) == (None, [])
    assert api._walk_scope(SimpleNamespace(RESOURCE_SPEC=ResourceSpec(walks=False)), '.',
                           SimpleNamespace(query_params=QueryParams({'exclude': 'sub'}))) == (None, [])


def test_the_typed_api_applies_the_uri_key_on_a_walk_the_adapter_does_not_scope_itself(tree):
    """metrics' provenance walk reads no exclude of its own: only the published scope prunes it."""
    from reveal import api
    (tree / 'sub' / 'c.py').write_text('y = 2\n', encoding='utf-8')
    files = {row['file'] for row in api.query('metrics://.?view=provenance&exclude=sub')['files']}
    assert files and not any(path.startswith('sub') for path in files)
    assert any(row['file'].startswith('sub') for row in api.query('metrics://.?view=provenance')['files'])


def test_a_cache_keyed_on_the_scope_counts_it_consulted(tree):
    """A cache hit applied the exclusion its entry was built under: reading the scope as a key counts as consulted, so
    the ledger never notes --exclude unused on a hit (the calls and imports caches key on it)."""
    from reveal.utils import exclusions
    exclusions.set_active_exclusions(tree, ['sub'])
    assert not exclusions.exclusions_consulted()
    assert exclusions.active_exclusions() == (tree, ('sub',)) and not exclusions.exclusions_consulted()  # a plain read
    assert exclusions.scope_cache_key() == (tree, ('sub',)) and exclusions.exclusions_consulted()
    exclusions.clear_active_exclusions()
    assert exclusions.scope_cache_key() == (None, ()) and not exclusions.exclusions_consulted()  # no scope: none


def test_a_cached_callees_answer_counts_the_scope_applied(tree):
    """Two callees requests with one --exclude in one MCP server (its tool calls share the callee cache): the second is
    a cache hit and still says nothing about --exclude (it said "Input --exclude has no effect")."""
    pytest.importorskip('mcp')
    import json
    from reveal.mcp_server import reveal_run
    (tree / 'app.py').write_text('def load():\n    return 1\n\n\ndef serve():\n    return load()\n', encoding='utf-8')
    for _ in range(2):
        doc = json.loads(reveal_run(['calls', '.', '--callees', 'serve', '--exclude', 'sub', '--format', 'json']))
        assert not [w for w in doc['meta']['warnings'] if w.get('code') == 'unused_flag'], doc['meta']['warnings']
