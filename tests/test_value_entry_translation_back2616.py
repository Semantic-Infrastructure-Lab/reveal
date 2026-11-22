"""A value-keyed legacy entry with a codec names the canonical value its retired value answers as (BACK-2616).

``LegacySpelling(NAME, value=V)`` alone is a retired value with no canonical form (AST ``view=calls``, BACK-2613): the
request says no request note. Git's ``view=log`` and ``detail=summary`` answer exactly as ``history`` and ``normal``, so
their entries carry a codec, and the binder reads the retired value as that canonical value wherever the control is
spelled (its own key or a legacy word of it). A replacement never names a spelling that itself retires (COMMAND_MODEL
"Retirement notes"): the request note renders the canonical value.
"""
import pytest

from reveal.utils.query_binding import bind_declared_params
from reveal.utils.query_parser import CliBinding, LegacySpelling, ParamSpec


def _view():
    return ParamSpec('view', 'string', 'd', None, str, choices=('history', 'blame'), role='operation',
                     cli=CliBinding(('--view',)),
                     legacy=(LegacySpelling('type'), LegacySpelling('view', value='log', codec=lambda _: 'history'),
                             LegacySpelling('view', value='calls')))


@pytest.mark.parametrize('query', ['view=log', 'type=log'])
def test_a_translated_retired_value_binds_as_its_canonical_value(query):
    assert dict.get(bind_declared_params((_view(),), query, transport='uri'), 'view') == 'history'


def test_typed_and_flag_sources_translate_too():
    assert dict.get(bind_declared_params((_view(),), {'view': 'log'}, transport='typed'), 'view') == 'history'


def test_only_an_untranslated_value_entry_is_a_retired_value_with_no_canonical_form():
    spec = _view()
    assert spec.retired_values == ('calls',)
    assert dict.get(bind_declared_params((spec,), 'view=calls', transport='uri'), 'view') == 'calls'
