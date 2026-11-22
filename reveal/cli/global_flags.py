"""Post-parse hook for global flags that set process-wide state (BACK-1378).

Reveal has two CLI forms (subcommands and the path/URI form) plus the MCP server. A global
flag applied in only one of them is silently dropped in the others; --provenance was exactly
that (BACK-1034, fixed by copying the call). main._dispatch_and_run calls this once for both
CLI forms (BACK-1058), and the MCP server calls it per request.

--copy is not here: it must wrap the whole run (tee stdout, copy on exit), so
main._dispatch_and_run applies it around the run, from the parsed args.
"""

from __future__ import annotations

from argparse import ArgumentTypeError, Namespace
from typing import Any, Dict

from ..utils.gitignore import set_gitignore_enabled
from ..utils.invocation_log import answer_is_json
from ..utils.json_utils import set_provenance_enabled
from ..utils.query_binding import ScalarOnceAction, switch_value
from .invocation import SWITCHES, retirement_note


# Flags in effect for every command once parsed: applied by apply_global_flags below, or, for
# --copy, around the whole run. The flag ledger (BACK-1514) never reports them as unused.
# --respect-gitignore is applied here too but is not one of them: it is a walk policy, judged
# like --exclude by whether the answer read it (BACK-2721).
PROCESS_GLOBAL_FLAGS = frozenset({'provenance', 'copy'})


def add_gitignore_arguments(parser: Any) -> None:
    """--respect-gitignore on|off (legacy --no-gitignore), for every parser whose command walks a tree.

    One declaration (the respect-gitignore switch) so the spelling, default and help cannot drift between the
    main parser and the subcommands; apply_global_flags() is what honors it.
    """
    add_switch_argument(parser, 'respect-gitignore')


def _on_off(value: str) -> str:
    """argparse ``type`` of a switch: the word as typed, checked by the shared on/off codec."""
    try:
        switch_value(value)
    except ValueError:
        raise ArgumentTypeError(f'expected on or off, got {value!r}') from None
    return value


class _SwitchAction(ScalarOnceAction):
    """One spelling of a switch: ``--NAME on|off`` records the word typed, ``--no-NAME`` and a short spelling record
    ``off``. The spellings of one switch share one conflict box, so different values exit 2 naming both and equal ones
    are one (COMMAND_MODEL "Conflicting values"); the namespace gets the codec's boolean."""

    def __call__(self, parser, namespace, values, option_string=None):
        typed = 'off' if self.nargs == 0 else values
        self._store(namespace, typed, option_string)
        setattr(namespace, self.dest, switch_value(typed))
        if self.nargs == 0 and option_string.startswith('--'):  # the legacy off flag; a short spelling has no row
            retirement_note('flag:' + option_string)


def add_switch_argument(parser: Any, name: str) -> None:
    """``--NAME on|off``, its legacy off flag (``--no-NAME`` or the one declared) and any short spelling of off, from
    ``SWITCHES[name]``: three arguments sharing one conflict box. The short spelling is the same word as off, not the
    legacy flag, so it has an argument of its own: a declared noun's help hides the legacy flag alone (BACK-2755)."""
    switch = SWITCHES[name]
    shared: Dict[str, Any] = {'dest': switch.dest, 'default': switch.default, 'action': _SwitchAction,
                              'comparable': switch_value, 'seen': {}}
    bare: Dict[str, Any] = {'nargs': '?', 'const': 'on'} if switch.bare_on else {}
    parser.add_argument('--' + name, type=_on_off, metavar='on|off', help=switch.help, **bare, **shared)
    parser.add_argument(switch.legacy_flag, nargs=0, **shared,
                        help=f'Same as --{name} off ({switch.legacy_flag} is deprecated)')
    if switch.short_off:
        parser.add_argument(*switch.short_off, nargs=0, **shared, help=f'Same as --{name} off')


_EXCLUDE_HELP = ('Exclude files/directories matching pattern from analysis entirely '
                 '(e.g., --exclude "*.min.js" --exclude "vendor/"). Repeatable. .gitignore '
                 'syntax, relative to the analysed path: a bare name matches at any depth; '
                 'REVEAL_IGNORE patterns are added to them.')


def add_exclude_argument(parser: Any, help: str = _EXCLUDE_HELP) -> None:
    """--exclude, for every parser whose command walks a tree (BACK-1517).

    One declaration so the spelling and action cannot drift. What honors it is the walk
    scope each dispatch publishes (``utils.exclusions.dispatch_scope``): handle_uri for
    URIs, ``cli/routing/subcommand.py`` for subcommands. A command that accepts it and
    never walks gets a flag-ledger note, not silence.
    """
    parser.add_argument('--exclude', action='append', metavar='PATTERN', help=help)


def rule_patterns(value: str) -> str:
    """argparse ``type`` for every --select/--ignore: an unknown rule code is a usage error.

    Without it a typo selected no rules and the run reported a clean result (BACK-1605).
    Returns the value normalized (spaces and empty items dropped), still comma-joined,
    so every consumer's ``.split(',')`` keeps working.
    """
    from ..rules import parse_rule_patterns
    try:
        return ','.join(parse_rule_patterns(value))
    except ValueError as e:
        raise ArgumentTypeError(str(e)) from None


def apply_global_flags(args: Namespace) -> None:
    """Apply flags whose effect is process-global state, from a parsed ``args``."""
    set_provenance_enabled(bool(getattr(args, 'provenance', False)))
    # A JSON answer carries the invocation's warnings and per-file diagnostics itself; any other
    # prints them on stderr (the CLI and MCP's reveal_query both pass here).
    answer_is_json(getattr(args, 'format', None) == 'json')
    # BACK-1386: --no-gitignore reaches every walker, not only the three
    # adapters that used to declare it.
    set_gitignore_enabled(getattr(args, 'respect_gitignore', True) is not False)
