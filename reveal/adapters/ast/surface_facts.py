"""Neutral fact extraction for surface:// (BACK-1330, stage 1 of BACK-1329).

One thin per-language extractor turns a parse tree into the same four fact shapes
(`Call`, `Import`, `New`, `Subshell`) so the rule layer (BACK-1331) sees one shape
whatever the language. Call naming reuses `reveal/core/callees` (BACK-1279): the
receiver/callee text comes from the same code the analyzer and `calls://` use, and is
only split here into `receiver` + `name`.

No behavior change: the per-language `nav_surface_*` scanners keep running until a
category migrates onto rules. Nothing imports this module yet except its tests.

See internal-docs/design/SURFACE_RULE_TABLE_ARCHITECTURE_2026-09-20.md.
"""

import ast
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from reveal.core import node_children as _children
from reveal.core import tree_root, ts_parse
from reveal.core.callees import (
    CHAIN_COLLAPSE,
    callee_name_from_node,
    extract_by_kind,
    is_misparsed_call,
)
from reveal.core.treesitter_compat import _zero_arg

logger = logging.getLogger(__name__)

# A string-literal argument is its text; any other argument is None, so positions hold.
Args = Tuple[Optional[str], ...]


@dataclass(frozen=True)
class Call:
    receiver: str          # dotted/scoped receiver path, '' for a bare call
    name: str              # called name (`Command` in `exec.Command(...)`)
    args: Args
    line: int
    sep: str = '.'         # separator between receiver and name in the source form

    @property
    def path(self) -> str:
        return f"{self.receiver}{self.sep}{self.name}" if self.receiver else self.name


@dataclass(frozen=True)
class Import:
    module: str            # module / package / header path as written
    names: Tuple[str, ...] = ()   # imported names (`b`, `c` in `use a::{b, c}`); () = whole module
    alias: str = ''
    line: int = 0


@dataclass(frozen=True)
class New:
    type_name: str         # constructed type, generics stripped
    args: Args
    line: int


@dataclass(frozen=True)
class Subshell:
    line: int              # backticks, `%x(...)`


Fact = Union[Call, Import, New, Subshell]

_ARG_LIST_KINDS = frozenset({'argument_list', 'arguments', 'value_arguments', 'call_suffix'})
_STRING_KINDS = frozenset({
    'string', 'string_literal', 'interpreted_string_literal', 'raw_string_literal',
    'encapsed_string', 'line_string_literal', 'string_content', 'template_string',
})
_LITERAL_PART_KINDS = frozenset(
    {'string_fragment', 'line_str_text', 'escape_sequence', 'str_escaped_char'})
_SEPARATORS = ('::', '->', '.')


def _text(content: bytes) -> Callable[[Any], str]:
    def get_text(n: Any) -> str:
        start, end = _zero_arg(n, 'start_byte'), _zero_arg(n, 'end_byte')
        return content[start:end].decode('utf-8', 'replace')
    return get_text


def _line(node: Any) -> int:
    return _zero_arg(node, 'start_position').row + 1


def _find(node: Any, *kinds: str) -> Optional[Any]:
    return next((c for c in _children(node) if _zero_arg(c, 'kind') in kinds), None)


def _split_path(path: str) -> Tuple[str, str, str]:
    """`a.b.c` -> ('a.b', 'c', '.'); `Command::new` -> ('Command', 'new', '::')."""
    best = (-1, '')
    for sep in _SEPARATORS:
        idx = path.rfind(sep)
        if idx > best[0]:
            best = (idx, sep)
    idx, sep = best
    if idx < 0:
        return '', path, '.'
    return path[:idx], path[idx + len(sep):], sep


def _string_value(node: Any, get_text: Callable[[Any], str]) -> Optional[str]:
    """Literal text of a string node, None when it interpolates or is not a string."""
    kind = _zero_arg(node, 'kind')
    if kind == 'argument' or kind == 'value_argument':      # C#/PHP/Kotlin/Swift wrappers
        named = [c for c in _children(node) if _zero_arg(c, 'is_named')]
        return _string_value(named[-1], get_text) if named else None
    if kind not in _STRING_KINDS:
        return None
    named = [c for c in _children(node) if _zero_arg(c, 'is_named')]
    if any(_zero_arg(c, 'kind') not in _LITERAL_PART_KINDS and 'content' not in _zero_arg(c, 'kind')
           for c in named):
        return None                       # interpolation: `$x`, `${x}`, `#{x}`, `\\(x)`, `{x}`
    parts = [get_text(c) for c in named]
    if parts:
        return ''.join(parts)
    raw = get_text(node)
    return raw[1:-1] if len(raw) >= 2 and raw[0] in '"\'`' and raw[-1] == raw[0] else raw


def _args_of(node: Any, get_text: Callable[[Any], str]) -> Args:
    """String-literal args of a call/new node, position-preserving."""
    arg_list = _find(node, *_ARG_LIST_KINDS)
    if arg_list is not None and _zero_arg(arg_list, 'kind') == 'call_suffix':
        arg_list = _find(arg_list, 'value_arguments')
    if arg_list is None:
        return ()
    return tuple(_string_value(c, get_text)
                 for c in _children(arg_list) if _zero_arg(c, 'is_named'))


# ── per-language imports ────────────────────────────────────────────────────

def _go_import(node: Any, get_text: Callable) -> List[Import]:
    path = _find(node, 'interpreted_string_literal', 'raw_string_literal')
    if path is None:
        return []
    alias = _find(node, 'package_identifier', 'blank_identifier', 'dot')
    return [Import(_string_value(path, get_text) or '',
                   alias=get_text(alias) if alias else '', line=_line(node))]


def _rust_use_paths(node: Any, get_text: Callable, prefix: str = '') -> List[Tuple[str, str]]:
    """Flatten a use tree into (full path, alias) pairs."""
    kind = _zero_arg(node, 'kind')
    join = lambda p, s: f"{p}::{s}" if p else s  # noqa: E731
    if kind == 'use_as_clause':
        path = node.child_by_field_name('path')
        alias = node.child_by_field_name('alias')
        return [(join(prefix, get_text(path)), get_text(alias) if alias else '')]
    if kind == 'scoped_use_list':
        path = node.child_by_field_name('path')
        lst = node.child_by_field_name('list')
        base = join(prefix, get_text(path)) if path else prefix
        out: List[Tuple[str, str]] = []
        for c in _children(lst) if lst else []:
            if _zero_arg(c, 'is_named'):
                out.extend(_rust_use_paths(c, get_text, base))
        return out
    if kind == 'use_list':
        out = []
        for c in _children(node):
            if _zero_arg(c, 'is_named'):
                out.extend(_rust_use_paths(c, get_text, prefix))
        return out
    return [(join(prefix, get_text(node)), '')]


def _rust_import(node: Any, get_text: Callable) -> List[Import]:
    arg = node.child_by_field_name('argument')
    if arg is None:
        return []
    return [Import(path, alias=alias, line=_line(node))
            for path, alias in _rust_use_paths(arg, get_text)]


def _dotted_import(kinds: Tuple[str, ...]) -> Callable[[Any, Callable], List[Import]]:
    """Java/C#/Kotlin/Swift/PHP-style: module text under one of `kinds`, optional alias."""
    def handler(node: Any, get_text: Callable) -> List[Import]:
        out = []
        clauses = [c for c in _children(node)
                   if _zero_arg(c, 'kind') == 'namespace_use_clause'] or [node]
        for clause in clauses:
            mod = _find(clause, *kinds)
            if mod is None:
                continue
            alias = clause.child_by_field_name('alias') or _find(clause, 'import_alias')
            alias_text = get_text(alias) if alias else ''
            if alias is not None and _zero_arg(alias, 'kind') == 'import_alias':
                alias_text = alias_text.replace('as', '', 1).strip()     # Kotlin `as F`
            out.append(Import(get_text(mod).lstrip('\\'), alias=alias_text, line=_line(clause)))
        return out
    return handler


def _cpp_include(node: Any, get_text: Callable) -> List[Import]:
    path = node.child_by_field_name('path')
    return [Import(get_text(path).strip('<>"'), line=_line(node))] if path else []


def _ts_import(node: Any, get_text: Callable) -> List[Import]:
    src = node.child_by_field_name('source')
    if src is None:
        return []
    module = _string_value(src, get_text) or ''
    names: List[str] = []
    alias = ''
    stack = list(_children(node))
    while stack:
        n = stack.pop()
        kind = _zero_arg(n, 'kind')
        if kind == 'import_specifier':
            nm = n.child_by_field_name('name')
            if nm is not None:
                names.append(get_text(nm))
        elif kind == 'namespace_import':
            ident = _find(n, 'identifier')
            alias = get_text(ident) if ident else ''
        elif kind == 'import_clause':
            ident = _find(n, 'identifier')
            if ident is not None:
                alias = get_text(ident)
            stack.extend(_children(n))
        elif kind in ('named_imports',):
            stack.extend(_children(n))
    return [Import(module, tuple(reversed(names)), alias, _line(node))]


# ── per-language spec ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class _Lang:
    parser: str
    call_kinds: frozenset
    import_kinds: Dict[str, Callable[[Any, Callable], List[Import]]]
    new_kinds: frozenset = frozenset()
    subshell_kinds: frozenset = frozenset()


_JAVA_LIKE = _dotted_import(('scoped_identifier', 'identifier'))

_LANGS: Dict[str, _Lang] = {
    'go': _Lang('go', frozenset({'call_expression'}), {'import_spec': _go_import}),
    'rust': _Lang('rust', frozenset({'call_expression'}), {'use_declaration': _rust_import}),
    'java': _Lang('java', frozenset({'method_invocation'}), {'import_declaration': _JAVA_LIKE},
                  new_kinds=frozenset({'object_creation_expression'})),
    'kotlin': _Lang('kotlin', frozenset({'call_expression'}),
                    {'import_header': _dotted_import(('identifier',))}),
    'csharp': _Lang('c_sharp', frozenset({'invocation_expression'}),
                    {'using_directive': _dotted_import(('qualified_name', 'identifier'))},
                    new_kinds=frozenset({'object_creation_expression'})),
    'cpp': _Lang('cpp', frozenset({'call_expression'}), {'preproc_include': _cpp_include},
                 new_kinds=frozenset({'new_expression'})),
    'php': _Lang('php', frozenset({'function_call_expression', 'member_call_expression',
                                   'scoped_call_expression'}),
                 {'namespace_use_declaration': _dotted_import(('qualified_name', 'name'))},
                 new_kinds=frozenset({'object_creation_expression'}),
                 subshell_kinds=frozenset({'shell_command_expression'})),
    'ruby': _Lang('ruby', frozenset({'call'}), {}, subshell_kinds=frozenset({'subshell'})),
    'swift': _Lang('swift', frozenset({'call_expression'}),
                   {'import_declaration': _dotted_import(('identifier',))}),
    'typescript': _Lang('typescript', frozenset({'call_expression'}),
                        {'import_statement': _ts_import},
                        new_kinds=frozenset({'new_expression'})),
    'tsx': _Lang('tsx', frozenset({'call_expression'}), {'import_statement': _ts_import},
                 new_kinds=frozenset({'new_expression'})),
}

EXTENSION_LANGUAGE: Dict[str, str] = {
    '.py': 'python', '.go': 'go', '.rs': 'rust', '.java': 'java', '.kt': 'kotlin', '.kts': 'kotlin',
    '.cs': 'csharp', '.cpp': 'cpp', '.cc': 'cpp', '.cxx': 'cpp', '.hpp': 'cpp', '.hh': 'cpp',
    '.h': 'cpp', '.php': 'php', '.rb': 'ruby', '.swift': 'swift',
    '.ts': 'typescript', '.js': 'typescript', '.mjs': 'typescript', '.cjs': 'typescript',
    '.tsx': 'tsx', '.jsx': 'tsx',
}

LANGUAGES = tuple(sorted({'python', *_LANGS}))


def _ruby_call_is_real(node: Any) -> bool:
    """Ruby's `call` kind is shared; the callee extractor claims only real Ruby calls."""
    return node.child_by_field_name('method') is not None


def _call_fact(node: Any, get_text: Callable, call_kinds: frozenset) -> Optional[Call]:
    if not _zero_arg(node, 'child_count') or is_misparsed_call(_zero_arg(node, 'kind'), node):
        return None
    handled, name = extract_by_kind(_zero_arg(node, 'kind'), node, get_text,
                                    call_node_types=call_kinds, chain_receiver=CHAIN_COLLAPSE)
    if not handled:
        first = node.child(0)
        name = callee_name_from_node(first, get_text, call_node_types=call_kinds,
                                     chain_receiver=CHAIN_COLLAPSE) if first is not None else None
    if not name:
        return None
    receiver, short, sep = _split_path(name)
    return Call(receiver, short, _args_of(node, get_text), _line(node), sep)


def _new_fact(node: Any, get_text: Callable, call_kinds: frozenset) -> Optional[New]:
    handled, name = extract_by_kind(_zero_arg(node, 'kind'), node, get_text,
                                    call_node_types=call_kinds, chain_receiver=CHAIN_COLLAPSE)
    if not (handled and name):
        return None
    type_name = re.sub(r'<.*>$', '', re.sub(r'^new\s+', '', name))
    return New(type_name, _args_of(node, get_text), _line(node))


def _walk_tree(root: Any, spec: _Lang, get_text: Callable) -> List[Fact]:
    facts: List[Fact] = []
    stack = [root]
    while stack:
        node = stack.pop()
        kind = _zero_arg(node, 'kind')
        if kind in spec.import_kinds:
            facts.extend(spec.import_kinds[kind](node, get_text))
        elif kind in spec.new_kinds:
            fact = _new_fact(node, get_text, spec.call_kinds)
            if fact:
                facts.append(fact)
        elif kind in spec.subshell_kinds:
            facts.append(Subshell(_line(node)))
        elif kind in spec.call_kinds and (kind != 'call' or _ruby_call_is_real(node)):
            fact = _call_fact(node, get_text, spec.call_kinds)
            if fact:
                facts.append(fact)
        stack.extend(reversed(_children(node)))
    return sorted(facts, key=lambda f: f.line)


# ── Python: ast walk emitting the same facts ────────────────────────────────

def _dotted(node: ast.AST) -> Optional[str]:
    parts: List[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return '.'.join(reversed(parts))
    return None


def _python_facts(source: str) -> List[Fact]:
    tree = ast.parse(source)
    facts: List[Fact] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            facts.extend(Import(a.name, alias=a.asname or '', line=node.lineno) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = '.' * node.level + (node.module or '')
            facts.extend(Import(module, (a.name,), a.asname or '', node.lineno) for a in node.names)
        elif isinstance(node, ast.Call):
            path = _dotted(node.func)
            if path is None:
                if isinstance(node.func, ast.Attribute):    # call on a call result: `.attr`
                    path = '.' + node.func.attr
                else:
                    continue
            receiver, name, sep = _split_path(path)
            args = tuple(
                a.value if isinstance(a, ast.Constant) and isinstance(a.value, str) else None
                for a in node.args)
            facts.append(Call(receiver, name, args, node.lineno, sep))
    return sorted(facts, key=lambda f: f.line)


# ── entry points ────────────────────────────────────────────────────────────

def extract_facts(source: str, language: str) -> List[Fact]:
    """Neutral facts for `source`, ordered by line. `language` is one of `LANGUAGES`."""
    if language == 'python':
        return _python_facts(source)
    spec = _LANGS[language]
    from tree_sitter_language_pack import get_parser   # lazy, like the nav_surface_* scanners
    tree = ts_parse(get_parser(spec.parser), source)
    return _walk_tree(tree_root(tree), spec, _text(source.encode('utf-8')))


def extract_file_facts(file_path: str) -> Optional[List[Fact]]:
    """Facts for a file, or None when the extension has no extractor or parsing fails."""
    language = EXTENSION_LANGUAGE.get(Path(file_path).suffix)
    if language is None:
        return None
    try:
        return extract_facts(Path(file_path).read_text(errors='replace'), language)
    except Exception as e:
        logger.warning("surface facts (%s) failed to parse %s: %s", language, file_path, e)
        return None
