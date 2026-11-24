"""BACK-2627: the ``--view`` spelling of the element views (D20) -- RED until step S3 lands it.

``reveal FILE ELEMENT --view boundary|effects|flow|exits`` answers exactly what today's flag answers (JSON apart from
the retirement note, text stdout, exit), on every fixture language for a named element and a line range; the old flag
keeps answering with one generated note naming its ``--view`` replacement (D5). Flow's selectors are ``--kind`` on the
flow view, a selection that repeats and combines (X3); effects keeps D10's modifiers and strict validation (X4);
boundary's transitive depth is strict on the new spelling and, since BACK-2793, on the legacy flag too. The 13 existing
element RETIREMENTS rows stop naming a replacement that itself retires. The vars, callsites and outputs homes wait on
Scott (X5-X7): no new spelling is asserted for them here.
"""
import json
import re
from pathlib import PurePosixPath

import pytest

from conftest import _run_reveal_direct as run, without_retirement_notes
from test_element_views_back2627 import (LANGUAGES, _python, _refused, _tool_error, copies,  # noqa: F401  (copies is a fixture)
                                         target)

pytestmark = pytest.mark.conformance

# (new spelling, old spelling) of each view the switch moves; flat (no element) is left to the X2 ruling.
VIEWS = {
    'boundary': (['--view', 'boundary'], ['--boundary']),
    'effects': (['--view', 'effects'], ['--effects']),
    'flow': (['--view', 'flow'], ['--flow']),
    'exits': (['--view', 'exits'], ['--exits']),
}
VARIANTS = {
    'boundary-transitive': (['--view', 'boundary', '--transitive'], ['--boundary', '--transitive']),
    'boundary-transitive-depth': (['--view', 'boundary', '--transitive', '--depth', '3'],
                                  ['--boundary', '--transitive', '--depth', '3']),
    'effects-loops': (['--view', 'effects', '--in-loops'], ['--effects', '--in-loops']),
    # D1 (COMMAND_MODEL Depth row): structural depth on --view is --nesting-depth; the legacy flags keep --depth.
    'effects-loops-depth': (['--view', 'effects', '--in-loops', '--nesting-depth', '2'],
                            ['--effects', '--in-loops', '--depth', '2']),
    'effects-state': (['--view', 'effects', '--state'], ['--effects', '--state']),
    'effects-transitive': (['--view', 'effects', '--transitive', '--depth', '1'], ['--effects', '--transitive', '--depth', '1']),
    'flow-if': (['--view', 'flow', '--kind', 'if'], ['--flow=if']),
    'flow-loop': (['--view', 'flow', '--kind', 'loop'], ['--flow=loop']),
    'flow-try': (['--view', 'flow', '--kind', 'try'], ['--flow=try']),
    'flow-if-try': (['--view', 'flow', '--kind', 'if', '--kind', 'try'], ['--flow=if,try']),
    'flow-depth': (['--view', 'flow', '--nesting-depth', '1'], ['--flow', '--depth', '1']),
}


def _positionals(language, mode):
    _, element, selected, _, _ = target(language)
    return [element] if mode == 'named' else [':' + selected]


def _notes(answer):
    return [w for w in answer['meta'].get('warnings', []) if w.get('code') == 'retired_spelling']


def assert_same_answer(path, positionals, new, old, view):
    """The new spelling answers with no note; the old one answers the same JSON and text with one note naming
    ``--view VIEW``; both exit alike."""
    current = run(path, *positionals, *new, '--format', 'json')
    assert current.returncode == 0, current.stderr[:400]
    answer = json.loads(current.stdout)
    assert answer['type'] == 'element_view' and not _notes(answer)
    legacy = run(path, *positionals, *old, '--format', 'json')
    assert legacy.returncode == current.returncode
    legacy_answer = json.loads(legacy.stdout)
    notes = _notes(legacy_answer)
    assert len(notes) == 1 and f'--view {view}' in notes[0]['replacement'], notes
    assert without_retirement_notes(legacy_answer) == answer
    assert run(path, *positionals, *new).stdout == run(path, *positionals, *old).stdout


@pytest.mark.parametrize('mode', ['named', 'range'])
@pytest.mark.parametrize('view', list(VIEWS))
@pytest.mark.parametrize('language', LANGUAGES)
def test_view_answers_what_the_old_flag_answers(copies, language, view, mode):  # noqa: F811
    new, old = VIEWS[view]
    assert_same_answer(copies[language], _positionals(language, mode), new, old, view)


@pytest.mark.parametrize('variant', list(VARIANTS))
@pytest.mark.parametrize('language', ['python', 'typescript', 'go', 'ruby'])
def test_view_modifiers_answer_what_the_old_modifiers_answer(copies, language, variant):  # noqa: F811
    new, old = VARIANTS[variant]
    element = target(language)[4] if variant.startswith(('effects-loops', 'effects-state', 'flow-loop')) else None
    assert_same_answer(copies[language], [element or target(language)[1]], new, old, variant.split('-')[0])


def test_view_answers_on_reveal_run_as_on_the_cli(copies):  # noqa: F811
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_run
    path, element = copies['python'], target('python')[1]
    argv = [path, element, '--view', 'boundary', '--format', 'json']
    cli = run(*argv)
    assert cli.returncode == 0, cli.stderr[:400]
    assert reveal_run(argv) == cli.stdout


# -- X3: --kind on the flow view is a selection that repeats and combines -------------------------------------------

def test_flow_kind_repeats_and_an_equal_repeat_is_one_term(copies):  # noqa: F811
    path, element = copies['python'], target('python')[1]
    once = run(path, element, '--view', 'flow', '--kind', 'try', '--format', 'json')
    twice = run(path, element, '--view', 'flow', '--kind', 'try', '--kind', 'try', '--format', 'json')
    assert once.returncode == twice.returncode == 0, once.stderr[:400]
    assert json.loads(once.stdout) == json.loads(twice.stdout)


@pytest.mark.parametrize('flags,name', [
    pytest.param(['--view', 'boundary', '--kind', 'if'], 'kind', id='kind-on-boundary'),
    pytest.param(['--view', 'boundary', '--in-loops'], 'in-loops', id='in-loops-on-boundary'),
    pytest.param(['--view', 'exits', '--transitive'], 'transitive', id='transitive-on-exits'),
    pytest.param(['--view', 'flow', '--kind', 'nosuch'], 'nosuch', id='unknown-kind'),
])
def test_a_modifier_the_view_does_not_read_exits_2_naming_it(copies, flags, name):  # noqa: F811
    response = run(copies['python'], target('python')[1], *flags, '--format', 'json')
    assert response.returncode == 2 and name in response.stdout + response.stderr
    assert 'unrecognized arguments' not in response.stderr


def test_unknown_view_exits_2_naming_the_element_views(copies):  # noqa: F811
    response = run(copies['python'], target('python')[1], '--view', 'nosuch')
    said = response.stdout + response.stderr
    assert response.returncode == 2 and all(view in said for view in VIEWS), said[:400]


def test_old_flag_and_view_together_are_one_answer_or_two(copies):  # noqa: F811
    path, element = copies['python'], target('python')[1]
    same = run(path, element, '--view', 'boundary', '--boundary', '--format', 'json')
    assert same.returncode == 0, same.stderr[:400]  # one view, two spellings: equal values are one
    other = run(path, element, '--view', 'exits', '--boundary', '--format', 'json')
    _refused(other, '--view', '--boundary', 'conflicting spellings')  # D2: one control, two values


# -- X4: effects keeps D10's strict validation on the new spelling -------------------------------------------------

@pytest.mark.parametrize('flags', [['--depth', '2'], ['--in-loops', '--state'], ['--in-loops', '--transitive'],
                                   ['--state', '--transitive'], ['--transitive', '--depth', '0'],
                                   ['--transitive', '--depth', '6']], ids=lambda flags: ''.join(flags))
def test_view_effects_validates_like_effects(copies, flags):  # noqa: F811
    path, element = copies['python'], target('python')[1]
    assert run(path, element, '--effects', *flags).returncode == 2  # the D10 rule on today's spelling
    response = run(path, element, '--view', 'effects', *flags)
    assert response.returncode == 2 and 'unrecognized arguments' not in response.stderr, response.stderr[:400]


# -- X10 reversed, E8 (BACK-2793): boundary's transitive depth is strict on --view and on the legacy flag ----------

@pytest.mark.parametrize('depth', ['0', '6', '-1'])
def test_view_boundary_transitive_depth_is_strict(copies, depth):  # noqa: F811
    path, element = copies['python'], target('python')[1]
    for view in (['--boundary'], ['--view', 'boundary']):  # the legacy flag clamped until BACK-2793
        response = run(path, element, *view, '--transitive', '--depth', depth)
        assert response.returncode == 2 and f'depth must be 1..5, got {int(depth)}' in response.stderr, response.stderr
        assert 'unrecognized' not in response.stderr


def test_view_boundary_transitive_states_its_depth_in_text_and_json(copies):  # noqa: F811
    path, element = copies['python'], target('python')[1]
    argv = [path, element, '--view', 'boundary', '--transitive', '--depth', '4']
    assert 'depth=4' in run(*argv).stdout
    response = run(*argv, '--format', 'json')
    assert response.returncode == 0, response.stderr[:400]
    assert [value for key, value in json.loads(response.stdout)['meta'].items() if 'depth' in key] == [4]


# -- X2: the ast view and the path-read refusal stay ---------------------------------------------------------------

def test_sibling_ast_view_still_binds_ast_and_a_directory_refuses_element_views(copies):  # noqa: F811
    folder = PurePosixPath(copies['python']).parent.as_posix()
    response = run(f'ast://{folder}', '--view', 'dict-heatmap', '--format', 'json')
    assert response.returncode == 0, response.stderr[:400]
    assert run(folder, '--view', 'boundary').returncode == 2
    assert run(folder, '--name', 'process_order', '--view', 'boundary').returncode == 2


# -- the 13 element RETIREMENTS rows name no replacement that itself retires ----------------------------------------

ELEMENT_ROWS = ['flag:--deps', 'flag:--mutations', 'flag:--writes', 'flag:--calls', 'target:nav.outline',
                'flag:--ifmap', 'flag:--loopmap', 'flag:--catchmap', 'flag:--returns', 'flag:--sideeffects',
                'flag:--fanout', 'flag:--statewrites', 'flag:--flowto']
# The rows whose view is ruled; deps/mutations/writes/calls wait on X6-X8.
RULED_REPLACEMENTS = {
    'target:nav.outline': '--view flow', 'flag:--ifmap': '--view flow --kind if',
    'flag:--loopmap': '--view flow --kind loop', 'flag:--catchmap': '--view flow --kind try',
    'flag:--returns': '--view exits', 'flag:--flowto': '--view exits', 'flag:--sideeffects': '--view effects',
    'flag:--fanout': '--view effects --in-loops', 'flag:--statewrites': '--view effects --state',
}
NEW_ROWS = {'flag:--boundary': '--view boundary', 'flag:--effects': '--view effects', 'flag:--flow': '--view flow',
            'flag:--exits': '--view exits'}


def test_every_element_row_names_no_replacement_that_itself_retires():
    from reveal.cli.invocation import RETIREMENTS
    assert set(ELEMENT_ROWS) <= set(RETIREMENTS)
    for key in ELEMENT_ROWS:
        named = re.findall(r'(?<![\w-])--[a-z][\w-]*', RETIREMENTS[key].replacement)
        assert not [flag for flag in named if f'flag:{flag}' in RETIREMENTS], (key, RETIREMENTS[key].replacement)


@pytest.mark.parametrize('key', list(RULED_REPLACEMENTS))
def test_ruled_element_rows_name_their_view(key):
    from reveal.cli.invocation import RETIREMENTS
    assert RETIREMENTS[key].replacement.startswith(RULED_REPLACEMENTS[key]), RETIREMENTS[key].replacement


@pytest.mark.parametrize('key', list(NEW_ROWS))
def test_the_four_view_flags_have_note_stage_rows(key):
    from reveal.cli.invocation import RETIREMENTS
    assert key in RETIREMENTS and RETIREMENTS[key].stage == 'note'
    assert RETIREMENTS[key].replacement.startswith(NEW_ROWS[key]), RETIREMENTS[key].replacement


@pytest.mark.parametrize('old,new', [(['--ifmap'], ['--view', 'flow', '--kind', 'if']),
                                     (['--returns'], ['--view', 'exits']),
                                     (['--fanout'], ['--view', 'effects', '--in-loops'])])
def test_retired_flags_answer_what_their_named_view_answers(copies, old, new):  # noqa: F811
    path, element = copies['python'], target('python')[1]
    current = run(path, element, *new, '--format', 'json')
    assert current.returncode == 0, current.stderr[:400]
    legacy = json.loads(run(path, element, *old, '--format', 'json').stdout)
    assert without_retirement_notes(legacy) == json.loads(current.stdout)


# =================================================================================================================
# Applicability, One answer per request and Conflicting values on the legacy flags (E6, E7, E13; moved here from
# test_element_views_back2627.py at S4). They come from the declarations S3a adds (X1); a hand-written check is
# forbidden, so they stay RED with the spelling until then.
# =================================================================================================================

# -- E6 (One answer per request): two views exit 2 naming both -----------------------------------------------------

# Two views of the one view control are its two values: the binder's Conflicting-values error naming both (D2); a
# view beside a standalone operation, or two operations, are two answers.
TWO_VIEWS = [
    pytest.param(['{element}', '--boundary', '--exits'], ('boundary', 'exits', 'conflicting spellings'),
                 id='boundary-exits'),
    pytest.param(['{element}', '--varflow', 'result', '--boundary'], ('varflow', 'boundary', 'one answer per request'),
                 id='varflow-boundary'),
    pytest.param(['{element}', '--inputs', '--outputs'], ('inputs', 'outputs', 'one answer per request'),
                 id='inputs-outputs'),
    pytest.param(['{element}', '--flow', '--exits'], ('flow', 'exits', 'conflicting spellings'), id='flow-exits'),
    pytest.param(['{element}', '--boundary', '--outline'], ('boundary', 'outline', 'conflicting spellings'),
                 id='boundary-outline'),
    pytest.param(['{element}', '--callsites', '--keys', 'result'], ('callsites', 'keys', 'one answer per request'),
                 id='callsites-keys'),
    pytest.param([':13', '--scope', '--boundary'], ('scope', 'boundary', 'one answer per request'),
                 id='scope-boundary'),
]


@pytest.mark.parametrize('argv,names', TWO_VIEWS)
def test_two_views_exit_2_naming_both(copies, argv, names):
    path, element = _python(copies)
    response = run(path, *[word.replace('{element}', element) for word in argv], '--format', 'json')
    _refused(response, *names)


def test_sibling_one_view_given_twice_is_one_view_and_effects_already_refuses_a_second(copies):
    path, element = _python(copies)
    twice = run(path, element, '--boundary', '--boundary', '--format', 'json')
    assert twice.returncode == 0 and json.loads(twice.stdout)['meta']['flag'] == 'boundary'
    assert run(path, element, '--effects', '--boundary', '--format', 'json').returncode == 2  # D10


def test_two_views_are_a_tool_error_on_reveal_run(copies):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_run
    path, element = _python(copies)
    _tool_error(reveal_run([path, element, '--boundary', '--exits', '--format', 'json']), 'boundary', 'exits')


# -- E7 (Applicability): a modifier the selected view does not read exits 2 naming it -------------------------------

UNREAD = [
    pytest.param(['--inputs', '--transitive'], 'transitive', id='inputs-transitive'),
    pytest.param(['--exits', '--transitive'], 'transitive', id='exits-transitive'),
    pytest.param(['--flow', '--transitive'], 'transitive', id='flow-transitive'),
    pytest.param(['--boundary', '--cross-calls'], 'cross', id='boundary-cross-calls'),
    pytest.param(['--keys', 'result', '--cross-calls'], 'cross', id='keys-cross-calls'),
    pytest.param(['--boundary', '--head', '2'], 'head', id='boundary-head'),
    pytest.param(['--exits', '--depth', '2'], 'depth', id='exits-depth'),
    pytest.param(['--varflow', 'result', '--depth', '2'], 'depth', id='varflow-depth'),
    pytest.param(['--varflow', 'result', '--cross-calls', '--depth', '2'], 'depth', id='cross-calls-depth'),
]


@pytest.mark.parametrize('flags,name', UNREAD)
def test_unread_modifier_exits_2_naming_it(copies, flags, name):
    path, element = _python(copies)
    _refused(run(path, element, *flags, '--format', 'json'), name, 'not read by this answer')


def test_depth_without_transitive_exits_2_naming_what_it_requires(copies):
    """F-a: boundary reads --depth only with --transitive, so the binder's requires message refuses it."""
    path, element = _python(copies)
    _refused(run(path, element, '--boundary', '--depth', '2', '--format', 'json'), 'depth', 'transitive')


@pytest.mark.parametrize('flags,name', [(['--boundary', '--limit', '2'], '--limit'), (['--exits', '--files'], '--files'),
                                        (['--view', 'flow', '--max-items', '3'], '--max-items')])
def test_a_main_parser_control_no_element_view_reads_exits_2_as_unsupported(copies, flags, name):
    """D3 (U1): an element request takes the globals, its declarations and the measured reads; any other given
    main-parser control is an unsupported control (D18), exit 2 naming it."""
    path, element = _python(copies)
    _refused(run(path, element, *flags, '--format', 'json'), name, 'unsupported control')


@pytest.mark.parametrize('flags', [['--view', 'boundary'], ['--view', 'flow', '--kind', 'if'], ['--boundary'],
                                   ['--varflow', 'result']], ids=['view-boundary', 'view-flow', 'old-boundary', 'varflow'])
def test_verbose_on_an_element_request_exits_2_naming_detail(copies, flags):
    """Conformance cell 4 (rule 4, BACK-2654 note #17): the global --verbose is --detail full, and element views declare
    no detail control, so an element request refuses it, exit 2 naming detail, as a declared noun without detail does."""
    path, element = _python(copies)
    _refused(run(path, element, *flags, '--verbose', '--format', 'json'), '--verbose', 'detail')


def test_sibling_verbose_on_a_path_read_without_an_element_view_still_answers(copies):
    """Negative control: the refusal is the element request's; a file outline and an element extraction keep their
    answer with --verbose."""
    path, element = _python(copies)
    for argv in ((path, '--verbose'), (path, element, '--verbose')):
        assert run(*argv, '--format', 'json').returncode == 0, argv


def test_callsites_value_and_range_conflict(copies):
    """X9: --callsites N-M's value retires into --range, so both together are two values of one selection."""
    path, element = _python(copies)
    _refused(run(path, element, '--callsites', '13-14', '--range', '15-16', '--format', 'json'), 'callsites', 'range')


@pytest.mark.parametrize('flags', [['--boundary', '--transitive'], ['--boundary', '--transitive', '--depth', '3'],
                                   ['--flow', '--depth', '2'], ['--effects', '--in-loops', '--depth', '2'],
                                   ['--varflow', 'result', '--cross-calls'], ['--effects', '--transitive', '--depth', '1']])
def test_sibling_modifiers_their_view_reads_answer(copies, flags):
    path, element = _python(copies)
    response = run(path, element, *flags, '--format', 'json')
    assert response.returncode == 0, response.stderr
    assert not [w for w in json.loads(response.stdout)['meta']['warnings'] if w.get('type') == 'unused_flag']


def test_sibling_effects_already_refuses_an_unread_depth(copies):
    path, element = _python(copies)
    assert run(path, element, '--effects', '--depth', '2', '--format', 'json').returncode == 2  # D10


def test_unread_modifier_is_a_tool_error_on_reveal_run(copies):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_nav, reveal_run
    path, element = _python(copies)
    _tool_error(reveal_run([path, element, '--exits', '--transitive', '--format', 'json']), 'transitive')
    _tool_error(reveal_nav(path, element, 'boundary', transitive=True), 'effects')  # sibling: typed controls refuse


# -- E13: an element view on a directory -------------------------------------------------------------------------

@pytest.mark.parametrize('view', [['--boundary'], ['--varflow', 'x'], ['--exits'], ['--flow'], ['--inputs'],
                                  ['--callsites']], ids=lambda view: view[0][2:])
def test_element_view_on_a_directory_exits_2(copies, view):
    folder = PurePosixPath(copies['python']).parent.as_posix()
    _refused(run(folder, *view, '--format', 'json'))


def test_sibling_directory_effects_already_refuses_and_listing_answers(copies):
    folder = PurePosixPath(copies['python']).parent.as_posix()
    assert run(folder, '--effects').returncode == 2  # D10
    assert run(folder).returncode == 0


def test_element_view_on_a_directory_is_a_tool_error_on_reveal_run(copies):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_run
    _tool_error(reveal_run([PurePosixPath(copies['python']).parent.as_posix(), '--boundary', '--format', 'json']))
