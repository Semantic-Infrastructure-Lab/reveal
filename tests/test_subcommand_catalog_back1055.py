"""One home for the subcommand listing (BACK-1055 first slice).

`COMMANDS` (reveal/cli/invocation.py) owns each subcommand's usage and one-line summary.
The `--help-all` listing is generated from it; AGENT_HELP.md's table is hand-written, so it
is checked against it here instead of being allowed to drift.
"""
import re
from pathlib import Path

import pytest

from reveal.cli.invocation import COMMANDS, EPILOG_ORDER, render_subcommand_lines
from reveal.cli.parser import build_help_epilog

AGENT_HELP = Path(__file__).resolve().parent.parent / 'reveal' / 'docs' / 'AGENT_HELP.md'
ROW = re.compile(r'^\| `(reveal [^`]+)` \| (.+?) \| `reveal \w+ --help` \|$', re.MULTILINE)


def _doc_rows(markdown):
    """{subcommand: (usage, one-liner)} from the AGENT_HELP.md subcommands table."""
    section = markdown.split('## Subcommands Reference', 1)[1].split('\n---', 1)[0]
    return {usage.split()[1]: (usage, summary) for usage, summary in ROW.findall(section)}


def _catalog_problems(commands, order, rows):
    problems = []
    for name, spec in commands.items():
        if not (spec.usage and spec.summary):
            problems.append(f'{name}: COMMANDS entry has no usage/summary')
    if set(order) != set(commands) or len(order) != len(commands):
        problems.append(f'EPILOG_ORDER differs from COMMANDS: {sorted(set(order) ^ set(commands))}')
    if set(rows) != set(commands):
        problems.append(f'AGENT_HELP.md table rows differ from COMMANDS: {sorted(set(rows) ^ set(commands))}')
    for name, (usage, summary) in rows.items():
        spec = commands.get(name)
        if spec and usage != spec.usage:
            problems.append(f'{name}: AGENT_HELP.md usage {usage!r} != {spec.usage!r}')
        if spec and not summary.startswith(spec.summary):
            problems.append(f'{name}: AGENT_HELP.md one-liner does not start with {spec.summary!r}')
    return problems


def test_catalog_agrees_with_agent_help():
    rows = _doc_rows(AGENT_HELP.read_text(encoding='utf-8'))
    assert len(rows) == len(COMMANDS), sorted(rows)
    assert not _catalog_problems(COMMANDS, EPILOG_ORDER, rows)


def test_help_all_lists_every_command_from_the_catalog():
    epilog = build_help_epilog(full=True)
    assert render_subcommand_lines() in epilog
    assert render_subcommand_lines().count('\n') == len(COMMANDS) - 1


def test_catalog_gate_bites():
    """Negative control: a dropped doc row, a renamed usage, a drifted summary, and an
    entry with no summary are each reported."""
    rows = _doc_rows(AGENT_HELP.read_text(encoding='utf-8'))
    dropped = {k: v for k, v in rows.items() if k != 'deps'}
    assert any('deps' in p for p in _catalog_problems(COMMANDS, EPILOG_ORDER, dropped))
    renamed = {**rows, 'deps': ('reveal deps <path>', rows['deps'][1])}
    assert any('usage' in p for p in _catalog_problems(COMMANDS, EPILOG_ORDER, renamed))
    drifted = {**rows, 'deps': (rows['deps'][0], 'Something else entirely')}
    assert any('one-liner' in p for p in _catalog_problems(COMMANDS, EPILOG_ORDER, drifted))
    blank = {**COMMANDS, 'deps': COMMANDS['deps']._replace(summary='')}
    assert any('no usage/summary' in p for p in _catalog_problems(blank, EPILOG_ORDER, rows))
