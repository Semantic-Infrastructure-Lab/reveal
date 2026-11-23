"""One constructor binding entry (S8 of the vocab V1 inventory, BACK-2772): ``bound_constructor_params`` binds a noun
constructor's controls once. Params the declarations built (prepared or bound) pass unchanged; a typed mapping binds as
typed values; a parsed but unbound query (``parse_query_params``) or a hand-built ``QueryParams`` rebinds as its text,
as the URI binds it; no params bind the URI query. ``prepared_constructor_params`` is the same entry for the noun that
binds after reading its source (JSON)."""
import pytest

from reveal.adapters.patches.adapter import PatchesAdapter
from reveal.adapters.stats.adapter import MetricsAdapter
from reveal.errors import RequestValidationError, UnsupportedOverrideError
from reveal.utils.query_binding import (bind_declared_params, bound_constructor_params, join_uri_and_flags,
                                        prepare_declared_params, prepared_constructor_params,
                                        unsupported_controls_message)
from reveal.utils.query_parser import (CliBinding, LegacySpelling, ParamSpec, QueryParams, parse_query_params,
                                       whole_number)

SPECS = (ParamSpec('limit', 'integer', 'Cap', None, whole_number, minimum=0),
         ParamSpec('name', 'string', 'Name', None, str))


def test_no_params_bind_the_uri_query():
    params = bound_constructor_params(SPECS, 'limit=4', None)
    assert dict(params.peek_items()) == {'limit': 4} and params._transport == 'uri'


def test_a_mapping_binds_as_typed_values():
    params = bound_constructor_params(SPECS, 'limit=9', {'limit': '3', 'name': 'x'})  # params win over the query
    assert dict(params.peek_items()) == {'limit': 3, 'name': 'x'} and params._transport == 'typed'


@pytest.mark.parametrize('built', [
    lambda: bind_declared_params(SPECS, 'limit=3', transport='uri'),
    lambda: bind_declared_params(SPECS, {'limit': 3}, transport='typed'),
    lambda: prepare_declared_params(SPECS, 'limit=3', 'uri'),  # prepared, not yet bound: Claude's predictor reads it
    lambda: prepare_declared_params(SPECS, {'limit': 3}, 'typed'),
    lambda: join_uri_and_flags(SPECS, prepare_declared_params(SPECS, 'name=a', 'uri'),
                               prepare_declared_params(SPECS, {'limit': 3}, 'typed')),
], ids=['bound-uri', 'bound-typed', 'prepared-uri', 'prepared-typed', 'joined'])
def test_params_the_declarations_built_pass_unchanged(built):
    params = built()
    assert bound_constructor_params(SPECS, 'limit=9', params) is params
    assert prepared_constructor_params(SPECS, 'limit=9', params) is params


def test_an_empty_bound_request_passes_unchanged():
    params = bind_declared_params(SPECS, '', transport='uri')
    assert not params._normalized and bound_constructor_params(SPECS, None, params) is params


@pytest.mark.parametrize('unbound', [lambda: parse_query_params('limit=5'), lambda: QueryParams({'limit': '5'})],
                         ids=['parsed', 'hand-built'])
def test_an_unbound_query_rebinds_as_its_text(unbound):
    given = unbound()
    params = bound_constructor_params(SPECS, None, given)
    assert params is not given and dict(params.peek_items()) == {'limit': 5}
    assert dict(params.peek_items()) == dict(bind_declared_params(SPECS, 'limit=5', transport='uri').peek_items())


def test_an_unbound_query_is_refused_as_its_uri_is():
    with pytest.raises(ValueError) as uri:
        bind_declared_params(SPECS, 'limit=-1', transport='uri')
    with pytest.raises(ValueError) as rebound:
        bound_constructor_params(SPECS, None, parse_query_params('limit=-1'))
    assert type(rebound.value) is type(uri.value) and str(rebound.value) == str(uri.value)


def test_a_parsed_bare_operator_key_is_a_where_term_as_on_the_uri():
    """Metrics' former own branch (a library caller's parse_query_params): a bare ``lines>5`` is that where term."""
    rebound = bound_constructor_params(MetricsAdapter.PARAM_SPECS, None, parse_query_params('lines>5'))
    uri = bind_declared_params(MetricsAdapter.PARAM_SPECS, 'lines>5', transport='uri')
    assert dict(rebound.peek_items()) == dict(uri.peek_items()) and rebound.get('where') == ['lines>5']


def test_prepared_entry_prepares_without_converting():
    params = prepared_constructor_params(SPECS, None, {'limit': '3'})
    assert params._prepared and not params._normalized and dict(params.peek_items()) == {'limit': '3'}
    assert dict(prepared_constructor_params(SPECS, 'limit=4', None).peek_items()) == {'limit': '4'}
    rebound = prepared_constructor_params(SPECS, None, parse_query_params('limit=5'))
    assert rebound._transport == 'uri' and dict(rebound.peek_items()) == {'limit': '5'}


def test_a_noun_constructor_binds_a_parsed_query(tmp_path):
    """Before S8 a parsed query reached Patches' answer unbound (the raw text '2', no conversion)."""
    adapter = PatchesAdapter(str(tmp_path), params=parse_query_params('limit=2'))
    assert adapter.query_params['limit'] == 2
    bound = bind_declared_params(PatchesAdapter.PARAM_SPECS, {'limit': 2}, transport='typed')
    assert PatchesAdapter(str(tmp_path), params=bound).query_params is bound


# --- the typed source's refusal (D21): a key no declaration spells is rule 3's invalid request ------------------

SPELLED = (ParamSpec('sort', 'string', 'Order', None, str, aliases=('sort_by',),
                     legacy=(LegacySpelling('rank', codec=lambda value: f'-{value}'),),
                     cli=CliBinding(('--sort',), dest='order')),
           ParamSpec('head', 'integer', 'Slice', None, whole_number, flag_only='applied', cli=CliBinding(('--head',))))


@pytest.mark.parametrize('prepare', [lambda source: bind_declared_params(SPECS, source, transport='typed'),
                                     lambda source: prepare_declared_params(SPECS, source, 'typed'),
                                     lambda source: bound_constructor_params(SPECS, None, source)],
                         ids=['bind', 'prepare', 'constructor'])
def test_a_typed_key_no_declaration_spells_is_refused_with_the_shared_message(prepare):
    with pytest.raises(UnsupportedOverrideError) as raised:
        prepare({'limit': 1, 'bogus': 1, 'other': 2})
    assert str(raised.value) == unsupported_controls_message(SPECS, ['bogus', 'other'])
    assert isinstance(raised.value, TypeError)  # what an unexpected keyword is to a library caller


@pytest.mark.parametrize('key,value,bound', [('sort', 'name', 'name'), ('sort_by', 'name', 'name'),
                                             ('rank', 'size', '-size'), ('order', 'name', 'name'), ('head', 3, 3)],
                         ids=['name', 'alias', 'legacy-word', 'cli-destination', 'flag-only'])
def test_every_spelling_a_declaration_gives_still_binds(key, value, bound):
    params = bind_declared_params(SPELLED, {key: value}, transport='typed')
    name = 'head' if key == 'head' else 'sort'
    assert params[name] == bound


def test_the_uri_keeps_its_own_unknown_key_refusal():
    """The URI's rule-3 refusal is unchanged: the same message, a RequestValidationError that is no TypeError."""
    with pytest.raises(RequestValidationError) as raised:
        bind_declared_params(SPECS, 'bogus=1', transport='uri')
    assert not isinstance(raised.value, UnsupportedOverrideError)
    assert str(raised.value) == unsupported_controls_message(SPECS, ['bogus'])
