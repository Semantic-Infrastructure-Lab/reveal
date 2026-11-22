"""One legacy word can stand for several canonical controls (``LegacySpelling.sets``, BACK-2614 ruling Q2-A).

The word's own value binds to the control that owns the entry; ``sets`` holds the other canonical controls it stands for,
with fixed values. Markdown's ``aggregate=F`` is an entry on ``field`` setting ``view=aggregate``; element views
(BACK-2627) need two pairs (``--fanout`` is ``view=effects`` and ``in-loops=true``). Translated at binding on every
transport: an equal value of a set control is one setting, a different one is the Conflicting-values error naming both
spellings. These are the seam's own controls on toy declarations; an entry with empty ``sets`` binds exactly as before.
"""
import argparse

import pytest

from reveal.utils.query_binding import (add_declared_arguments, bind_declared_params, join_uri_and_flags,
                                        legacy_flag_dests, prepare_declared_params, reject_two_answers)
from reveal.utils.query_parser import CliBinding, LegacySpelling, ParamSpec, ResourceSpec

VIEW = ParamSpec('view', 'string', 'view', None, str, choices=('list', 'agg', 'effects'), role='operation',
                 cli=CliBinding(('--view',)), legacy=(LegacySpelling('old', codec=lambda raw: 'list'),))
FIELD = ParamSpec('field', 'string', 'field', None, str, cli=CliBinding(('--field',)),
                  legacy=(LegacySpelling('agg', flag='--agg', sets=(('view', 'agg'),)),
                          LegacySpelling('fanout', flag='--fanout', sets=(('view', 'effects'), ('loops', 'yes'))),
                          LegacySpelling('plain')))
LOOPS = ParamSpec('loops', 'string', 'loops', None, str, cli=CliBinding(('--loops',)))
TARGET = ParamSpec('target', 'string', 'target', None, str, role='operation', cli=CliBinding(('--target',)))
SPECS = (VIEW, FIELD, LOOPS, TARGET)


def test_the_entry_translates_to_its_owner_and_every_set_control():
    assert FIELD.legacy_entry('agg').translate('type') == {'field': 'type', 'view': 'agg'}
    assert FIELD.legacy_entry('fanout').translate('x') == {'field': 'x', 'view': 'effects', 'loops': 'yes'}
    assert FIELD.legacy_entry('plain').translate('x') == {'field': 'x'}  # empty sets: its owner only


@pytest.mark.parametrize('source,transport', [('fanout=x', 'uri'), ({'fanout': 'x'}, 'typed')])
def test_the_word_binds_every_control_on_every_transport(source, transport):
    params = bind_declared_params(SPECS, source, transport=transport)
    assert (params['field'], params['view'], params['loops']) == ('x', 'effects', 'yes')


def test_the_word_binds_every_control_as_a_typed_override():
    params = bind_declared_params(SPECS, '', transport='uri', overrides={'fanout': 'x'})
    assert (params['field'], params['view'], params['loops']) == ('x', 'effects', 'yes')


@pytest.mark.parametrize('source,transport', [('plain=x', 'uri'), ({'plain': 'x'}, 'typed')])
def test_empty_sets_is_a_no_op(source, transport):
    params = bind_declared_params(SPECS, source, transport=transport)
    assert (params['field'], params.get('view'), params.get('loops')) == ('x', None, None)
    assert params._implied_by == {}


@pytest.mark.parametrize('source', ['agg=type&field=type', 'view=agg&agg=type', 'view=agg&field=type&agg=type',
                                    'fanout=x&loops=yes&view=effects'])
def test_an_equal_value_of_a_set_control_is_one_setting(source):
    bind_declared_params(SPECS, source, transport='uri')


@pytest.mark.parametrize('source,named', [
    ('agg=type&field=tags', ('field', 'agg')),       # the owner: the existing Conflicting-values error
    ('view=list&agg=type', ('view', 'agg')),          # a set control
    ('old=1&agg=type', ('old', 'agg')),               # a set control given by its own legacy word
    ('fanout=x&loops=no', ('loops', 'fanout')),
])
def test_a_different_value_names_both_spellings(source, named):
    with pytest.raises(ValueError, match=r'conflicting spellings') as caught:
        bind_declared_params(SPECS, source, transport='uri')
    assert all(name in str(caught.value) for name in named), caught.value


@pytest.mark.parametrize('source,named', [
    ({'field': 'tags', 'agg': 'type'}, '--field, --agg'),
    ({'view': 'list', 'agg': 'type'}, '--view, --agg'),
    ({'loops': 'no', 'fanout': 'x'}, '--loops, --fanout'),
])
def test_a_different_flag_value_names_both_flags_as_typed(source, named):
    """The subcommand form: each spelling is the flag that carried it."""
    spelled = {'field': '--field', 'view': '--view', 'loops': '--loops', 'agg': '--agg', 'fanout': '--fanout'}
    with pytest.raises(ValueError, match=r'conflicting spellings') as caught:
        prepare_declared_params(SPECS, source, 'typed', spelled=spelled)
    assert named in str(caught.value), caught.value


def test_a_different_override_value_names_both_spellings():
    with pytest.raises(ValueError, match=r'conflicting spellings: view, agg'):
        bind_declared_params(SPECS, '', transport='uri', overrides={'view': 'list', 'agg': 'type'})


@pytest.mark.parametrize('source,overrides', [('agg=type&target=t', None), ({'agg': 'type', 'target': 't'}, None),
                                              ('target=t', {'agg': 'type'})])
def test_an_answer_the_word_selects_is_named_by_the_word(source, overrides):
    """One answer per request: the view a word sets meets another operation under the word's name, whichever source
    (URI, typed keywords, a typed override) gave the word."""
    transport = 'uri' if isinstance(source, str) else 'typed'
    with pytest.raises(ValueError, match=r'agg and target select different answers'):
        bind_declared_params(SPECS, source, transport=transport, overrides=overrides)


def test_its_old_flag_keeps_an_argument_of_its_own():
    """The generated --agg stores under the legacy name (a shared argument would drop the set controls)."""
    assert legacy_flag_dests(FIELD) == {'agg': 'agg', 'fanout': 'fanout'}
    parser = argparse.ArgumentParser()
    add_declared_arguments(parser, SPECS, ResourceSpec())
    namespace = vars(parser.parse_args(['.', '--agg', 'type']))
    params = bind_declared_params(SPECS, {k: v for k, v in namespace.items() if k != 'path'}, transport='typed')
    assert (params['field'], params['view']) == ('type', 'agg')


def test_a_flag_after_a_uri_names_the_legacy_flag_that_set_the_control():
    """"Flags after a URI": ``?view=list --agg b`` exits naming --agg, the flag typed, not --view."""
    uri = prepare_declared_params(SPECS, 'view=list', 'uri')
    typed = prepare_declared_params(SPECS, {'agg': 'b'}, 'typed', spelled={'agg': '--agg'})
    with pytest.raises(ValueError, match=r'^--agg conflicts with view=list'):
        join_uri_and_flags(SPECS, uri, typed, spelled={'agg': '--agg'})


def test_a_flag_after_a_uri_that_agrees_is_one_setting():
    uri = prepare_declared_params(SPECS, 'view=agg', 'uri')
    typed = prepare_declared_params(SPECS, {'agg': 'b'}, 'typed', spelled={'agg': '--agg'})
    joined = join_uri_and_flags(SPECS, uri, typed, spelled={'agg': '--agg'})
    assert (joined['field'], joined['view']) == ('b', 'agg')
