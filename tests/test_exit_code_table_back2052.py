"""One exit-code table, rendered into every D6 command's help (BACK-2051 slice 5, BACK-2052).

The words live in cli/invocation.py (EXIT_CODES, EXIT_CODE_WORDING) beside COMMANDS; a command's
--help derives from them and from the --fail-on values its owner declares, so help cannot
promise an exit 1 that the command can never produce.
"""
import os
import subprocess
import sys

import pytest

from reveal.cli.invocation import (COMMANDS, EXIT_CODES, EXIT_CODE_WORDING, RETIREMENTS,
                                   exit_codes_text)
from reveal.cli.routing.declared import declared_adapter_class

_DECLARED = sorted(n for n, spec in COMMANDS.items() if spec.declared_adapter)
_FILE_COMMANDS = ('check', 'review', 'health')


def _help(command):
    env = {**os.environ, 'COLUMNS': '300'}
    return subprocess.run([sys.executable, '-m', 'reveal', command, '--help'], capture_output=True,
                          text=True, env=env, timeout=60, check=False, encoding='utf-8').stdout


def test_retirement_inventory_matches_the_shipped_migrations():
    """Keep the inventory explicit; each migration is exercised in its owning tests.

    BACK-2377 adds architecture aliases; BACK-2364 adds contextual navigation corrections.
    """
    assert sorted(RETIREMENTS) == ['flag:--also-json', 'flag:--calls', 'flag:--catchmap', 'flag:--check', 'flag:--deps',
                                   'flag:--flowto', 'flag:--ifmap', 'flag:--loopmap', 'flag:--mutations',
                                   'flag:--returns', 'flag:--search', 'flag:--writes', 'param:ast.callee_of', 'param:ast.calls',
                                   'param:calls.external', 'param:calls.modules', 'param:calls.root', 'param:calls.target', 'param:calls.uncalled', 'scheme:architecture', 'scheme:classify', 'scheme:depends', 'scheme:deps', 'scheme:stats', 'scheme:testability', 'scheme:trace', 'subcommand:architecture', 'subcommand:deps', 'subcommand:review', 'subcommand:testability',
                                   'subcommand:trace', 'target:health.code', 'target:nav.outline', 'value:ast.show=calls']


def test_table_covers_the_four_codes_and_commands_only_reword_them():
    assert sorted(EXIT_CODES) == [0, 1, 2, 3]
    for command, wording in EXIT_CODE_WORDING.items():
        assert command in COMMANDS and set(wording) <= set(EXIT_CODES)


def test_a_command_without_a_findings_gate_never_documents_exit_1():
    text = exit_codes_text('pack', ('none',))
    assert '  1  ' not in text and '--fail-on none reports' not in text
    assert '  1  ' in exit_codes_text('deps', ('none', 'findings'))


@pytest.mark.parametrize('command', _FILE_COMMANDS)
def test_file_commands_print_the_table(command):
    out = _help(command)
    for line in exit_codes_text(command).splitlines():
        assert line.strip() in out, (command, line)
    # Negative control: another command's wording is not in this help.
    assert exit_codes_text('health') not in _help('check')


@pytest.mark.parametrize('name', _DECLARED)
def test_declared_command_help_matches_its_declared_gates(name):
    gates = getattr(declared_adapter_class(name), 'FINDINGS_POLICIES', ('none',))
    out = _help(name)
    for line in exit_codes_text(name, gates).splitlines():
        assert line.strip() in out, (name, line)
    assert ('1  ' in out.split('Exit codes:')[1].split('\n\n')[0]) == ('findings' in gates)
