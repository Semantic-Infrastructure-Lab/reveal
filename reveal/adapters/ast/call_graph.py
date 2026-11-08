"""Call-site name maps for the AST and calls adapters, and ast://'s cross-file ``resolved_calls``.

A function's raw ``calls`` list (bare names like ["validate_item", "db.insert"]) stays a
List[str]; ``resolved_calls`` adds, per call, the file its import names, read from the same
import analysis imports:// and calls' callee resolution use (BACK-2566: this module's own
per-file import resolver, ``build_symbol_map``, disagreed with the import graph and is gone).
"""

import ast
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...analyzers.imports.base import get_extractor
from ...analyzers.imports.bindings import Binding, ProjectBindings
from ...utils.path_utils import to_posix
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


def resolved_calls(calls: List[str], bindings: Dict[str, Binding]) -> List[Dict[str, Any]]:
    """A function's raw ``calls`` list with the file each call's qualifier or bare name is bound to,
    from the caller file's import bindings (``analyzers/imports/bindings.py``, the resolution
    imports:// does; BACK-2566). Every entry has ``name``; one whose import resolved to a project
    file adds ``resolved_file`` and ``resolved_name``::

        calls    = ["db.insert", "validate_item", "len"]
        bindings = {"db": Binding("lib/database.py", False), "validate_item": Binding("utils/v.py", False)}
        -> [{"name": "db.insert", "resolved_file": "lib/database.py", "resolved_name": "insert"},
            {"name": "validate_item", "resolved_file": "utils/v.py", "resolved_name": "validate_item"},
            {"name": "len"}]
    """
    result: List[Dict[str, Any]] = []
    for call in calls:
        entry: Dict[str, Any] = {'name': call}
        binding = bindings.get(call.split('.')[0])
        if binding is not None and binding.target:
            entry['resolved_file'] = to_posix(_spelled(binding.target))
            entry['resolved_name'] = call.split('.', 1)[1] if '.' in call else call
        result.append(entry)
    return result


def _spelled(target: str) -> str:
    """The target as the shortest path from the cwd, as the result's ``file`` is spelled
    ('../pkg/v.py' from inside pkg reads 'v.py'; an extractor's absolute path reads relative, so the
    JSON carries no home directory); absolute only where no relative path exists (another drive)."""
    try:
        return os.path.relpath(os.path.abspath(target))
    except ValueError:
        return target


def annotate_resolved_calls(elements: List[Dict[str, Any]], target: str) -> None:
    """Add ``resolved_calls`` to each function-like element with at least one call bound to a project
    file. The import analysis for ``target`` is built on the first element that has calls, and only
    inside a project (a package marker, a repository or ``.reveal.yaml`` above ``target``): a loose
    file's imports name no project to resolve in, and its directory (a Downloads folder, /tmp/x) can be
    any size; a 1 s query of one file took 73 s walking a shared temp directory."""
    from ...analyzers.imports.resolution import choose_scan_root
    if not any(elem.get('calls') for elem in elements) or choose_scan_root(Path(target)).inferred:
        return
    bindings = ProjectBindings(Path(target))
    for elem in elements:
        if elem.get('calls') and elem.get('file'):
            resolved = resolved_calls(elem['calls'], bindings.of(elem['file']))
            if any('resolved_file' in entry for entry in resolved):
                elem['resolved_calls'] = resolved
