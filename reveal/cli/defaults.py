"""Default CLI argument namespace for internal routing (MCP server and test helpers).

The defaults ARE the parser's defaults: they are read off ``create_argument_parser`` once,
so a flag added to the parser is present here with its real default and cannot drift.
A hand-kept copy had lost 36 dests and disagreed on ``depth`` (BACK-1362).
"""

from __future__ import annotations

import copy
from argparse import ArgumentParser, Namespace
from functools import lru_cache

# Dests read by `pack` internals that no main-parser flag defines (the pack subcommand
# owns them). Kept here so pack routed through _default_args still has them.
_PACK_EXTRAS: dict = {'content': False, 'focus': None, 'budget': '2000'}


@lru_cache(maxsize=1)
def _parser_defaults() -> dict:
    from .parser import create_argument_parser

    # full_help=False: don't let a stray --help-all in sys.argv change what is built.
    parser = create_argument_parser('0', full_help=False)
    return {**_PACK_EXTRAS, **vars(parser.parse_args([]))}


@lru_cache(maxsize=1)
def _option_names() -> dict:
    """dest -> the flag's spelling (``max_items`` -> ``--max-items``), for messages."""
    from .parser import create_argument_parser

    return option_names_of(create_argument_parser('0', full_help=False))


def option_names_of(parser: ArgumentParser) -> dict:
    """dest -> the long spelling of each option ``parser`` defines."""
    names: dict = {}
    for action in parser._actions:
        long_options = [o for o in action.option_strings if o.startswith('--')]
        if long_options and action.dest not in names:
            names[action.dest] = long_options[0]
    return names


def option_defaults_of(parser: ArgumentParser) -> dict:
    """dest -> default of each option ``parser`` defines (positionals are not flags).

    For a subcommand's own parser, where ``parse_args([])`` may fail on a required
    argument (``reveal trace --from``).
    """
    return {action.dest: action.default for action in parser._actions
            if action.option_strings and action.dest != 'help'}


def _default_args(**overrides) -> Namespace:
    """Return a Namespace with all reveal CLI defaults for internal routing functions."""
    from .parser import _format_default

    defaults = copy.deepcopy(_parser_defaults())
    # `format` defaults from REVEAL_FORMAT (BACK-1362), which the cache above would
    # freeze at its first call: one caller that ran with REVEAL_FORMAT=json made every
    # later call in the process emit JSON (MCP tools, handle_uri). Read it per call.
    defaults['format'] = _format_default()
    defaults.update(overrides)
    return Namespace(**defaults)
