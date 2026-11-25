"""help://quick teaches the ladder from the command registry (BACK-1055; plan 3.1).

The commands block is generated (reveal/cli/help_screen.py ``quick_ladder``): every path read and every live
subcommand that declares a rung, in rung order, each subcommand by its ``starter`` and ``summary``. No adapter rank
(the retired ``QUICK_RANK``), no ``get_help()`` example and no ``COMMANDS.usage`` copy feeds it. The task router
(``_CURATED_DECISION_TREE``) stays curated prose, each row keyed to the noun its example runs; every live noun,
resource and verb is on the ladder or has a row. Every command the page prints runs as written in the
executable-docs named fixture.
"""
import json
import re

import pytest

import test_example_recipes_run as recipes
from conftest import _run_reveal_direct
from test_example_recipes_run import named_harness  # noqa: F401  (the module-scoped fixture)

from reveal.adapters.help import HelpAdapter
from reveal.adapters.registry import OPS_SCHEMES
from reveal.cli.help_screen import PATH_READS, RUNG_QUESTIONS, quick_ladder
from reveal.cli.invocation import COMMANDS, RETIREMENTS

pytestmark = pytest.mark.contract

LIVE = {name: spec for name, spec in COMMANDS.items() if f'subcommand:{name}' not in RETIREMENTS}
ROUTED_ROLES = ('noun', 'resource', 'verb')  # the roles a reader asks a task of; ops and tooling sit behind help
# The page never routes a reader to these (a URL or account placeholder, a host): ops and session rows sit
# behind a family row and are not printed.
UNRUNNABLE = re.compile(r'example\.com|USER/|my-session|auth-refactor')


def _page():
    return HelpAdapter('help://quick').get_element('quick')


def _uncovered(page, curated):
    """Live nouns, resources and verbs neither on the ladder nor keyed by a curated row."""
    covered = {row['noun'] for row in page['commands']} | {row['noun'] for row in curated}
    return sorted(name for name, spec in LIVE.items() if spec.role in ROUTED_ROLES and name not in covered)


def _printed_commands(page):
    """Every command the text page prints: the ladder's commands and each decision-tree example."""
    commands = [row['cmd'] for row in page['commands']] + [row['example'] for row in page['decision_tree']]
    return list(dict.fromkeys(commands))


def test_the_ladder_is_every_rung_declaration_in_rung_order():
    page = _page()
    expected = ([cmd for cmd, rung, _ in PATH_READS if rung is not None]
                + [spec.starter for spec in LIVE.values() if spec.rung is not None])
    assert sorted(row['cmd'] for row in page['commands']) == sorted(expected)
    rungs = [row['rung'] for row in page['commands']]
    assert rungs == sorted(rungs) and None not in rungs
    assert page['rungs'] == [{'rung': r, 'question': RUNG_QUESTIONS[r]} for r in sorted(set(rungs))]
    for row in page['commands']:
        if row['noun']:
            spec = LIVE[row['noun']]
            assert (row['cmd'], row['description'], row['rung']) == (spec.starter, spec.summary, spec.rung)
    assert {0, 1, 2, 3, 4, 5} == set(rungs)  # path reads fill rungs 2 and 4, subcommands the rest


def test_a_new_command_reaches_the_ladder_from_its_declaration_alone(monkeypatch):
    from reveal.cli import help_screen
    spec = COMMANDS['contracts']._replace(starter='reveal novel src/', summary='A noun the registry just gained', rung=3)
    monkeypatch.setitem(help_screen.COMMANDS, 'novel', spec)
    rows = [row for row in quick_ladder()['commands'] if row['noun'] == 'novel']
    assert rows == [{'cmd': 'reveal novel src/', 'description': 'A noun the registry just gained', 'rung': 3,
                     'noun': 'novel'}]


def test_every_curated_row_is_keyed_to_a_live_noun_or_a_resource_scheme():
    for row in HelpAdapter._CURATED_DECISION_TREE:
        noun = row['noun']
        assert noun == '' or noun in LIVE or noun in OPS_SCHEMES, row
        if noun in LIVE:
            assert f'reveal {noun}' in row['example'] or f'{noun}://' in row['example'], row
        if noun == '':  # a path read: no subcommand runs
            assert not any(f'reveal {name} ' in row['example'] for name in LIVE), row


def test_every_live_noun_resource_and_verb_is_on_the_ladder_or_has_a_row():
    assert not _uncovered(_page(), HelpAdapter._CURATED_DECISION_TREE), _uncovered(
        _page(), HelpAdapter._CURATED_DECISION_TREE)


def test_the_coverage_check_bites():
    """Positive control: dropping the only json and pack rows is reported."""
    curated = [row for row in HelpAdapter._CURATED_DECISION_TREE if row['noun'] not in ('json', 'pack')]
    assert _uncovered(_page(), curated) == ['json', 'pack']


def test_family_rows_keep_ops_and_sessions_one_hop_away():
    page = _page()
    printed = {row['noun'] for row in page['decision_tree']}
    assert not printed & ({*OPS_SCHEMES, 'claude', 'codex'})
    family = [row for row in page['decision_tree'] if row['want'].startswith('Other resources')]
    assert [row['example'] for row in family] == ['reveal help://adapters'] * 2


def test_a_missing_row_gets_one_gap_row(monkeypatch):
    """The gap row is the completeness backstop: a noun with no row and no ladder entry is named once."""
    assert not [row for row in _page()['decision_tree'] if row['want'].startswith('other tooling')]
    monkeypatch.setattr(HelpAdapter, '_CURATED_DECISION_TREE',
                        [row for row in HelpAdapter._CURATED_DECISION_TREE if row['noun'] != 'json'])
    gaps = [row for row in _page()['decision_tree'] if row['want'].startswith('other tooling')]
    assert [row['want'] for row in gaps] == ['other tooling not named above: json']


def test_text_and_json_carry_the_same_ladder():
    text = _run_reveal_direct('help://quick')
    data = _run_reveal_direct('help://quick', '--format', 'json')
    assert (text.returncode, data.returncode, text.stderr, data.stderr) == (0, 0, '', '')
    page = json.loads(data.stdout)
    for row in page['rungs']:
        assert f"Rung {row['rung']}, {row['question']}" in text.stdout
    for row in page['commands']:
        assert f"  {row['cmd']}" in text.stdout
    ladder = text.stdout.partition('What do you want to do?')[0]
    assert max(len(line) for line in ladder.splitlines()) <= 120  # the ladder wraps as --agent-help does


@pytest.mark.parametrize('command', [c for c in _printed_commands(_page()) if not UNRUNNABLE.search(c)])
def test_every_command_on_the_page_runs_as_written(named_harness, command):  # noqa: F811
    recipes._assert_text_as_written(named_harness, command, literal=True)


def test_only_the_hidden_family_rows_are_unrunnable():
    """The page prints no command the harness cannot run: the unrunnable examples are all behind a family row."""
    printed = [c for c in _printed_commands(_page()) if UNRUNNABLE.search(c)]
    assert printed == [], printed
    hidden = [row['example'] for row in HelpAdapter._CURATED_DECISION_TREE if UNRUNNABLE.search(row['example'])]
    assert len(hidden) == 7, hidden
