"""One Invocation, parsed once, for every CLI form (BACK-1058).

The command line used to be read in eight places. main.py indexed ``sys.argv`` for the
subcommand name, ``--perf``, ``--copy`` and ``--sort -field``. ``--help-all``, "was --format
typed?" and the provenance manifest's ``command`` each re-read it deeper in the stack.
Each reader parsed it a little differently, and that is how flags got lost between
forms. ``argv[1]`` was the only place a subcommand could be named, so
``reveal --format json overview .`` answered "overview not found". The raw ``'-c' in argv``
check missed ``-qc``, which argparse accepts, so nothing was copied and nothing was said.
Under the MCP server, ``sys.argv`` is the server's own command line, so a provenance
manifest named ``reveal-mcp`` as the command that produced a query's result.

Here the command line is read once: :meth:`Invocation.parse` takes the entry point's
argv, and every later question asks the Invocation. The entry point publishes it with
:func:`invocation_scope`. Code below the CLI reads it with :func:`current_invocation`.
The MCP server publishes the CLI command equivalent to each call it runs.
"""

from __future__ import annotations

import importlib
import re
import sys
from argparse import ArgumentParser, Namespace
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, NamedTuple, Optional, Sequence, Tuple

from ..utils.invocation_log import current_log, log_scope, noted_for_json


class CommandSpec(NamedTuple):
    """A named subcommand: where its parser and runner live, and what it renders."""
    module: str
    parser_factory: str
    runner: str
    # --format values the runner renders when no same-named adapter declares them.
    # None: the same-named adapter's declaration applies.
    formats: Optional[Tuple[str, ...]] = None
    # How the command is invoked and what it is for: the one home for the subcommand
    # listing in `--help-all`; AGENT_HELP.md's table is checked against it (BACK-1055).
    usage: str = ''
    summary: str = ''
    # The reveal/docs guide help://<name> opens, when that is not the same-named
    # adapter's guide. '' leaves help://<name> to the adapter guide, if any (BACK-1055).
    help_guide: str = ''

    declared_adapter: str = ''
    # Whether the command writes the --also-json artifact. The one declaration: a command that
    # does not rejects the flag with exit 2 and leaves it out of its --help (BACK-2094).
    also_json: bool = False

    def load(self) -> Tuple[ArgumentParser, Callable[[Namespace], None]]:
        if self.declared_adapter:
            from functools import partial
            from .routing.declared import create_declared_parser, run_declared_command
            return create_declared_parser(self.declared_adapter), partial(
                run_declared_command, self.declared_adapter)
        mod = importlib.import_module(self.module)
        return getattr(mod, self.parser_factory)(), getattr(mod, self.runner)


def _spec(name: str, usage: str, summary: str, formats: Optional[Tuple[str, ...]] = None,
          help_guide: str = '', also_json: bool = False) -> CommandSpec:
    return CommandSpec(f'reveal.cli.commands.{name}', f'create_{name}_parser', f'run_{name}',
                       formats, usage, summary, help_guide, also_json=also_json)


def _declared(name: str, usage: str, summary: str, help_guide: str = '') -> CommandSpec:
    """A noun the same-named adapter declares: no module of its own, `load()` builds both from the declaration."""
    return CommandSpec('', '', '', None, usage, summary, help_guide, declared_adapter=name, also_json=True)


_SUBCOMMANDS_GUIDE = 'guides/SUBCOMMANDS_GUIDE.md'


# Every subcommand. help://schemas/<name> also reads this table to tell a CLI-only command
# from an unknown name (BACK-1028). health and review have no same-named adapter, and their
# runners render only these formats (measured: grep/typed output matched text byte for byte).
COMMANDS: Dict[str, CommandSpec] = {
    'ast':         _declared('ast', 'reveal ast [path] [--where EXPR] [--kind KIND]',
                     'Find code elements by properties; repeated --where expressions are ANDed'),
    'architecture': _declared('architecture',
                     'reveal architecture [path] [--against REF]',
                     'Retired: use reveal overview [path] [--against REF]'),
    'calls':        _declared('calls',
                     'reveal calls --callers FUNC',
                     'Call graph: callers, callees (--depth N, --detail), --sort=-callers'),
    'check':        _spec('check',
                     'reveal check <path>',
                     'Run quality rules on a file or directory',
                     ('text', 'json', 'grep'),  # also PATH --check (BACK-1644)
                     help_guide=_SUBCOMMANDS_GUIDE, also_json=True),
    'claude':       _declared('claude', 'reveal claude [RESOURCE] [--view VIEW] [--match TEXT]',
                     'Inspect Claude sessions and installation resources through declared controls'),
    'codex':        _declared('codex', 'reveal codex [RESOURCE] [--since DATE] [--limit N]',
                     'Inspect Codex CLI sessions and installation resources through declared controls'),
    'contracts':    _declared('contracts',
                     'reveal contracts [path]',
                     'Architectural seams: ABCs, Protocols/interfaces, TypedDicts, dataclasses'),
    'deps':         _declared('deps',
                     'reveal deps [path]',
                     'Retired: use reveal imports <path> --external, --circular or --unused (one graph build); '
                     'dependency health: external packages, circular deps, unused imports'),
    'dev':          _spec('dev',
                     'reveal dev <command>',
                     'Scaffold adapters/analyzers/rules; inspect effective `.reveal.yaml` config',
                     help_guide=_SUBCOMMANDS_GUIDE),
    'health':       _spec('health',
                     'reveal health [URI...]',
                     'Ops health: SSL + databases + DNS + nginx',
                     ('text', 'json'), help_guide=_SUBCOMMANDS_GUIDE),
    'hotspots':     _declared('hotspots',
                     'reveal hotspots [path]',
                     'Retired: use reveal metrics <path> --view hotspots (files, --fail-on findings) and the ast:// '
                     'complexity sort (functions); high-complexity files and functions'),
    'imports':      _declared('imports',
                     'reveal imports [path]',
                     'Import graph: who imports what (--importers), fan-in, cycles, unused imports, layer violations'),
    'git':          _declared('git', 'reveal git [path[@REF]] [--view VIEW] [--where EXPR]',
                             'Inspect repository history and historical files'),
    'json':         _declared('json', 'reveal json FILE[/KEY] [--where EXPR] [--view VIEW]',
                     'Navigate JSON data, filter array elements or inspect schema, keys and types'),
    'markdown':     _declared('markdown', 'reveal markdown [path] [--where EXPR] [--match TEXT]',
                     'Find documents by frontmatter/body; inspect links and aggregate fields'),
    'metrics':      _declared('metrics',
                     'reveal metrics [path]',
                     'Per-file lines, complexity and quality; --view hotspots ranks files; --view provenance tags every file'),
    'offline':      _spec('offline',
                     'reveal offline',
                     'Pre-download tree-sitter grammars for offline/air-gapped use'),
    'overview':     _declared('overview',
                     'reveal overview [path]',
                     'Compact project map: scope, components, import relationships'),
    'pack':         _declared('pack',
                     'reveal pack <path>',
                     'Token-budgeted context snapshot for LLM consumption',
                     help_guide=_SUBCOMMANDS_GUIDE),  # pack:// guide is a pointer stub
    'patches':      _declared('patches',
                     'reveal patches [path]',
                     'Mock/patch pressure in tests, grouped by target; --view pressure joins it with production boundary fan-out'),
    'review':       _spec('review',
                     'reveal review <path>',
                     'Retired: use reveal check --changed RANGE and the diff:// adapter',
                     ('text', 'json'), help_guide=_SUBCOMMANDS_GUIDE),
    'scaffold':     _spec('scaffold',
                     'reveal scaffold <kind>',
                     'Retired: use `reveal dev new-*`',
                     help_guide=_SUBCOMMANDS_GUIDE),
    'env':          _declared('env', 'reveal env [NAME]',
                     'Inspect environment variables, or one variable, with sensitive values redacted'),
    'sqlite':       _declared('sqlite', 'reveal sqlite DB[/TABLE] [--view health]',
                     'Inspect a SQLite database, a table or view, or its integrity through declared controls'),
    'xlsx':         _declared('xlsx', 'reveal xlsx FILE [--sheet NAME] [--match TEXT] [--powerpivot MODE] ...',
                     'Inspect an Excel workbook: sheets, cells, search, Power Pivot, Power Query, names, connections'),
    'surface':      _declared('surface',
                     'reveal surface [path]',
                     'External surfaces: CLI commands, HTTP routes, env vars, network calls, FS writes, subprocess calls'),
    'testability':  _declared('testability',
                     'reveal testability [path]',
                     'Retired: use reveal patches <path> --view pressure (the same answer); '
                     'test patch pressure joined with production boundary fan-out',
                     help_guide='guides/TESTABILITY_GUIDE.md'),
    'trace':        _declared('trace',
                     'reveal trace --from FUNC',
                     'Retired: use reveal calls --callees FUNC --depth N --detail (the same walk); '
                     'depth-indented narrative with side effects'),
}


# Order of the `--help-all` subcommand listing: task entry points first, tooling last.
EPILOG_ORDER = ('ast', 'overview', 'imports', 'deps', 'hotspots', 'git', 'claude', 'codex', 'json', 'sqlite', 'xlsx', 'env', 'markdown', 'metrics', 'contracts', 'surface',
                'patches', 'testability', 'calls', 'trace', 'check', 'review', 'health', 'pack', 'dev',
                'scaffold', 'offline', 'architecture')


# What each exit code means for a command on the D6 outcome policy (the exit-code contract). The one
# home for the wording help prints; a command words a code more specifically in EXIT_CODE_WORDING.
EXIT_CODES: Dict[int, str] = {
    0: 'completed; no enabled findings gate matched',
    1: 'a findings gate matched',
    2: 'request rejected before analysis (usage error, missing path)',
    3: 'required analysis or output failed or was incomplete',
}
EXIT_CODE_WORDING: Dict[str, Dict[int, str]] = {
    'check': {0: 'no enabled severity gate matched (default: high)',
              1: 'findings at or above --fail-on (default: high)',
              3: 'scan incomplete (a file could not be parsed/checked), or a requested '
                 '--output json=PATH artifact could not be written'},
    'review': {0: 'pass',
               1: 'findings (warnings, or a blocking high/critical issue, told apart by overall_status)',
               2: 'invalid target',
               3: 'incomplete (some files could not be checked or ranked; beats findings)'},
    'health': {0: 'all pass', 1: 'findings (warnings or failing checks)', 2: 'usage error (no target)',
               3: 'a check failed, could not reach its target (a missing local path included), '
                  'or was incomplete'},
    'deps': {1: 'circular dependencies or unused imports matched --fail-on findings (default: none)'},
    'imports': {1: 'the --circular, --unused or --violations view had a row and --fail-on findings was given '
                   '(default: none)'},
    'hotspots': {1: 'file quality below 70 or function complexity above 20 matched '
                    '--fail-on findings (default: none)'},
    'metrics': {1: 'with --view hotspots, an analysed file with quality below 70 or a function with complexity '
                   'above 20 matched --fail-on findings (default: none)'},
}
# Commands whose findings gate is on unless --fail-on none says otherwise.
FINDINGS_BY_DEFAULT = ('check', 'review', 'health')

# The retired spellings (surface program ground rule 7, release strategy D5): the one table every
# kind of retired name goes into, so a later phase adds a row instead of a print. A key is
# namespaced by the kind of spelling, so a subcommand, a scheme and a parameter of the same name
# cannot collide, and ``depends://?root=`` stays apart from ``calls://?root=``:
#   subcommand:<name>            reveal trace ...
#   scheme:<name>                trace://...
#   param:<scheme>.<param>       calls://...?root=
#   value:<scheme>.<param>=<v>   ast://...?show=calls
#   flag:<--flag>                --search
#   flag:<noun>.<--flag>         reveal ast ... --head (a main-parser flag a declared noun keeps, LEGACY_CLI_MODIFIERS)
#   mcp:<tool>                   reveal_trace
# A row's stage says what the spelling does now: ``note`` prints the note and answers as before,
# ``phase7`` is recorded and prints nothing yet (MCP tool names stay until Phase 7), ``error``
# is the cut release: exit 2 with the same text. A ``removed`` row is a spelling deleted outright
# rather than renamed (python://): it is at ``error`` from the day it lands and its text says it was
# removed. retirement_note() is the one reader.
STAGES = ('note', 'phase7', 'error')
RETIREMENT_KEY = re.compile(
    r'^(?:subcommand:[a-z][a-z0-9-]*'
    r'|scheme:[a-z][a-z0-9+.-]*'
    r'|param:[a-z][a-z0-9+.-]*\.[^.=\s]+'
    r'|value:[a-z][a-z0-9+.-]*\.[^.=\s]+=.*'
    r'|flag:--[a-z][a-z0-9-]*'
    r'|flag:[a-z][a-z0-9-]*\.--[a-z][a-z0-9-]*'
    r'|target:[a-z][a-z0-9-]*\.[a-z][a-z0-9-]*'  # a kind of target a subcommand stops taking
    r'|mcp:[a-z][a-z0-9_]*)$')


@dataclass(frozen=True)
class Retirement:
    """One retired spelling: *old* as the user types it, what replaces it, and its stage.
    ``removed`` marks a spelling deleted outright (no adapter answers it any more)."""
    old: str
    replacement: str
    stage: str = 'note'
    removed: bool = False
    # The replacement is another noun or nothing, or answers differently (a legacy operation: Calls root, Claude
    # tail, Metrics hotspots; or a legacy cap or detail level: Metrics top, Claude full/raw): the spelling stays a
    # parameter of its own until the cut rather than a legacy entry on a canonical control (COMMAND_MODEL "Retirement
    # notes", "Legacy operations", BACK-2654).
    standalone: bool = False

    def __post_init__(self) -> None:
        if not self.old or not self.replacement:
            raise ValueError('a retirement names the old spelling and its replacement')
        if self.stage not in STAGES:
            raise ValueError(f'retirement stage {self.stage!r} is not one of {STAGES}')
        if self.removed and self.stage != 'error':
            raise ValueError('a removed spelling cannot answer: its stage is error')

    @property
    def text(self) -> str:
        """The one wording, for the note, the error and the JSON warning."""
        state = 'was removed' if self.removed else 'is deprecated'
        if self.stage == 'note' and not self.removed:
            state += ' and works until 1.0'  # the agent-help line: old spellings still work until 1.0 (BACK-2716)
        return f'{self.old} {state}; use {self.replacement}.'


@dataclass(frozen=True)
class Switch:
    """A presentation switch (COMMAND_MODEL "Switches", BACK-2654 rule 15): ``--NAME on|off``. ``--no-NAME`` is its
    legacy spelling of off (a ``flag:--no-NAME`` RETIREMENTS row, generated from SWITCHES); ``short_off`` are short
    spellings of off, the same word, so they carry no note."""
    name: str
    help: str
    short_off: Tuple[str, ...] = ()
    # The old flag for off when it is not --no-NAME (respect-gitignore's --no-gitignore), named here explicitly.
    legacy: str = ''
    # The value when the switch is not typed; None lets a later default decide (config/env for breadcrumbs).
    default: Optional[bool] = None
    # The switch typed without a value means on: respect-gitignore's old no-value --respect-gitignore.
    bare_on: bool = False

    @property
    def dest(self) -> str:
        return self.name.replace('-', '_')

    @property
    def legacy_flag(self) -> str:
        return self.legacy or f'--no-{self.name}'


# The one declaration: each parser that carries a switch calls global_flags.add_switch_argument, and RETIREMENTS
# below generates each switch's flag:--no-NAME row from it. The namespace holds the switch's boolean under NAME, or
# None when it was not typed (the default applies: config/env for breadcrumbs, on for the others); respect-gitignore
# keeps its old dest and default (respect_gitignore=True), which every walker reads.
SWITCHES: Dict[str, Switch] = {switch.name: switch for switch in (
    Switch('breadcrumbs', 'Navigation hints after the output: on, or off for scripting (default: on in a terminal, '
           'off when piped; REVEAL_BREADCRUMBS and display.breadcrumbs set the default)', short_off=('-q',)),
    Switch('fallback', 'TreeSitter fallback for file types without an analyzer: on (default) or off'),
    Switch('group', 'Collapse a rule repeated many times in one file into one line: on (default), or off to show '
           'every check result'),
    Switch('snippets', 'The source-code excerpt in each violation (the 📝 line / JSON "context" field): on (default), '
           'or off to keep only rule/file/line/severity/suggestion, so the output embeds no source (BACK-1182)'),
    Switch('respect-gitignore', 'Skip files git ignores: on (default; tracked files are never skipped) or off to '
           'include them', legacy='--no-gitignore', default=True, bare_on=True),
)}


# The main parser's flags a declared noun keeps until the cut, typed after its URI or on its subcommand (Scott
# 2026-11-19, BACK-2706 and BACK-2708; COMMAND_MODEL "Flags after a URI", BACK-2673): noun -> flag -> what replaces it.
# One flag:<noun>.<flag> row each, generated below; the noun declares each flag as a flag-only modifier
# (ParamSpec.flag_only) on the answers that read it, and tests/test_legacy_cli_modifiers_back2673.py holds the two to
# each other. They answer differently from the replacements (a slice of the shown rows, no offset on some nouns), so
# every row is standalone.
_LIMIT_N = '--limit N'
_OFFSET = '--offset START-1 --limit END-START+1'
_LAST = 'a descending --sort with --limit N (the last N rows have no spelling of their own)'
_SLICED = {'--head': _LIMIT_N, '--tail': _LAST, '--range': _OFFSET}


def _no_check(noun: str) -> Dict[str, str]:
    """--check and its --lint alias on a noun whose answers they never changed (BACK-2708 ruling 2)."""
    return dict.fromkeys(('--check', '--lint'),
                         f'reveal check <path> to check files (the flag never changed a {noun}:// answer)')

LEGACY_CLI_MODIFIERS: Dict[str, Dict[str, str]] = {
    **{noun: _SLICED for noun in ('ast', 'markdown', 'metrics')},
    **{noun: {**_SLICED, **_no_check(noun)} for noun in ('git', 'json')},
    'xlsx': _no_check('xlsx'),  # --head/--tail/--range never sliced an xlsx answer: they exit 2
    'env': _no_check('env'),  # --head/--tail/--range never sliced an env answer: they exit 2
    'calls': {'--head': '--limit N on a ranking (--sort=-callers --limit N); --depth N on a callers or callees walk',
              '--tail': 'a descending --sort with --limit N on a ranking (the last N rows have no spelling of their own)',
              '--range': '--limit N on a ranking (calls has no offset)'},
    # --tail as on every noun (Scott 2026-11-19, BACK-2709). --type/--name/--search: supported legacy (D18).
    'claude': {'--head': _LIMIT_N, '--tail': _LAST, '--range': _OFFSET,
               '--type': '--where tool==TYPE on the workflow view',
               **dict.fromkeys(('--name', '--search'), '--match TEXT on the workflow view and history; '
                                                       '--where session~=TEXT on the session list'),
               **_no_check('claude')},
    # Codex pages its list answers with --limit/--offset (ruling Q6) and has no sort.
    'codex': {'--head': _LIMIT_N, '--range': _OFFSET,
              '--tail': '--offset TOTAL-N --limit N (the last N rows have no spelling of their own)',
              **_no_check('codex')},
    'hotspots': {'--head': '--limit N, which caps each list',
                 '--tail': '--limit N, which keeps each list\'s worst N (each list is ranked worst first)',
                 '--range': '--limit N, which caps each list (hotspots has no offset)'},
    'imports': {'--head': '--limit N on a ranking or the entrypoints',
                '--tail': 'a descending --sort with --limit N (the last N rows have no spelling of their own)',
                '--range': '--limit N on a ranking (imports has no offset)'},
    'pack': {flag: '--budget N, which sizes the pack (it has no row slice)' for flag in ('--head', '--tail', '--range')},
    'patches': {'--head': '--limit N for the groups, --top N in --view pressure',
                '--tail': '--limit N, which keeps the first N groups (the groups are ranked)',
                '--range': '--limit N, which caps the groups (patches has no offset)'},
    'testability': {'--head': 'reveal patches <path> --view pressure --limit N',
                    '--tail': 'reveal patches <path> --view pressure --limit N, which keeps the first N (each list is ranked)',
                    '--range': 'reveal patches <path> --view pressure --limit N, which caps each list (no offset)'},
}


# The two older BACK-1906 notes, then Phase 2b's call-graph spellings (BACK-2066). A param:
# row covers the URI parameter and the same parameter typed as a declared subcommand's flag.
RETIREMENTS: Dict[str, Retirement] = {
    **{f'flag:{noun}.{flag}': Retirement(f'{noun} {flag}', replacement, standalone=True)
       for noun, flags in LEGACY_CLI_MODIFIERS.items() for flag, replacement in flags.items()},
    'subcommand:scaffold': Retirement('reveal scaffold', 'reveal dev new-adapter NAME (or new-analyzer/new-rule)'),
    # D9: one compact map and comparison owner; pack --architecture is a separate live control.
    'subcommand:architecture': Retirement('reveal architecture', 'reveal overview <path> [--against REF]'),
    'scheme:architecture': Retirement('architecture://', 'reveal overview <path> [--against REF]'),
    'flag:--deps': Retirement('--deps', '--inputs'),
    'flag:--mutations': Retirement('--mutations', '--outputs'),
    'flag:--writes': Retirement('--writes', '--outputs'),
    'flag:--calls': Retirement('--calls', '--callsites'),
    # The element views (BACK-2627, D20): one --view; structural depth is --nesting-depth (COMMAND_MODEL Depth row).
    'target:nav.outline': Retirement('code-element --outline', '--view flow (its --depth is --nesting-depth); '
                                                               'file and Markdown outlines remain --outline'),
    'flag:--ifmap': Retirement('--ifmap', '--view flow --kind if (its --depth is --nesting-depth)'),
    'flag:--loopmap': Retirement('--loopmap', '--view flow --kind loop (its --depth is --nesting-depth)'),
    'flag:--catchmap': Retirement('--catchmap', '--view flow --kind try (its --depth is --nesting-depth)'),
    'flag:--returns': Retirement('--returns', '--view exits'),
    'flag:--sideeffects': Retirement('--sideeffects', '--view effects'),
    'flag:--fanout': Retirement('--fanout', '--view effects --in-loops (its --depth is --nesting-depth)'),
    'flag:--statewrites': Retirement('--statewrites', '--view effects --state'),
    'flag:--flowto': Retirement('--flowto', '--view exits for static exit sites; the former reachability verdict is '
                                            'retired'),
    'flag:--boundary': Retirement('--boundary', '--view boundary'),
    'flag:--effects': Retirement('--effects', '--view effects (with --in-loops its --depth is --nesting-depth)'),
    'flag:--flow': Retirement('--flow', '--view flow; selectors are --kind if|loop|try, repeated to combine; its '
                                        '--depth is --nesting-depth'),
    'flag:--exits': Retirement('--exits', '--view exits'),
    'flag:--search': Retirement('--search', '--name PATTERN (regex)'),
    # One row for the file route's --check and its --lint alias.
    'flag:--check': Retirement('file --check/--lint', 'reveal check <path>'),
    # --also-json is the one JSON file sink of --output FORMAT[=PATH] (BACK-2089 slice 5a); it answers until the cut.
    'flag:--also-json': Retirement('--also-json PATH', '--output json=PATH'),
    # Rule 4 (COMMAND_MODEL "Detail", BACK-2654): the global --verbose on a declared noun is --detail full; a noun whose
    # verbose lifts its caps declares it as a legacy word of the uncapping control instead (param:<noun>.verbose rows).
    'flag:--verbose': Retirement('--verbose', '--detail full'),
    # Switches (COMMAND_MODEL "Switches", BACK-2654 rule 15): each switch's legacy off flag (--no-NAME, or the one its
    # declaration names) is --NAME off, one row per SWITCHES entry, generated. A short spelling of off (-q): no row.
    **{f'flag:{switch.legacy_flag}': Retirement(switch.legacy_flag, f'--{switch.name} off') for switch in SWITCHES.values()},
    # review folded into check --changed plus the diff:// adapter (D3, BACK-2068 slice 3b): it answers as before until the
    # cut. Its hotspots and complexity sections have no new home until stats becomes metrics (BACK-2069);
    # the MCP tool reveal_review keeps its name until Phase 7.
    'subcommand:review': Retirement('reveal review', 'reveal check --changed RANGE (rules) and '
                                    "reveal 'diff://git://A/.:git://B/.' (structure); a directory: reveal check DIR"),
    # health is the ops entry point (P3-1, BACK-2068 slice 3c): a local code target still answers until the cut
    # (D5), but code quality is check's. An .conf nginx file is an ops target and stays.
    'target:health.code': Retirement('reveal health on a code path', 'reveal check <path>; health keeps ssl://, '
                                     'domain://, mysql://, sqlite:// and nginx .conf targets'),
    # A positional element on a resource scheme that binds its query (BACK-2764, option B): it answers until the cut,
    # where a declared noun without such a row refuses it (``element_retirement``). COMMAND_MODEL rule 2 names the
    # topic in the URI; a reveal source file is a path, which ``reveal reveal://FILE`` names.
    'target:help.element': Retirement('help:// TOPIC', 'help://TOPIC'),
    'target:reveal.element': Retirement('reveal://FILE ELEMENT', 'reveal PATH ELEMENT on that source file '
                                        '(reveal reveal://FILE names its path)'),
    # diff:// names its element in the URI (rule 1 composes addresses; BACK-2768): diff://LEFT:RIGHT/ELEMENT answers
    # for plain-file and git:// sides alike, so the positional element after it is the older spelling.
    'target:diff.element': Retirement('diff://LEFT:RIGHT ELEMENT', 'diff://LEFT:RIGHT/ELEMENT'),
    # trace merged into calls (BACK-2066): both spellings keep trace's frames shape until the cut
    # (decision c); the MCP tool reveal_trace keeps its name until Phase 7 (decision g).
    'subcommand:trace': Retirement('reveal trace', 'reveal calls <path> --callees FUNC --depth N --detail'),
    'scheme:trace': Retirement('trace://', 'reveal calls <path> --callees FUNC --depth N --detail'),
    'param:calls.root': Retirement('calls ?root= (--root)',
                                   '--callees FUNC --depth N, the same walk', standalone=True),
    # Decision (a): an alias that answers identically until the cut.
    'param:calls.target': Retirement('calls ?target= (--target)', '--callers FUNC, the same answer'),
    'param:calls.rank': Retirement('calls ?rank=callers (--rank callers)', '--sort=-callers'),
    'param:calls.top': Retirement('calls ?top=N (--top N)', '--limit N; 0 is uncapped'),
    'param:calls.type': Retirement('calls ?type=KIND (--type KIND)', '--kind KIND; legacy method keeps its existing population'),
    # Imports vocabulary (BACK-2620): aliases that answer identically until the cut.
    'param:imports.rank': Retirement('imports ?rank=fan-in (--rank fan-in)', '--sort=-fan-in'),
    'param:imports.top': Retirement('imports ?top=N (--top N)', '--limit N; 0 is uncapped'),
    'param:imports.verbose': Retirement('imports ?verbose (--verbose)',
                                        '--detail full; JSON keeps "verbose": true'),
    'param:imports.max_files': Retirement('imports ?max_files=N (--max-files N)',
                                          '--scan-limit N, the same input budget'),
    # verbose where it adds detail (BACK-2654 rule 4) or only lifts caps (note #17): translated, the same answer.
    'param:git.verbose': Retirement('git ?verbose (--verbose)', '--detail full'),
    # Git vocabulary (BACK-2616, D20): type is view's older word (its aggregate limit binds as --scan-limit, so the
    # answer is the same); no_merges and raw are legacy values of the merges switch and the detail level; log and summary
    # are older values of view and detail.
    'param:git.type': Retirement('git ?type=VIEW', '--view VIEW, the same answer'),
    'param:git.no_merges': Retirement('git ?no_merges (--no-merges)', '--merges off'),
    'param:git.raw': Retirement('git ?raw=1', '--detail raw, the historical file text'),
    # Blame's ignore was two controls in one scalar (BACK-2733): its value decides which it is, the same answer.
    'param:git.ignore': Retirement('git ?ignore=SHAS|off (--ignore)',
                                   '--ignore-commits SHAS; ignore=off is --auto-ignore off, the same answer'),
    'value:git.view=log': Retirement('git --view log (?type=log)', '--view history, the same answer'),
    'value:git.detail=summary': Retirement('git --detail summary', '--detail normal, the same answer'),
    'param:pack.verbose': Retirement('pack ?verbose (--verbose)',
                                     '--detail full; JSON keeps "verbose": true'),
    'param:overview.verbose': Retirement('overview ?verbose (--verbose)', '--all, the same uncapped map'),
    # Overview's map sections are its rows, capped by limit (Scott 2026-11-20, BACK-2622 B): top=0 showed no graph rows,
    # which no limit value spells, so top stays a setting of its own until the cut; imports is a switch.
    'param:overview.top': Retirement('overview ?top=N (--top N)', '--limit N, which caps each map section; 0 is uncapped',
                                     standalone=True),
    'param:overview.no_imports': Retirement('overview ?no_imports (--no-imports)', '--imports off'),
    'param:patches.group': Retirement('patches ?group=MODE (--group MODE)', '--view MODE'),
    'param:patches.top': Retirement('the pressure report ?top=N (--top N)', '--limit N; 0 is uncapped'),
    'param:patches.no_suppress': Retirement('patches --no-suppress', '--suppress off'),
    'param:patches.min_patches': Retirement('the pressure report ?min_patches=N (--min-patches N)',
                                            "--where 'patches>=N'"),
    'param:patches.min_categories': Retirement('the pressure report ?min_categories=N (--min-categories N)',
                                               "--where 'categories>=N'"),
    # JSON's first bare selectors are views (BACK-2615, D20): the same answer, one spelling.
    'param:json.schema': Retirement('json ?schema (first bare selector)', '--view schema'),
    'param:json.flatten': Retirement('json ?flatten (first bare selector)', '--view flatten'),
    'param:json.gron': Retirement('json ?gron (first bare selector)', '--view flatten'),
    'param:json.type': Retirement('json ?type (first bare selector)', '--view type'),
    'param:json.keys': Retirement('json ?keys (first bare selector)', '--view keys'),
    'param:json.length': Retirement('json ?length (first bare selector)', '--view length'),
    # data-only answers a bare lines array, not the envelope: a standalone legacy setting until the cut (BACK-2725).
    'param:json.data-only': Retirement('json ?data-only (with ?gron or ?flatten)',
                                       '--view flatten --detail raw, the same lines inside the JSON envelope',
                                       standalone=True),
    # SQLite's integrity check is a view (ruling Q4, BACK-2626): the same answer and exit, one spelling.
    'param:sqlite.check': Retirement('sqlite --check (?check)', '--view health'),
    # xlsx's different words (BACK-2626): the cell rectangle is --cells, the search is --match (one term answers
    # exactly as ?search did; repeated terms AND per row).
    'param:xlsx.range': Retirement('xlsx ?range=RANGE', '--cells RANGE'),
    'param:xlsx.search': Retirement('xlsx ?search=TEXT', '--match TEXT'),
    # env's show_secrets returned sensitive values unredacted through api.query; it was removed outright, with no
    # deprecation period (Scott 2026-11-22, BACK-2752), so its row starts at the error stage.
    'param:env.show_secrets': Retirement('env:// show_secrets', 'reveal env NAME, which shows a sensitive value as *** '
                                         '(secret values are redacted on every output; no control discloses them)',
                                         stage='error', removed=True),
    'param:contracts.impls': Retirement('contracts ?impls=N (--impls N)', '--implementations-limit N'),
    'param:contracts.no_implementations': Retirement('contracts --no-implementations', '--implementations off'),
    # Surface's D20 words (BACK-2623): the category is a kind, the test filter is tests, the rollup is a view and its
    # depth dir-depth. top cut the text only where limit cuts the answer, so it stays a cap of its own until the cut.
    'param:surface.type': Retirement('surface ?type=KIND (--type KIND)', '--kind KIND'),
    'param:surface.source_only': Retirement('surface ?source_only (--source-only)', '--tests exclude'),
    'param:surface.by': Retirement('surface ?by=dir (--by dir)', '--view dir'),
    'param:surface.depth': Retirement('surface ?depth=N (--depth N)', '--dir-depth N'),
    'param:surface.top': Retirement('surface ?top=N (--top N)',
                                    '--limit N, which caps each category in JSON and text; 0 is uncapped',
                                    standalone=True),
    'param:architecture.verbose': Retirement('architecture ?verbose (--verbose)',
                                             'reveal overview <path> --all, the same uncapped map'),
    'param:hotspots.verbose': Retirement('hotspots ?verbose (--verbose)', '--limit 0, both rankings uncapped'),
    # limit is Hotspots' and Testability's cap (COMMAND_MODEL "Caps", BACK-2673): top is the same value's old word.
    **{f'param:{noun}.top': Retirement(f'{noun} ?top=N (--top N)', '--limit N, which caps each list; 0 is uncapped')
       for noun in ('hotspots', 'testability')},
    'param:testability.verbose': Retirement('testability ?verbose (--verbose)',
                                            'reveal patches <path> --view pressure --limit 0, every group'),
    'param:deps.verbose': Retirement('deps ?verbose (--verbose)', '--top 0, every text section uncapped'),
    # Metrics' vocabulary (BACK-2621, Scott 2026-11-15): the hotspot ranking is a view whose rows limit caps,
    # filters are where (the complexity pair is the file average, avg_complexity), switches take on|off.
    # The row names the parameter, not one value: ?hotspots=false is noted too (it answers as if omitted).
    'param:metrics.hotspots': Retirement('metrics ?hotspots (--hotspots)',
                                         '--view hotspots: the ranked files are the rows; '
                                         'hotspots false is the default, so omit it', standalone=True),
    'param:metrics.top': Retirement('metrics ?top=N (--top N)', '--limit N in --view hotspots; 0 is uncapped', standalone=True),
    'param:metrics.min_lines': Retirement('metrics ?min_lines=N (--min-lines N)', "--where 'lines>=N'"),
    'param:metrics.max_lines': Retirement('metrics ?max_lines=N (--max-lines N)', "--where 'lines<=N'"),
    'param:metrics.min_functions': Retirement('metrics ?min_functions=N (--min-functions N)',
                                              "--where 'functions>=N'"),
    'param:metrics.min_complexity': Retirement('metrics ?min_complexity=N (--min-complexity N)',
                                               "--where 'avg_complexity>=N', the file average"),
    'param:metrics.max_complexity': Retirement('metrics ?max_complexity=N (--max-complexity N)',
                                               "--where 'avg_complexity<=N', the file average"),
    'param:metrics.no_churn': Retirement('metrics --no-churn', '--churn off'),
    'param:metrics.no_merges': Retirement('metrics ?no_merges (--no-merges)', '--merges off'),
    'param:metrics.summary_only': Retirement('metrics ?summary_only (--summary-only)', '--detail summary'),
    # calls?modules folded into imports (BACK-1054 slice S5, Q4/Q8): the module graph is imports' edges, in the
    # old shape without call_count, until the cut.
    'param:calls.modules': Retirement('calls ?modules (--modules)',
                                      'reveal imports <path> --importers --scope path, the same import edges as '
                                      'each module\'s importers', standalone=True),
    'param:calls.external': Retirement('calls ?external (--external)',
                                       'reveal imports <path> --importers (--scope root, the default), importers '
                                       'from the whole project root', standalone=True),
    # D8 (BACK-2195): ?uncalled is retired. It answers unchanged in shape until the cut (BACK-2200), with no
    # confidence in any language; ?callers=NAME answers "is this used?" and the language's own tool answers the rest.
    'param:calls.uncalled': Retirement('calls ?uncalled (--uncalled)',
                                       '--callers NAME for one function, or the language\'s own '
                                       'dead-code tool (vulture, knip, staticcheck/deadcode, rustc dead_code, '
                                       'Roslyn IDE0051, Periphery, Psalm)', standalone=True),
    # Decision (e): ast's call filters are retired, not kept as element filters; calls= matched call
    # text in every scanned file instead of the callers index, so the two could disagree.
    # Claude vocabulary retains its legacy readers/codecs until the cut (BACK-2617).
    # summary, search and contains answer differently from their replacements on most resources (BACK-2654 note #12):
    # standalone legacy words until the cut; each note names the replacement for what the word did.
    'param:claude.summary': Retirement('claude ?summary',
        'claude://session/NAME --detail summary on the session overview; on a session sub-resource '
        'summary answered the overview analytics, and --detail summary there exits 2', standalone=True),
    'param:claude.search': Retirement('claude ?search',
        'claude://session/NAME --match TEXT on the session overview for the session-wide search, or --match TEXT '
        'on sessions, history and search; on a session sub-resource --match filters that view or exits 2', standalone=True),
    'param:claude.contains': Retirement('claude ?contains',
        '--match TEXT on /messages for narrative text, or with --tools/--errors for tool-result text; '
        'where --match is unsupported the request exits 2', standalone=True),
    'param:claude.filter': Retirement('claude ?filter',
        'sessions --where session~=TEXT, a case-insensitive session-name substring'),
    'param:claude.tail': Retirement('claude ?tail',
        '--view messages --sort=-message_index --limit N selects latest-first; the legacy slice stays chronological, zero is empty and negative counts retain all turns; canonical limit=0 is uncapped', standalone=True),
    # last is tail's other spelling (last == tail=1, last=N == tail=N): a legacy entry on tail, not a parameter.
    'param:claude.last': Retirement('claude ?last',
        '--view messages --sort=-message_index --limit N selects latest-first; the legacy slice stays chronological, bare last or zero selects one; canonical limit=0 is uncapped'),
    # full and raw answer differently from detail=full/raw (BACK-2654 note #9): legacy settings of their own until the cut.
    'param:claude.full': Retirement('claude ?full',
        '--detail full on a supported expanding view; unsupported views reject', standalone=True),
    'param:claude.raw': Retirement('claude ?raw',
        '--view messages or --view prompts with --detail raw; canonical raw also expands the text display', standalone=True),
    # Codex vocabulary (BACK-2618, rulings Q1-Q4): filter, full and last/tokens/goal answer exactly as their
    # replacements; search answers as --match except that its JSON query stays a string (match echoes a list of terms),
    # so it is a standalone legacy operation until the cut. They are URI words only: the codex subcommand has no flag for
    # them, so ?search= (no canonical form) says only its own note.
    'param:codex.filter': Retirement('codex ?filter=TEXT',
                                     "--where 'session~=TEXT', the same title or first-message substring"),
    'param:codex.search': Retirement('codex ?search=TEXT',
                                     '--match TEXT, the same content search, whose JSON query is a list of terms; '
                                     'repeated terms AND per session', standalone=True),
    'param:codex.full': Retirement('codex ?full', '--detail full'),
    'param:codex.last': Retirement('codex ?last', '--view last'),
    'param:codex.tokens': Retirement('codex ?tokens', '--view tokens'),
    'param:codex.goal': Retirement('codex ?goal', '--view goal'),
    'param:ast.calls': Retirement('ast://?calls=', "reveal calls <path> --callers NAME, or --grep 'PATTERN' for a pattern", standalone=True),
    # Different words for one control are legacy spellings with a note (COMMAND_MODEL "Different words", BACK-2654);
    # Git type is D18-deferred and stays note-free. AST show is --view (D20, BACK-2613).
    'param:ast.type': Retirement('ast ?type=KIND (--type KIND, or the where field type)',
                                 "--kind KIND, or the where field kind (--where 'kind!=KIND'), the same element kind"),
    'param:ast.show': Retirement('ast ?show=VIEW (--show VIEW)', '--view VIEW, the same answer (dict-heatmap or '
                                                                 'dict-schemas; the calls view retired to reveal calls)'),
    # A bare shared control name is never a field (BACK-2654 rule 8): AST's bare depth is its where term, and depth is
    # nesting_depth's retired field word (BACK-2613 Q10).
    'param:ast.depth': Retirement('ast ?depth OP N (bare, or the where field depth)', "--where 'nesting_depth OP N', "
                                                                                     'the same nesting-depth filter'),
    'param:markdown.body-contains': Retirement('markdown ?body-contains=TEXT (--body-contains TEXT)',
                                               '--match TEXT, the same body match; repeats AND'),
    'param:markdown.fields': Retirement('markdown ?fields=A,B', '--columns A,B, the same frontmatter columns'),
    'param:markdown.link-graph': Retirement('markdown ?link-graph (--link-graph)', '--view links, the same link graph'),
    'param:markdown.lint': Retirement('markdown ?lint (--lint)', '--view lint, the same front-matter queue'),
    # aggregate=F is two controls, --field F and --view aggregate (LegacySpelling.sets, ruling Q2-A).
    'param:markdown.aggregate': Retirement('markdown ?aggregate=FIELD (--aggregate FIELD)',
                                           '--view aggregate --field FIELD, the same frequency table'),
    'param:ast.callee_of': Retirement('ast://?callee_of=', 'reveal calls <path> --callees NAME', standalone=True),
    # The within-file call graph view retired to the calls noun: a retired value of view that answers until the cut, with
    # no canonical form (standalone; the request says no request note).
    'value:ast.show=calls': Retirement('ast ?show=calls (--show calls)',
                                       "reveal calls <path> --callers NAME or --callees NAME, or --grep 'PATTERN'",
                                       standalone=True),
    'value:ast.view=calls': Retirement('ast ?view=calls (--view calls)',
                                       "reveal calls <path> --callers NAME or --callees NAME, or --grep 'PATTERN'",
                                       standalone=True),
    # stats became metrics and absorbed classify (D2, BACK-2069): both old schemes answer from the
    # metrics owner, unchanged, until the cut. File hotspots are metrics' ?hotspots=true ranking.
    'scheme:stats': Retirement('stats://', 'reveal metrics <path> (the same answer)'),
    # hotspots retired into two commands (BACK-2149, Scott 2026-11-06): files and the --fail-on findings gate are
    # metrics' hotspots ranking, functions are ast's complexity sort. Both spellings answer as before until the
    # cut, which waits on the due-diligence script moving off hotspots:// (BACK-2153). has_test_hint is retired
    # with no replacement field (the D8 pattern of ?uncalled).
    'subcommand:hotspots': Retirement('reveal hotspots',
                                      "reveal metrics <path> --view hotspots [--fail-on findings] (files) and "
                                      "reveal ast <path> --where 'complexity>=10' --sort=-complexity --limit 10 "
                                      '(functions); has_test_hint, an unmeasured test-name heuristic, has no '
                                      'replacement field (use a coverage tool)'),
    'scheme:hotspots': Retirement('hotspots://', 'reveal metrics <path> --view hotspots (files) and '
                                  "reveal ast <path> --where 'complexity>=10' --sort=-complexity --limit 10 (functions); has_test_hint, "
                                  'an unmeasured test-name heuristic, has no replacement field (use a coverage tool)'),
    'param:hotspots.functions_only': Retirement('hotspots ?functions_only (--functions-only)',
                                                "reveal ast <path> --where 'complexity>=10' --sort=-complexity --limit 10, the same "
                                                'function ranking (min_complexity=N is complexity>=N, top=N is --limit N)', standalone=True),
    'param:hotspots.files_only': Retirement('hotspots ?files_only (--files-only)',
                                            'reveal metrics <path> --view hotspots, the same file ranking', standalone=True),
    # testability became patches ?view=pressure (D2, Q-P4-2, BACK-2160): the old scheme answers from the patches owner,
    # unchanged, until the cut.
    'subcommand:testability': Retirement('reveal testability', 'reveal patches <path> --view pressure (the same answer)'),
    'scheme:testability': Retirement('testability://', 'reveal patches <path> --view pressure (the same answer)'),
    'scheme:classify': Retirement('classify://', 'reveal metrics <path> --view provenance (the same answer)'),
    # depends folded into imports (BACK-1054 slice S6, Q8): it answers from the imports:// engine's build with its old
    # shapes and exit code (0 on a partial answer, BACK-2181) until the cut, which waits on BACK-2153.
    'scheme:depends': Retirement('depends://', 'reveal imports <path> --importers (one file: --importers FILE)'),
    # deps folded into imports (BACK-1054 slice S4, Q5/Q8): both spellings answer from one imports:// build with deps'
    # old shapes and exit codes until the cut, which waits on a due-diligence consumer moving first (BACK-2153).
    'subcommand:deps': Retirement('reveal deps', 'reveal imports <path> --external, --circular or --unused'),
    'scheme:deps': Retirement('deps://', 'reveal imports <path> --external, --circular or --unused'),
    # python:// was removed outright, not moved (D4, BACK-2225, Scott 2026-10-25): no reveal scheme answers its
    # questions, so the row names the interpreter's own tools and starts at the error stage.
    'scheme:python': Retirement('python://', 'python -m site (sys.path), python -m pip list or python -m pip show NAME '
                                '(packages); no reveal scheme replaces it', stage='error', removed=True),
}


def current_schemes(*, core_only: bool = False) -> list:
    """Registered schemes to teach a reader: every one the RETIREMENTS table does not retire.

    Retired schemes stay registered (they answer with a note until the cut), so registry
    consumers that check adapters keep the full list; hints and listings use this one (BACK-2532).
    """
    from ..adapters.registry import OPS_SCHEMES, is_internal_scheme, list_supported_schemes
    return [scheme for scheme in list_supported_schemes()
            if f'scheme:{scheme}' not in RETIREMENTS
            and (not core_only or (scheme not in OPS_SCHEMES and not is_internal_scheme(scheme)))]


class RetiredSpellingError(Exception):
    """A spelling at the ``error`` stage was used: the caller exits 2 with its text."""

    def __init__(self, key: str, entry: Retirement) -> None:
        super().__init__(entry.text)
        self.key = key
        self.entry = entry


def effects_requested(args) -> bool:
    """Whether a parsed path request asks for the effects view by a D10 spelling (``--effects``, ``--view effects``)."""
    return bool(getattr(args, 'effects', False)) or getattr(args, 'view', None) == 'effects'


def refuse_effects_beside(args, spelling: str) -> None:
    """D10's effects target rule, kept as it was (BACK-2627 R5): the effects view answers one code file, so a special
    mode that preempts the file route (``--stdin``, ``--rules``, ...) beside it is an invalid request, exit 2. The other
    D10 rules (exclusive modes, depth, slices, other views) come from the element declarations."""
    from ..errors import NavRequestValidationError

    if effects_requested(args):
        raise NavRequestValidationError(f'--effects cannot combine with the {spelling} view.')


def retired_flag_key(option: str) -> Optional[str]:
    """The ``flag:`` RETIREMENTS key of a typed long option, or None. Exact: a long option is spelled in full, so an
    abbreviation never reaches here (BACK-2705)."""
    key = 'flag:' + option
    return key if key in RETIREMENTS else None


# dest -> the option string the user typed for it, for controls with several spellings (a switch's --NAME, its legacy
# flag and its short spelling): notes name a flag as typed (BACK-2654, the item F principle). One per invocation.
_TYPED: ContextVar[Optional[Dict[str, str]]] = ContextVar('reveal_typed_spellings', default=None)


def record_spelling(dest: str, option: str) -> None:
    """The parser saw *option* for *dest* in this invocation; the first spelling typed is the one notes name."""
    typed = _TYPED.get()
    if typed is not None:
        typed.setdefault(dest, option)


def _typed_options(token: str, actions: Dict[str, Any]) -> list:
    """The (option string, value attached) pairs *token* spells, as argparse resolves it: an exact option, ``--x=v``,
    or a cluster of short options (``-ic``; a value-taking short option ends it). A long option is spelled in full on
    every reveal parser (BACK-2705), so no prefix is resolved."""
    if not token.startswith('-') or token == '-':
        return []
    if token.startswith('--'):
        name, eq, _ = token.partition('=')
        return [(name, bool(eq))] if name in actions else []
    if token in actions:
        return [(token, False)]
    found, rest = [], token[1:]
    while rest and f'-{rest[0]}' in actions:
        option, rest = f'-{rest[0]}', rest[1:]
        takes_value = getattr(actions[option], 'nargs', None) != 0
        found.append((option, takes_value and bool(rest)))
        if takes_value:
            break
    return found


def record_typed_spellings(parser: ArgumentParser, argv: Sequence[str]) -> None:
    """After a parse: for each flag *parser* spells more than one way (a switch's --NAME, its legacy off flag and -q;
    --check/--lint; --top/--limit; -i/--ignore-case), record the spelling *argv* typed, so notes and errors name it
    (BACK-2654 item D3). The spellings come from the parser's own actions; a flag's value is never read as a flag."""
    actions = parser._option_string_actions
    count: Dict[str, int] = {}
    for action in parser._actions:
        count[action.dest] = count.get(action.dest, 0) + len(action.option_strings)
    expect_value = False
    for token in argv:
        if token == '--':
            break
        if expect_value:
            expect_value = False
            continue
        for option, attached in _typed_options(token, actions):
            action = actions[option]
            if count.get(action.dest, 0) > 1:
                record_spelling(action.dest, option)
            expect_value = action.nargs not in (0, '?', '*') and not attached


def typed_spelling(dest: str, default: str) -> str:
    """The option string the user typed for *dest*, else *default* (outside an invocation, or not typed)."""
    return (_TYPED.get() or {}).get(dest, default)


def typed_spellings() -> Dict[str, str]:
    """Every dest -> typed option string recorded in this invocation."""
    return dict(_TYPED.get() or {})


def _shared_name_retirement(key: str) -> Optional[Retirement]:
    """The one generated row family (BACK-2654 rule 8): ``param:NOUN.NAME`` for a bare key named like a shared control
    that an open-field noun does not declare, a legacy spelling of the identical where term until the cut. Generated
    from the noun's declarations (``shared_name_is_legacy_field``), never typed per key."""
    from ..utils.query_parser import SHARED_CONTROL_NAMES
    scheme, _, name = key[len('param:'):].partition('.') if key.startswith('param:') else ('', '', '')
    if name not in SHARED_CONTROL_NAMES:
        return None
    from ..adapters.registry import get_adapter_class
    from ..utils.query_binding import shared_name_is_legacy_field
    declarations = getattr(get_adapter_class(scheme), 'PARAM_SPECS', None)
    if not isinstance(declarations, tuple) or not shared_name_is_legacy_field(declarations, name):
        return None
    return Retirement(f'{scheme} bare ?{name} (a shared control name)',
                      f"--where '{name} OP VALUE', the same field filter")


def generated_retirements() -> Dict[str, Retirement]:
    """Every row of the generated family, by key, for the teaching-surface checks: RETIREMENTS does not hold them, so
    a scan of its keys alone never sees a doc that teaches ``markdown://docs?kind=guide``."""
    from ..adapters.registry import list_supported_schemes
    from ..utils.query_parser import SHARED_CONTROL_NAMES
    rows = {}
    for scheme in sorted(list_supported_schemes()):
        for name in SHARED_CONTROL_NAMES:
            row = _shared_name_retirement(f'param:{scheme}.{name}')
            if row is not None:
                rows[f'param:{scheme}.{name}'] = row
    return rows


def retirement_note(key: str) -> Optional[Retirement]:
    """The one hook: consulted where each kind of spelling is parsed. Returns the table row for
    *key*, or None when it is not retired (nothing printed). A ``note`` row joins the invocation's
    log: a JSON answer carries it as a ``meta.warnings`` entry, and otherwise its note is printed on
    stderr once, after the answer (when a host asked for stderr; ``utils.invocation_log``);
    ``phase7`` is only recorded; ``error`` raises RetiredSpellingError."""
    entry = RETIREMENTS.get(key) or _shared_name_retirement(key)
    if entry is None:
        return None
    if entry.stage == 'error':
        raise RetiredSpellingError(key, entry)
    log = current_log()
    if log is None:  # a library call outside any invocation: nobody to tell
        return entry
    if entry.stage == 'phase7':
        log.recorded[key] = entry
    else:
        # Said once, by the log: in a JSON answer's meta.warnings, else on stderr after the answer.
        log.noted.setdefault(key, entry)
    return entry


# The stage of the one request note (``request_note``): a URI request to an analysis-only scheme, or a URI with a query
# string, is a retiring spelling of its canonical request (D20). The cut turns it to 'error' (BACK-2718).
REQUEST_STAGE = 'note'
REQUEST_FORMS = ('cli', 'mcp', 'python')
_FORM: ContextVar[str] = ContextVar('reveal_request_form', default='cli')


def element_retirement(scheme: str) -> Optional[str]:
    """The ``target:SCHEME.element`` row of a scheme whose positional element still answers until the cut, noted, or
    None: the one check every transport's unread-element refusal consults (the CLI's URI route and ``api.query``), so
    a bound noun with no such row refuses the element as before (BACK-2764)."""
    key = f'target:{scheme}.element'
    return key if retirement_note(key) is not None else None


def request_form() -> str:
    """The transport the running request came in on: ``cli`` (also a ``--stdin`` line), ``mcp`` or ``python``."""
    return _FORM.get()


_INTERNAL: ContextVar[bool] = ContextVar('reveal_internal_request', default=False)


@contextmanager
def internal_request() -> Iterator[None]:
    """Mark the request a router builds for a spelling the user did not type as its own (``reveal a.py --name X`` runs
    an ``ast://`` URI internally): it says no request note, since the user's actual spelling has its own note."""
    token = _INTERNAL.set(True)
    try:
        yield
    finally:
        _INTERNAL.reset(token)


def request_note(scheme: str, replacement_for: Callable[[str], str]) -> Optional[Retirement]:
    """The one note of a retiring URI request: *replacement_for(form)* is the executable canonical request rendered from
    the bound request in the running transport's own form. Keyed ``request:<scheme>`` so it is said once per scheme per
    invocation; at the ``error`` stage it raises like any retired spelling (exit 2, the same text). A request a router
    built itself (``internal_request``) says nothing."""
    if _INTERNAL.get():
        return None
    from .routing.canonical import UnrenderableRequest
    try:
        replacement = replacement_for(request_form())
    except UnrenderableRequest:
        _say_covered_notes()  # no canonical form to recommend: each covered spelling says its own row
        return None
    entry = Retirement(f'a {scheme}:// request', replacement, REQUEST_STAGE)
    key = f'request:{scheme}'
    if entry.stage == 'error':
        raise RetiredSpellingError(key, entry)
    log = current_log()
    if log is not None:
        log.covered.clear()  # this note says them
        (log.recorded if entry.stage == 'phase7' else log.noted).setdefault(key, entry)
    return entry


def begin_uri_request() -> None:
    """A URI request starts: no covered spelling of an earlier request in the same invocation carries over."""
    log = current_log()
    if log is not None:
        log.covered.clear()


def note_uri_spelling(key: str) -> None:
    """A retired spelling a URI request spells: said now (``retirement_note``), or, a per-key row the request note covers,
    kept on the log until the request note renders. A request with a canonical form drops it (the one note says it); one
    with none (a control no flag spells) says it after all; a rejected request says neither."""
    if not request_note_covers(key):
        retirement_note(key)
        return
    log = current_log()
    if log is not None:
        log.covered.append(key)


def _say_covered_notes() -> None:
    log = current_log()
    if log is None:
        return
    covered, log.covered = log.covered, []
    for key in covered:
        retirement_note(key)


def request_noted(scheme: str) -> bool:
    """Whether a URI request of *scheme* says the one request note: a declared noun (its URI runs the declared route that
    binds the request) that is not a retired twin (architecture, stats, trace...: its own ``scheme:`` row is its note)."""
    spec = COMMANDS.get(scheme)
    return spec is not None and bool(spec.declared_adapter) and f'scheme:{scheme}' not in RETIREMENTS


def request_note_covers(key: str) -> bool:
    """Whether a per-key note is the spelling of a request that ``request_note`` replaces: a ``param:``/``value:`` row at
    the note stage, of a scheme that says the request note, naming a replacement for this noun's own control. A
    standalone row (a legacy operation with no identical canonical form) and every error-stage row keep their own
    note."""
    if not key.startswith(('param:', 'value:')):
        return False
    if not request_noted(key.partition(':')[2].partition('.')[0]):
        return False
    entry = RETIREMENTS.get(key) or _shared_name_retirement(key)
    return entry is not None and entry.stage == 'note' and not entry.standalone and not entry.removed


def noted_retirements() -> Dict[str, Retirement]:
    """The ``note``-stage spellings this invocation used, by key."""
    log = current_log()
    return dict(log.noted) if log is not None else {}


def retirement_warnings() -> list:
    """meta.warnings entries for the noted retirements, for a JSON document (which then carries the
    note: it is not printed on stderr beside a JSON answer): code ``retired_spelling``. ``field`` is
    the key, so two retired spellings are two entries under note_warning's (type, code, field) dedupe."""
    return [{'type': 'retired_spelling', 'code': 'retired_spelling', 'message': entry.text, 'field': key, 'old': entry.old,
             'replacement': entry.replacement, 'stage': entry.stage}
            for key, entry in noted_for_json().items()]


_QUERY_OPERATOR = re.compile(r'!=|~=|>=|<=|=|>|<')


def uri_retirement_keys(uri: str) -> list:
    """The table keys a URI spells: its scheme, each query parameter, each parameter value."""
    from urllib.parse import unquote_plus
    scheme, sep, rest = uri.partition('://')
    if not sep:
        return []
    scheme = scheme.lower()
    keys = [f'scheme:{scheme}']
    for pair in rest.partition('?')[2].partition('#')[0].split('&'):
        if not pair:
            continue
        # The parameter is the text before its operator: ``calls~=x`` and ``calls!=x`` spell
        # ``calls`` as ``calls=x`` does; only ``=`` names a value.
        match = _QUERY_OPERATOR.search(pair)
        name, op, value = (pair[:match.start()], match.group(0), pair[match.end():]) if match else (pair, '', '')
        name = unquote_plus(name)
        keys.append(f'param:{scheme}.{name}')
        if op == '=':
            keys.append(f'value:{scheme}.{name}={unquote_plus(value)}')
    return keys


def exit_codes_text(command: str, gates: Sequence[str] = ('none', 'findings')) -> str:
    """The exit-code lines `reveal <command> --help` prints, from EXIT_CODES. *gates* are the
    --fail-on values the command supports: without 'findings' it never exits 1."""
    wording = {**EXIT_CODES, **EXIT_CODE_WORDING.get(command, {})}
    codes = [c for c in wording if c != 1 or 'findings' in gates]
    lines = ['Exit codes:'] + [f'  {c}  {wording[c]}' for c in codes]
    if command in FINDINGS_BY_DEFAULT:
        lines.append('--fail-on none reports findings without exit 1; lost analysis still exits 3.')
    return '\n'.join(lines)


def subcommand_help_guides() -> Dict[str, str]:
    """help:// topic -> reveal/docs guide for each subcommand that declares its own guide."""
    return {name: spec.help_guide for name, spec in COMMANDS.items() if spec.help_guide}


def render_subcommand_lines() -> str:
    """The `--help-all` subcommand rows, generated from COMMANDS."""
    return '\n'.join(f'  {COMMANDS[n].usage:<26}  {COMMANDS[n].summary}' for n in EPILOG_ORDER
                     if f'subcommand:{n}' not in RETIREMENTS)


_DESC_SORT = re.compile(r'^-[a-zA-Z_][a-zA-Z0-9_]*$')


def _normalize(tokens: Sequence[str]) -> Tuple[Tuple[str, ...], bool]:
    """(tokens with --perf removed and ``--sort -field`` joined, whether --perf was given).

    ``--perf`` is handled at the process boundary, since it has to time the whole run. So it
    is taken out here, and a command whose parser doesn't declare it still accepts it.
    argparse rejects ``--sort -modified`` because ``-modified`` looks like a flag, but it
    accepts ``--sort=-modified``, so the space form is joined. Tokens after ``--`` are
    positional and are left alone.
    """
    out: list = []
    perf = False
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == '--':
            out.extend(tokens[i:])
            break
        if tok == '--perf':
            perf = True
        elif tok == '--sort' and i + 1 < len(tokens) and _DESC_SORT.match(tokens[i + 1]):
            out.append(f'--sort={tokens[i + 1]}')
            i += 1
        else:
            out.append(tok)
        i += 1
    return tuple(out), perf


def _global_option_arity() -> Dict[str, int]:
    """Option string -> number of values, for the options every command accepts."""
    from .parser import _build_global_options_parser

    arity = {}
    for action in _build_global_options_parser()._actions:
        takes = 0 if action.nargs == 0 else 1
        for opt in action.option_strings:
            arity[opt] = takes
    return arity


def _find_command(tokens: Tuple[str, ...]) -> Optional[int]:
    """Index of the subcommand name, or None for the path/URI form.

    The name is the first positional token. Only global options (the ones every
    subcommand also accepts) may come before it. After any other option, or after ``--``,
    the invocation is the path form, as it always was.
    """
    if not tokens:
        return None
    if not tokens[0].startswith('-'):
        return 0 if tokens[0] in COMMANDS else None
    arity = _global_option_arity()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if not tok.startswith('-') or tok == '-':
            return i if tok in COMMANDS else None
        opt, has_value = tok.split('=', 1)[0], '=' in tok
        if opt not in arity:
            return None
        i += 1 + (arity[opt] if not has_value else 0)
    return None


@dataclass(frozen=True)
class Invocation:
    """One command line, parsed once."""

    argv: Tuple[str, ...]                  # after the program name, normalized
    program: str = 'reveal'
    perf: bool = False
    command_index: Optional[int] = field(default=None, compare=False)

    @classmethod
    def parse(cls, argv: Sequence[str]) -> 'Invocation':
        """Build from a full argv (``argv[0]`` is the program)."""
        program = argv[0] if argv else 'reveal'
        tokens, perf = _normalize(list(argv[1:]))
        return cls(tokens, program, perf, _find_command(tokens))

    @property
    def command(self) -> Optional[str]:
        """The subcommand name, or None for the path/URI form."""
        return None if self.command_index is None else self.argv[self.command_index]

    @property
    def command_argv(self) -> list:
        """What the command's parser parses: every token except the subcommand name."""
        if self.command_index is None:
            return list(self.argv)
        return list(self.argv[:self.command_index] + self.argv[self.command_index + 1:])

    @property
    def bare(self) -> bool:
        """``reveal`` with nothing after it (``--perf`` aside)."""
        return not self.argv

    def typed(self, option: str) -> bool:
        """Whether ``option`` was typed on the command line (``--x`` or ``--x=value``)."""
        for tok in self.argv:
            if tok == '--':
                return False
            if tok == option or tok.startswith(option + '='):
                return True
        return False

    @property
    def display(self) -> str:
        """The command line as one string, for a provenance manifest."""
        return ' '.join((self.program,) + self.argv)


_CURRENT: ContextVar[Optional[Invocation]] = ContextVar('reveal_invocation', default=None)


def current_invocation() -> Optional[Invocation]:
    """The invocation being run, or None outside one (a library call, a unit test)."""
    return _CURRENT.get()


@contextmanager
def invocation_scope(invocation: Invocation, *, retirements_to_stderr: bool = True,
                     form: str = 'cli') -> Iterator[Invocation]:
    """Publish ``invocation`` for the code it runs, and restore the previous one on exit. It
    also opens the invocation's log (``utils.invocation_log``); the MCP server passes
    ``retirements_to_stderr=False`` and returns the fact in the tool result; *form* names the transport a request note
    renders its replacement for (``cli``, ``mcp`` or ``python``)."""
    if form not in REQUEST_FORMS:
        raise ValueError(f'form is one of {REQUEST_FORMS}, not {form!r}')
    token = _CURRENT.set(invocation)
    typed_token = _TYPED.set({})
    form_token = _FORM.set(form)
    try:
        with log_scope(retirements_to_stderr):
            yield invocation
    finally:
        _FORM.reset(form_token)
        _TYPED.reset(typed_token)
        _CURRENT.reset(token)
