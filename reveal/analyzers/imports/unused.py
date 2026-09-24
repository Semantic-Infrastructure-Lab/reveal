"""The one definition of "is this import unused?" (BACK-1066).

Both the I001 rule and the `imports://?unused` adapter answer this question. They
used to carry separate implementations that disagreed: the adapter called a
`from x import a, b, c` statement used if ANY name was (so it missed `b` and `c`),
knew only `# noqa`, and skipped `# type: ignore`; I001 judged each name (matching
Ruff F401) and understood Python/JS/Go/Rust suppression comments, but flagged a
used `import * as fs from 'fs'` as an unused `*`. Both now call this module.
"""

from typing import TYPE_CHECKING, FrozenSet, List, Set

if TYPE_CHECKING:  # types.py imports this module for ImportGraph.find_unused_imports
    from .types import ImportStatement

# Imports that bring names into scope without a bindable local name, so usage of
# the imported items never shows up as the import's own name (BACK-420), and JS
# imports that bind nothing at all: `import './x.css'`, bare `require('./x')`,
# and an `import('x')` expression, which is itself the use (BACK-1395).
UNJUDGED_IMPORT_TYPES = frozenset({
    'star_import', 'glob_use', 'dot_import',
    'side_effect_import', 'side_effect_require', 'dynamic_import',
})


def has_suppression_comment(source_line: str) -> bool:
    """True when the source line carries a suppression for unused imports.

    Python `# noqa` / `# noqa: F401` / `# noqa: I001`, JavaScript
    `// eslint-disable...unused`, Go `// nolint`, Rust `#[allow(unused...)]`.
    """
    if not source_line:
        return False

    line_lower = source_line.lower()

    if '# noqa' in line_lower:
        # Generic noqa (no colon) or specific F401/I001
        return ':' not in line_lower or 'f401' in line_lower or 'i001' in line_lower
    if '// eslint-disable' in line_lower and 'unused' in line_lower:
        return True
    if '// nolint' in line_lower and ('unused' in line_lower or ':' not in line_lower):
        return True
    if '#[allow' in line_lower and 'unused' in line_lower:
        return True
    return False


def should_skip_import(stmt: 'ImportStatement') -> bool:
    """True for imports that are never judged (and so never reported)."""
    return (
        stmt.import_type in UNJUDGED_IMPORT_TYPES
        or stmt.is_type_checking          # used only in type hints
        or stmt.skip_unused               # language lacks reliable symbol-usage semantics
        or has_suppression_comment(stmt.source_line)
        or stmt.file_path.name in ('__init__.py', '__init__.pyi')  # re-export pattern: imports are public API
    )


_PYTHON_SUFFIXES = ('.py', '.pyi')


def _is_explicit_reexport(stmt: 'ImportStatement', entry: str = '') -> bool:
    """PEP 484 redundant alias (`import X as X`, `from m import X as X`): the
    documented way to re-export a name from a module or stub, never unused."""
    if stmt.file_path.suffix not in _PYTHON_SUFFIXES:
        return False
    if entry:
        name, _, alias = entry.partition(' as ')
        return bool(alias) and name.strip() == alias.strip()
    return stmt.alias is not None and stmt.alias == stmt.module_name


def is_named_import(stmt: 'ImportStatement') -> bool:
    """`from X import a, b` shape: individual names are judged one by one.

    A namespace import (`import * as ns from 'm'`) also carries the placeholder
    `['*']` but binds one name, its alias, so it is judged as a whole.
    """
    return bool(stmt.imported_names) and stmt.import_type != 'namespace_import'


def bound_name(entry: str) -> str:
    """Local name an imported-name entry binds ('X as Y' -> 'Y')."""
    return entry.split(' as ')[-1].strip() if ' as ' in entry else entry


def unused_entries(stmt: 'ImportStatement', symbols_used: Set[str],
                   exports: FrozenSet[str] = frozenset()) -> List[str]:
    """The parts of `stmt` that are never referenced, as written in the source.

    `[]` means the import is used (or is not judged). For a named import each
    unused name is returned (`'X as Y'` entries verbatim); for `import X`,
    `import X as Y` and namespace imports the single bound name is returned.
    Names re-exported via `__all__` (`exports`) or a PEP 484 redundant alias
    count as used.
    """
    if should_skip_import(stmt) or _is_explicit_reexport(stmt):
        return []
    if any(alt in symbols_used for alt in stmt.alt_names):
        return []
    if is_named_import(stmt):
        return [name for name in stmt.imported_names
                if bound_name(name) not in symbols_used and bound_name(name) not in exports
                and not _is_explicit_reexport(stmt, name)]
    if stmt.import_type == 'namespace_import':
        name = stmt.alias or ''
    else:
        name = stmt.alias or stmt.module_name.split('.')[0]
    if name in symbols_used or name in exports:
        return []
    return [name or '*']
