"""Typed API overlays extend declared binding without consuming query controls."""
import pytest

from reveal.utils.query_binding import bind_declared_params, boolean_value
from reveal.utils.query_parser import CliBinding, ParamSpec, QueryParams, collect_query_keys

pytestmark = pytest.mark.component


def test_uri_and_typed_override_convert_once_without_consuming():
    calls = []

    def convert(value):
        calls.append(value)
        return value + '!'

    spec = ParamSpec('name', 'string', '', '', convert, uri_codec='percent')
    with collect_query_keys() as log:
        params = bind_declared_params([spec], 'name=old%26', transport='uri', overrides={'name': 'new%26+,'})
        assert calls == ['old&', 'new%26+,']
        assert log.seen == {'name'} and log.used == set()
        assert spec.read(params) == 'new%26+,!'
        assert calls == ['old&', 'new%26+,'] and log.used == {'name'}


@pytest.mark.parametrize('value,expected', [(False, False), (None, True)])
def test_boolean_false_and_none_default_override_uri(value, expected):
    spec = ParamSpec('flag', 'boolean', '', True, boolean_value)
    params = bind_declared_params([spec], 'flag=true', transport='uri', overrides={'flag': value})
    assert spec.read(params) is expected


@pytest.mark.parametrize('value,expected', [(0, 0), (None, 7)])
def test_zero_and_none_default_override_uri(value, expected):
    spec = ParamSpec('depth', 'integer', '', 7, int, minimum=0)
    params = bind_declared_params([spec], 'depth=3', transport='uri', overrides={'depth': value})
    assert spec.read(params) == expected


def test_invalid_original_source_precedes_valid_or_unknown_overrides():
    spec = ParamSpec('depth', 'integer', '', 0, int, minimum=0)
    for overrides in ({'depth': 0}, {'nonsense': True}):
        with pytest.raises(ValueError, match='depth must be >= 0'):
            bind_declared_params([spec], 'depth=-1', transport='uri', overrides=overrides)


def test_unknown_override_rejects_instead_of_typed_preparation_dropping():
    spec = ParamSpec('name', 'string', '', '', str)
    assert bind_declared_params([spec], {'nonsense': True}, transport='typed') == {}
    with pytest.raises(TypeError, match='nonsense'):
        bind_declared_params([spec], '', transport='uri', overrides={'nonsense': True})


def test_overlay_names_are_canonical_not_cli_destination_aliases():
    spec = ParamSpec('name', 'string', '', '', str, cli=CliBinding(('--name',), dest='cli_name'))
    assert spec.read(bind_declared_params([spec], {'cli_name': 'old'}, transport='typed')) == 'old'
    params = bind_declared_params([spec], {'cli_name': 'old'}, transport='typed', overrides={'name': 'new'})
    assert spec.read(params) == 'new'
    with pytest.raises(TypeError, match='cli_name'):
        bind_declared_params([spec], '', transport='uri', overrides={'cli_name': 'new'})


def test_omission_empty_strings_and_original_mapping_are_preserved():
    specs = [ParamSpec('first', 'string', '', '', str), ParamSpec('second', 'string', '', '', str)]
    source = {'first': 'original'}
    overrides = {'second': ''}
    params = bind_declared_params(specs, source, transport='typed', overrides=overrides)
    assert specs[0].read(params) == 'original' and specs[1].read(params) == ''
    assert source == {'first': 'original'} and overrides == {'second': ''}
    assert bind_declared_params(specs, '', transport='uri', overrides={}) == {}


def test_list_codec_typed_overlay_keeps_percent_plus_and_commas_and_detects_mutation():
    spec = ParamSpec('names', 'string', '', [], list, uri_codec='comma-percent')
    override = {'names': ['x%26', 'y+z', 'a,b']}
    params = bind_declared_params([spec], 'names=uri%2Cone,plus+sign', transport='uri', overrides=override)
    assert spec.read(params) == ['x%26', 'y+z', 'a,b']
    assert override == {'names': ['x%26', 'y+z', 'a,b']}
    params['names'].append('changed')
    with pytest.raises(ValueError, match='Normalized names changed'):
        spec.read(params)


def test_omitted_override_retains_uri_normalization_and_unknown_uri_key():
    calls = []

    def convert(value):
        calls.append(value)
        return value + '!'

    spec = ParamSpec('name', 'string', '', '', convert)
    with collect_query_keys() as log:
        params = bind_declared_params([spec], 'name=value&unknown=true', transport='uri', overrides={})
        assert log.used == set()
        assert spec.read(params) == 'value!'
        assert calls == ['value']
        assert dict(params.peek_items())['unknown'] == 'true'
        assert log.used == {'name'}


def test_typed_source_and_override_queryparams_are_not_read_as_applied():
    analysis = ParamSpec('name', 'string', '', '', str, role='analysis')
    top = ParamSpec('top', 'integer', '', None, int, role='presentation')
    with collect_query_keys() as log:
        source = QueryParams(name='original')
        overrides = QueryParams(top=0)
        params = bind_declared_params([analysis, top], source, transport='typed', overrides=overrides)
        assert log.seen == {'name', 'top'} and log.used == set()
        assert analysis.read(params) == 'original'
        assert log.used == {'name'}
        assert top.read(params) == 0 and log.used == {'name', 'top'}
