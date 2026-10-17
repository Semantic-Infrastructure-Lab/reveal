"""Declared binding preserves typed values, legacy URI spelling and actual reads."""
import argparse
from urllib.parse import quote

import pytest

from reveal.utils import query_parser as query


@pytest.fixture
def binding():
    from reveal.utils import query_binding
    return query_binding


def spec(name='value', **kwargs):
    return query.ParamSpec(name, 'string', 'Arbitrary scalar', '', str, **kwargs)


@pytest.mark.parametrize('value', ['', '  hi  ', '%26', '+', 'a,b', 'a=b', 'a&b', '雪?z'])
def test_percent_scalar_round_trip_is_exactly_once(binding, value):
    declaration = spec(uri_codec='percent')
    encoded = binding.encode_param_value(declaration, value)
    params = binding.bind_declared_params((declaration,), f'value={encoded}', transport='uri')
    assert declaration.read(params) == value
    typed = binding.bind_declared_params((declaration,), {'value': value}, transport='typed')
    assert declaration.read(typed) == value


def test_list_codec_splits_before_decoding_and_keeps_empty(binding):
    declaration = query.ParamSpec('paths', 'array', 'Paths', (), tuple, uri_codec='comma-percent')
    values = ['a,b.py', '%26', ' a ', '', 'x&y', '雪?z']
    encoded = binding.encode_param_value(declaration, values)
    assert encoded == ','.join(quote(value, safe='') for value in values)
    params = binding.bind_declared_params((declaration,), 'paths='+encoded, transport='uri')
    assert declaration.read(params) == tuple(values)
    typed = binding.bind_declared_params((declaration,), {'paths': values}, transport='typed')
    assert declaration.read(typed) == tuple(values)


def test_binding_validates_without_consumption_or_reconversion(binding):
    calls = []

    def convert(value):
        calls.append(value)
        return str(value)+'!'

    declaration = query.ParamSpec('value', 'string', 'Converted once', '', convert)
    with query.collect_query_keys() as log:
        params = binding.bind_declared_params((declaration,), 'value=hello', transport='uri')
        assert log.seen == {'value'} and not log.used
        assert declaration.read(params) == 'hello!'
        assert declaration.read(params) == 'hello!' and log.used == {'value'}
        assert calls == ['hello']


def test_cli_omission_and_boolean_polarity(binding):
    declarations = (
        spec(cli=query.CliBinding(('--value',))),
        query.ParamSpec('enabled', 'boolean', 'Toggle', True, binding.boolean_value,
                        cli=query.CliBinding(('--disabled',), action='store_false')),
    )
    parser = argparse.ArgumentParser()
    binding.add_declared_arguments(parser, declarations, query.ResourceSpec())
    args = parser.parse_args([])
    assert vars(args) == {'path': '.'}
    with query.collect_query_keys() as log:
        params = binding.bind_declared_params(declarations, vars(args), transport='typed')
        assert not log.seen and not log.used
        assert declarations[1].read(params) is True
    args = parser.parse_args(['--disabled', '--value', ''])
    params = binding.bind_declared_params(declarations, vars(args), transport='typed')
    assert declarations[1].read(params) is False and declarations[0].read(params) == ''


@pytest.mark.parametrize('raw,expected', [('enabled', True), ('enabled=false', False),
                                         ('enabled=false&enabled=true', True)])
def test_bare_boolean_false_and_repeated_last_wins(binding, raw, expected):
    declaration = query.ParamSpec('enabled', 'boolean', 'Toggle', False, binding.boolean_value)
    params = binding.bind_declared_params((declaration,), raw, transport='uri')
    assert declaration.read(params) is expected


def test_schema_additions_do_not_reinterpret_legacy_flags(binding):
    legacy = query.ParamSpec('n', 'integer', 'Rows', 2, int, cli_flags=(('all', '1000000'),))
    assert legacy.schema() == {'type': 'integer', 'description': 'Rows', 'examples': [], 'default': 2}
    assert query.param_cli_flags((legacy,)) == {'all': 'n=1000000'}
    declared = spec(cli=query.CliBinding(('--value',)), choices=('one', 'two'), role='analysis')
    schema = declared.schema()
    assert schema['choices'] == ['one', 'two'] and schema['role'] == 'analysis'
    assert schema['cli']['flags'] == ['--value']
    with pytest.raises(ValueError, match='value'):
        binding.bind_declared_params((declared,), {'value': 'three'}, transport='typed')


def test_raw_legacy_query_exclude_and_filters_do_not_decode(binding):
    declaration = spec()
    params = binding.bind_declared_params((declaration,), 'value=%26+  ', transport='uri')
    assert declaration.read(params) == '%26+'
    assert query.split_exclude_param(query.join_exclude_patterns(['a,b', '%26'])) == ['a,b', '%26']
    assert query.parse_query_filters('name=a%26b')[0].value == 'a%26b'


def test_resource_raw_existing_path_wins_then_decodes_once(binding, tmp_path):
    declaration = query.ResourceSpec(uri_codec='existing-path-first')
    raw = tmp_path / '%26'
    decoded = tmp_path / '&'
    raw.mkdir()
    decoded.mkdir()
    assert binding.bind_resource_path(declaration, str(raw), transport='uri') == str(raw)
    encoded_literal = str(tmp_path / '%2526')
    assert binding.bind_resource_path(declaration, encoded_literal, transport='uri') == str(raw)
    raw.rmdir()
    assert binding.bind_resource_path(declaration, str(raw), transport='uri') == str(decoded)
    question = tmp_path / 'what?,part'
    question.mkdir()
    encoded = str(tmp_path / quote(question.name, safe=''))
    assert binding.bind_resource_path(declaration, encoded, transport='uri') == str(question)
    assert binding.bind_resource_path(declaration, str(question), transport='typed') == str(question)
    assert binding.bind_resource_path(query.ResourceSpec(), encoded, transport='uri') == encoded
