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

    def load(self) -> Tuple[ArgumentParser, Callable[[Namespace], None]]:
        if self.declared_adapter:
            from functools import partial
            from .routing.declared import create_declared_parser, run_declared_command
            return create_declared_parser(self.declared_adapter), partial(
                run_declared_command, self.declared_adapter)
        mod = importlib.import_module(self.module)
        return getattr(mod, self.parser_factory)(), getattr(mod, self.runner)


def _spec(name: str, usage: str, summary: str, formats: Optional[Tuple[str, ...]] = None,
          help_guide: str = '') -> CommandSpec:
    return CommandSpec(f'reveal.cli.commands.{name}', f'create_{name}_parser', f'run_{name}',
                       formats, usage, summary, help_guide)


def _declared(name: str, usage: str, summary: str, help_guide: str = '') -> CommandSpec:
    """A noun the same-named adapter declares: no module of its own, `load()` builds both from the declaration."""
    return CommandSpec('', '', '', None, usage, summary, help_guide, declared_adapter=name)


_SUBCOMMANDS_GUIDE = 'guides/SUBCOMMANDS_GUIDE.md'


# Every subcommand. help://schemas/<name> also reads this table to tell a CLI-only command
# from an unknown name (BACK-1028). health and review have no same-named adapter, and their
# runners render only these formats (measured: grep/typed output matched text byte for byte).
COMMANDS: Dict[str, CommandSpec] = {
    'architecture': _declared('architecture',
                     'reveal architecture [path]',
                     'Architectural brief: entry points, core abstractions, risks'),
    'check':        _spec('check',
                     'reveal check <path>',
                     'Run quality rules on a file or directory',
                     ('text', 'json', 'grep'),  # also PATH --check (BACK-1644)
                     help_guide=_SUBCOMMANDS_GUIDE),
    'contracts':    _declared('contracts',
                     'reveal contracts [path]',
                     'Architectural seams: ABCs, Protocols/interfaces, TypedDicts, dataclasses'),
    'deps':         _declared('deps',
                     'reveal deps [path]',
                     'Dependency health: external packages, circular deps, unused imports'),
    'dev':          _spec('dev',
                     'reveal dev <command>',
                     'Scaffold adapters/analyzers/rules; inspect effective `.reveal.yaml` config',
                     help_guide=_SUBCOMMANDS_GUIDE),
    'health':       _spec('health',
                     'reveal health [path]',
                     'Unified health: code rules + SSL + databases + DNS',
                     ('text', 'json'), help_guide=_SUBCOMMANDS_GUIDE),
    'hotspots':     _declared('hotspots',
                     'reveal hotspots [path]',
                     'High-complexity files and functions that need attention'),
    'offline':      _spec('offline',
                     'reveal offline',
                     'Pre-download tree-sitter grammars for offline/air-gapped use'),
    'overview':     _declared('overview',
                     'reveal overview [path]',
                     'One-glance dashboard: languages, quality, hotspots, recent git'),
    'pack':         _declared('pack',
                     'reveal pack <path>',
                     'Token-budgeted context snapshot for LLM consumption',
                     help_guide=_SUBCOMMANDS_GUIDE),  # pack:// guide is a pointer stub
    'review':       _spec('review',
                     'reveal review <path>',
                     'Assess quality + structural changes before a PR merge',
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
                     'Test patch pressure joined with production boundary fan-out',
                     help_guide='guides/TESTABILITY_GUIDE.md'),
    'trace':        _declared('trace',
                     'reveal trace --from FUNC',
                     'Walk call graph from a named entry point; depth-indented narrative with side-effect classification'),
}


# Order of the `--help-all` subcommand listing: task entry points first, tooling last.
EPILOG_ORDER = ('overview', 'architecture', 'deps', 'hotspots', 'contracts', 'surface',
                'testability', 'trace', 'check', 'review', 'health', 'pack', 'dev',
                'scaffold', 'offline')


# What each exit code means for a command on the D6 outcome policy (EXIT_CODE_CONTRACT.md). The one
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
                 '--also-json artifact could not be written'},
    'review': {0: 'pass',
               1: 'findings (warnings, or a blocking high/critical issue, told apart by overall_status)',
               2: 'invalid target',
               3: 'incomplete (some files could not be checked or ranked; beats findings)'},
    'health': {0: 'all pass', 1: 'findings (warnings or failing checks)', 2: 'usage error (no target)',
               3: 'a check failed, could not reach its target (a missing local path included), '
                  'or was incomplete'},
    'deps': {1: 'circular dependencies or unused imports matched --fail-on findings (default: none)'},
    'hotspots': {1: 'file quality below 70 or function complexity above 20 matched '
                    '--fail-on findings (default: none)'},
}
# Commands whose findings gate is on unless --fail-on none says otherwise.
FINDINGS_BY_DEFAULT = ('check', 'review', 'health')

# Old spelling -> (replacement, D5 stage) for names the surface program retires. Empty: Phase 1 removes
# no names; help and error messages derive from it once a later phase adds entries.
RETIREMENTS: Dict[str, Tuple[str, str]] = {}


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
def invocation_scope(invocation: Invocation) -> Iterator[Invocation]:
    """Publish ``invocation`` for the code it runs, and restore the previous one on exit."""
    token = _CURRENT.set(invocation)
    try:
        yield invocation
    finally:
        _CURRENT.reset(token)
