"""URI CLI forwarding follows the native declaration's zero policy."""
from types import SimpleNamespace

import pytest

from reveal.adapters import base
from reveal.cli.defaults import _default_args
from reveal.cli.routing.flag_specs import inject_query_flags
from reveal.utils.query_parser import ParamSpec, parse_query_params


@pytest.mark.parametrize('submitted', [0, 1])
def test_declared_uncapped_zero_is_exact_for_any_owner(monkeypatch, submitted):
    adapter = SimpleNamespace(CLI_QUERY_FLAGS={'limit': 'cap={value}'},
                              PARAM_SPECS=(ParamSpec('cap', 'integer', 'cap', None, int, zero_policy='all'),))
    monkeypatch.setattr(base, 'get_adapter_class', lambda scheme: adapter)
    result = inject_query_flags('', 'unrelated', _default_args(limit=submitted))
    assert parse_query_params(result.lstrip('?')) == {'cap': str(submitted)}


def test_legacy_empty_zero_policy_is_not_reinterpreted(monkeypatch):
    adapter = SimpleNamespace(CLI_QUERY_FLAGS={'limit': 'cap={value}'},
                              PARAM_SPECS=(ParamSpec('cap', 'integer', 'cap', None, int, zero_policy='empty'),))
    monkeypatch.setattr(base, 'get_adapter_class', lambda scheme: adapter)
    result = inject_query_flags('', 'legacy', _default_args(limit=0))
    assert parse_query_params(result.lstrip('?')) == {'cap': '1000000'}
