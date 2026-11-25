"""The `--agent-help` screen, generated from the command registry (BACK-1055; COMMAND_MODEL rule 6).

`--agent-help` and `help://agent` print this one screen: the model, the path reads (rungs 0-2 and the
element views), one entry per live subcommand from its `COMMANDS` entry (role, rung, starter, summary),
"How options work" and the exit codes. A subcommand reaches the screen by declaring its role on its entry,
so a new noun needs no edit here, and a retired one (no role) never appears. `help://agent/full` stays the
long hand-written reference (reveal/docs/AGENT_HELP.md).
"""
import textwrap
from typing import List, Tuple

from ..nav_params import ELEMENT_VIEWS
from ..version import __version__
from .invocation import COMMAND_ROLES, COMMANDS, EPILOG_ORDER, EXIT_CODES, CommandSpec

# Plan section 3.1: the question each rung answers.
RUNG_QUESTIONS = {0: 'orient: what is here?', 1: 'structure: what does this contain?',
                  2: 'content: show me this one thing', 3: 'relations: what connects to it?',
                  4: 'behaviour: what does this function touch?',
                  5: 'judgment inputs: where are risk, debt and boundaries?'}
# The roles off the ladder, each under one heading, in COMMAND_ROLES order.
ROLE_HEADINGS = {'verb': 'Verbs off the ladder (any target):',
                 'resource': 'Resources (data and session stores; a URI names one, e.g. sqlite://app.db/users):',
                 'ops': 'Ops probes (the hosting family: reveal help adapters):',
                 'tooling': 'Tooling:'}
WIDTH = 120
COLUMN = 36  # the command column; a longer starter puts its summary on the next line

# The screen's prose, its one copy. The path reads share the entries' column; "How options work" is
# COMMAND_MODEL's text of record.
AGENT_HELP_PROSE = """\
Reveal {version}: structure first, then read only what the question needs.

reveal PATH [ELEMENT]             read a file or directory: outline first, then one element
                                  ELEMENT = Name | Class.method | "Heading" | :N-M | key.path
reveal PATH ELEMENT --view V      how a function behaves: {views}
reveal NOUN [TARGET] [--option]   ask a derived dataset about TARGET
reveal VERB TARGET...             act on any target: {verbs}
SCHEME://RESOURCE [--option]      a resource by its address, with the noun's flags

Paths read (start here; quote every --where expression and URI: > < & | are shell operators):
  reveal src/                           0 orient: the directory tree (reveal docs/ --ext md: one file type)
  reveal src/app.py                     1 structure: the file's outline (functions, classes, imports)
  reveal src/app.py load_config         2 content: one element (also Class.method, :120-160)
  reveal docs/guide.md "API guide"      2 content: one section of a document
  reveal src/ --grep validate_item      2 content: matching lines, grouped by their enclosing function
  reveal src/app.py :180 --scope        the element enclosing a line; --outline nests a file's outline
  reveal src/app.py load_config --view boundary
                                        4 behaviour: inputs, environment and effects in one report

{commands}

How options work (every noun):
  reveal NOUN TARGET --option value; a resource URI takes the same flags (git://FILE --view history --limit 5)
  One name per idea: --limit/--offset (0 = no cap), --sort [-]FIELD, --where 'FIELD OP VALUE',
    --match TEXT, --detail LEVEL, --view NAME, --since/--until DATE, --against REF, --tests MODE
  Switches take on/off: --churn off.
  Filters and selections repeat and combine; settings take one value (twice, differently: exit 2).
  One answer per request; an option the selected answer does not use exits 2 and names the ones it does.
  An unknown option or field exits 2 naming the ones the noun takes (a field the data defines warns).
  Old spellings still work until 1.0 and print their replacement.
  Config files and environment set defaults; what you pass overrides them (config ignore always applies).
  Config that cannot be used fails the request: missing or invalid exits 2, unreadable exits 3.

Scripting: --format json puts the whole answer on stdout, its warnings inside it (meta.warnings);
  --breadcrumbs off (or -q) drops the next-step hints.
Exit codes (a command's --help words its own):
{exits}

Next: reveal help quick (task router) | reveal help NOUN (one noun's guide) | reveal NOUN --help (its flags)
  reveal help schemas/NOUN --format json (machine-readable controls) | reveal help --match TEXT (search)
  reveal help agent/full (the full reference); reveal help TOPIC and help://TOPIC are the same page."""


def _live() -> List[Tuple[str, CommandSpec]]:
    """Every subcommand that declares a role, in the `--help-all` listing order."""
    order = {name: i for i, name in enumerate(EPILOG_ORDER)}
    return sorted(((name, spec) for name, spec in COMMANDS.items() if spec.role),
                  key=lambda item: order.get(item[0], len(order)))


def _entry(spec: CommandSpec) -> List[str]:
    """One subcommand: its starter, then its summary wrapped at the command column."""
    indent = ' ' * (COLUMN + 4)
    summary = textwrap.wrap(spec.summary, WIDTH - len(indent)) or ['']
    if len(spec.starter) > COLUMN:
        return [f'  {spec.starter}'] + [indent + part for part in summary]
    return [f'  {spec.starter:<{COLUMN}}  {summary[0]}'] + [indent + part for part in summary[1:]]


def _command_lines(live: List[Tuple[str, CommandSpec]]) -> List[str]:
    """The ladder rungs the commands declare, then each other role under its heading."""
    lines: List[str] = []
    for rung in sorted({spec.rung for _, spec in live if spec.rung is not None}):
        lines.append(f'Rung {rung}, {RUNG_QUESTIONS[rung]}')
        for _, spec in live:
            if spec.rung == rung:
                lines += _entry(spec)
    for role in COMMAND_ROLES:
        members = [spec for _, spec in live if spec.role == role and spec.rung is None]
        if members:
            lines.append(ROLE_HEADINGS[role])
            for spec in members:
                lines += _entry(spec)
    return lines


def render_agent_help() -> str:
    """The `--agent-help` screen (at most 150 lines: COMMAND_MODEL rule 6)."""
    live = _live()
    return AGENT_HELP_PROSE.format(
        version=__version__,
        views=' | '.join(ELEMENT_VIEWS),
        verbs=' | '.join(name for name, spec in live if spec.role == 'verb'),
        commands='\n'.join(_command_lines(live)),
        exits='\n'.join(f'  {code}  {text}' for code, text in sorted(EXIT_CODES.items())),
    )
