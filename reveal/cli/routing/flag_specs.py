"""Global CLI flags that reach a URI adapter as a query fragment (BACK-1376).

One table says how each flag becomes a fragment; an adapter opts in by declaring
`ResourceAdapter.CLI_QUERY_FLAGS = {flag: fragment}`. Before this, each flag had its own
`_inject_*` function with a hard-coded set of "aware" schemes, and every new flag repeated
the pattern (and the bug: a flag accepted by argparse and silently dropped).

Rules that apply to every flag here:
  - a flag and the URI giving one key different values is an invalid request naming both (exit 2); an equal
    value is one value, carried by the flag (COMMAND_MODEL "Conflicting values", BACK-2654);
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
from ..invocation import retirement_note
from .ledger import delegate, mark, peek


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
    control: bool = False                 # sets a request control: a declared noun that does not receive it
                                          # exits 2 naming its controls (rule 3, BACK-2654)
    # A declared noun (PARAM_SPECS) binds the flag from its own declarations, never from CLI_QUERY_FLAGS:
    # declarations -> (key, value); raises when the noun declares nothing to receive it (rule 4, note #17).
    declared_binding: Callable[[Any], tuple] | None = None


# The value functions `peek`: reading a flag here is not using it. inject_query_flags marks a
# flag once it is injected or noted, and the flag ledger (BACK-1514) reports the rest.
def _typed(dest: str) -> Callable[[Any], Any | None]:
    return lambda args: peek(args, dest) or None


def _switch(dest: str) -> Callable[[Any], bool | None]:
    return lambda args: True if peek(args, dest, False) else None


def _set(dest: str) -> Callable[[Any], Any | None]:
    # Unlike _typed, a falsy value counts: --limit 0 is a real request (no cap).
    return lambda args: peek(args, dest)


def _verbose_binding(declarations: Any) -> tuple:
    from ...utils.query_binding import verbose_binding
    return verbose_binding(declarations)


def _sort(args: Any) -> str | None:
    field = peek(args, 'sort')
    if not field:
        return None
    return f'-{field}' if peek(args, 'desc', False) and not field.startswith('-') else field


def _no_gitignore(args: Any) -> bool | None:
    # --respect-gitignore's argparse default is True, indistinguishable from typing it,
    # so only the True -> False transition (--no-gitignore) is a real signal.
    return False if peek(args, 'respect_gitignore', True) is False else None


# Order is the order fragments are appended to the query string.
FLAG_SPECS: tuple[FlagSpec, ...] = (
    FlagSpec('since', '--since', _typed('since'), warn_unsupported=True, already_scoped=('date>',), control=True),
    FlagSpec('until', '--until', _typed('until'), warn_unsupported=True, already_scoped=('date<',), control=True),
    FlagSpec('respect_gitignore', '--no-gitignore', _no_gitignore, warn_unsupported=True),
    # --all / --verbose: undeclared adapters honor them without a query fragment (nginx),
    # so a missing declaration is not evidence of a dropped flag.
    FlagSpec('all', '--all', _switch('all')),
    # --verbose is --detail full on a declared noun, or the noun's own legacy word verbose (rule 4, note #17).
    FlagSpec('verbose', '--verbose', _switch('verbose'), declared_binding=_verbose_binding),
    # metrics' global switches (BACK-2621): forwarded as declared fragments, not by matching get_structure's
    # parameter names; an adapter that declares neither reports them as unused flags.
    FlagSpec('hotspots', '--hotspots', _switch('hotspots')),
    FlagSpec('code_only', '--code-only', _switch('code_only')),
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


def _query_value(resource: str, key: str) -> str:
    return next((pair.partition('=')[2] for pair in resource.partition('?')[2].split('&')
                 if pair.partition('=')[0] == key), '')


def _same_value(adapter_class: Any, key: str, left: str, right: str) -> bool:
    """Two raw values of one key, compared as the noun reads them (``limit=05`` is ``--limit 5``)."""
    if left == right:
        return True
    from ...utils.query_binding import boolean_value
    spec = next((p for p in getattr(adapter_class, 'PARAM_SPECS', ()) if key in p.spellings), None)
    try:
        if spec is None:  # a walk-policy switch (respect_gitignore)
            return boolean_value(left) == boolean_value(right)
        return bool(spec.validate(spec.canonical_value(key, left)) == spec.validate(spec.canonical_value(key, right)))
    except ValueError:  # a value the noun rejects is rejected when it binds; as typed, these two differ
        return False


def _join_uri_value(args: Any, spec: Any, adapter_class: Any, resource: str, key: str, fragment: str) -> None:
    """The URI already sets *key*: the flag's equal value is the same request, carried by the flag; a different
    value is an invalid request naming both (BACK-2654; the URI used to win with a note, BACK-1685)."""
    uri_value = _query_value(resource, key)
    if _same_value(adapter_class, key, uri_value, fragment.partition('=')[2]):
        delegate(args, spec.dest, key)
        return
    mark(args, spec.dest)
    from ...errors import RequestValidationError
    raise RequestValidationError(f"{spec.option} conflicts with {key}={uri_value} in the URI: "
                                 f"{key} is set twice with different values; give it once")


def _join_flag_value(args: Any, spec: Any, adapter_class: Any, key: str, fragment: str,
                     earlier: tuple[str, str]) -> None:
    """Two global flags set one key: equal values are one request; different values are invalid."""
    option, earlier_fragment = earlier
    if _same_value(adapter_class, key, earlier_fragment.partition('=')[2], fragment.partition('=')[2]):
        delegate(args, spec.dest, key)
        return
    mark(args, spec.dest)
    from ...errors import RequestValidationError
    raise RequestValidationError(f"{spec.option} conflicts with {option}: both set {key} with different values; "
                                 "give one")


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


def _native_uncapped_value(adapter_class: Any, fragment: str, fallback: int) -> int:
    """Use the declared native zero policy instead of approximating an uncapped answer."""
    parameter = fragment.partition('=')[0]
    declaration = next((p for p in getattr(adapter_class, 'PARAM_SPECS', ())
                        if parameter in p.spellings), None)
    return 0 if declaration is not None and declaration.zero_policy == 'all' else fallback


def _reject_unreceived_control(adapter_class: Any, spec: FlagSpec) -> None:
    """An explicit control flag a declared noun does not receive (rule 3, BACK-2654): exit 2 with the binder's
    teaching (its supported controls), not a note."""
    declarations = getattr(adapter_class, 'PARAM_SPECS', None)
    if spec.control and declarations:
        from ...errors import RequestValidationError
        from ...utils.query_binding import unsupported_controls_message
        raise RequestValidationError(unsupported_controls_message(declarations, [spec.option]))


def _declared_fragment(args: Any, spec: FlagSpec, binding: Callable[[Any], tuple], declarations: Any,
                       scheme: str) -> str:
    """The fragment a declared noun's own declarations give *spec*, with its note (rule 4, BACK-2654 note #17): the
    noun's legacy word, under its ``param:`` row, or ``detail=full``, under the flag's own row."""
    try:
        key, value = binding(declarations)
    except ValueError:
        mark(args, spec.dest)
        raise
    retirement_note('flag:' + spec.option if key == 'detail' else f'param:{scheme}.{key}')
    return f"{key}={'true' if value is True else value}"


def _fragment_for(args: Any, spec: FlagSpec, adapter_class: Any, scheme: str, declared: Mapping) -> str | None:
    """The fragment *spec* reaches this adapter with: from a declared noun's own declarations when the flag binds
    that way (rule 4), else the adapter's CLI_QUERY_FLAGS declaration."""
    declarations = getattr(adapter_class, 'PARAM_SPECS', None)
    if spec.declared_binding is not None and declarations:
        return _declared_fragment(args, spec, spec.declared_binding, declarations, scheme)
    return declared.get(spec.dest)


def inject_query_flags(resource: str, scheme: str, args: Any) -> str:
    """Append the query fragment for every CLI flag in effect that this scheme's adapter
    declares; print a note for the flags it does not support (where the spec says to)."""
    from ...adapters.base import get_adapter_class
    adapter_class = get_adapter_class(scheme)
    declared = _declared(adapter_class)
    honors_result_control = getattr(adapter_class, 'HONORS_RESULT_CONTROL', True)
    injected: dict[str, tuple[str, str]] = {}  # query key -> (the flag that set it, its fragment)
    for spec in FLAG_SPECS:
        value = spec.value(args)
        if value is None:
            continue
        if spec.universal and not honors_result_control:
            mark(args, spec.dest)
            print(f"Note: {spec.option} has no effect on {scheme}:// -- it does not take "
                  f"sort=/limit=/offset=.", file=sys.stderr)
            continue
        fragment = _fragment_for(args, spec, adapter_class, scheme, declared)
        if fragment and spec.unbounded is not None and value == 0:
            value = _native_uncapped_value(adapter_class, fragment, spec.unbounded)
        fragment = fragment or spec.universal
        if fragment:
            fragment = fragment.replace('{value}', str(value))
            key = fragment.partition('=')[0]
            if key in injected:
                # --all and --limit both map to top= on hotspots/calls/testability: one key, two flags.
                _join_flag_value(args, spec, adapter_class, key, fragment, injected[key])
            elif any(token in resource for token in spec.already_scoped):
                mark(args, spec.dest)  # the caller scoped it in the URI (date>...)
            elif not _has_key(resource, key):
                resource = f"{resource}{'&' if '?' in resource else '?'}{fragment}"
                injected[key] = (spec.option, fragment)
                delegate(args, spec.dest, key)
            else:
                _join_uri_value(args, spec, adapter_class, resource, key, fragment)
        elif spec.warn_unsupported:
            _reject_unreceived_control(adapter_class, spec)
            mark(args, spec.dest)
            aware = ', '.join(f'{s}://' for s in _supporting_schemes(spec.dest))
            print(f"Note: {spec.option} has no effect on {scheme}:// -- only {aware} support it.",
                  file=sys.stderr)
    return resource
