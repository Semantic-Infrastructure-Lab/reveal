"""Default CLI argument namespace for internal routing (MCP server and test helpers).

The defaults ARE the parser's defaults: they are read off ``create_argument_parser`` once,
so a flag added to the parser is present here with its real default and cannot drift.
A hand-kept copy had lost 36 dests and disagreed on ``depth`` (BACK-1362).
"""

from __future__ import annotations

import copy
from argparse import Namespace
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


def _default_args(**overrides) -> Namespace:
    """Return a Namespace with all reveal CLI defaults for internal routing functions."""
    defaults = copy.deepcopy(_parser_defaults())
    defaults.update(overrides)
    return Namespace(**defaults)
