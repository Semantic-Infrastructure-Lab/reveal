"""A flag-only legacy modifier (ParamSpec.flag_only, BACK-2673): the declared parser generates its flag, converted as
the main parser's type= did, and applicability judges it, but it is no URI key, no api.query keyword and no schema
query parameter, so neither transport gains a spelling it never had."""
import argparse

import pytest

from reveal.errors import RequestValidationError, UnsupportedOverrideError
from reveal.utils.query_binding import (add_declared_arguments, apply_declared_overrides, prepare_declared_params,
                                        reject_unread_controls, reject_unsupported_overrides)
from reveal.utils.query_parser import CliBinding, ParamSpec, ResourceSpec, line_range, param_schema, whole_number

LIMIT = ParamSpec('limit', 'integer', 'Row cap', None, whole_number, minimum=0, cli=CliBinding(('--limit',)))
HEAD = ParamSpec('head', 'integer', 'First N rows', None, whole_number, minimum=0, flag_only='applied',
                 cli=CliBinding(('--head',), metavar='N', exclusive='slice'), answers=('rows',))
TAIL = ParamSpec('tail', 'integer', 'Last N rows', None, whole_number, minimum=0, flag_only='applied',
                 cli=CliBinding(('--tail',), metavar='N', exclusive='slice'))
RANGE = ParamSpec('range', 'string', 'Rows START-END', None, line_range, flag_only='applied',
                  cli=CliBinding(('--range',), metavar='START-END', exclusive='slice'))
CHECK = ParamSpec('check', 'boolean', 'Legacy no-op', False, bool, flag_only='inert',
                  cli=CliBinding(('--check', '--lint'), action='store_true'))
SPECS = (LIMIT, HEAD, TAIL, RANGE, CHECK)


def _parser():
    parser = argparse.ArgumentParser(prog='reveal demo')
    add_declared_arguments(parser, SPECS, ResourceSpec('path', 'path', 'The path', required=False))
    return parser


def test_the_flags_are_generated_and_stored_converted():
    from reveal.utils.query_binding import convert_flag_only
    args = _parser().parse_args(['p', '--head', '3', '--check'])
    assert args.head == '3' and args.check is True  # as typed: the binder judges a bad value with its diagnostics
    convert_flag_only(SPECS, args)
    assert args.head == 3
    for typed, stored in (('2-4', (2, 4)), ('3-', (3, None))):
        args = _parser().parse_args(['p', '--range', typed])
        convert_flag_only(SPECS, args)
        assert args.range == stored
    assert _parser().parse_args(['p', '--lint']).check is True


@pytest.mark.parametrize('typed,said', [({'head': '-1'}, 'head must be >= 0'),
                                        ({'range': 'x'}, 'range must be START-END'),
                                        ({'range': '4-2'}, 'Range start must be <= end')])
def test_a_bad_value_stays_as_typed_for_the_binder_to_refuse(typed, said):
    from argparse import Namespace
    from reveal.utils.query_binding import bind_prepared_params, convert_flag_only
    args = Namespace(**typed)
    convert_flag_only(SPECS, args)
    assert vars(args) == typed
    with pytest.raises(RequestValidationError, match=said):
        bind_prepared_params(SPECS, prepare_declared_params(SPECS, typed, 'typed'), transport='typed')


def test_two_slices_exit_2_naming_both(capsys):
    with pytest.raises(SystemExit) as stop:
        _parser().parse_args(['p', '--head', '1', '--tail', '1'])
    assert stop.value.code == 2
    assert 'not allowed with argument --head' in capsys.readouterr().err


def test_a_typed_source_binds_it_as_a_given_control():
    params = prepare_declared_params(SPECS, {'head': 3}, 'typed')
    assert dict(params) == {'head': 3} and params._given == {'head'}


def test_it_is_judged_by_applicability_like_any_control():
    params = prepare_declared_params(SPECS, {'head': 3}, 'typed')
    reject_unread_controls(SPECS, params, lambda: 'rows')  # the declared answer reads it
    with pytest.raises(RequestValidationError, match="control 'head' is not read by this answer"):
        reject_unread_controls(SPECS, params, lambda: 'summary')


@pytest.mark.parametrize('key', ['head', 'tail', 'range', 'check', 'lint'])
def test_it_is_no_uri_key(key):
    with pytest.raises(RequestValidationError) as refused:
        prepare_declared_params(SPECS, f'{key}=1', 'uri')
    message = str(refused.value)
    assert f"unsupported control '{key}'" in message
    assert 'supported controls: limit' in message and 'head' not in message.partition('supported controls:')[2]


def test_a_uri_key_the_noun_declares_still_binds():  # negative control: the canonical control is untouched
    assert dict(prepare_declared_params(SPECS, 'limit=2', 'uri')) == {'limit': '2'}


@pytest.mark.parametrize('key', ['head', 'check'])
def test_it_is_no_api_query_keyword(key):
    with pytest.raises(UnsupportedOverrideError, match=f"unsupported control '{key}'"):
        reject_unsupported_overrides(SPECS, {key: 1})
    params = prepare_declared_params(SPECS, '', 'uri')
    with pytest.raises(UnsupportedOverrideError, match=f"unsupported control '{key}'"):
        apply_declared_overrides(SPECS, params, {key: 1})


def test_it_is_no_schema_query_parameter():
    assert list(param_schema(SPECS)) == ['limit']


@pytest.mark.parametrize('kwargs', [{'flag_only': 'yes', 'cli': CliBinding(('--x',))}, {'flag_only': 'applied'},
                                    {'flag_only': 'applied', 'cli': CliBinding(('--x',)), 'aliases': ('y',)}])
def test_a_malformed_declaration_is_refused(kwargs):
    with pytest.raises(ValueError):
        ParamSpec('x', 'integer', 'X', None, whole_number, **kwargs)


def test_a_uri_and_the_flags_after_it_join_with_the_modifier_kept_as_typed():
    from reveal.utils.query_binding import join_uri_and_flags
    joined = join_uri_and_flags(SPECS, prepare_declared_params(SPECS, 'limit=2', 'uri'),
                                prepare_declared_params(SPECS, {'range': (2, 4)}, 'typed'))
    assert dict(joined) == {'limit': '2', 'range': (2, 4)} and joined._given == {'limit', 'range'}
    assert joined._source_query == 'limit=2'  # no URI spelling to echo


def test_withholding_drops_the_modifiers_once_judged():
    from reveal.utils.query_binding import withhold_flag_only
    params = prepare_declared_params(SPECS, {'head': 3, 'limit': 2}, 'typed')
    withhold_flag_only(SPECS, params)
    assert dict(params) == {'limit': 2} and params._given == {'limit'}


def test_an_adapter_built_from_bound_params_never_meets_a_modifier():
    from reveal.adapters.factory import _canonical_init
    from reveal.utils.query_binding import bind_prepared_params

    class Demo:
        PARAM_SPECS = SPECS
        RESULT_TYPE = 'rows'  # the answer that reads head: applicability passes, then the build withholds it

        def __init__(self, resource, params=None):
            self.params = dict(params)

    params = bind_prepared_params(SPECS, prepare_declared_params(SPECS, {'head': 3, 'limit': 2}, 'typed'),
                                  transport='typed')
    assert _canonical_init(Demo, 'p', params=params).params == {'limit': 2}


def test_legacy_slices_declares_the_three_flags_as_one_exclusive_group():
    from reveal.utils.query_parser import legacy_slices
    head, range_ = legacy_slices(head=('rows',), range=())
    assert (head.name, head.flag_only, head.answers, head.cli.flags, head.cli.exclusive) == \
        ('head', 'applied', ('rows',), ('--head',), 'slice')
    assert range_.validate('2-3') == (2, 3) and range_.answers == ()
    with pytest.raises(ValueError, match='no legacy slice modifier'):
        legacy_slices(first=())
