"""The shared join of a URI and the flags typed after it (COMMAND_MODEL "Flags after a URI", BACK-2673), as a unit.

``query_binding.join_uri_and_flags`` takes the URI's prepared params and the typed flags' prepared params and makes one
request under "Conflicting values": a flag-only control is added, equal scalars are one value, different scalars are an
invalid request naming the flag as typed and the URI's ``key=value``, repeatable controls combine with the URI's terms
first. The result binds with transport 'uri' and keeps the URI's metadata. The URI route does not call it yet (Step 3b-2).
"""
import pytest

from reveal.cli.routing.declared import declared_adapter_class
from reveal.utils.query_binding import (bind_prepared_params, flag_conflicts_with_uri_message, join_uri_and_flags,
                                        prepare_declared_params)
from reveal.utils.query_parser import peek_query_items


def _join(noun, query, typed, spelled=None):
    specs = declared_adapter_class(noun).PARAM_SPECS
    uri = prepare_declared_params(specs, query, 'uri')
    flags = prepare_declared_params(specs, typed, 'typed', spelled=spelled)
    return specs, join_uri_and_flags(specs, uri, flags, spelled=spelled)


def _bound(noun, query, typed, spelled=None):
    specs, joined = _join(noun, query, typed, spelled)
    return dict(peek_query_items(bind_prepared_params(specs, joined, transport='uri')))


def test_no_flags_is_the_uri_request_unchanged():
    specs = declared_adapter_class('ast').PARAM_SPECS
    alone = dict(peek_query_items(bind_prepared_params(specs, prepare_declared_params(specs, 'limit=3&where=lines>1',
                                                                                         'uri'), transport='uri')))
    assert _bound('ast', 'limit=3&where=lines>1', {}) == alone == {'limit': 3, 'where': ['lines>1']}
    _specs, joined = _join('ast', 'limit=3', {'limit': None, 'where': None})  # an omitted flag arrives as None
    assert joined._source_query == 'limit=3' and joined._given == {'limit'} and joined._transport == 'uri'


def test_a_control_only_a_flag_gives_is_added_and_binds_as_the_flag_typed_it():
    assert _bound('ast', 'sort=name', {'limit': 5}) == {'sort': 'name', 'limit': 5}
    _specs, joined = _join('ast', 'sort=name', {'limit': 5})
    assert joined._source_query == 'sort=name&limit=5' and joined._given == {'sort', 'limit'}


@pytest.mark.parametrize('noun,query,typed', [('ast', 'limit=5', {'limit': 5}), ('ast', 'limit=05', {'limit': 5}),
                                              ('ast', 'builtins=true', {'builtins': True}),
                                              ('calls', 'limit=3', {'top': 3})])
def test_equal_scalar_values_are_one_value(noun, query, typed):
    _specs, joined = _join(noun, query, typed, spelled={'top': '--top'})
    alone_specs = declared_adapter_class(noun).PARAM_SPECS
    alone = bind_prepared_params(alone_specs, prepare_declared_params(alone_specs, query, 'uri'), transport='uri')
    assert dict(peek_query_items(bind_prepared_params(alone_specs, joined, transport='uri'))) == \
        dict(peek_query_items(alone))
    assert joined._source_query == query  # nothing appended: the URI's value stands for both


@pytest.mark.parametrize('noun,query,typed,spelled,named', [
    ('ast', 'limit=3', {'limit': 5}, {'limit': '--limit'}, ('--limit', 'limit=3')),
    ('ast', 'builtins=false', {'builtins': True}, {'builtins': '--builtins'}, ('--builtins', 'builtins=false')),
    ('calls', 'limit=3', {'top': 5}, {'top': '--top'}, ('--top', 'limit=3')),       # a legacy flag, named as typed
    ('calls', 'top=3', {'top': 5}, {'top': '--limit'}, ('--limit', 'top=3')),       # a legacy URI key, named as typed
])
def test_different_scalar_values_name_the_flag_and_the_uri_key_as_typed(noun, query, typed, spelled, named):
    with pytest.raises(ValueError) as raised:
        _join(noun, query, typed, spelled)
    assert str(raised.value) == flag_conflicts_with_uri_message(named[0], *named[1].split('='))
    assert all(name in str(raised.value) for name in named)


def test_a_repeatable_control_combines_the_uri_terms_first():
    assert _bound('ast', 'where=lines>1', {'where': ['complexity>2', 'name~=a']}) == {
        'where': ['lines>1', 'complexity>2', 'name~=a']}
    _specs, joined = _join('ast', 'where=lines>1', {'where': ['complexity>2']})
    assert joined._source_query == 'where=lines>1&where=complexity>2'


def test_a_repeatable_controls_spellings_and_codec_survive_the_join():
    """Markdown ``match`` is percent-coded and has a legacy spelling: the URI's two spellings, then the flag's term
    (encoded on the way in, decoded once on binding)."""
    assert _bound('markdown', 'match=x&body-contains=y', {'match': ['a b']}) == {'match': ['x', 'y', 'a b']}
    _specs, joined = _join('markdown', 'match=x', {'match': ['a b']})
    assert joined._source_query == 'match=x&match=a%20b'
    assert _bound('markdown', 'sort=title', {'match': ['a b']}) == _bound('markdown', 'sort=title&match=a%20b', {})


def test_a_repeatable_walk_control_combines_with_the_flag():
    """The overview comparison cell of BACK-2673 note #5: the URI's ``exclude`` and ``--exclude`` both apply, as the
    two URI keys do."""
    assert _bound('overview', 'exclude=tests', {'exclude': ['vendor']}) == _bound('overview', 'exclude=tests&exclude=vendor', {})


def test_the_uri_metadata_is_kept_and_the_aliases_supplied_are_joined():
    specs = declared_adapter_class('imports').PARAM_SPECS
    uri = prepare_declared_params(specs, 'unused&scan_limit=5', 'uri')
    flags = prepare_declared_params(specs, {'limit': 2}, 'typed')
    joined = join_uri_and_flags(specs, uri, flags)
    assert joined._folded == uri._folded and joined._selectors == uri._selectors and joined._aliases == uri._aliases
    assert joined._supplied_aliases == uri._supplied_aliases | flags._supplied_aliases == {'scan_limit'}
    assert joined._given == uri._given | {'limit'}
    folded_specs = declared_adapter_class('markdown').PARAM_SPECS
    folded_uri = prepare_declared_params(folded_specs, 'title=Guide', 'uri')
    folded = join_uri_and_flags(folded_specs, folded_uri, prepare_declared_params(folded_specs, {'limit': 2}, 'typed'))
    assert folded._folded == folded_uri._folded == ('title',)


def test_a_value_the_control_rejects_is_rejected_by_the_join():
    with pytest.raises(ValueError):
        _join('ast', 'limit=3', {'limit': -1}, {'limit': '--limit'})


@pytest.mark.parametrize('noun,flag', [('imports', 'importers'), ('calls', 'detail')])
def test_a_flag_given_without_its_value_joins_as_the_bare_uri_key(noun, flag):
    """A flag whose value is optional (``--importers``, ``--detail``) typed alone is the URI's bare key (``?importers``),
    never the word ``true``: Imports read ``importers=true`` as a file named ``true`` (exit 2, no such file)."""
    specs = declared_adapter_class(noun).PARAM_SPECS
    bare = dict(peek_query_items(bind_prepared_params(specs, prepare_declared_params(specs, flag, 'uri'),
                                                      transport='uri')))
    _specs, joined = _join(noun, '', {flag: True})
    assert dict(peek_query_items(bind_prepared_params(specs, joined, transport='uri'))) == bare
    assert joined._source_query == flag
