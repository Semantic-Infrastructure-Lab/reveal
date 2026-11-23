"""Switches (BACK-2654 rule 15, COMMAND_MODEL "Switches"): positive names with on/off values sharing one codec."""
import json

import pytest

from reveal.adapters.git.params import MERGES
from reveal.cli.invocation import RETIREMENTS
from reveal.utils.query_binding import switch_value


@pytest.mark.parametrize('value, expected', [
    ('on', True), ('off', False), ('ON', True), ('Off', False),
    ('true', True), ('false', False), ('yes', True), ('no', False), ('1', True), ('0', False),
    (True, True), (False, False),
])
def test_the_shared_switch_codec_reads_on_off_and_booleans(value, expected):
    assert switch_value(value) is expected


@pytest.mark.parametrize('value', ['maybe', '', 'enabled', 2, None])
def test_the_shared_switch_codec_rejects_other_values(value):
    with pytest.raises(ValueError):
        switch_value(value)


@pytest.mark.parametrize('value, include', [
    ('on', True), ('OFF', False), ('true', True), ('0', False), ('1', True), (False, False),
])
def test_git_merges_is_the_shared_codec(value, include):
    """A legacy boolean spelling is the switch's value on every view (BACK-2656: it no longer routes to ownership)."""
    assert MERGES.validate(value) is include


# --- rule 15: presentation switches -------------------------------------------------------------------------
# Each case: label -> (argv before the switch, environment); the switch is the label's first word. The request answers
# differently with the switch off, which the control in test_each_switch_takes_on_and_off asserts, so an equal answer
# is evidence.
_LONG_LINES = '\n'.join(f'x{i} = 1  # {"y" * 130}' for i in range(12)) + '\n'
CASES = {
    'breadcrumbs': (['a.py'], {'REVEAL_BREADCRUMBS': '1'}),
    'fallback': (['x.unknownext'], {}),
    'group': (['check', 'long.py', '--select', 'E501', '--severity', 'low'], {}),
    'group-file-check': (['long.py', '--check', '--select', 'E501', '--severity', 'low'], {}),
    'snippets': (['check', 'long.py', '--select', 'E501', '--severity', 'low'], {}),
}
SWITCH_OF = {label: label.split('-')[0] for label in CASES}


@pytest.fixture
def project(tmp_path, monkeypatch, settled_hints):
    (tmp_path / 'a.py').write_text('def f(x):\n    return x\n', encoding='utf-8')
    (tmp_path / 'long.py').write_text(_LONG_LINES, encoding='utf-8')
    (tmp_path / 'x.unknownext').write_text('hello\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    for name in ('REVEAL_BREADCRUMBS', 'REVEAL_FORMAT'):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def _run(case, *extra, env=None, monkeypatch=None):
    from conftest import _run_reveal_direct
    argv, case_env = CASES[case]
    for name, value in {**case_env, **(env or {})}.items():
        monkeypatch.setenv(name, value)
    result = _run_reveal_direct(*argv, *extra)
    return result.returncode, result.stdout, result.stderr


def _answer(run):
    """What a request answers, notes aside: exit, stdout and stderr without its note lines."""
    rc, out, err = run
    return rc, out, '\n'.join(line for line in err.splitlines() if not line.startswith('note:'))


def _notes(run):
    return [line for line in run[2].splitlines() if line.startswith('note:')]


@pytest.mark.parametrize('case', sorted(CASES))
def test_each_switch_takes_on_and_off_and_answers_as_the_old_flag(project, monkeypatch, case):
    switch = SWITCH_OF[case]
    default = _run(case, monkeypatch=monkeypatch)
    old = _run(case, f'--no-{switch}', monkeypatch=monkeypatch)
    assert _answer(old) != _answer(default), f'control: --no-{switch} changes nothing on {CASES[case][0]}'
    off, on = _run(case, f'--{switch}', 'off', monkeypatch=monkeypatch), _run(case, f'--{switch}=on', monkeypatch=monkeypatch)
    assert _answer(off) == _answer(old), f'--{switch} off answers differently from --no-{switch}: {off}'
    assert _answer(on) == _answer(default), f'--{switch} on answers differently from the default: {on}'
    assert not _notes(off) or all(f'--no-{switch}' not in note for note in _notes(off)), _notes(off)


@pytest.mark.parametrize('case', sorted(CASES))
def test_the_old_no_flag_answers_with_its_replaced_by_note(project, monkeypatch, case):
    switch = SWITCH_OF[case]
    old = _run(case, f'--no-{switch}', monkeypatch=monkeypatch)
    assert f'note: {RETIREMENTS[f"flag:--no-{switch}"].text}' in _notes(old), old[2]


@pytest.mark.parametrize('case', ['group', 'snippets'])
def test_the_old_no_flag_note_reaches_the_json_answer(project, monkeypatch, case):
    switch = SWITCH_OF[case]
    rc, out, _err = _run(case, f'--no-{switch}', '--format', 'json', monkeypatch=monkeypatch)
    warnings = json.loads(out).get('meta', {}).get('warnings', [])
    assert any(w.get('code') == 'retired_spelling' and w.get('field') == f'flag:--no-{switch}' for w in warnings), out


@pytest.mark.parametrize('case', sorted(CASES))
def test_the_old_flag_against_an_opposite_switch_exits_2_naming_both(project, monkeypatch, case):
    switch = SWITCH_OF[case]
    rc, out, err = _run(case, f'--no-{switch}', f'--{switch}', 'on', monkeypatch=monkeypatch)
    assert rc == 2 and f'conflicting spellings: --no-{switch}, --{switch}' in err, (rc, err)


@pytest.mark.parametrize('case', sorted(CASES))
def test_the_old_flag_and_an_equal_switch_count_once(project, monkeypatch, case):
    switch = SWITCH_OF[case]
    both, once = (_run(case, f'--no-{switch}', f'--{switch}', 'off', monkeypatch=monkeypatch),
                  _run(case, f'--{switch}', 'off', monkeypatch=monkeypatch))
    old = _run(case, f'--no-{switch}', monkeypatch=monkeypatch)
    # Both must be the old flag's own answer: two rejections would compare equal too (fallback's answer exits 2).
    assert 'conflicting spellings' not in both[2] and _answer(both) == _answer(once) == _answer(old), both


@pytest.mark.parametrize('case', sorted(CASES))
def test_a_switch_given_twice_differently_exits_2_and_a_value_outside_on_off_exits_2(project, monkeypatch, case):
    switch = SWITCH_OF[case]
    rc, _out, err = _run(case, f'--{switch}', 'on', f'--{switch}', 'off', monkeypatch=monkeypatch)
    assert rc == 2 and f'--{switch} on and --{switch} off' in err, (rc, err)
    rc, _out, err = _run(case, f'--{switch}', 'maybe', monkeypatch=monkeypatch)
    assert rc == 2 and f'--{switch}' in err and "'maybe'" in err and 'on or off' in err, (rc, err)


def test_q_is_a_note_free_short_spelling_of_breadcrumbs_off(project, monkeypatch):
    short, off = _run('breadcrumbs', '-q', monkeypatch=monkeypatch), _run('breadcrumbs', '--breadcrumbs', 'off', monkeypatch=monkeypatch)
    assert _answer(short) == _answer(off) and not _notes(short), short
    rc, _out, err = _run('breadcrumbs', '-q', '--breadcrumbs', 'on', monkeypatch=monkeypatch)
    assert rc == 2 and 'conflicting spellings: -q, --breadcrumbs' in err, (rc, err)


def test_every_switch_is_declared_once_and_its_retirement_row_is_generated():
    from reveal.cli.global_flags import SWITCHES
    from reveal.cli.invocation import RETIREMENTS
    assert set(SWITCHES) == {'breadcrumbs', 'fallback', 'group', 'snippets', 'respect-gitignore'}
    legacy = {name: f'--no-{name}' for name in SWITCHES} | {'respect-gitignore': '--no-gitignore'}
    for name in SWITCHES:
        row = RETIREMENTS[f'flag:{legacy[name]}']
        assert (row.old, row.replacement, row.stage, row.standalone) == (legacy[name], f'--{name} off', 'note', False)
    assert 'flag:--no-respect-gitignore' not in RETIREMENTS


def _parsers():
    from reveal.cli.commands.check import create_check_parser
    from reveal.cli.parser import create_argument_parser
    from reveal.cli.routing.declared import create_declared_parser
    return {'main': create_argument_parser('0'), 'check': create_check_parser(), 'ast': create_declared_parser('ast')}


@pytest.mark.parametrize('parser_name, switches', [
    ('main', ('breadcrumbs', 'fallback', 'group')), ('check', ('breadcrumbs', 'group', 'snippets')),
    ('ast', ('breadcrumbs',)),
])
def test_each_parser_carrying_a_switch_generates_both_spellings_on_one_positive_dest(parser_name, switches):
    actions = _parsers()[parser_name]._option_string_actions
    for name in switches:
        assert actions[f'--{name}'].dest == name and actions[f'--{name}'].metavar == 'on|off', (parser_name, name)
        assert actions[f'--no-{name}'].dest == name, f'{parser_name}: --no-{name} is a hand row (dest no_{name})'
    assert not [option for option in actions if option.startswith('--no-') and option[5:] in
                ('breadcrumbs', 'fallback', 'group', 'snippets') and actions[option].dest.startswith('no_')]


@pytest.mark.parametrize('flag', ['--no-implementations', '--no-suppress'])
def test_other_no_flags_are_not_switches_yet(flag):
    """Negative control: contracts --no-implementations and patches --no-suppress belong to their packages; neither
    has a generated row."""
    from reveal.cli.invocation import RETIREMENTS
    assert f'flag:{flag}' not in RETIREMENTS


@pytest.mark.parametrize('typed', [['--group', 'off'], ['--no-group']])
def test_a_switch_typed_off_is_a_given_flag_beside_a_second_path(project, typed):
    """A switch off is a value (False), not an absent flag: beside a second path it is refused like --group on, and
    the refusal names the switch by its flag; the legacy spelling also prints its note."""
    from conftest import _run_reveal_direct
    result = _run_reveal_direct('a.py', 'long.py', *typed)
    assert result.returncode == 2 and 'long.py' in result.stderr and '--group' in result.stderr, result.stderr
    assert (f'note: {RETIREMENTS["flag:--no-group"].text}' in result.stderr) == (typed == ['--no-group'])


@pytest.mark.parametrize('view', [[], ['f'], ['--metadata'], ['--typed']], ids=['structure', 'element', 'metadata', 'typed'])
@pytest.mark.parametrize('switch', ['breadcrumbs', 'fallback'])
def test_the_old_no_flag_note_reaches_every_file_view_json_answer(project, switch, view):
    """Rule 2 on the file route's JSON writers (structure, element, metadata, typed): a legacy switch spelling there
    answers with its retired_spelling warning, as the URI and subcommand writers already do."""
    from conftest import _run_reveal_direct
    result = _run_reveal_direct('a.py', *view, f'--no-{switch}', '--format', 'json')
    warnings = json.loads(result.stdout).get('meta', {}).get('warnings', [])
    assert result.returncode == 0 and [w.get('field') for w in warnings if w.get('code') == 'retired_spelling'] == [
        f'flag:--no-{switch}'], result.stdout



# --- item D2: --respect-gitignore on|off, --no-gitignore its named legacy spelling ---------------------------

@pytest.mark.parametrize('parser_name', ['main', 'check', 'ast'])
def test_respect_gitignore_is_a_switch_on_every_walking_parser(parser_name):
    actions = _parsers()[parser_name]._option_string_actions
    positive, legacy = actions['--respect-gitignore'], actions['--no-gitignore']
    assert positive.dest == legacy.dest == 'respect_gitignore' and positive.metavar == 'on|off', parser_name
    assert type(positive) is type(legacy) and type(positive).__name__ == '_SwitchAction', parser_name


def _walk(*extra):
    from conftest import _run_reveal_direct
    result = _run_reveal_direct('.', *extra)
    return result.returncode, result.stdout, result.stderr


def test_no_gitignore_notes_its_replacement_and_conflicts_with_an_opposite_switch(project):
    old = _walk('--no-gitignore')
    assert f'note: {RETIREMENTS["flag:--no-gitignore"].text}' in _notes(old), old[2]
    rc, _out, err = _walk('--no-gitignore', '--respect-gitignore', 'on')
    assert rc == 2 and 'conflicting spellings: --no-gitignore, --respect-gitignore' in err, (rc, err)
    both = _walk('--no-gitignore', '--respect-gitignore', 'off')
    assert _answer(both) == _answer(old) == _answer(_walk('--respect-gitignore', 'off')), both


def test_bare_respect_gitignore_still_means_on(project):
    """The old no-value --respect-gitignore (the default, on) answers as before without a note (the control half, green
    before and after); --respect-gitignore on answers the same (red until the switch exists)."""
    bare, on, default = _walk('--respect-gitignore'), _walk('--respect-gitignore', 'on'), _walk()
    assert bare[0] == 0 and _answer(bare) == _answer(default) and not _notes(bare), bare
    assert _answer(on) == _answer(default), on


# --- item D2: notes name a switch as typed (the item F principle) -------------------------------------------

@pytest.mark.parametrize('typed, named', [(['--no-group'], '--no-group'), (['--group', 'off'], '--group'),
                                          (['-q'], '-q'), (['--no-breadcrumbs'], '--no-breadcrumbs')])
def test_the_ledger_names_a_switch_as_typed(project, typed, named):
    from conftest import _run_reveal_direct
    target = ['a.py', 'f'] if named.endswith('group') else ['ast', '.']
    err = _run_reveal_direct(*target, *typed).stderr
    note = next((line for line in err.splitlines() if 'has no effect' in line), '')
    assert note.startswith(f'Note: {named} has no effect'), err


@pytest.mark.parametrize('typed, hint', [(['--no-group'], 'reveal --stdin --no-group'),
                                         (['--group', 'off'], 'reveal --stdin --group on|off')])
def test_the_second_path_refusal_names_a_switch_as_typed(project, typed, hint):
    from conftest import _run_reveal_direct
    err = _run_reveal_direct('a.py', 'long.py', *typed).stderr
    refusal = '\n'.join(line for line in err.splitlines() if not line.startswith('note:'))
    assert hint in refusal and (typed[0] != '--no-group' or '--group ' not in refusal.replace('--no-group', '')), err


def test_a_flag_spec_note_names_respect_gitignore_as_typed(project):
    from conftest import _run_reveal_direct
    conf = project / 'site.conf'
    conf.write_text('server {\n  listen 80;\n}\n', encoding='utf-8')
    err = _run_reveal_direct(f'nginx://{conf.as_posix()}', '--respect-gitignore', 'off').stderr  # undeclared (reveal:// is)
    assert '--respect-gitignore has no effect on nginx://' in err, err



@pytest.mark.parametrize('view', [[], ['--files'], ['--meta']], ids=['tree', 'files', 'meta'])
def test_the_legacy_gitignore_note_reaches_the_directory_json_answers(project, view):
    """Rule 2 on the directory views' JSON writers (tree, --files, directory metadata): --no-gitignore there answers
    with its retired_spelling warning, as the file views do."""
    from conftest import _run_reveal_direct
    result = _run_reveal_direct('.', *view, '--no-gitignore', '--format', 'json')
    warnings = json.loads(result.stdout).get('meta', {}).get('warnings', [])
    assert result.returncode == 0 and [w.get('field') for w in warnings if w.get('code') == 'retired_spelling'] == [
        'flag:--no-gitignore'], result.stdout


# --- item D3: every flag with several spellings is named as typed ------------------------------------------

def _every_parser():
    from reveal.cli.invocation import COMMANDS
    from reveal.cli.parser import create_argument_parser
    yield 'main', create_argument_parser('0')
    for name, spec in sorted(COMMANDS.items()):
        yield name, spec.load()[0]


def _spellings_of(parser):
    """dest -> every option string spelling it, from the parser's actions (several actions may share a dest)."""
    spellings = {}
    for action in parser._actions:
        if action.dest != 'help':
            spellings.setdefault(action.dest, []).extend(action.option_strings)
    return {dest: options for dest, options in spellings.items() if len(options) > 1}


def _typed_case(parser, option):
    action = parser._option_string_actions[option]
    return [option, 'X'] if action.nargs not in (0, '?') else [option]


def test_every_spelling_of_every_aliased_flag_is_recorded_as_typed():
    """Generated from the parsers: for each flag with more than one spelling (--check/--lint, --top/--limit, -i, ...),
    the spelling the command line typed is the one notes and errors name."""
    from reveal.cli.invocation import Invocation, invocation_scope, record_typed_spellings, typed_spelling
    checked = 0
    for name, parser in _every_parser():
        for dest, options in _spellings_of(parser).items():
            for option in options:
                argv = _typed_case(parser, option)
                with invocation_scope(Invocation.parse(['reveal', *argv])):
                    record_typed_spellings(parser, argv)
                    assert typed_spelling(dest, '<none>') == option, (name, dest, option)
                checked += 1
    assert checked > 100, checked


def test_typed_spellings_skip_a_value_and_read_attached_and_clustered_forms():
    from reveal.cli.invocation import Invocation, invocation_scope, record_typed_spellings, typed_spellings
    from reveal.cli.parser import create_argument_parser
    parser = create_argument_parser('0')
    argv = ['a.py', '--name', '-v', '--search=x', '-ic', '--lint']  # '-v' is --name's value, not --verbose
    with invocation_scope(Invocation.parse(['reveal', *argv])):
        record_typed_spellings(parser, argv)
        typed = typed_spellings()
    assert typed.get('name') == '--name' and 'verbose' not in typed, typed
    assert typed.get('ignore_case') == '-i' and typed.get('copy') == '-c' and typed.get('check') == '--lint', typed


@pytest.mark.parametrize('argv, says', [
    (['a.py', 'f', '-i'], 'Note: -i has no effect on the file view'),
    (['a.py', 'f', '-r'], 'Note: -r has no effect on the file view'),
    (['a.py', 'f', '-v'], 'Note: -v has no effect on the file view'),
    (['diff://a.py:long.py', '-v'], 'Note: -v has no effect on diff:// queries'),  # undeclared (reveal:// is, BACK-2767)
    (['a.py', 'long.py', '--search', 'f'], "Error: --search answers for the whole of a.py"),
    (['a.py', 'f', '--lint'], 'Error: --lint reads no element'),
    (['a.py', 'f', '--ignore-case'], 'Note: --ignore-case has no effect on the file view'),  # control: first spelling
])
def test_notes_and_refusals_name_an_aliased_flag_as_typed(project, argv, says):
    from conftest import _run_reveal_direct
    err = _run_reveal_direct(*argv).stderr
    assert says in err, err
