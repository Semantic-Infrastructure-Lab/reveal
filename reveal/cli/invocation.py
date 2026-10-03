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

    def load(self) -> Tuple[ArgumentParser, Callable[[Namespace], None]]:
        mod = importlib.import_module(self.module)
        return getattr(mod, self.parser_factory)(), getattr(mod, self.runner)


def _spec(name: str, formats: Optional[Tuple[str, ...]] = None) -> CommandSpec:
    return CommandSpec(f'reveal.cli.commands.{name}', f'create_{name}_parser', f'run_{name}', formats)


# Every subcommand. help://schemas/<name> also reads this table to tell a CLI-only command
# from an unknown name (BACK-1028). health and review have no same-named adapter, and their
# runners render only these formats (measured: grep/typed output matched text byte for byte).
COMMANDS: Dict[str, CommandSpec] = {
    'architecture': _spec('architecture'),
    'check':        _spec('check', ('text', 'json', 'grep')),  # also PATH --check (BACK-1644)
    'contracts':    _spec('contracts'),
    'deps':         _spec('deps'),
    'dev':          _spec('dev'),
    'health':       _spec('health', ('text', 'json')),
    'hotspots':     _spec('hotspots'),
    'offline':      _spec('offline'),
    'overview':     _spec('overview'),
    'pack':         _spec('pack'),
    'review':       _spec('review', ('text', 'json')),
    'scaffold':     _spec('scaffold'),
    'surface':      _spec('surface'),
    'testability':  _spec('testability'),
    'trace':        _spec('trace'),
}


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
