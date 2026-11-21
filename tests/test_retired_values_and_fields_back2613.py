"""Retired values and retired where fields in the declarations and the canonical request (BACK-2613, S3b).

A value-keyed legacy entry (``LegacySpelling(NAME, value=V)``) declares a value the control retired but still answers
until the cut (AST ``view=calls``): it is accepted beside the declared ``choices``, and a request that gives it has no
canonical form (``UnrenderableRequest``: no request note; its own value row says what replaces it). A retired where field
either answers identically as another field (``field_words``: AST ``type`` -> ``kind``, ``depth`` -> ``nesting_depth``),
which the canonical request spells, or has no canonical form (AST ``calls``: another noun).
"""
import argparse

import pytest

from reveal.utils.query_parser import CliBinding, LegacySpelling, ParamSpec, where_param


def _view():
    return ParamSpec('view', 'string', 'd', None, str, choices=('a', 'b'), role='operation',
                     legacy=(LegacySpelling('view', value='old'),), cli=CliBinding(('--view',)))


def test_a_retired_value_is_accepted_beside_the_choices():
    spec = _view()
    assert spec.retired_values == ('old',)
    assert spec.validate('old') == 'old' and spec.validate('a') == 'a'
    with pytest.raises(ValueError, match="one of"):
        spec.validate('bogus')


def test_a_spec_without_value_entries_has_no_retired_values():
    assert ParamSpec('view', 'string', 'd', None, str, choices=('a',)).retired_values == ()


def test_where_param_carries_field_words():
    spec = where_param('d', retired_fields=('type', 'calls'), field_words=(('type', 'kind'),))
    assert spec.field_words == (('type', 'kind'),)
    assert where_param('d').field_words == ()


@pytest.mark.parametrize('term,expected', [
    ('type!=function', 'kind!=function'), ('type=class', 'kind=class'), ('name=type', 'name=type'),
    ('typed=1', 'typed=1'), ('lines>3', 'lines>3'),
])
def test_canonical_where_term_spells_the_canonical_field(term, expected):
    from reveal.cli.routing.canonical import canonical_where_terms
    spec = where_param('d', retired_fields=('type', 'calls'), field_words=(('type', 'kind'),))
    assert canonical_where_terms(spec, [term]) == [expected]


def test_a_retired_field_with_no_canonical_word_is_unrenderable():
    from reveal.cli.routing.canonical import UnrenderableRequest, canonical_where_terms
    spec = where_param('d', retired_fields=('type', 'calls'), field_words=(('type', 'kind'),))
    with pytest.raises(UnrenderableRequest):
        canonical_where_terms(spec, ['calls=beta'])


def test_a_retired_value_makes_the_request_unrenderable():
    from reveal.cli.routing.canonical import UnrenderableRequest, render_request
    from reveal.utils.query_binding import prepare_declared_params
    spec = _view()

    class Noun:
        PARAM_SPECS = (spec,)

    parser = argparse.ArgumentParser()
    parser.add_argument('--view')
    assert render_request('cli', 'demo', 'p', prepare_declared_params((spec,), 'view=a', 'uri'),
                          parser=parser, adapter=Noun, presentation=False) == 'reveal demo p --view a'
    with pytest.raises(UnrenderableRequest):
        render_request('cli', 'demo', 'p', prepare_declared_params((spec,), 'view=old', 'uri'),
                       parser=parser, adapter=Noun, presentation=False)
