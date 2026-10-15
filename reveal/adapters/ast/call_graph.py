"""Cross-file call graph resolution for the AST adapter (Phase 3).

Given a function's raw `calls` list (bare names like ["validate_item", "db.insert"]),
and the import map for the file, resolves entries to their source files where possible.

Keeps `calls` as List[str] (backward-compat) and adds `resolved_calls` as List[Dict]
with optional `resolved_file` + `resolved_name` keys.
"""

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...analyzers.imports.base import get_extractor
from ...utils.pyparse import parse_python


def build_symbol_map(file_path: str) -> Dict[str, Optional[str]]:
    """Build a symbol → resolved-file-path map from a file's imports.

    Uses the language extractor registry so only languages with a registered
    extractor (Python, JS, Go, Rust) participate in resolution.  An empty map
    for unsupported languages or an unreadable file; an extractor bug propagates,
    as it does in imports:// (BACK-1614).

    Args:
        file_path: Absolute or relative path to the source file.

    Returns:
        Dict mapping each imported symbol (or module alias) to its resolved
        absolute file path, or None when the import target could not be found
        on disk (e.g. stdlib or third-party package).
    """
    path = Path(file_path)
    extractor = get_extractor(path)
    if not extractor:
        return {}

    try:
        imports = extractor.extract_imports(path)
    except OSError:
        return {}

    base_path = path.parent
    symbol_map: Dict[str, Optional[str]] = {}

    for stmt in imports:
        try:
            resolved = extractor.resolve_import(stmt, base_path)
        except (OSError, ValueError):  # a target path that can't be stat'd or made relative
            resolved = None

        resolved_str = str(resolved) if resolved else None

        if stmt.imported_names:
            # from X import Y, Z  or  from X import Y as alias
            for name_spec in stmt.imported_names:
                effective = _strip_alias(name_spec)
                symbol_map[effective] = resolved_str
        elif stmt.alias:
            # import X as alias
            symbol_map[stmt.alias] = resolved_str
        else:
            # import X  →  map the top-level name
            top = stmt.module_name.split('.')[0] if stmt.module_name else ''
            if top:
                symbol_map[top] = resolved_str

    return symbol_map


def _strip_alias(name_spec: str) -> str:
    """Return effective name from 'X as Y' → 'Y', or name as-is."""
    if ' as ' in name_spec:
        _, alias = name_spec.split(' as ', 1)
        return alias.strip()
    return name_spec.strip()


def build_alias_map(file_path: str) -> Dict[str, str]:
    """Map imported aliases to their canonical (original) names for a single file.

    For ``from utils import helper as h`` → ``{'h': 'helper'}``.
    For ``import numpy as np`` → ``{'np': 'numpy'}``.

    Only entries WITH an explicit alias are included.  Unaliased imports
    (``from utils import helper``) are omitted because the call name and
    the definition name are already identical.

    Args:
        file_path: Absolute or relative path to the source file.

    Returns:
        Dict mapping alias → original_name.  Empty dict for an unsupported
        language or an unreadable file.
    """
    path = Path(file_path)
    try:
        extractor = get_extractor(path)
        if not extractor:
            return {}
        imports = extractor.extract_imports(path)
    except OSError:
        return {}

    alias_map: Dict[str, str] = {}
    for stmt in imports:
        if stmt.imported_names:
            # from X import Y as Z  →  Z (alias) → Y (original)
            for name_spec in stmt.imported_names:
                if ' as ' in name_spec:
                    original, alias = name_spec.split(' as ', 1)
                    alias_map[alias.strip()] = original.strip()
        elif stmt.alias and stmt.module_name:
            # import X as alias  →  alias → top-level module name
            top = stmt.module_name.split('.')[0]
            if stmt.alias != top:
                alias_map[stmt.alias] = top
    return alias_map


ClassAliasSpan = Tuple[int, int, Dict[str, str]]


def build_class_attribute_aliases(file_path: str, alias_map: Dict[str, str]) -> List[ClassAliasSpan]:
    """Python class bodies that rebind an import alias as a class attribute (BACK-1846).

    After ``from m import Timer as Schedule``, ``class T: Schedule = Schedule`` makes
    ``self.Schedule()`` inside ``T`` a call of ``Timer``.  An alias otherwise renames bare
    calls only (BACK-1833), so this is the one dotted form it reaches.

    Returns ``(first_line, last_line, {attribute: canonical})`` per class; classes without a
    binding are kept (empty dict) so a nested class shadows its outer class's bindings.
    Empty when no class binds an alias, for non-Python files, an empty *alias_map*, or an
    unparsable file.
    """
    if not alias_map or Path(file_path).suffix not in ('.py', '.pyi'):
        return []
    try:
        tree = parse_python(Path(file_path).read_text(encoding='utf-8'), file_path)
    except (OSError, ValueError, SyntaxError):
        return []
    spans: List[ClassAliasSpan] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bindings: Dict[str, str] = {}
        for stmt in node.body:
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target] if isinstance(stmt, ast.AnnAssign) else []
            value = getattr(stmt, 'value', None)
            if isinstance(value, ast.Name) and value.id in alias_map:
                bindings.update({t.id: alias_map[value.id] for t in targets if isinstance(t, ast.Name)})
        spans.append((node.lineno, node.end_lineno or node.lineno, bindings))
    return spans if any(span[2] for span in spans) else []


def class_attribute_alias(callee: str, line: int, spans: List[ClassAliasSpan]) -> Optional[str]:
    """Canonical name for ``self.X``/``cls.X`` at *line* when the innermost enclosing class binds X."""
    receiver, _, attribute = callee.partition('.')
    if receiver not in ('self', 'cls') or not attribute or '.' in attribute:
        return None
    enclosing = [span for span in spans if span[0] <= line <= span[1]]
    if not enclosing:
        return None
    innermost = max(enclosing, key=lambda span: span[0])
    return innermost[2].get(attribute)


def resolve_callees(
    calls: List[str],
    symbol_map: Dict[str, Optional[str]],
) -> List[Dict[str, Any]]:
    """Enrich a raw `calls` list with source-file metadata where resolvable.

    For each call entry, checks whether the base name (left of the first dot)
    appears in `symbol_map`.  If it does, adds `resolved_file` and
    `resolved_name` to the entry dict.

    Args:
        calls: List of bare call strings, e.g. ["validate_item", "db.insert"].
        symbol_map: Symbol → resolved-path map from `build_symbol_map`.

    Returns:
        List of dicts.  Every entry has at minimum ``{"name": <original>}``.
        Resolved entries additionally carry ``resolved_file`` and
        ``resolved_name``.

    Example::

        calls      = ["db.insert", "validate_item", "len"]
        symbol_map = {"db": "/lib/database.py", "validate_item": "/utils/v.py"}

        result = [
            {"name": "db.insert",      "resolved_file": "/lib/database.py", "resolved_name": "insert"},
            {"name": "validate_item",  "resolved_file": "/utils/v.py",      "resolved_name": "validate_item"},
            {"name": "len"},
        ]
    """
    result: List[Dict[str, Any]] = []
    for call in calls:
        entry: Dict[str, Any] = {'name': call}
        local_name = call.split('.')[0]
        resolved_file = symbol_map.get(local_name)
        if resolved_file:
            entry['resolved_file'] = resolved_file
            entry['resolved_name'] = call.split('.', 1)[1] if '.' in call else call
        result.append(entry)
    return result
