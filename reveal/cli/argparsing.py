"""The one argument-parser class every reveal command line is parsed with (BACK-2705)."""

import argparse


class RevealArgumentParser(argparse.ArgumentParser):
    """A long option is spelled in full: argparse's unique-prefix expansion is off on every parser reveal builds (the
    main parser, each subcommand's, their subparsers, the global options parent, ``reveal-mcp``), so an abbreviation
    (``--lim``, ``--no-git``) is an unknown option with the same refusal as any other, never a second, undeclared
    spelling of a flag (COMMAND_MODEL "Spellings"). Subparsers made with ``add_subparsers`` inherit the class."""

    def __init__(self, *args, **kwargs):
        kwargs['allow_abbrev'] = False
        super().__init__(*args, **kwargs)
