"""Every live subcommand declares where `--agent-help` teaches it, and its starter runs (BACK-1055).

COMMAND_MODEL rule 6: `--agent-help` is generated from the noun registry, one line per noun. The registry is
`COMMANDS` (reveal/cli/invocation.py); each live entry declares its `role` (COMMAND_ROLES), its `rung` on the
plan's ladder (section 3.1; None off the ladder) and one `starter`, a subcommand-form command the screen prints.
A retired subcommand declares none, so no generated screen can teach it. Each starter runs as written in the
executable-docs harness's named fixture (tests/doc_command_fixture.py), the gate the guides' commands pass.
"""
import shlex

import pytest

import test_example_recipes_run as recipes
from scripts.check_retired_names import scan
from teaching_patterns import retiring_lines
from test_example_recipes_run import named_harness  # noqa: F401  (the module-scoped fixture)

from reveal.cli.invocation import COMMAND_ROLES, COMMANDS, RETIREMENTS

pytestmark = pytest.mark.contract

LIVE = sorted(name for name in COMMANDS if f'subcommand:{name}' not in RETIREMENTS)
RETIRED = sorted(name for name in COMMANDS if f'subcommand:{name}' in RETIREMENTS)
# Plan section 3.1: the code nouns sit on rungs 0-5; a verb may sit on one (check and diff are judgment inputs).
LADDER_ROLES = {'noun': range(0, 6), 'verb': range(0, 6)}


def _declaration_problems(name, spec):
    problems = []
    if spec.role not in COMMAND_ROLES:
        problems.append(f'{name}: role {spec.role!r} is not one of {COMMAND_ROLES}')
    if spec.role == 'noun' and spec.rung is None:
        problems.append(f'{name}: a noun declares its rung')
    if spec.rung is not None and spec.rung not in LADDER_ROLES.get(spec.role, ()):
        problems.append(f'{name}: rung {spec.rung!r} is not a ladder rung for role {spec.role!r}')
    words = shlex.split(spec.starter) if spec.starter else []
    if words[:2] != ['reveal', name]:
        problems.append(f'{name}: starter {spec.starter!r} is not `reveal {name} ...`')
    problems += [f'{name}: starter teaches a retiring spelling: {line}' for line in retiring_lines(spec.starter)]
    problems += [f'{name}: starter teaches retired {key}' for _, key, _ in scan(spec.starter)]
    return problems


def test_the_live_and_retired_sets_are_not_vacuous():
    assert len(LIVE) >= 20 and len(RETIRED) >= 5, (LIVE, RETIRED)
    assert {'overview', 'calls', 'check', 'help', 'json'} <= set(LIVE)


@pytest.mark.parametrize('name', LIVE)
def test_every_live_subcommand_declares_role_rung_and_starter(name):
    assert not _declaration_problems(name, COMMANDS[name])


@pytest.mark.parametrize('name', RETIRED)
def test_a_retired_subcommand_declares_nothing_to_teach(name):
    spec = COMMANDS[name]
    assert (spec.role, spec.rung, spec.starter) == ('', None, ''), name


def test_every_role_has_a_live_command():
    """Each COMMAND_ROLES entry heads a group on the screen; an empty one would print a bare heading."""
    assert {COMMANDS[name].role for name in LIVE} == set(COMMAND_ROLES)


@pytest.mark.parametrize('spec, expected', [
    (COMMANDS['calls']._replace(role='nouns'), "role 'nouns' is not one of"),
    (COMMANDS['calls']._replace(rung=None), 'a noun declares its rung'),
    (COMMANDS['json']._replace(rung=3), "not a ladder rung for role 'resource'"),
    (COMMANDS['calls']._replace(starter='reveal imports src/'), 'is not `reveal calls ...`'),
    (COMMANDS['calls']._replace(starter="reveal calls 'calls://src/?callers=main'"), 'retiring spelling'),
    (COMMANDS['calls']._replace(starter='reveal calls src/ --sort=-callers --top 5'), 'retired param:calls.top'),
])
def test_the_declaration_check_bites(spec, expected):
    """Positive controls: each broken declaration is named; the live entry it was built from passes."""
    assert any(expected in problem for problem in _declaration_problems('calls', spec)), (
        _declaration_problems('calls', spec))
    assert not _declaration_problems('calls', COMMANDS['calls'])


@pytest.mark.parametrize('name', LIVE)
def test_every_starter_runs_as_written(named_harness, name):  # noqa: F811
    recipes._assert_text_as_written(named_harness, COMMANDS[name].starter, literal=True)


def test_the_starter_gate_bites(named_harness):  # noqa: F811
    """Negative control: a starter naming a function or flag the fixture lacks fails the same gate."""
    for broken in ('reveal calls src/ --callers no_such_function', 'reveal overview src/ --no-such-flag'):
        with pytest.raises(AssertionError):
            recipes._assert_text_as_written(named_harness, broken, literal=True)
