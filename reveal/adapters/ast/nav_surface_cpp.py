"""Tree-sitter surface extraction for C++ — env vars, FS writes, HTTP routes, CLI, includes.

BACK-403 pt 2 (surface breadth). C++ has no single dominant web framework, so
route coverage is the two most common shapes, both leading-`/` guarded:

- **cpp-httplib**: `svr.Get("/path", handler)` — a `field_expression` call whose
  field is a title-case HTTP verb (`Get`/`Post`/… — cpp-httplib capitalises
  them, which conveniently keeps this off a lowercase `cache.get("key")`).
- **Crow**: `CROW_ROUTE(app, "/path")(...)` — a `CROW_ROUTE`/`CROW_BP_ROUTE`
  call whose string argument is the path (method is `ANY`; Crow sets verbs via a
  chained `.methods(...)` this pass does not resolve).

Other categories:
- **env**: `getenv("KEY")` / `std::getenv("KEY")` (reads).
- **filesystem writes**: an `std::ofstream`/`ofstream` declaration, or a
  `fopen`/`freopen`/`open` call.
- **CLI entrypoint**: `int main(...)` — a top-level `function_definition` whose
  declarator name is `main`.
- **network/db/sdk egress**: `#include <...>` header-path taxonomy.

Route coverage is deliberately conservative (macro-heavy / template-heavy
frameworks like Pistache and Drogon are not statically reachable without
expansion) — it surfaces the common shapes and declines the rest rather than
guess.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from .nav_surface_common import _get_text, _get_line, _add_once

from reveal.core import node_children as _children
from reveal.core import tree_root, ts_parse
from reveal.core.treesitter_compat import _zero_arg

# #include header-path roots (matched as a prefix on the header path).
_NET_HEADERS: tuple = ('curl/', 'cpr/', 'boost/asio', 'boost/beast', 'restclient',
                       'cpp-httplib', 'httplib.h')
_DB_HEADERS: tuple = ('pqxx/', 'sqlite3', 'mysql', 'mysqlx', 'mongocxx/', 'bsoncxx/',
                      'hiredis', 'sw/redis++', 'soci/')
_SDK_HEADERS: tuple = ('aws/', 'google/cloud', 'stripe/')

_HEADER_TAXONOMY: tuple = (
    (_NET_HEADERS, 'network'),
    (_DB_HEADERS, 'db'),
    (_SDK_HEADERS, 'sdk'),
)

# cpp-httplib route verbs (title-case, as the library declares them).
_HTTP_VERBS: Dict[str, str] = {
    'Get': 'GET', 'Post': 'POST', 'Put': 'PUT', 'Delete': 'DELETE',
    'Patch': 'PATCH', 'Options': 'OPTIONS',
}

_CROW_ROUTE_MACROS: frozenset = frozenset({'CROW_ROUTE', 'CROW_BP_ROUTE'})
_ENV_FUNCS: frozenset = frozenset({'getenv', 'std::getenv', 'secure_getenv'})
_FS_CALL_FUNCS: frozenset = frozenset({'fopen', 'freopen'})
_OFSTREAM_TYPES: frozenset = frozenset({'ofstream', 'std::ofstream', 'std::fstream', 'fstream'})

_EMPTY_KEYS = ('cli', 'http', 'env', 'network', 'db', 'sdk', 'fs')


def scan_file_surface_cpp(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse one C++ file and return categorised surface entries."""
    try:
        from tree_sitter_language_pack import get_parser
        source = Path(file_path).read_text(errors='replace')
        parser = get_parser('cpp')
        tree = ts_parse(parser, source)
    except Exception:
        return {k: [] for k in _EMPTY_KEYS}

    content_bytes = source.encode('utf-8')
    return _scan_tree(tree, file_path, content_bytes)


def _scan_tree(tree: Any, file_path: str, content_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
    surfaces: Dict[str, List[Dict[str, Any]]] = {k: [] for k in _EMPTY_KEYS}

    stack = [tree_root(tree)]
    while stack:
        node = stack.pop()
        kind = _zero_arg(node, 'kind')
        if kind == 'preproc_include':
            _process_include(node, file_path, content_bytes, surfaces)
        elif kind == 'call_expression':
            _process_call(node, file_path, content_bytes, surfaces)
        elif kind == 'function_definition':
            _process_function(node, file_path, content_bytes, surfaces)
        elif kind == 'declaration':
            _process_declaration(node, file_path, content_bytes, surfaces)
        for ch in reversed(_children(node)):
            stack.append(ch)

    return surfaces


def _string_content(node: Any, content_bytes: bytes) -> Optional[str]:
    if _zero_arg(node, 'kind') != 'string_literal':
        return None
    for ch in _children(node):
        if _zero_arg(ch, 'kind') == 'string_content':
            return _get_text(ch, content_bytes)
    return _get_text(node, content_bytes).strip('"')


def _first_string_arg(call_node: Any, content_bytes: bytes) -> Optional[str]:
    args = next((c for c in _children(call_node) if _zero_arg(c, 'kind') == 'argument_list'), None)
    if args is None:
        return None
    for arg in _children(args):
        if _zero_arg(arg, 'kind') == 'string_literal':
            return _string_content(arg, content_bytes)
    return None


def _process_include(node: Any, file_path: str, content_bytes: bytes,
                     surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    header = None
    for ch in _children(node):
        if _zero_arg(ch, 'kind') == 'system_lib_string':
            header = _get_text(ch, content_bytes).strip('<>')
        elif _zero_arg(ch, 'kind') == 'string_literal':
            header = _string_content(ch, content_bytes)
    if not header:
        return
    line = _get_line(node)
    for headers, category in _HEADER_TAXONOMY:
        for prefix in headers:
            if header == prefix or header.startswith(prefix):
                _add_once(surfaces[category],
                          {'type': 'include', 'name': header, 'file': file_path, 'line': line})
                return


def _process_function(node: Any, file_path: str, content_bytes: bytes,
                      surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    declarator = next((c for c in _children(node) if _zero_arg(c, 'kind') == 'function_declarator'), None)
    if declarator is None:
        return
    name = next((_get_text(c, content_bytes) for c in _children(declarator)
                 if _zero_arg(c, 'kind') == 'identifier'), None)
    if name == 'main':
        surfaces['cli'].append({
            'type': 'main', 'name': 'main', 'file': file_path, 'line': _get_line(node),
        })


def _process_declaration(node: Any, file_path: str, content_bytes: bytes,
                         surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    """`std::ofstream out("/path");` — an ofstream/fstream declaration is a
    file-write surface."""
    type_node = next((c for c in _children(node)
                      if _zero_arg(c, 'kind') in ('qualified_identifier', 'type_identifier')), None)
    if type_node is None:
        return
    type_text = _get_text(type_node, content_bytes)
    if type_text in _OFSTREAM_TYPES or type_text.split('::')[-1] in ('ofstream', 'fstream'):
        surfaces['fs'].append({
            'type': 'fs_write', 'name': type_text, 'file': file_path, 'line': _get_line(node),
        })


def _process_call(node: Any, file_path: str, content_bytes: bytes,
                  surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    # Crow's `CROW_ROUTE(app, "/p")([]{})` nests the route macro call inside an
    # outer call; the tree walk visits that inner call_expression on its own, so
    # only the direct-callee shapes are handled here (no manual recursion — that
    # would double-count the inner CROW_ROUTE call).
    fn = next((c for c in _children(node)
               if _zero_arg(c, 'kind') in ('identifier', 'qualified_identifier', 'field_expression')), None)
    if fn is None:
        return
    line = _get_line(node)

    # env: getenv / std::getenv
    if _zero_arg(fn, 'kind') in ('identifier', 'qualified_identifier'):
        fn_text = _get_text(fn, content_bytes)
        if fn_text in _ENV_FUNCS:
            key = _first_string_arg(node, content_bytes)
            if key:
                surfaces['env'].append({
                    'type': 'env_var', 'name': key, 'expr': fn_text,
                    'file': file_path, 'line': line,
                })
            return
        if fn_text in _FS_CALL_FUNCS:
            surfaces['fs'].append({
                'type': 'fs_write', 'name': fn_text, 'file': file_path, 'line': line,
            })
            return
        # Crow: CROW_ROUTE(app, "/path")(...)
        if fn_text in _CROW_ROUTE_MACROS:
            path = _first_string_arg(node, content_bytes)
            if path and path.startswith('/'):
                surfaces['http'].append({
                    'type': 'route', 'name': '?', 'path': path, 'methods': 'ANY',
                    'decorator': f'{fn_text}()', 'file': file_path, 'line': line,
                })
            return

    # cpp-httplib: svr.Get("/path", handler)
    if _zero_arg(fn, 'kind') == 'field_expression':
        field = next((c for c in _children(fn) if _zero_arg(c, 'kind') == 'field_identifier'), None)
        if field is not None:
            verb = _get_text(field, content_bytes)
            if verb in _HTTP_VERBS:
                path = _first_string_arg(node, content_bytes)
                if path and path.startswith('/'):
                    surfaces['http'].append({
                        'type': 'route', 'name': '?', 'path': path,
                        'methods': _HTTP_VERBS[verb], 'decorator': f'.{verb}()',
                        'file': file_path, 'line': line,
                    })
