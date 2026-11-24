"""The element views' declarations bind every spelling to one canonical request (BACK-2627 S3b-2, S3a design 3-4).

``reveal/nav_params.py`` declares the element answer; it is not wired into the file route yet (S3b-3), so these tests
generate its arguments onto a parser that owns the main parser's shared flags (``--depth``, ``--range``, ``--head``,
``--tail``, ``--name``, ``--grep``, ``--type``, ``--sort``: C1 keeps them), read the namespace with
``declared.typed_source`` and bind with ``bind_element_request``. Expected sides: each legacy flag binds the request its
``--view`` spelling binds (the S3b-1 parity table measured those answers equal on 19 languages); D10's effects rules come
from ``requires``; two views or a view and an operation are one setting or one answer per request; a modifier the
answer does not read is refused (Applicability); a directory refuses every element view.
"""
import argparse
from pathlib import Path

import pytest

from reveal.cli.routing.declared import typed_source
from reveal.errors import RequestValidationError
from reveal.nav_params import (ELEMENT_KEYS, ELEMENT_VIEW_SPECS, ELEMENT_VIEWS, ElementRequest, bind_element_request,
                               element_request_given)
from reveal.utils.query_binding import add_declared_arguments

FILE = (Path(__file__).parent / 'fixtures' / 'conformance' / 'python' / 'sample.py').as_posix()
FOLDER = Path(FILE).parent.as_posix()
ELEMENT = 'process_order'


def _parser() -> argparse.ArgumentParser:
    """The main parser's flags that other path-read answers also read, as the main parser declares them."""
    parser = argparse.ArgumentParser(exit_on_error=False)
    parser.add_argument('--depth', type=int, default=None)
    parser.add_argument('--head', type=int)
    parser.add_argument('--tail', type=int)
    parser.add_argument('--range', type=str)
    parser.add_argument('--name', '--search', dest='name', type=str)
    parser.add_argument('--grep', type=str)
    parser.add_argument('--sort', type=str)
    parser.add_argument('--type', type=str)
    add_declared_arguments(parser, ELEMENT_VIEW_SPECS, None)
    return parser


def _source(argv):
    return typed_source(ELEMENT_VIEW_SPECS, _parser().parse_args(argv))


def bind(argv, *, path=FILE, element=ELEMENT):
    source, spelled = _source(argv)
    return bind_element_request(source, spelled, path=path, element=element)


def refused(argv, *names, path=FILE):
    with pytest.raises(RequestValidationError) as caught:
        bind(argv, path=path)
    for name in names:
        assert name in str(caught.value), (name, str(caught.value))
    return str(caught.value)


# -- generation -----------------------------------------------------------------------------------------------------

def test_the_declarations_generate_every_flag_once_beside_the_main_parsers_own():
    parser = _parser()
    flags = {flag for spec in ELEMENT_VIEW_SPECS for flag in spec.flags}
    assert flags <= set(parser._option_string_actions)
    for owned in ('--depth', '--range', '--head', '--tail', '--name', '--grep', '--type', '--sort'):
        assert parser._option_string_actions[owned].default is not argparse.SUPPRESS  # the parser's own argument
    assert parser._option_string_actions['--flow'].nargs == '?'  # C3: --flow[=SEL]
    assert '--outline' not in flags  # the main parser keeps --outline for file and Markdown outlines


def test_the_view_choices_are_the_four_element_views():
    assert ELEMENT_VIEWS == ('boundary', 'effects', 'flow', 'exits')
    message = refused(['--view', 'nosuch'], 'nosuch')
    assert all(view in message for view in ELEMENT_VIEWS), message


# -- every legacy flag binds what its replacement binds (the S3b-1 parity table) --------------------------------------

PARITY = [
    (['--boundary'], ['--view', 'boundary']),
    (['--exits'], ['--view', 'exits']),
    (['--returns'], ['--view', 'exits']),
    (['--flowto'], ['--view', 'exits']),
    (['--effects'], ['--view', 'effects']),
    (['--sideeffects'], ['--view', 'effects']),
    (['--sideeffects', '--transitive'], ['--view', 'effects', '--transitive']),
    (['--effects', '--transitive', '--depth', '3'], ['--view', 'effects', '--transitive', '--depth', '3']),
    (['--effects', '--in-loops'], ['--view', 'effects', '--in-loops']),
    (['--effects', '--in-loops', '--depth', '2'], ['--view', 'effects', '--in-loops', '--nesting-depth', '2']),
    (['--effects', '--state'], ['--view', 'effects', '--state']),
    (['--fanout'], ['--view', 'effects', '--in-loops']),
    (['--fanout', '--depth', '2'], ['--view', 'effects', '--in-loops', '--nesting-depth', '2']),
    (['--statewrites'], ['--view', 'effects', '--state']),
    (['--flow'], ['--view', 'flow']),
    (['--flow=if'], ['--view', 'flow', '--kind', 'if']),
    (['--flow', 'loop'], ['--view', 'flow', '--kind', 'loop']),
    (['--flow=if,try'], ['--view', 'flow', '--kind', 'if', '--kind', 'try']),
    (['--flow', '--depth', '1'], ['--view', 'flow', '--nesting-depth', '1']),
    (['--ifmap'], ['--view', 'flow', '--kind', 'if']),
    (['--loopmap'], ['--view', 'flow', '--kind', 'loop']),
    (['--catchmap'], ['--view', 'flow', '--kind', 'try']),
    (['--loopmap', '--depth', '2'], ['--view', 'flow', '--kind', 'loop', '--nesting-depth', '2']),
    (['--boundary', '--transitive'], ['--view', 'boundary', '--transitive']),
    (['--boundary', '--transitive', '--depth', '3'], ['--view', 'boundary', '--transitive', '--depth', '3']),
    (['--deps'], ['--inputs']),
    (['--mutations'], ['--outputs']),
    (['--writes'], ['--outputs']),
    (['--calls'], ['--callsites']),
    (['--calls', '13-14'], ['--callsites', '13-14']),
]


@pytest.mark.parametrize('legacy,canonical', PARITY, ids=lambda argv: ' '.join(argv))
def test_each_legacy_flag_binds_its_replacements_request(legacy, canonical):
    assert bind(legacy) == bind(canonical)


@pytest.mark.parametrize('legacy,other', [
    (['--ifmap'], ['--view', 'flow']), (['--fanout'], ['--view', 'effects']), (['--statewrites'], ['--view', 'effects']),
    (['--boundary'], ['--view', 'exits']), (['--fanout', '--depth', '2'], ['--view', 'effects', '--in-loops']),
    (['--boundary', '--transitive', '--depth', '3'], ['--view', 'boundary', '--transitive', '--depth', '4']),
])
def test_sibling_the_comparison_sees_a_different_request(legacy, other):
    """Positive control for the parity table: a request that differs in one field is not equal."""
    assert bind(legacy) != bind(other)


def test_the_code_element_outline_binds_the_flow_view():
    """``--outline`` has no generated flag here: the file route puts it in the source only for an element request on a
    code file (its ``target:nav.outline`` row)."""
    for depth in (None, 2):
        source, spelled = _source([] if depth is None else ['--depth', str(depth)])
        legacy = bind_element_request({**source, 'outline': True}, spelled, path=FILE, element=ELEMENT)
        assert legacy == bind(['--view', 'flow'] + ([] if depth is None else ['--nesting-depth', str(depth)]))


@pytest.mark.parametrize('argv,expected', [
    (['--view', 'boundary'], dict(view='boundary', mode=None, kind=(), transitive=False, depth=None)),
    (['--view', 'effects'], dict(view='effects', mode='ordinary')),
    (['--view', 'effects', '--in-loops'], dict(view='effects', mode='loops', nesting_depth=3)),
    (['--view', 'effects', '--state'], dict(view='effects', mode='state')),
    (['--view', 'boundary', '--transitive'], dict(transitive=True, depth=2)),
    (['--view', 'flow', '--kind', 'try', '--kind', 'if', '--kind', 'try'], dict(view='flow', kind=('try', 'if'))),
    (['--varflow', 'result', '--cross-calls'], dict(view=None, operation='varflow', value='result', cross_calls=True)),
    (['--callsites'], dict(operation='callsites', value='FULL')),
    (['--around'], dict(operation='around', value=20)),
    (['--scope'], dict(operation='scope', value=None)),
    (['--view', 'exits', '--range', '13-14'], dict(view='exits', range=(13, 14))),
])
def test_the_bound_request_records_the_selection(argv, expected):
    request = bind(argv)
    assert isinstance(request, ElementRequest) and request.path == FILE and request.element == ELEMENT
    assert {key: getattr(request, key) for key in expected} == expected


def test_effects_answers_are_keyed_by_their_mode():
    assert [bind(argv).answer for argv in (['--effects'], ['--fanout'], ['--statewrites'], ['--exits'], ['--deps'])] \
        == ['effects:ordinary', 'effects:loops', 'effects:state', 'exits', 'inputs']


# -- X10 reversed, E8 (BACK-2793): every spelling of the transitive depth is the one walk depth, refused outside 1..5 --

@pytest.mark.parametrize('depth', ['0', '-1', '9'])
@pytest.mark.parametrize('view', ['--boundary', '--sideeffects'])
def test_the_legacy_transitive_depth_is_strict(view, depth):
    # it clamped (0 meant the default 2, -1 walked one hop, 9 five)
    refused([view, '--transitive', '--depth', depth], f'depth must be 1..5, got {int(depth)}')


@pytest.mark.parametrize('view', ['--boundary', '--sideeffects'])
def test_the_legacy_transitive_depth_binds_an_in_range_value(view):
    assert bind([view, '--transitive', '--depth', '4']).depth == 4
    assert bind([view, '--transitive']).depth == 2


@pytest.mark.parametrize('depth', ['0', '6', '-1'])
@pytest.mark.parametrize('view', [['--view', 'boundary'], ['--view', 'effects'], ['--effects']])
def test_the_canonical_transitive_depth_is_strict(view, depth):
    refused([*view, '--transitive', '--depth', depth], f'depth must be 1..5, got {int(depth)}')


# -- X4/D10: effects' modifiers through requires ----------------------------------------------------------------------

@pytest.mark.parametrize('flags,names', [
    (['--in-loops', '--state'], ('in-loops', 'state')),
    (['--in-loops', '--transitive'], ('transitive', 'in-loops')),
    (['--state', '--transitive'], ('transitive', 'state')),
    (['--depth', '2'], ('depth', 'transitive')),
    (['--state', '--depth', '2'], ('depth',)),
    (['--nesting-depth', '2'], ('nesting-depth', 'in-loops')),
    (['--state', '--nesting-depth', '2'], ('nesting-depth',)),
])
@pytest.mark.parametrize('view', [['--view', 'effects'], ['--effects']])
def test_effects_modifiers_follow_d10(view, flags, names):
    refused([*view, *flags], *names)


@pytest.mark.parametrize('argv', [['--view', 'effects', '--in-loops', '--nesting-depth', '2'],
                                  ['--view', 'effects', '--transitive', '--depth', '5'],
                                  ['--view', 'flow', '--nesting-depth', '1'], ['--fanout', '--nesting-depth', '4']])
def test_sibling_the_modifiers_effects_and_flow_read_bind(argv):
    assert bind(argv) is not None


def test_d1_depth_on_flow_and_loops_is_graph_hops_on_the_canonical_spelling():
    """COMMAND_MODEL Depth row: --view flow and --view effects --in-loops take --nesting-depth; their --depth is hops."""
    refused(['--view', 'flow', '--depth', '1'], 'depth')
    refused(['--view', 'effects', '--in-loops', '--depth', '2'], 'depth')


# -- Conflicting values and one answer per request -------------------------------------------------------------------

@pytest.mark.parametrize('argv,named', [
    (['--boundary', '--exits'], '--boundary, --exits'),
    (['--view', 'exits', '--boundary'], '--view, --boundary'),
    (['--flow', '--exits'], '--exits, --flow'),
    (['--flow=if', '--view', 'exits'], '--view, --flow'),
])
def test_two_views_are_one_control_with_two_values(argv, named):
    refused(argv, 'view: conflicting spellings', named)


@pytest.mark.parametrize('argv', [['--view', 'boundary', '--boundary'], ['--fanout', '--in-loops'],
                                  ['--fanout', '--effects'], ['--ifmap', '--kind', 'if'], ['--flow=if', '--flow=if']])
def test_an_equal_value_through_two_spellings_is_one_setting(argv):
    assert bind(argv) is not None


def test_legacy_and_canonical_kinds_combine():
    assert bind(['--flow=if', '--kind', 'try']).kind in (('if', 'try'), ('try', 'if'))
    assert set(bind(['--ifmap', '--catchmap']).kind) == {'if', 'try'}


@pytest.mark.parametrize('argv', [['--fanout', '--state'], ['--fanout', '--statewrites']])
def test_two_effects_modes_are_one_view_refused_by_d10(argv):
    """Both words are view=effects (one setting); the modes they set meet D10's exclusion."""
    refused(argv, 'in-loops', 'state')


@pytest.mark.parametrize('argv,names', [
    (['--varflow', 'result', '--boundary'], ('varflow', 'boundary')),
    (['--inputs', '--outputs'], ('inputs', 'outputs')),
    (['--callsites', '--keys', 'result'], ('callsites', 'keys')),
    (['--scope', '--boundary'], ('scope', 'boundary')),
    (['--view', 'boundary', '--grep', 'x'], ('view', 'grep')),
    (['--view', 'boundary', '--name', 'x'], ('view', 'name')),
    (['--deps', '--writes'], ('inputs', 'outputs')),
])
def test_two_answers_are_one_answer_per_request(argv, names):
    refused(argv, *names, 'one answer per request')


# -- Applicability: a modifier the answer does not read ---------------------------------------------------------------

@pytest.mark.parametrize('argv,name', [
    (['--view', 'boundary', '--kind', 'if'], 'kind'),
    (['--view', 'boundary', '--in-loops'], 'in-loops'),
    (['--view', 'exits', '--transitive'], 'transitive'),
    (['--inputs', '--transitive'], 'transitive'),
    (['--flow', '--transitive'], 'transitive'),
    (['--boundary', '--cross-calls'], 'cross-calls'),
    (['--keys', 'result', '--cross-calls'], 'cross-calls'),
    (['--boundary', '--head', '2'], 'head'),
    (['--exits', '--depth', '2'], 'depth'),
    (['--varflow', 'result', '--depth', '2'], 'depth'),
    (['--varflow', 'result', '--cross-calls', '--depth', '2'], 'depth'),
    (['--narrow', 'x', '--range', '1-2'], 'range'),
    (['--scope', '--range', '1-2'], 'range'),
    (['--view', 'exits', '--nesting-depth', '2'], 'nesting-depth'),
])
def test_a_modifier_the_answer_does_not_read_is_refused_naming_it(argv, name):
    refused(argv, name, 'not read by this answer')


@pytest.mark.parametrize('argv,names', [
    (['--boundary', '--depth', '2'], ('depth', 'transitive')),       # depth is read by boundary, with --transitive
    (['--callsites', '13-14', '--range', '15-16'], ('range', 'callsites')),  # X9: two ranges of one selection
])
def test_a_modifier_without_what_it_requires_is_refused_naming_both(argv, names):
    refused(argv, *names)


@pytest.mark.parametrize('argv', [['--callsites', '--range', '13-14'], ['--boundary', '--range', '13-14'],
                                  ['--varflow', 'result', '--range', '13-14'], ['--keys', 'result', '--range', '13-14']])
def test_sibling_the_range_selects_lines_of_the_answers_that_read_it(argv):
    assert bind(argv).range == (13, 14)


@pytest.mark.parametrize('argv,name', [(['--view', 'flow', '--kind', 'nosuch'], 'nosuch'),
                                       (['--view', 'flow', '--kind', 'if,try'], 'repeat --kind'),
                                       (['--flow=bogus'], 'flow selectors')])
def test_an_unknown_kind_is_refused_naming_the_kinds(argv, name):
    refused(argv, name, 'if', 'loop', 'try')


# -- the directory refusal and the requests that are not element requests ---------------------------------------------

@pytest.mark.parametrize('argv', [['--view', 'boundary'], ['--boundary'], ['--varflow', 'x'], ['--exits'], ['--flow'],
                                  ['--inputs'], ['--callsites'], ['--view', 'boundary', '--name', 'x']])
@pytest.mark.parametrize('element', [None, ELEMENT])
def test_a_directory_refuses_every_element_view(argv, element):
    source, spelled = _source(argv)
    with pytest.raises(RequestValidationError, match=r'must be a file.*element views read one file'):
        bind_element_request(source, spelled, path=FOLDER, element=element)


def test_the_whole_file_flat_view_binds():
    request = bind(['--view', 'boundary'], element=None)
    assert request is not None and request.element is None and request.view == 'boundary'


@pytest.mark.parametrize('argv', [[], ['--depth', '2'], ['--range', '1-5'], ['--head', '3'], ['--name', 'x'],
                                  ['--grep', 'x'], ['--type', 'function'], ['--sort', 'name']])
@pytest.mark.parametrize('path', [FILE, FOLDER])
def test_a_request_without_an_element_control_is_not_an_element_request(argv, path):
    source, spelled = _source(argv)
    assert not element_request_given(source)
    assert bind_element_request(source, spelled, path=path, element=None) is None


def test_the_element_keys_are_every_spelling_of_the_element_controls():
    assert {'view', 'kind', 'boundary', 'flow', 'fanout', 'outline', 'deps', 'calls', 'scope', 'around'} <= ELEMENT_KEYS
    assert not {'depth', 'range', 'head', 'tail', 'name', 'grep', 'type', 'sort'} & ELEMENT_KEYS


# -- a typed source (MCP reveal_nav, S3b-4) binds by name and by presence ---------------------------------------------

@pytest.mark.parametrize('source,argv', [
    ({'view': 'effects', 'in-loops': True}, ['--view', 'effects', '--in-loops']),
    ({'fanout': True}, ['--fanout']),
    ({'flow': 'if,loop'}, ['--view', 'flow', '--kind', 'if', '--kind', 'loop']),
    ({'flow': True}, ['--view', 'flow']),
    ({'view': 'boundary', 'transitive': True, 'depth': 3}, ['--view', 'boundary', '--transitive', '--depth', '3']),
])
def test_a_typed_source_binds_like_its_flags(source, argv):
    assert bind_element_request(source, path=FILE, element=ELEMENT) == bind(argv)


def test_a_typed_source_names_the_conflict_by_key():
    with pytest.raises(RequestValidationError, match=r'view: conflicting spellings: boundary, exits'):
        bind_element_request({'boundary': True, 'exits': True}, path=FILE, element=ELEMENT)
