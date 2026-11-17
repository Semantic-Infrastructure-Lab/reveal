"""Switches (BACK-2654 rule 15, COMMAND_MODEL "Switches"): positive names with on/off values sharing one codec."""
import json

import pytest

from reveal.adapters.git.params import merge_policy
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


@pytest.mark.parametrize('value, include, legacy', [
    ('on', True, False), ('OFF', False, False), ('true', True, True), ('0', False, True), (False, False, False),
])
def test_git_merges_reads_the_shared_codec_and_remembers_a_legacy_boolean(value, include, legacy):
    policy = merge_policy(value)
    assert (policy.include, policy.legacy) == (include, legacy)


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
def project(tmp_path, monkeypatch):
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
    assert f'note: --no-{switch} is deprecated; use --{switch} off.' in _notes(old), old[2]


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
    assert 'conflicting spellings' not in both[2] and _answer(both) == _answer(once), both  # fallback's answer exits 2


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
    assert set(SWITCHES) == {'breadcrumbs', 'fallback', 'group', 'snippets'}
    for name in SWITCHES:
        row = RETIREMENTS[f'flag:--no-{name}']
        assert (row.old, row.replacement, row.stage, row.standalone) == (f'--no-{name}', f'--{name} off', 'note', False)


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


@pytest.mark.parametrize('flag', ['--no-implementations', '--no-suppress', '--no-gitignore'])
def test_other_no_flags_are_not_switches_yet(flag):
    """Negative control: contracts --no-implementations and patches --no-suppress belong to their packages, and
    --no-gitignore is not one of the four presentation switches; none has a generated row."""
    from reveal.cli.invocation import RETIREMENTS
    assert f'flag:{flag}' not in RETIREMENTS
