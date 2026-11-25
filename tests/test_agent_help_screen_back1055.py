"""`--agent-help` is generated from the command registry, within its budget (BACK-1055; COMMAND_MODEL rule 6).

The screen (reveal/cli/help_screen.py) teaches the model, the path reads and one entry per live subcommand
from its COMMANDS declaration (role, rung, starter, summary), then "How options work" and the exit codes, in at
most 150 lines. This file holds the screen to that: every live subcommand exactly once, no retired one, the
options block naming only shared control names, and every concrete command it prints running as written in
the executable-docs named fixture. `--agent-help` and `help://agent` print the same screen; the full guide stays
behind `help://agent/full`. No retiring spelling: tests/test_teaching_one_spelling_back2713.py (URI requests)
and the `--agent-help` surface of scripts/check_retired_names.py (RETIREMENTS rows).
"""
import re

import pytest

import test_example_recipes_run as recipes
from conftest import _run_reveal_direct
from test_example_recipes_run import named_harness  # noqa: F401  (the module-scoped fixture)

from reveal.cli.help_screen import render_agent_help
from reveal.cli.invocation import COMMANDS, RETIREMENTS
from reveal.utils.query_parser import SHARED_CONTROL_NAMES

pytestmark = pytest.mark.contract

BUDGET = 150  # COMMAND_MODEL rule 6
LIVE = sorted(name for name in COMMANDS if f'subcommand:{name}' not in RETIREMENTS)
RETIRED = sorted(name for name in COMMANDS if f'subcommand:{name}' in RETIREMENTS)
OPTIONS_HEADING = 'How options work (every noun):'
# Words the model and the options block use as placeholders; a command naming one is a template, not a call.
PLACEHOLDERS = {'PATH', 'ELEMENT', 'NOUN', 'VERB', 'TARGET', 'TOPIC', 'TEXT', 'FIELD', 'FILE', 'NAME', 'V'}


def _entries(screen):
    """The command entries: the `  reveal NAME ...` lines between the first rung heading and the options block."""
    block = screen[screen.index('\nRung '):screen.index(OPTIONS_HEADING)]
    return [line.strip() for line in block.splitlines() if line.startswith('  reveal ')]


def _options_block(screen):
    return screen.partition(OPTIONS_HEADING)[2].partition('\n\n')[0].strip('\n').splitlines()


def _commands(screen):
    """Every concrete command the screen prints: a `reveal ...` line up to its two-space column, templates left out."""
    found = []
    for line in screen.splitlines():
        text = line.strip()
        if not text.startswith('reveal ') or text.startswith('reveal NOUN TARGET --option'):
            continue
        command = re.split(r'\s{2,}', text)[0]
        if not PLACEHOLDERS & set(re.findall(r'\b[A-Z]+\b', command)) or command in _starters():
            found.append(command)
    return list(dict.fromkeys(found))


def _starters():
    return {COMMANDS[name].starter for name in LIVE}


def _screen_problems(screen, live=LIVE, retired=RETIRED):
    problems = []
    lines = screen.splitlines()
    if len(lines) > BUDGET:
        problems.append(f'{len(lines)} lines, over the budget of {BUDGET}')
    heads = [entry.split()[1] for entry in _entries(screen)]
    problems += [f'{name}: {heads.count(name)} entries' for name in live if heads.count(name) != 1]
    problems += [f'retired {name} is taught' for name in retired if re.search(rf'\breveal {name}\b', screen)]
    block = _options_block(screen)
    if len(block) < 5:
        problems.append(f'the options block has {len(block)} lines')
    shown = {flag for line in block if line.strip().startswith(('One name per idea', '--match'))
             for flag in re.findall(r'--([a-z]+)', line)}
    problems += [f'--{name} in the options block is not a shared control name'
                 for name in sorted(shown - set(SHARED_CONTROL_NAMES))]
    if not shown:
        problems.append('the options block names no shared control')
    return problems


@pytest.fixture(scope='module')
def screen():
    return render_agent_help()


def test_the_screen_meets_its_budget_and_teaches_every_live_command_once(screen):
    assert not _screen_problems(screen), _screen_problems(screen)
    assert len(LIVE) >= 20 and len(_entries(screen)) == len(LIVE)


def test_agent_help_and_help_agent_print_the_generated_screen(screen):
    """One screen, two doors; the long guide stays behind help://agent/full."""
    outputs = [_run_reveal_direct(*args) for args in (('--agent-help',), ('help://agent',), ('help', 'agent'))]
    assert [(r.returncode, r.stderr) for r in outputs] == [(0, '')] * 3
    assert outputs[0].stdout == outputs[1].stdout == outputs[2].stdout
    assert screen in outputs[0].stdout and len(outputs[0].stdout.splitlines()) <= BUDGET
    full = _run_reveal_direct('help://agent/full')
    assert full.returncode == 0 and len(full.stdout.splitlines()) > 1000
    assert 'Before You Read This' not in full.stdout and OPTIONS_HEADING not in full.stdout


def test_a_new_command_reaches_the_screen_from_its_declaration_alone(monkeypatch):
    """The screen is generated: a declared role, rung and starter are all a command needs."""
    from reveal.cli import help_screen
    spec = COMMANDS['contracts']._replace(starter='reveal novel src/', summary='A noun the registry just gained')
    monkeypatch.setitem(help_screen.COMMANDS, 'novel', spec)
    text = render_agent_help()
    assert 'reveal novel src/' in text and 'A noun the registry just gained' in text
    assert not _screen_problems(text, live=LIVE + ['novel'])


@pytest.mark.parametrize('mutate, expected', [
    (lambda s: s + '\n' * BUDGET, 'over the budget'),
    (lambda s: s.replace('  reveal overview src/', '  reveal overview src/\n  reveal overview src/', 1),
     'overview: 2 entries'),
    (lambda s: s.replace('  reveal surface src/', '  surface src/', 1), 'surface: 0 entries'),
    (lambda s: s.replace('Rung 0,', '  reveal deps src/\nRung 0,', 1), 'retired deps is taught'),
    (lambda s: s.replace('--detail LEVEL', '--verbose', 1), '--verbose in the options block'),
])
def test_the_screen_check_bites(screen, mutate, expected):
    """Positive controls: each broken screen is named; the generated one passes."""
    assert any(expected in problem for problem in _screen_problems(mutate(screen))), _screen_problems(mutate(screen))
    assert not _screen_problems(screen)


def test_the_screen_prints_concrete_commands_beyond_the_starters(screen):
    commands = _commands(screen)
    assert _starters() <= set(commands)
    assert {'reveal src/app.py load_config', 'reveal src/app.py load_config --view boundary',
            'reveal help quick'} <= set(commands)
    assert not any('NOUN' in c or 'PATH' in c.split() for c in commands if c not in _starters())


@pytest.mark.parametrize('command', _commands(render_agent_help()))
def test_every_command_on_the_screen_runs_as_written(named_harness, command):  # noqa: F811
    recipes._assert_text_as_written(named_harness, command, literal=True)
