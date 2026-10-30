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
from typing import Callable, Dict, Iterator, NamedTuple, Optional, Sequence, Tuple


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
    'architecture': _declared('architecture',
                     'reveal architecture [path]',
                     'Architectural brief: entry points, core abstractions, risks'),
    'calls':        _declared('calls',
                     'reveal calls --callers FUNC',
                     'Call graph: callers, callees (--depth N, --detail), --rank callers, --modules'),
    'check':        _spec('check',
                     'reveal check <path>',
                     'Run quality rules on a file or directory',
                     ('text', 'json', 'grep'),  # also PATH --check (BACK-1644)
                     help_guide=_SUBCOMMANDS_GUIDE, also_json=True),
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
                     'reveal health [path]',
                     'Ops health: SSL + databases + DNS + nginx',
                     ('text', 'json'), help_guide=_SUBCOMMANDS_GUIDE),
    'hotspots':     _declared('hotspots',
                     'reveal hotspots [path]',
                     'High-complexity files and functions that need attention'),
    'imports':      _declared('imports',
                     'reveal imports [path]',
                     'Import graph: who imports what (--importers), fan-in, cycles, unused imports, layer violations'),
    'metrics':      _declared('metrics',
                     'reveal metrics [path]',
                     'Per-file lines, complexity and quality; --hotspots ranks files; --view provenance tags every file'),
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
                     'Older alias of `reveal dev new-*` — prefer `reveal dev`',
                     help_guide=_SUBCOMMANDS_GUIDE),
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
EPILOG_ORDER = ('overview', 'architecture', 'imports', 'deps', 'hotspots', 'metrics', 'contracts', 'surface',
                'patches', 'testability', 'calls', 'trace', 'check', 'review', 'health', 'pack', 'dev',
                'scaffold', 'offline')


# What each exit code means for a command on the D6 outcome policy (the exit-code contract). The one
# home for the wording help prints; a command words a code more specifically in EXIT_CODE_WORDING.
EXIT_CODES: Dict[int, str] = {
    0: 'completed; no enabled findings gate matched',
    1: 'a findings gate matched',
    2: 'request rejected before analysis (usage error, missing path)',
    3: 'required analysis or output failed or was incomplete',
}
EXIT_CODE_WORDING: Dict[str, Dict[int, str]] = {
    'check': {0: 'no issues', 1: 'issues found',
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
#   mcp:<tool>                   reveal_trace
# A row's stage says what the spelling does now: ``note`` prints the note and answers as before,
# ``phase7`` is recorded and prints nothing yet (MCP tool names stay until Phase 7), ``error``
# is the cut release: exit 2 with the same text. retirement_note() is the one reader.
STAGES = ('note', 'phase7', 'error')
RETIREMENT_KEY = re.compile(
    r'^(?:subcommand:[a-z][a-z0-9-]*'
    r'|scheme:[a-z][a-z0-9+.-]*'
    r'|param:[a-z][a-z0-9+.-]*\.[^.=\s]+'
    r'|value:[a-z][a-z0-9+.-]*\.[^.=\s]+=.*'
    r'|flag:--[a-z][a-z0-9-]*'
    r'|target:[a-z][a-z0-9-]*\.[a-z][a-z0-9-]*'  # a kind of target a subcommand stops taking
    r'|mcp:[a-z][a-z0-9_]*)$')


@dataclass(frozen=True)
class Retirement:
    """One retired spelling: *old* as the user types it, what replaces it, and its stage."""
    old: str
    replacement: str
    stage: str = 'note'

    def __post_init__(self) -> None:
        if not self.old or not self.replacement:
            raise ValueError('a retirement names the old spelling and its replacement')
        if self.stage not in STAGES:
            raise ValueError(f'retirement stage {self.stage!r} is not one of {STAGES}')

    @property
    def text(self) -> str:
        """The one wording, for the note, the error and the JSON warning."""
        return f'{self.old} is deprecated; use {self.replacement}.'


# The two older BACK-1906 notes, then Phase 2b's call-graph spellings (BACK-2066). A param:
# row covers the URI parameter and the same parameter typed as a declared subcommand's flag.
RETIREMENTS: Dict[str, Retirement] = {
    'flag:--deps': Retirement('--deps', '--inputs'),
    'flag:--mutations': Retirement('--mutations', '--outputs'),
    'flag:--writes': Retirement('--writes', '--outputs'),
    'flag:--calls': Retirement('--calls', '--callsites'),
    'flag:--search': Retirement('--search', '--name PATTERN (regex)'),
    # One row for the file route's --check and its --lint alias.
    'flag:--check': Retirement('file --check/--lint', 'reveal check <path>'),
    # --also-json is the one JSON file sink of --output FORMAT[=PATH] (BACK-2089 slice 5a); it answers until the cut.
    'flag:--also-json': Retirement('--also-json PATH', '--output json=PATH'),
    # review folded into check --changed plus the diff:// adapter (D3, BACK-2068 slice 3b): it answers as before until the
    # cut. Its hotspots and complexity sections have no new home until stats becomes metrics (BACK-2069);
    # the MCP tool reveal_review keeps its name until Phase 7.
    'subcommand:review': Retirement('reveal review', 'reveal check --changed RANGE (rules) and '
                                    "reveal 'diff://git://A/.:git://B/.' (structure); a directory: reveal check DIR"),
    # health is the ops entry point (P3-1, BACK-2068 slice 3c): a local code target still answers until the cut
    # (D5), but code quality is check's. An .conf nginx file is an ops target and stays.
    'target:health.code': Retirement('reveal health on a code path', 'reveal check <path>; health keeps ssl://, '
                                     'domain://, mysql://, sqlite:// and nginx .conf targets'),
    # trace merged into calls (BACK-2066): both spellings keep trace's frames shape until the cut
    # (decision c); the MCP tool reveal_trace keeps its name until Phase 7 (decision g).
    'subcommand:trace': Retirement('reveal trace', 'reveal calls <path> --callees FUNC --depth N --detail'),
    'scheme:trace': Retirement('trace://', 'calls://<path>?callees=FUNC&depth=N&detail'),
    'param:calls.root': Retirement('calls ?root= (--root)',
                                   '?callees=FUNC&depth=N (--callees FUNC --depth N), the same walk'),
    # Decision (a): an alias that answers identically until the cut.
    'param:calls.target': Retirement('calls ?target= (--target)', '?callers=FUNC (--callers FUNC), the same answer'),
    # calls?modules folded into imports (BACK-1054 slice S5, Q4/Q8): the module graph is imports' edges, in the
    # old shape without call_count, until the cut.
    'param:calls.modules': Retirement('calls ?modules (--modules)',
                                      'imports://<path>?importers&scope=path (reveal imports <path> --importers '
                                      '--scope path), the same import edges as each module\'s importers'),
    'param:calls.external': Retirement('calls ?external (--external)',
                                       'imports://<path>?importers (scope=root, the default), importers from the '
                                       'whole project root'),
    # D8 (BACK-2195): ?uncalled is retired. It answers unchanged in shape until the cut (BACK-2200), with no
    # confidence in any language; ?callers=NAME answers "is this used?" and the language's own tool answers the rest.
    'param:calls.uncalled': Retirement('calls ?uncalled (--uncalled)',
                                       '?callers=NAME (--callers NAME) for one function, or the language\'s own '
                                       'dead-code tool (vulture, knip, staticcheck/deadcode, rustc dead_code, '
                                       'Roslyn IDE0051, Periphery, Psalm)'),
    # Decision (e): ast's call filters are retired, not kept as element filters; calls= matched call
    # text in every scanned file instead of the callers index, so the two could disagree.
    'param:ast.calls': Retirement('ast://?calls=', "calls://<path>?callers=NAME, or --grep 'PATTERN' for a pattern"),
    'param:ast.callee_of': Retirement('ast://?callee_of=', 'calls://<path>?callees=NAME'),
    'value:ast.show=calls': Retirement('ast://?show=calls',
                                       "calls://<path>?callers=NAME or ?callees=NAME, or --grep 'PATTERN'"),
    # stats became metrics and absorbed classify (D2, BACK-2069): both old schemes answer from the
    # metrics owner, unchanged, until the cut. File hotspots are metrics' ?hotspots=true ranking.
    'scheme:stats': Retirement('stats://', 'metrics://<path> (the same answer)'),
    # testability became patches ?view=pressure (D2, Q-P4-2, BACK-2160): the old scheme answers from the patches owner,
    # unchanged, until the cut.
    'subcommand:testability': Retirement('reveal testability', 'reveal patches <path> --view pressure (the same answer)'),
    'scheme:testability': Retirement('testability://', 'patches://<path>?view=pressure (the same answer)'),
    'scheme:classify': Retirement('classify://', 'metrics://<path>?view=provenance (the same answer)'),
    # depends folded into imports (BACK-1054 slice S6, Q8): it answers from the imports:// engine's build with its old
    # shapes and exit code (0 on a partial answer, BACK-2181) until the cut, which waits on BACK-2153.
    'scheme:depends': Retirement('depends://', 'imports://<path>?importers (one file: ?importers=FILE)'),
    # deps folded into imports (BACK-1054 slice S4, Q5/Q8): both spellings answer from one imports:// build with deps'
    # old shapes and exit codes until the cut, which waits on a due-diligence consumer moving first (BACK-2153).
    'subcommand:deps': Retirement('reveal deps', 'reveal imports <path> --external, --circular or --unused'),
    'scheme:deps': Retirement('deps://', 'imports://<path>?external, ?circular or ?unused'),
}


class RetiredSpellingError(Exception):
    """A spelling at the ``error`` stage was used: the caller exits 2 with its text."""

    def __init__(self, key: str, entry: Retirement) -> None:
        super().__init__(entry.text)
        self.key = key
        self.entry = entry


class RetirementLog:
    """The retired spellings one invocation used. ``to_stderr`` is False for a host (MCP) that
    returns the fact in its result instead of printing it."""

    def __init__(self, to_stderr: bool = True) -> None:
        self.to_stderr = to_stderr
        self.noted: Dict[str, Retirement] = {}
        self.recorded: Dict[str, Retirement] = {}


_LOG: ContextVar[Optional[RetirementLog]] = ContextVar('reveal_retirement_log', default=None)


def retirement_note(key: str) -> Optional[Retirement]:
    """The one hook: consulted where each kind of spelling is parsed. Returns the table row for
    *key*, or None when it is not retired (nothing printed). A ``note`` row prints its note to
    stderr once per invocation (when a host asked for stderr) and joins the log that the JSON
    ``meta.warnings`` entry is built from; ``phase7`` is only recorded; ``error`` raises
    RetiredSpellingError."""
    entry = RETIREMENTS.get(key)
    if entry is None:
        return None
    if entry.stage == 'error':
        raise RetiredSpellingError(key, entry)
    log = _LOG.get()
    if log is None:  # a library call outside any invocation: nobody to tell
        return entry
    if entry.stage == 'phase7':
        log.recorded[key] = entry
    elif key not in log.noted:
        log.noted[key] = entry
        if log.to_stderr:
            print(f'note: {entry.text}', file=sys.stderr)  # boundary-ok: print -- the one retirement note
    return entry


def noted_retirements() -> Dict[str, Retirement]:
    """The ``note``-stage spellings this invocation used, by key."""
    log = _LOG.get()
    return dict(log.noted) if log is not None else {}


def retirement_warnings() -> list:
    """meta.warnings entries for noted_retirements(): code ``retired_spelling``. ``field`` is the
    key, so two retired spellings are two entries under note_warning's (type, code, field) dedupe."""
    return [{'type': 'retired_spelling', 'code': 'retired_spelling', 'message': entry.text, 'field': key, 'old': entry.old,
             'replacement': entry.replacement, 'stage': entry.stage}
            for key, entry in noted_retirements().items()]


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
    return '\n'.join(f'  {COMMANDS[n].usage:<26}  {COMMANDS[n].summary}' for n in EPILOG_ORDER)


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
def invocation_scope(invocation: Invocation, *, retirements_to_stderr: bool = True) -> Iterator[Invocation]:
    """Publish ``invocation`` for the code it runs, and restore the previous one on exit. It
    also opens the invocation's RetirementLog; the MCP server passes
    ``retirements_to_stderr=False`` and returns the fact in the tool result."""
    token = _CURRENT.set(invocation)
    log_token = _LOG.set(RetirementLog(retirements_to_stderr))
    try:
        yield invocation
    finally:
        _LOG.reset(log_token)
        _CURRENT.reset(token)
