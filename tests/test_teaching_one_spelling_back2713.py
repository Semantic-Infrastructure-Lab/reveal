"""The first screens teach one spelling (BACK-2713, D20).

COMMAND_MODEL rule 2 and "Flags after a URI": analysis nouns are taught as subcommands (``reveal calls src/ --callers
X``) and a resource URI takes the same flags (``claude://sessions/ --match TEXT``). The screens an agent reads first,
``--agent-help``, ``help://quick`` (text and its JSON ``decision_tree``), the MCP server instructions and every MCP
tool description, name no analysis-only scheme and no URI query option. ``help://`` topics and ``diff://`` stay
URIs (rule 1: no flag form exists). The "How options work" block opens with the COMMAND_MODEL target line, and
help://quick's catch-all row names only nouns the page does not already show. The retirement ratchet cannot see this
class (its patterns come from RETIREMENTS keys; request notes are generated), so this file is its guard.
"""
import asyncio
import json
import re
import subprocess
import sys

import pytest

from teaching_patterns import retiring_lines

# COMMAND_MODEL "Cross-noun rules and conformance": the first line of the published "How options work" block.
TARGET_LINE = ('reveal NOUN TARGET --option value; a resource URI takes the same flags '
               '(git://FILE --view history --limit 5)')
AGENT_HELP_BUDGET = 150  # COMMAND_MODEL rule 6


def _nouns(text):
    """The nouns a printed line names: ``reveal NOUN`` commands and ``NOUN://`` schemes."""
    return set(re.findall(r'\breveal ([a-z]+)\b(?![/.])', text)) | set(re.findall(r'\b([a-z]+)://', text))


def _reveal(*args):
    proc = subprocess.run([sys.executable, '-m', 'reveal', *args], capture_output=True, text=True,
                          encoding='utf-8', timeout=120)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


@pytest.fixture(scope='module')
def agent_help():
    return _reveal('--agent-help')


@pytest.fixture(scope='module')
def quick_page():
    return _reveal('help://quick'), json.loads(_reveal('help://quick', '--format', 'json'))


@pytest.fixture(scope='module')
def mcp_server():
    import reveal.mcp_server as module
    return module


def test_agent_help_teaches_one_spelling(agent_help):
    assert not retiring_lines(agent_help), '\n'.join(retiring_lines(agent_help))


def test_help_quick_text_teaches_one_spelling(quick_page):
    text, _ = quick_page
    assert not retiring_lines(text), '\n'.join(retiring_lines(text))


def test_help_quick_decision_tree_teaches_one_spelling(quick_page):
    _, page = quick_page
    rows = page['decision_tree']
    assert len(rows) >= 10, f'the decision tree went vacuous: {len(rows)} rows'
    failures = [f"{row['want']}: {line}" for row in rows
                for line in retiring_lines(f"{row['use']}\n{row['example']}")]
    assert not failures, '\n'.join(failures)


def test_mcp_instructions_teach_one_spelling(mcp_server):
    assert 'progressive disclosure' in mcp_server.mcp.instructions  # the text under test is the server's
    failures = retiring_lines(mcp_server.mcp.instructions)
    assert not failures, '\n'.join(failures)


def test_every_mcp_tool_description_teaches_one_spelling(mcp_server):
    tools = asyncio.run(mcp_server.mcp.list_tools())
    assert len(tools) >= 10, f'the tool inventory went vacuous: {[t.name for t in tools]}'
    failures = [f'{tool.name}: {line}' for tool in tools for line in retiring_lines(tool.description or '')]
    assert not failures, '\n'.join(failures)


def test_how_options_work_opens_with_the_target_line(agent_help):
    _, found, block = agent_help.partition('How options work (every noun):')
    assert found, 'the --agent-help first screen has no "How options work" block'
    first = next(line.strip() for line in block.splitlines()
                 if line.strip() and line.strip() != '**' and not line.lstrip().startswith('```'))
    assert first == TARGET_LINE


def test_agent_help_stays_within_its_line_budget(agent_help):
    lines = agent_help.splitlines()
    assert 20 <= len(lines) <= AGENT_HELP_BUDGET, f'--agent-help prints {len(lines)} lines'


def test_help_quick_gap_row_names_no_noun_shown_above_it(quick_page):
    _, page = quick_page
    rows = page['decision_tree']
    gaps = [row for row in rows if row['want'].startswith('other tooling not named above:')]
    assert len(gaps) == 1, gaps
    named = {name.strip() for name in gaps[0]['want'].partition(':')[2].split(',')}
    shown = set().union(*(_nouns(row['cmd']) for row in page['commands']),
                        *(_nouns(f"{row['use']} {row['example']}") for row in rows if row is not gaps[0]))
    assert not named & shown, f'the gap row names nouns the page already shows: {sorted(named & shown)}'


@pytest.mark.parametrize('line', [
    "| Who calls a function | `reveal 'calls://src/?callers=my_fn'` |",
    "| Unused or circular imports | `reveal 'imports://src/?unused'` / `?circular` |",
    "| Prior Claude sessions | `reveal 'claude://sessions/?match=auth-refactor'` |",
    'reveal NOUN TARGET --option value  ==  NOUN://TARGET?option=value  (same answer, same exit)',
    'On a URI, ?FIELD OP VALUE is the same filter as --where.',
    'check import health / circular deps  →  imports://',
    "6. reveal_query('calls://<dir>?callees=FN&depth=2&detail') — \"what happens when X runs?\"",
    "'?limit=N', '?sort=field' (or '?sort=-field' for desc) and '?offset=M'",
    'calls:// and imports:// cap their rankings, patches://?view=pressure takes it too',
])
def test_the_check_bites_on_the_lines_it_replaced(line):
    """Positive control: lines the first screens printed before BACK-2713 are found."""
    assert retiring_lines(line) == [line.strip()]


@pytest.mark.parametrize('line', [
    "reveal 'help://search?search=<term>' # full-text search",
    "structure: `reveal 'diff://git://main/.:git://HEAD/.'`",
    'reveal claude://sessions/ --match auth-refactor',
    'reveal NOUN TARGET --option value; a resource URI takes the same flags (git://FILE --view history --limit 5)',
    'reveal sqlite path/to/app.db',
    'reveal_health(target)  — fast go/no-go verdict; also probes ssl:///mysql:///domain:// targets, not just code',
    "reveal_run(['calls', 'src', '--callees', 'main', '--depth', '2', '--detail'])",
    'What do you want to do?',
])
def test_the_check_passes_the_spellings_that_stay(line):
    """Negative control: resource URIs with flags, help:// and diff:// topics, and subcommands pass."""
    assert retiring_lines(line) == []


def test_the_gap_row_reader_sees_subcommand_labels():
    """Positive control: a ``reveal NOUN`` label names its noun (the gap row once read only ``NOUN://``)."""
    assert _nouns('reveal surface src/ --kind http') == {'surface'}
    assert _nouns('reveal src/app.py load_config') == set()
    assert _nouns("reveal diff://git://HEAD~1/.:git://HEAD/.") == {'diff', 'git'}
