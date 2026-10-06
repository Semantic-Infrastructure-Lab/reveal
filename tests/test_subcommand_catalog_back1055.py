"""One home for the subcommand listing (BACK-1055 slices 1-2).

`COMMANDS` (reveal/cli/invocation.py) owns each subcommand's usage and one-line summary.
The `--help-all` listing is generated from it; AGENT_HELP.md's table is hand-written, so it
is checked against it here instead of being allowed to drift.

Slice 2: a subcommand whose help:// topic is not its same-named adapter's guide declares
it as `help_guide` on its COMMANDS entry; help.py merges those in (static_help_map) instead
of keeping its own alias rows.
"""
import re
from pathlib import Path

from reveal.adapters.help import HelpAdapter
from reveal.cli.invocation import COMMANDS, EPILOG_ORDER, render_subcommand_lines, subcommand_help_guides
from reveal.cli.parser import build_help_epilog

DOCS = Path(__file__).resolve().parent.parent / 'reveal' / 'docs'
AGENT_HELP = DOCS / 'AGENT_HELP.md'
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


def _help_guide_problems(commands, static_help):
    problems = []
    for name, spec in commands.items():
        if not spec.help_guide:
            continue
        if name in static_help:
            problems.append(f'{name}: help topic in both COMMANDS.help_guide and STATIC_HELP')
        if not (DOCS / spec.help_guide).is_file():
            problems.append(f'{name}: help_guide {spec.help_guide} does not exist')
    return problems


def test_subcommand_help_guides_come_from_commands():
    assert not _help_guide_problems(COMMANDS, HelpAdapter.STATIC_HELP)
    merged = HelpAdapter.static_help_map()
    for name, guide in subcommand_help_guides().items():
        assert merged[name] == guide
        assert HelpAdapter().help_topics[name].file == guide


def test_help_guide_gate_bites():
    """Negative control: a guide also kept in STATIC_HELP, and a missing file, are reported."""
    dup = {**HelpAdapter.STATIC_HELP, 'dev': 'guides/SUBCOMMANDS_GUIDE.md'}
    assert any('both' in p for p in _help_guide_problems(COMMANDS, dup))
    gone = {**COMMANDS, 'dev': COMMANDS['dev']._replace(help_guide='guides/NO_SUCH_GUIDE.md')}
    assert any('does not exist' in p for p in _help_guide_problems(gone, HelpAdapter.STATIC_HELP))


GUIDE_SECTION = re.compile(r'^## reveal (\w+)\b', re.MULTILINE)


def _unreachable_subcommand_sections(commands, guide_text, open_topic):
    """Subcommands SUBCOMMANDS_GUIDE.md has a `## reveal <name>` section for whose
    help://<name> does not open."""
    missing = []
    for name in sorted(set(GUIDE_SECTION.findall(guide_text)) & set(commands)):
        result = open_topic(name)
        if not isinstance(result, dict) or 'error' in result:
            missing.append(name)
    return missing


def test_every_documented_subcommand_has_a_help_topic():
    guide = (DOCS / 'guides' / 'SUBCOMMANDS_GUIDE.md').read_text(encoding='utf-8')
    adapter = HelpAdapter()
    assert not _unreachable_subcommand_sections(COMMANDS, guide, adapter.get_element)
    # A subcommand pointed at the shared guide opens on its own section.
    for name, guide_file in subcommand_help_guides().items():
        if guide_file.endswith('SUBCOMMANDS_GUIDE.md'):
            content = adapter.get_element(name)['content']
            assert content.lstrip().lower().startswith(f'## reveal {name}'), name


def test_documented_subcommand_gate_bites():
    """Negative control: a documented subcommand whose topic does not open is reported."""
    guide = '## reveal deps — Dependency Health\n'
    assert _unreachable_subcommand_sections(COMMANDS, guide, lambda name: None) == ['deps']
