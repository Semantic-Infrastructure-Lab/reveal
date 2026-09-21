"""Data model for surface:// rule tables: match kinds, provenance, and `Rule` (BACK-1360).

A leaf module. It depends only on `surface_facts`, so every rule-table module
(`surface_rules_subprocess`, `_fs`, `_env`, `_imports`, `_sockets`) can import it, and the
engine (`surface_rules`) can import them, without a cycle. Table modules must NOT import
`surface_rules`; `tests/test_surface_rules.py` enforces that.

See `surface_rules.py` for the semantics of each field, and
internal-docs/design/SURFACE_RULE_TABLE_ARCHITECTURE_2026-09-20.md.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Union

from .surface_facts import LANGUAGES

Names = Union[str, Tuple[str, ...]]


# ── match kinds ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Call:
    """A call site.

    `receiver`: None = any, '' = bare call only (not a call on another call's result), else
    exact match on the collapsed receiver path. `qualified` matches the full callee text with
    the receiver chain kept (`Runtime.getRuntime().exec`). `resolved` matches on the
    import-resolved path instead of the source spelling. `bare=False` rejects an unqualified
    `name(...)`, for extension functions that only make sense on a receiver.
    """
    name: Names = ()
    receiver: Optional[str] = None
    receiver_endswith: str = ''
    qualified: Optional[str] = None
    resolved: bool = False
    bare: Optional[bool] = None     # False = needs a receiver (a call on a call result counts)
    # True = the call must pass a string-literal argument; the first one is offered as `{key}`.
    # A call with none (`System.getenv()`, a variable key, an interpolated string) is no match.
    string_arg: bool = False


@dataclass(frozen=True)
class New:
    """A language-level constructor expression (`new Foo(..)`)."""
    type: Names = ()


@dataclass(frozen=True)
class Subshell:
    """Backticks / `%x(..)`."""


@dataclass(frozen=True)
class Import:
    """An import of `module` or anything beneath it (segment-aligned prefix).

    An entry containing `*` is a glob over the whole module text instead (`aws_sdk_*`,
    `aws-sdk-*`); `*` also crosses separators. Use it for families that share a name prefix
    but have no common segment: Rust crates (`aws_sdk_s3`), Ruby gems (`aws-sdk-s3`).
    """
    module: Names = ()


Match = Union[Call, New, Subshell, Import]


@dataclass(frozen=True)
class ImportedFrom:
    """Provenance: the file imports `module` (segment-aligned suffix of an import path)."""
    module: str


# Entry-name placeholders each match kind can fill.
_PLACEHOLDERS: Dict[type, Tuple[str, ...]] = {
    Call: ('path', 'receiver', 'name', 'key'),
    New: ('type',),
    Subshell: (),
    Import: ('module',),
}

CATEGORIES = ('cli', 'http', 'mcp', 'env', 'network', 'db', 'sdk', 'fs', 'subprocess')


@dataclass(frozen=True)
class Rule:
    category: str
    lang: str
    match: Match
    entry_name: str                       # `str.format` template, see _PLACEHOLDERS
    example: str                          # source that must produce an entry from THIS rule
    counter_examples: Tuple[str, ...] = ()  # lookalikes that must produce no entry at all
    requires: Optional[ImportedFrom] = None
    entry_type: str = ''                  # the entry's `type` field; '' = the category name
    entry_expr: str = ''                  # template for the entry's `expr` field; '' = no `expr`

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(f'unknown category {self.category!r}')
        if self.lang not in LANGUAGES:
            raise ValueError(f'unknown language {self.lang!r}')
        if not self.example.strip():
            raise ValueError(f'{self.category}/{self.lang}: a rule needs an example')
        fields = {f: 'x' for f in _PLACEHOLDERS[type(self.match)]}
        try:
            self.entry_name.format(**fields)
        except (KeyError, IndexError) as e:
            raise ValueError(f'entry_name {self.entry_name!r} uses {e} not offered by '
                             f'{type(self.match).__name__}') from None
        try:
            self.entry_expr.format(**fields)
        except (KeyError, IndexError) as e:
            raise ValueError(f'entry_expr {self.entry_expr!r} uses {e} not offered by '
                             f'{type(self.match).__name__}') from None
        if isinstance(self.match, Call) and not self.match.string_arg and (
                '{key}' in self.entry_name or '{key}' in self.entry_expr):
            raise ValueError('{key} needs Call(string_arg=True)')


def check_table(category: str, rules: Tuple[Rule, ...]) -> None:
    """A category's table may hold only that category's rules."""
    bad = [r for r in rules if r.category != category]
    if bad:
        raise ValueError(f'{category}: table holds rules for {sorted({r.category for r in bad})}')
