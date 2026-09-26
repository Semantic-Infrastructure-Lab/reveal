"""Global CLI flags that reach a URI adapter as a query fragment (BACK-1376).

One table says how each flag becomes a fragment; an adapter opts in by declaring
`ResourceAdapter.CLI_QUERY_FLAGS = {flag: fragment}`. Before this, each flag had its own
`_inject_*` function with a hard-coded set of "aware" schemes, and every new flag repeated
the pattern (and the bug: a flag accepted by argparse and silently dropped).

Rules that apply to every flag here:
  - a value already in the URI wins over the CLI flag (exact key match, not substring);
  - an adapter that does not declare the flag is left alone -- and, for flags whose
    absence means "ignored" (`warn_unsupported`), the user is told which schemes do.

Not covered here, on purpose: --exclude's walk-scope side channel plus REVEAL_IGNORE, which
is not "declare a fragment" shaped. --exclude's
query *format* for the adapters that read ?exclude= lives here, in `exclude_fragment`, so the
`overview` subcommand and the URI form cannot drift apart.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from ...utils.query_parser import join_exclude_patterns


@dataclass(frozen=True)
class FlagSpec:
    dest: str                             # argparse dest; key in CLI_QUERY_FLAGS
    option: str                           # spelling shown in the "no effect" note
    value: Callable[[Any], Any | None]    # args -> value to inject; None = flag not set
    warn_unsupported: bool = False        # note when the adapter declares no support
    already_scoped: tuple[str, ...] = ()  # raw URI substrings meaning "caller scoped it"
    universal: str | None = None          # fragment for every adapter with HONORS_RESULT_CONTROL
                                          # (sort=/limit=; applied by a few, warned about by the rest)
    unbounded: int | None = None          # value a declared fragment gets for a 0 ("no cap"): an
                                          # adapter's own `top=0` may mean "nothing" (hotspots)


def _typed(dest: str) -> Callable[[Any], Any | None]:
    return lambda args: getattr(args, dest, None) or None


def _switch(dest: str) -> Callable[[Any], bool | None]:
    return lambda args: True if getattr(args, dest, False) else None


def _set(dest: str) -> Callable[[Any], Any | None]:
    # Unlike _typed, a falsy value counts: --limit 0 is a real request (no cap).
    return lambda args: getattr(args, dest, None)


def _sort(args: Any) -> str | None:
    field = getattr(args, 'sort', None)
    if not field:
        return None
    return f'-{field}' if getattr(args, 'desc', False) and not field.startswith('-') else field


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
    # Result-control keys, injected without a per-adapter declaration. Only ast/markdown/json/
    # git/stats apply them; most other adapters warn "Unknown query param" and ignore them, and
    # those that cannot receive a query key at all set HONORS_RESULT_CONTROL = False and get the
    # "no effect" note instead (BACK-1385).
    # --limit's argparse default is None ('typed or not'); `check` applies its own cap of 50.
    # An adapter that declares its own native cap in CLI_QUERY_FLAGS (hotspots/calls/depends/
    # testability `top={value}`) gets that instead of the universal key (BACK-1496).
    FlagSpec('sort', '--sort', _sort, universal='sort={value}'),
    FlagSpec('limit', '--limit', _set('limit'), universal='limit={value}', unbounded=1_000_000),
)


def exclude_fragment(patterns: Any) -> str:
    """The `exclude=` query fragment for overview://, stats:// and pack:// ('' if none).

    Patterns are comma-joined; ',', '&', '=' and '%' inside a pattern are percent-escaped
    (BACK-1380) and the adapters decode with `split_exclude_param`.
    """
    return f"exclude={join_exclude_patterns(patterns)}" if patterns else ''


def _has_key(resource: str, key: str) -> bool:
    return any(pair.partition('=')[0] == key for pair in resource.partition('?')[2].split('&'))


def _declared(adapter_class: Any) -> Mapping:
    declared = getattr(adapter_class, 'CLI_QUERY_FLAGS', None)
    return declared if isinstance(declared, Mapping) else {}


def _supporting_schemes(dest: str) -> list:
    from ...adapters.base import get_adapter_class, list_supported_schemes
    return sorted(s for s in list_supported_schemes() if dest in _declared(get_adapter_class(s)))


RESULT_CONTROL_KEYS = frozenset({'sort', 'limit', 'offset'})


def strip_result_control_keys(resource: str, adapter_class: Any) -> tuple[str, list]:
    """Remove typed `sort=`/`limit=`/`offset=` from the query of an adapter that cannot receive
    them (HONORS_RESULT_CONTROL = False); return the new resource and the removed keys (BACK-1385)."""
    if getattr(adapter_class, 'HONORS_RESULT_CONTROL', True) or '?' not in resource:
        return resource, []
    base, _, query = resource.partition('?')
    kept: list[str] = []
    removed: list[str] = []
    for pair in query.split('&'):
        key = pair.partition('=')[0]
        if key in RESULT_CONTROL_KEYS:
            removed.append(key)
        else:
            kept.append(pair)
    if not removed:
        return resource, []
    return (f"{base}?{'&'.join(kept)}" if kept else base), removed


def inject_query_flags(resource: str, scheme: str, args: Any) -> str:
    """Append the query fragment for every CLI flag in effect that this scheme's adapter
    declares; print a note for the flags it does not support (where the spec says to)."""
    from ...adapters.base import get_adapter_class
    adapter_class = get_adapter_class(scheme)
    declared = _declared(adapter_class)
    honors_result_control = getattr(adapter_class, 'HONORS_RESULT_CONTROL', True)
    for spec in FLAG_SPECS:
        value = spec.value(args)
        if value is None:
            continue
        if spec.universal and not honors_result_control:
            print(f"Note: {spec.option} has no effect on {scheme}:// -- it does not take "
                  f"sort=/limit=/offset=.", file=sys.stderr)
            continue
        fragment = declared.get(spec.dest)
        if fragment and spec.unbounded is not None and value == 0:
            value = spec.unbounded
        fragment = fragment or spec.universal
        if fragment:
            fragment = fragment.replace('{value}', str(value))
            if not _has_key(resource, fragment.partition('=')[0]) and not any(
                    token in resource for token in spec.already_scoped):
                resource = f"{resource}{'&' if '?' in resource else '?'}{fragment}"
        elif spec.warn_unsupported:
            aware = ', '.join(f'{s}://' for s in _supporting_schemes(spec.dest))
            print(f"Note: {spec.option} has no effect on {scheme}:// -- only {aware} support it.",
                  file=sys.stderr)
    return resource
