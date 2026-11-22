"""An old flag whose value was optional (``LegacySpelling.flag_optional``, BACK-2627 S3a C3).

The element views' ``--flow[=SEL]`` took an optional selector: bare ``--flow`` is every kind, ``--flow=if`` one. Its
legacy entry declares the value a bare flag stands for (``flag_value``) and ``flag_optional``; the declared parser then
generates the old flag with an optional value (argparse ``nargs='?'``, the bare flag's value as ``const``), in an argument
of its own under the legacy name, and the binder translates both forms as it translates any legacy value. These are the
seam's own controls on toy declarations: an entry without ``flag_optional`` generates exactly as before, and no declared
noun sets it.
"""
import argparse

import pytest

from reveal.utils.query_binding import add_declared_arguments, bind_declared_params, legacy_flag_dests
from reveal.utils.query_parser import CliBinding, LegacySpelling, ParamSpec, ResourceSpec


def _selection(raw):
    """The toy codec: the bare flag's value is every item, an explicit value is a comma union."""
    return 'all' if raw == 'ALL' else raw.replace(',', '+')


MODE = ParamSpec('mode', 'string', 'mode', None, str, cli=CliBinding(('--mode',)),
                 legacy=(LegacySpelling('old', flag='--old', flag_value='ALL', flag_optional=True, codec=_selection),
                         LegacySpelling('bare', flag='--bare', flag_value='fixed'),
                         LegacySpelling('valued', flag='--valued', codec=str.upper)))
VIEW = ParamSpec('view', 'string', 'view', None, str, choices=('list', 'tree'), role='operation',
                 cli=CliBinding(('--view',)))
TERMS = ParamSpec('term', 'string', 'term', None, lambda value: value, repeatable=True, cli=CliBinding(('--term',)),
                  legacy=(LegacySpelling('pick', flag='--pick', flag_value=(), flag_optional=True,
                                         codec=lambda raw: list(raw) if raw == () else [raw],
                                         sets=(('view', 'tree'),)),))
SPECS = (MODE, VIEW, TERMS)


def _parse(argv):
    parser = argparse.ArgumentParser()
    add_declared_arguments(parser, SPECS, ResourceSpec())
    return vars(parser.parse_args(['.', *argv]))


def _bound(argv):
    namespace = {key: value for key, value in _parse(argv).items() if key != 'path'}
    return bind_declared_params(SPECS, namespace, transport='typed')


@pytest.mark.parametrize('argv,stored', [(['--old'], 'ALL'), (['--old=a,b'], 'a,b'), (['--old', 'a,b'], 'a,b')])
def test_the_old_flag_takes_an_optional_value_under_its_legacy_name(argv, stored):
    assert _parse(argv)['old'] == stored


@pytest.mark.parametrize('argv,mode', [(['--old'], 'all'), (['--old=a,b'], 'a+b'), (['--old', 'a'], 'a')])
def test_the_binder_translates_the_bare_and_the_valued_form(argv, mode):
    assert _bound(argv)['mode'] == mode


def test_the_generated_argument_is_optional_valued_and_a_bare_flag_is_its_const():
    parser = argparse.ArgumentParser()
    add_declared_arguments(parser, SPECS, ResourceSpec())
    action = parser._option_string_actions['--old']
    assert (action.dest, action.nargs, action.const) == ('old', '?', 'ALL')
    assert legacy_flag_dests(MODE) == {'old': 'old', 'bare': 'bare'}  # a valued word shares --mode's argument


def test_sibling_entries_without_it_generate_as_before():
    """A no-value old flag stands for its value (nargs 0); a valued one requires its value (nargs None)."""
    parser = argparse.ArgumentParser()
    add_declared_arguments(parser, SPECS, ResourceSpec())
    assert parser._option_string_actions['--bare'].nargs == 0
    assert parser._option_string_actions['--valued'].nargs is None
    assert _bound(['--bare'])['mode'] == 'fixed' and _bound(['--valued', 'x'])['mode'] == 'X'
    with pytest.raises(SystemExit):
        _parse(['--valued'])


def test_an_equal_value_through_both_spellings_is_one_setting_and_a_different_one_conflicts():
    assert _bound(['--old', '--mode', 'all'])['mode'] == 'all'
    with pytest.raises(ValueError, match=r'mode: conflicting spellings'):
        _bound(['--old=a', '--mode', 'b'])


@pytest.mark.parametrize('argv,terms', [(['--pick'], []), (['--pick=x'], ['x']), (['--pick=x', '--term', 'y'], ['x', 'y'])])
def test_on_a_repeatable_control_both_forms_append_and_set_their_controls(argv, terms):
    """A bare flag whose translation is an empty selection still sets the controls it stands for (``--flow`` is
    ``view=flow`` with every kind)."""
    params = _bound(argv)
    flattened = [item for value in params['term'] for item in (value if isinstance(value, list) else [value])]
    assert sorted(flattened) == terms and params['view'] == 'tree'  # a union: the binder orders it by spelling


@pytest.mark.parametrize('entry', [dict(flag='--x', flag_optional=True), dict(flag_value='v', flag_optional=True)])
def test_an_optional_value_needs_its_flag_and_the_bare_flags_value(entry):
    with pytest.raises(ValueError, match=r'optional'):
        LegacySpelling('x', **entry)


def test_no_declared_noun_sets_it():
    """Effect on other nouns: none declares an optional-value old flag, so every noun's parser generates as before."""
    from reveal.cli.invocation import COMMANDS
    from reveal.cli.routing.declared import declared_adapter_class
    declared = [declared_adapter_class(name) for name, command in COMMANDS.items() if command.declared_adapter]
    assert declared, 'no declared noun found: the scan is empty'
    assert not [(adapter.__name__, entry.name) for adapter in declared for spec in adapter.PARAM_SPECS
                for entry in spec.legacy if entry.flag_optional]
