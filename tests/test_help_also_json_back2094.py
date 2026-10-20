"""BACK-2094: a command's --help lists --also-json only when the command writes it.

`reveal health` and `reveal review` inherit the global output options, so their help listed
--also-json (with text saying it works with `check` and declared adapter commands only)
while both rejected it with exit 2. Whether a command takes the option is one declaration,
which the rejection and the help both read.
"""

import pytest

from conftest import _run_reveal_direct
from reveal.cli.invocation import COMMANDS

REJECTING = ('health', 'review')
HONORING = ('check', 'overview')


def _help(*command):
    result = _run_reveal_direct(*command, '--help')
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.mark.parametrize('name', REJECTING)
def test_help_of_a_rejecting_command_does_not_list_the_option(name):
    assert '--also-json' not in _help(name), f'reveal {name} --help advertises an option it rejects'


@pytest.mark.parametrize('name', REJECTING)
def test_rejection_is_unchanged(name, tmp_path):
    (tmp_path / 'm.py').write_text('X = 1\n', encoding='utf-8')
    result = _run_reveal_direct(name, tmp_path, '--also-json', tmp_path / 'out.json')
    assert result.returncode == 2
    assert f'--also-json is not supported by reveal {name}' in result.stderr
    assert not (tmp_path / 'out.json').exists()


@pytest.mark.parametrize('name', HONORING)
def test_help_of_a_command_that_writes_it_still_lists_it(name):
    """Negative control: check (the one non-declared command that writes the artifact) and a
    declared noun keep the option and its text."""
    text = _help(name)
    assert '--also-json PATH' in text
    assert 'A write that fails exits 3' in text


def test_the_main_help_still_lists_it():
    assert '--also-json PATH' in _run_reveal_direct('--help').stdout


def test_one_declaration_decides_help_and_rejection():
    """Every command's help lists the option exactly when its spec says it writes it."""
    for name, spec in COMMANDS.items():
        listed = '--also-json' in _help(name)
        assert listed == spec.also_json, f'reveal {name}: help lists the option={listed}, spec says {spec.also_json}'
