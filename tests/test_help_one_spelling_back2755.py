"""A declared noun's usage and --help list only canonical flags (Scott 2026-11-22, BACK-2755).

Every option whose spelling has a note-stage RETIREMENTS row is hidden (argparse SUPPRESS) on every declared noun by one
rule in the declared parser; a hidden flag still parses and answers with its note until the cut, and help://schemas keeps
listing legacy spellings as machine data. The conformance test's column 28 measures the rule on every declared noun; this
file holds the shared seams it needs, each as a unit:

- the binder: a legacy entry's old flag that rode inside its control's argument (``--kind, --type``) gets an argument of
  its own, the same dest and options, sharing the control's conflict box, so it can be hidden alone;
- the switches: a switch's short spelling of off (``-q``, canonical) and its legacy off flag (``--no-breadcrumbs``) are
  two arguments sharing one conflict box, so the legacy flag can be hidden and ``-q`` stays;
- the main ``--help`` digest names no old flag, a generated one or one with an argument of its own (``--deps``).
"""
import argparse
import json

import pytest

from conftest import _run_reveal_direct
from reveal.cli.invocation import COMMANDS
from reveal.cli.routing.declared import create_declared_parser, declared_adapter_class
from reveal.utils.query_binding import add_declared_arguments
from reveal.utils.query_parser import CliBinding, LegacySpelling, ParamSpec, ResourceSpec

DECLARED = sorted(name for name, spec in COMMANDS.items() if spec.declared_adapter)


def _kind():
    """A control whose legacy word's old flag takes a value and translates (``--type fn`` is ``--kind function``)."""
    return ParamSpec('kind', 'string', 'Kind', None, str, cli=CliBinding(('--kind',)),
                     legacy=(LegacySpelling('type', codec=lambda value: {'fn': 'function'}.get(value, value),
                                            flag='--type'),))


def _match():
    return ParamSpec('match', 'string', 'Match', (), list, repeatable=True, cli=CliBinding(('--match',)),
                     legacy=(LegacySpelling('body-contains', flag='--body-contains'),))


def _parser(*specs):
    parser = argparse.ArgumentParser(exit_on_error=False)
    add_declared_arguments(parser, specs, ResourceSpec())
    return parser


# --- the binder ----------------------------------------------------------------------------------------------------

def test_a_legacy_flag_that_rode_its_controls_argument_has_one_of_its_own():
    parser = _parser(_kind(), _match())
    for canonical, legacy in (('--kind', '--type'), ('--match', '--body-contains')):
        own, old = parser._option_string_actions[canonical], parser._option_string_actions[legacy]
        assert own is not old, f'{legacy} still shares {canonical}\'s argument: it cannot be hidden alone'
        assert old.option_strings == [legacy] and own.option_strings == [canonical]
        assert (old.dest, old.nargs, type(old)) == (own.dest, own.nargs, type(own))


def test_a_separated_legacy_flag_binds_translates_and_conflicts_as_before():
    """Negative control (holds before and after the split): the old flag stores its control's value, translated; a
    different value beside the control exits 2 naming both; an equal one is one; a repeatable control accumulates."""
    parser = _parser(_kind(), _match())
    assert parser.parse_args(['--type', 'fn']).kind == 'function'
    assert parser.parse_args(['--kind', 'function', '--type', 'fn']).kind == 'function'
    with pytest.raises(argparse.ArgumentError, match='conflicting spellings: --kind, --type'):
        parser.parse_args(['--kind', 'class', '--type', 'fn'])
    assert parser.parse_args(['--match', 'a', '--body-contains', 'b']).match == ['a', 'b']


def test_a_separated_legacy_flag_is_marked_an_old_flag():
    from reveal.utils.query_binding import is_legacy_flag_action
    parser = _parser(_kind())
    assert is_legacy_flag_action(parser._option_string_actions['--type'])
    assert not is_legacy_flag_action(parser._option_string_actions['--kind'])


def test_the_main_help_digest_names_no_old_flag_with_an_argument_of_its_own():
    """The element views' --deps, --mutations, --writes and --calls rode --inputs, --outputs and --callsites: separated,
    they are old flags the main digest skips, as it skips --boundary (BACK-2627); --help-all still lists them."""
    from reveal.cli.parser import create_argument_parser
    from reveal.utils.query_binding import is_legacy_flag_action
    full = create_argument_parser('0', full_help=True)
    old = {option for action in full._actions if is_legacy_flag_action(action) for option in action.option_strings}
    assert {'--deps', '--mutations', '--writes', '--calls', '--boundary'} <= old
    digest = '\n'.join(group.description or '' for group in create_argument_parser('0', full_help=False)._action_groups)
    assert not [option for option in old if f'{option},' in digest or f'{option}\n' in digest]


# --- the switches --------------------------------------------------------------------------------------------------

def _switch_parser():
    from reveal.cli.global_flags import add_switch_argument
    parser = argparse.ArgumentParser(exit_on_error=False)
    add_switch_argument(parser, 'breadcrumbs')
    return parser


def test_a_switchs_short_off_and_its_legacy_off_flag_are_two_arguments():
    parser = _switch_parser()
    short, legacy = parser._option_string_actions['-q'], parser._option_string_actions['--no-breadcrumbs']
    assert short is not legacy and short.option_strings == ['-q'] and legacy.option_strings == ['--no-breadcrumbs']
    assert 'deprecated' in legacy.help and 'deprecated' not in short.help


def test_the_switchs_spellings_still_share_one_conflict_box():
    """Negative control: off spelled twice is one; on beside an off spelling exits 2 naming both."""
    parser = _switch_parser()
    assert parser.parse_args(['-q', '--no-breadcrumbs']).breadcrumbs is False
    assert parser.parse_args(['--breadcrumbs', 'off', '-q']).breadcrumbs is False
    with pytest.raises(argparse.ArgumentError, match='--breadcrumbs, -q'):
        parser.parse_args(['--breadcrumbs', 'on', '-q'])


# --- the declared parser -------------------------------------------------------------------------------------------

@pytest.mark.parametrize('noun,hidden,shown', [
    ('markdown', ('--link-graph', '--lint', '--aggregate', '--body-contains', '--head', '--verbose', '-v',
                  '--also-json', '--no-breadcrumbs', '--no-gitignore'),
     ('--view', '--match', '--limit', '--breadcrumbs', '-q', '--respect-gitignore', '--format', '--output')),
    ('ast', ('--type', '--show', '--tail'), ('--kind', '--view', '--sort')),
    ('metrics', ('--top', '--hotspots', '--no-churn', '--min-lines'), ('--limit', '--churn', '--where')),
])
def test_a_declared_nouns_help_hides_its_note_stage_flags_and_shows_the_rest(noun, hidden, shown):
    parser = create_declared_parser(noun)
    for option in hidden:
        assert parser._option_string_actions[option].help is argparse.SUPPRESS, f'reveal {noun} -h lists {option}'
    for option in shown:
        assert parser._option_string_actions[option].help is not argparse.SUPPRESS, f'reveal {noun} -h hides {option}'


def test_a_hidden_flag_still_answers_with_its_note(tmp_path, monkeypatch):
    """Hidden is not removed: ``reveal ast . --type function`` answers as ``--kind function`` with its one note."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'a.py').write_text('def f():\n    return 1\n\n\nclass C:\n    pass\n', encoding='utf-8')
    legacy = _run_reveal_direct('ast', '.', '--type', 'function', '--format', 'json')
    canonical = _run_reveal_direct('ast', '.', '--kind', 'function', '--format', 'json')
    assert legacy.returncode == canonical.returncode == 0, legacy.stderr
    notes = [w for w in json.loads(legacy.stdout)['meta']['warnings'] if w.get('code') == 'retired_spelling']
    assert len(notes) == 1 and '--kind' in notes[0]['message'], notes
    assert '--type' not in _run_reveal_direct('ast', '--help').stdout


@pytest.mark.parametrize('noun', DECLARED)
def test_help_schemas_still_list_every_legacy_flag(noun):
    """help://schemas/NOUN is machine data, generated from the declarations, not from the parser's help: it keeps
    naming each legacy entry's old flag (BACK-2755 ruling (b))."""
    result = _run_reveal_direct(f'help://schemas/{noun}', '--format', 'json')
    assert result.returncode == 0, result.stderr
    flags = [entry.flag for spec in declared_adapter_class(noun).PARAM_SPECS for entry in spec.legacy if entry.flag]
    assert [flag for flag in flags if flag not in result.stdout] == []
