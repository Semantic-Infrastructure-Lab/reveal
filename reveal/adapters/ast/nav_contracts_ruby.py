"""Ruby contracts scanner — the mixin model (BACK-403 pt 2).

Ruby has no interface keyword, so it doesn't share `contracts.py`'s
`_scan_contracts_ts` classifier (TS/Java/C#/PHP/Swift/Kotlin all emit an
`interfaces`/`is_abstract`-shaped element set via `collect_structures`).
Ruby's native contract-like construct is the **mixin**: a `module` defining
shared behavior, pulled into a class via `include` (instance methods) or
`extend` (class methods). `collect_structures` never extracts `module`
nodes as elements at all (the shared node-type table only uses `'module'`
for hierarchical method nesting, not element extraction) and has no concept
of include/extend, so this walks Ruby's grammar directly instead — same
shape as `nav_surface_ruby.py`.

- **Contracts**: every `module Name ... end` declaration.
- **Implementations**: every `class Name [< Superclass] ... end` whose body
  contains a *direct* (not nested inside a method) `include`/`extend` call.
  Superclass and included/extended module names are both collected into one
  `bases`-shaped list per class, matched against contract names by
  `contracts.py`'s existing `_add_implementations` tail-matching — mirroring
  how it already treats "bases" as the full inheritance-relationship set.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from .nav_surface_common import _get_text, _get_line

from reveal.core import node_children as _children
from reveal.core import tree_root, ts_parse


def scan_file_contracts_ruby(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse one Ruby file and return {'modules': [...], 'classes': [...]}."""
    try:
        from tree_sitter_language_pack import get_parser
        source = Path(file_path).read_text(errors='replace')
        parser = get_parser('ruby')
        tree = ts_parse(parser, source)
    except Exception:
        return {'modules': [], 'classes': []}

    content_bytes = source.encode('utf-8')
    modules: List[Dict[str, Any]] = []
    classes: List[Dict[str, Any]] = []

    stack = [tree_root(tree)]
    while stack:
        node = stack.pop()
        kind = node.kind()
        if kind == 'module':
            _process_module(node, file_path, content_bytes, modules)
        elif kind == 'class':
            _process_class(node, file_path, content_bytes, classes)
        for ch in reversed(_children(node)):
            stack.append(ch)

    return {'modules': modules, 'classes': classes}


def _tail(name: str) -> str:
    """Last segment of a Ruby namespaced constant, e.g. 'A::B::C' -> 'C'."""
    return name.split('::')[-1]


def _const_text(node: Any, content_bytes: bytes) -> Optional[str]:
    """Text of a `constant` or `scope_resolution` node, tail-normalized."""
    if node.kind() in ('constant', 'scope_resolution'):
        return _tail(_get_text(node, content_bytes))
    return None


def _declared_name(node: Any, content_bytes: bytes) -> Optional[str]:
    """First `constant`/`scope_resolution` direct child — the module/class name."""
    for ch in _children(node):
        name = _const_text(ch, content_bytes)
        if name is not None:
            return name
    return None


def _process_module(node: Any, file_path: str, content_bytes: bytes,
                     modules: List[Dict[str, Any]]) -> None:
    name = _declared_name(node, content_bytes)
    if name is None:
        return
    modules.append({
        'name': name,
        'file': file_path,
        'line': _get_line(node),
        'bases': [],
        'decorators': [],
        'abstract_methods': [],
        'implementations': [],
        'category': 'modules',
        'is_abstract': False,
    })


def _superclass_name(node: Any, content_bytes: bytes) -> Optional[str]:
    for ch in _children(node):
        if ch.kind() != 'superclass':
            continue
        for inner in _children(ch):
            name = _const_text(inner, content_bytes)
            if name is not None:
                return name
    return None


def _mixin_names(node: Any, content_bytes: bytes) -> List[str]:
    """Modules pulled in via a direct `include`/`extend` call in the class body."""
    names: List[str] = []
    for ch in _children(node):
        if ch.kind() != 'body_statement':
            continue
        for stmt in _children(ch):
            if stmt.kind() != 'call':
                continue
            stmt_children = _children(stmt)
            ident = next((c for c in stmt_children if c.kind() == 'identifier'), None)
            if ident is None or _get_text(ident, content_bytes) not in ('include', 'extend'):
                continue
            args = next((c for c in stmt_children if c.kind() == 'argument_list'), None)
            if args is None:
                continue
            for arg in _children(args):
                name = _const_text(arg, content_bytes)
                if name is not None:
                    names.append(name)
    return names


def _process_class(node: Any, file_path: str, content_bytes: bytes,
                    classes: List[Dict[str, Any]]) -> None:
    name = _declared_name(node, content_bytes)
    if name is None:
        return
    bases: List[str] = []
    superclass = _superclass_name(node, content_bytes)
    if superclass is not None:
        bases.append(superclass)
    bases.extend(_mixin_names(node, content_bytes))

    classes.append({
        'name': name,
        'file': file_path,
        'line': _get_line(node),
        'bases': bases,
        'decorators': [],
        'abstract_methods': [],
        'implementations': [],
        'category': 'classes',
        'is_abstract': False,
    })
