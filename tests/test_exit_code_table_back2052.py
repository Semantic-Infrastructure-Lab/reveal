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


def test_no_surface_name_is_retired_in_phase_1():
    assert RETIREMENTS == {}


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
