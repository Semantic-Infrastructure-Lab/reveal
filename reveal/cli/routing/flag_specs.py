"""Global CLI flags that reach a URI adapter as a query fragment (BACK-1376).

One table says how each flag becomes a fragment; an adapter opts in by declaring
`ResourceAdapter.CLI_QUERY_FLAGS = {flag: fragment}`. Before this, each flag had its own
`_inject_*` function with a hard-coded set of "aware" schemes, and every new flag repeated
the pattern (and the bug: a flag accepted by argparse and silently dropped).

Rules that apply to every flag here:
  - a value already in the URI wins over the CLI flag (exact key match, not substring);
  - an adapter that does not declare the flag is left alone -- and, for flags whose
    absence means "ignored" (`warn_unsupported`), the user is told which schemes do.

Not covered here, on purpose: --exclude's walk-scope side channel plus REVEAL_IGNORE,
--sort and --limit (see handle_uri); they are not "declare a fragment" shaped. --exclude's
query *format* for the adapters that read ?exclude= lives here, in `exclude_fragment`, so the
`overview` subcommand and the URI form cannot drift apart.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FlagSpec:
    dest: str                             # argparse dest; key in CLI_QUERY_FLAGS
    option: str                           # spelling shown in the "no effect" note
    value: Callable[[Any], Any | None]    # args -> value to inject; None = flag not set
    warn_unsupported: bool = False        # note when the adapter declares no support
    already_scoped: tuple[str, ...] = ()  # raw URI substrings meaning "caller scoped it"


def _typed(dest: str) -> Callable[[Any], Any | None]:
    return lambda args: getattr(args, dest, None) or None


def _switch(dest: str) -> Callable[[Any], bool | None]:
    return lambda args: True if getattr(args, dest, False) else None


def _no_gitignore(args: Any) -> bool | None:
    # --respect-gitignore's argparse default is True, indistinguishable from typing it,
    # so only the True -> False transition (--no-gitignore) is a real signal.
    return False if getattr(args, 'respect_gitignore', True) is False else None


# Order is the order fragments are appended to the query string.
FLAG_SPECS: tuple[FlagSpec, ...] = (
    FlagSpec('since', '--since', _typed('since'), warn_unsupported=True, already_scoped=('date>',)),
    FlagSpec('until', '--until', _typed('until'), warn_unsupported=True, already_scoped=('date<',)),
    FlagSpec('respect_gitignore', '--no-gitignore', _no_gitignore, warn_unsupported=True),
    # --all / --verbose: many adapters honor them without a query fragment (claude,
    # nginx, overview), so a missing declaration is not evidence of a dropped flag.
    FlagSpec('all', '--all', _switch('all')),
    FlagSpec('verbose', '--verbose', _switch('verbose')),
)


def exclude_fragment(patterns: Any) -> str:
    """The `exclude=` query fragment for overview://, stats:// and pack:// ('' if none).

    Patterns are comma-joined and the adapters split on ',' with no decoding, so a pattern
    that itself contains ',' (or '&'/'=') is not representable and is silently split.
    """
    return f"exclude={','.join(patterns)}" if patterns else ''


def _has_key(resource: str, key: str) -> bool:
    return any(pair.partition('=')[0] == key for pair in resource.partition('?')[2].split('&'))


def _declared(adapter_class: Any) -> Mapping:
    declared = getattr(adapter_class, 'CLI_QUERY_FLAGS', None)
    return declared if isinstance(declared, Mapping) else {}


def _supporting_schemes(dest: str) -> list:
    from ...adapters.base import get_adapter_class, list_supported_schemes
    return sorted(s for s in list_supported_schemes() if dest in _declared(get_adapter_class(s)))


def inject_query_flags(resource: str, scheme: str, args: Any) -> str:
    """Append the query fragment for every CLI flag in effect that this scheme's adapter
    declares; print a note for the flags it does not support (where the spec says to)."""
    from ...adapters.base import get_adapter_class
    declared = _declared(get_adapter_class(scheme))
    for spec in FLAG_SPECS:
        value = spec.value(args)
        if value is None:
            continue
        fragment = declared.get(spec.dest)
        if fragment:
            fragment = fragment.replace('{value}', str(value))
            if not _has_key(resource, fragment.partition('=')[0]) and not any(
                    token in resource for token in spec.already_scoped):
                resource = f"{resource}{'&' if '?' in resource else '?'}{fragment}"
        elif spec.warn_unsupported:
            aware = '/'.join(f'{s}://' for s in _supporting_schemes(spec.dest))
            print(f"Note: {spec.option} has no effect on {scheme}:// -- only {aware} support it.",
                  file=sys.stderr)
    return resource
