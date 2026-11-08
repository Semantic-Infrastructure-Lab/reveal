"""Call-site name maps for the AST and calls adapters: import aliases and class-attribute aliases.

Where a call lands across files is calls://'s answer (``?callees=FILE:NAME&depth=2``), from the
import analysis imports:// builds. ast:// no longer annotates it (``resolved_calls``, retired by
Scott 2026-11-08, BACK-2566): this module's per-file import resolver, ``build_symbol_map``,
disagreed with the import graph, and the correct answer costs the project's import analysis,
which a rung-1/2 query should not pay.
"""

import ast
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ...analyzers.imports.base import get_extractor
from ...utils.pyparse import parse_python


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
