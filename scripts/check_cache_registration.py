"""Ratchet: every cache in reveal/ has an owner class in scripts/cache_manifest.json (BACK-2122).

Cache bugs came from caches nobody had classified: a process-wide dict that outlived an MCP
request (BACK-2117), an ``lru_cache`` frozen before plugin discovery (BACK-2120), a tree-sitter
memo that handed one worker thread's nodes to the next (BACK-2115). This scan finds the
cache sites by shape and requires each to be listed with who invalidates it.

Sites found (AST scan of ``reveal/``):

``container``  a module- or class-level empty ``dict``/``set``/``list``/``OrderedDict``/... that a
               function of the same module fills (``x[k] = v``, ``.add``, ``.append``, ``.update``,
               ``.setdefault``, ``|=``, ...), or whose name says cache/memo
``instance``   ``self._x = {}`` (or ``set()``...) whose name says cache/memo/seen
``lru``        ``@lru_cache`` / ``@cache`` on a function or method, or ``name = lru_cache(...)(fn)``
``thread-local``  ``threading.local()`` and instances of ``_ThreadLocalMemo``
``disk``       a ``DiskCache`` namespace: ``ImportsDiskCache("ns")``, a module string constant
               named ``*_NAMESPACE``, or a constant/literal first argument of ``disk_cache.get/put``

Owner classes (the manifest says which one each site is, and the check verifies what it can):

``request``        reset at every host request: a ``register_request_cache`` call in the module
``validated``      kept while a stamp is unchanged: ``register_validated_cache(name, THIS, ...)``
                   in the module
``disk``           an on-disk namespace (``core/disk_cache.py`` keys it by build and caller key)
``pure``           an ``lru_cache`` of a function of its arguments only
``thread-local``   a ``threading.local()`` or ``_ThreadLocalMemo``; the only owner a cache that
                   holds tree-sitter nodes, trees or parsers may have
``process-exempt`` anything else, with a stated ``reason``; the count may only fall

A module that touches tree-sitter must say what each of its non-thread-local caches holds
(``"holds": "plain"``); ``"holds": "tree-sitter"`` is only accepted on a thread-local owner, or on
an ``instance`` cache (``self._x``), whose lifetime is one object a call builds.
On the 1.8.1 language-pack floor a Node is unsendable across OS threads, and reveal-mcp runs
every tool call on its own thread.

Fails on: a site missing from the manifest, a manifest entry no site matches, an owner that
does not fit the site (or its registration), a missing reason, ``process-exempt`` above the
ceiling, a ``tests/conftest.py`` ``_MODULE_CACHES`` entry the manifest does not list.

Run:
    python scripts/check_cache_registration.py       # exits 1 on any problem
    python scripts/check_cache_registration.py -v    # list every site and its owner
"""
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
TREE = 'reveal'
MANIFEST = Path(__file__).resolve().parent / 'cache_manifest.json'
CONFTEST = ROOT / 'tests' / 'conftest.py'

OWNERS = ('request', 'validated', 'disk', 'pure', 'thread-local', 'process-exempt')
KINDS = ('container', 'instance', 'lru', 'thread-local', 'disk')

_CONTAINER_CTORS = frozenset({'dict', 'set', 'list', 'OrderedDict', 'defaultdict', 'deque', 'Counter',
                              'WeakKeyDictionary', 'WeakValueDictionary', 'WeakSet'})
_FILLERS = frozenset({'add', 'append', 'extend', 'update', 'setdefault', 'insert', 'appendleft',
                      'move_to_end', 'popitem', 'discard'})
_CACHE_NAME = re.compile(r'cache|memo', re.IGNORECASE)
_INSTANCE_NAME = re.compile(r'cache|memo|seen', re.IGNORECASE)
_TREESITTER_WORDS = ('tree_sitter', 'treesitter', 'ts_parse', 'get_parser', 'get_tree', 'tree_root',
                     'node_children', 'root_node', 'kind_nodes', '_ts_nodes_of_kind')


class Site(NamedTuple):
    kind: str
    line: int


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f'{base}.{node.attr}' if base else node.attr
    return ''


def _is_empty_container(value: ast.AST) -> bool:
    if isinstance(value, ast.Dict):
        return not value.keys
    if isinstance(value, (ast.List, ast.Set)):
        return not value.elts
    if isinstance(value, ast.Call):
        name = _dotted(value.func).split('.')[-1]
        if name == 'defaultdict':
            return True
        return name in _CONTAINER_CTORS and not value.args and not value.keywords
    return False


def _targets(node: ast.AST) -> Tuple[List[ast.AST], Any]:
    if isinstance(node, ast.Assign):
        return list(node.targets), node.value
    if isinstance(node, ast.AnnAssign) and node.value is not None:
        return [node.target], node.value
    return [], None


def _filled_names(tree: ast.AST) -> Set[str]:
    """Names (bare or attribute) a function in the module fills like a container."""
    filled: Set[str] = set()

    def name_of(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return ''

    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(func):
            if isinstance(node, ast.Subscript) and isinstance(node.ctx, (ast.Store, ast.Del)):
                filled.add(name_of(node.value))
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr in _FILLERS:
                filled.add(name_of(node.func.value))
            elif isinstance(node, ast.AugAssign):
                filled.add(name_of(node.target))
    filled.discard('')
    return filled


def _lru_decorated(func: ast.AST) -> bool:
    for dec in getattr(func, 'decorator_list', ()):
        target = dec.func if isinstance(dec, ast.Call) else dec
        if _dotted(target).split('.')[-1] in ('lru_cache', 'cache'):
            return True
    return False


def _string_constants(tree: ast.Module) -> Dict[str, str]:
    consts = {}
    for node in tree.body:
        targets, value = _targets(node)
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            for target in targets:
                if isinstance(target, ast.Name):
                    consts[target.id] = value.value
    return consts


def _defines_cache_clear(item: ast.stmt) -> bool:
    """``def cache_clear`` or ``cache_clear = staticmethod(wrapped.cache_clear)`` in a class body."""
    if isinstance(item, ast.FunctionDef):
        return item.name == 'cache_clear'
    targets, _value = _targets(item)
    return any(isinstance(t, ast.Name) and t.id == 'cache_clear' for t in targets)


def find_wrappers(source: str) -> Dict[str, str]:
    """Classes that wrap a cache (they define ``cache_clear``): {class name: site kind}.

    ``_ThreadLocalMemo`` holds a ``threading.local()``; any other (``_RubyInventoryPair``, whose
    ``cache_clear`` is the wrapped function's) fronts an ``lru_cache`` and is an ``lru`` site.
    """
    wrappers = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and any(_defines_cache_clear(item) for item in node.body):
            local = any(isinstance(n, ast.Call) and _dotted(n.func) == 'threading.local'
                        for n in ast.walk(node))
            wrappers[node.name] = 'thread-local' if local else 'lru'
    return wrappers


def find_sites(source: str, rel: str, wrappers: Optional[Dict[str, str]] = None,
               aliases: Optional[Dict[str, str]] = None) -> Dict[str, Site]:
    """Cache sites in one module: {id: Site}. An id is ``rel::qualified.name`` or ``disk:<namespace>``.

    *wrappers* is ``find_wrappers`` over the whole tree (an instance of a wrapper class built here
    is a cache site of the wrapper's kind). *aliases* collects ``rel::VARIABLE -> disk:<namespace>``
    for ``VARIABLE = ImportsDiskCache("namespace")``, the name tests/conftest.py uses.
    """
    wrappers = wrappers or {}
    aliases = aliases if aliases is not None else {}
    tree = ast.parse(source)
    sites: Dict[str, Site] = {}
    filled = _filled_names(tree)
    consts = _string_constants(tree)

    def add(ident: str, kind: str, line: int) -> None:
        sites.setdefault(ident, Site(kind, line))

    def visit(body: List[ast.stmt], scope: str, in_class: bool) -> None:
        for node in body:
            targets, value = _targets(node)
            for target in targets:
                if not isinstance(target, ast.Name) or value is None:
                    continue
                qual = scope + target.id
                if _is_empty_container(value) and (target.id in filled or _CACHE_NAME.search(target.id)):
                    add(f'{rel}::{qual}', 'container', node.lineno)
                elif isinstance(value, ast.Call):
                    callee = _dotted(value.func)
                    last = callee.split('.')[-1]
                    if callee == 'threading.local':
                        add(f'{rel}::{qual}', 'thread-local', node.lineno)
                    elif last in wrappers:
                        add(f'{rel}::{qual}', wrappers[last], node.lineno)
                    elif last == 'ImportsDiskCache' and value.args \
                            and isinstance(value.args[0], ast.Constant):
                        add(f'disk:{value.args[0].value}', 'disk', node.lineno)
                        aliases[f'{rel}::{qual}'] = f'disk:{value.args[0].value}'
                    elif isinstance(value.func, ast.Call) \
                            and _dotted(value.func.func).split('.')[-1] in ('lru_cache', 'cache'):
                        add(f'{rel}::{qual}', 'lru', node.lineno)
                if target.id.endswith('NAMESPACE') and target.id in consts:
                    add(f'disk:{consts[target.id]}', 'disk', node.lineno)
            if isinstance(node, ast.ClassDef):
                visit(node.body, f'{scope}{node.name}.', True)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if _lru_decorated(node):
                    add(f'{rel}::{scope}{node.name}', 'lru', node.lineno)
                if in_class:
                    for inner in ast.walk(node):
                        itargets, ivalue = _targets(inner)
                        for target in itargets:
                            if (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                                    and target.value.id == 'self'):
                                if ivalue is not None and _is_empty_container(ivalue) \
                                        and _INSTANCE_NAME.search(target.attr):
                                    add(f'{rel}::{scope}{target.attr}', 'instance', inner.lineno)
                                elif isinstance(ivalue, ast.Call) and _dotted(ivalue.func) == 'threading.local':
                                    add(f'{rel}::{scope}{target.attr}', 'thread-local', inner.lineno)
            elif isinstance(node, (ast.If, ast.Try)):
                visit(node.body, scope, in_class)
                for handler in getattr(node, 'handlers', ()):
                    visit(handler.body, scope, in_class)
                visit(getattr(node, 'orelse', []), scope, in_class)

    visit(tree.body, '', False)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ('get', 'put') and node.args
                and _dotted(node.func.value).split('.')[-1] == 'disk_cache'):
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                add(f'disk:{arg.value}', 'disk', node.lineno)
            elif isinstance(arg, ast.Name) and arg.id in consts:
                add(f'disk:{consts[arg.id]}', 'disk', node.lineno)
    return sites


def find_registrations(source: str) -> Tuple[bool, Set[str]]:
    """(module calls register_request_cache, names passed as the cache to register_validated_cache)."""
    tree = ast.parse(source)
    requests, validated = False, set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = _dotted(node.func).split('.')[-1]
        if callee == 'register_request_cache':
            requests = True
        elif callee == 'register_validated_cache' and len(node.args) >= 2:
            validated.add(_dotted(node.args[1]).split('.')[-1])
    return requests, validated


class Scan(NamedTuple):
    sites: Dict[str, Site]
    file_of: Dict[str, str]          # site id -> module path
    aliases: Dict[str, str]          # ImportsDiskCache variable id -> disk id
    tree_sitter_modules: Set[str]
    requests: Set[str]               # modules calling register_request_cache
    validated: Dict[str, Set[str]]   # module -> variable names registered as validated


def scan(root: Path = ROOT) -> Scan:
    sites: Dict[str, Site] = {}
    file_of: Dict[str, str] = {}
    aliases: Dict[str, str] = {}
    ts_modules: Set[str] = set()
    requests: Set[str] = set()
    validated: Dict[str, Set[str]] = {}
    paths = sorted((root / TREE).rglob('*.py'))
    texts = {path: path.read_text(encoding='utf-8') for path in paths}
    wrappers: Dict[str, str] = {}
    for text in texts.values():
        try:
            wrappers.update(find_wrappers(text))
        except SyntaxError:
            continue
    for path in paths:
        rel = path.relative_to(root).as_posix()
        source = texts[path]
        try:
            found = find_sites(source, rel, wrappers, aliases)
            has_request, names = find_registrations(source)
        except SyntaxError:
            continue
        for ident, site in found.items():
            if ident not in sites:
                sites[ident] = site
                file_of[ident] = rel
        if found and any(word in source for word in _TREESITTER_WORDS):
            ts_modules.add(rel)
        if has_request:
            requests.add(rel)
        if names:
            validated[rel] = names
    return Scan(sites, file_of, aliases, ts_modules, requests, validated)


def conftest_module_caches(text: str, root: Path = ROOT) -> List[str]:
    """Ids of the (module, attribute) pairs in ``tests/conftest.py::_MODULE_CACHES``."""
    tree = ast.parse(text)
    ids = []
    for node in ast.walk(tree):
        targets, value = _targets(node)
        if any(isinstance(t, ast.Name) and t.id == '_MODULE_CACHES' for t in targets) \
                and isinstance(value, (ast.Tuple, ast.List)):
            for pair in value.elts:
                if isinstance(pair, ast.Tuple) and len(pair.elts) == 2 \
                        and all(isinstance(e, ast.Constant) for e in pair.elts):
                    module, attr = pair.elts[0].value, pair.elts[1].value
                    base = module.replace('.', '/')
                    path = f'{base}/__init__.py' if (root / base / '__init__.py').exists() else f'{base}.py'
                    ids.append(f'{path}::{attr}')
    return ids


def check(manifest: Dict[str, Any], found: Scan, module_caches: List[str]) -> List[str]:
    """Every problem, one line each; empty when the manifest and the tree agree."""
    problems: List[str] = []
    entries: Dict[str, Dict[str, Any]] = manifest.get('caches', {})
    for ident in sorted(set(found.sites) - set(entries)):
        site = found.sites[ident]
        problems.append(f'unlisted {site.kind} cache {ident} ({found.file_of[ident]}:{site.line}): '
                        f'add it to scripts/cache_manifest.json with an owner ({", ".join(OWNERS)})')
    for ident in sorted(set(entries) - set(found.sites)):
        problems.append(f'stale manifest entry {ident}: no cache site matches it any more; delete it')
    exempt = 0
    for ident in sorted(set(entries) & set(found.sites)):
        entry, site, module = entries[ident], found.sites[ident], found.file_of[ident]
        owner = entry.get('owner')
        if owner not in OWNERS:
            problems.append(f'{ident}: owner {owner!r} is not one of {", ".join(OWNERS)}')
            continue
        name = ident.rsplit('::', 1)[-1].rsplit('.', 1)[-1]
        if owner == 'process-exempt':
            exempt += 1
            if not str(entry.get('reason', '')).strip():
                problems.append(f'{ident}: process-exempt needs a "reason"')
        if (site.kind == 'thread-local') != (owner == 'thread-local'):
            problems.append(f'{ident}: a {site.kind} site cannot have owner {owner} '
                            f'(thread-local owns exactly the threading.local sites)')
        if (site.kind == 'disk') != (owner == 'disk'):
            problems.append(f'{ident}: a {site.kind} site cannot have owner {owner} '
                            f'(disk owns exactly the namespaces)')
        if owner == 'pure' and site.kind != 'lru':
            problems.append(f'{ident}: only an lru_cache of a function of its arguments is pure')
        if owner == 'request' and module not in found.requests \
                and entry.get('registered_in') not in found.requests:
            problems.append(f'{ident}: owner request but {module} never calls register_request_cache '
                            f'(name the module that does in "registered_in")')
        if owner == 'validated' and name not in found.validated.get(module, ()):
            problems.append(f'{ident}: owner validated but {module} never passes {name} to '
                            f'register_validated_cache')
        holds = entry.get('holds')
        if holds == 'tree-sitter' and owner != 'thread-local' and site.kind != 'instance':
            problems.append(f'{ident}: a cache that holds tree-sitter values must be thread-local '
                            f'(or live on one instance that a call builds)')
        elif module in found.tree_sitter_modules and owner not in ('thread-local', 'disk') \
                and holds not in ('plain', 'tree-sitter'):
            problems.append(f'{ident}: {module} touches tree-sitter; say what this cache holds '
                            f'("holds": "plain"), or make it thread-local if it holds nodes, '
                            f'trees or parsers')
    ceiling = manifest.get('exempt_ceiling')
    if not isinstance(ceiling, int):
        problems.append('manifest has no integer "exempt_ceiling"')
    elif exempt > ceiling:
        problems.append(f'{exempt} process-exempt caches, ceiling {ceiling}: the count may only fall')
    elif exempt < ceiling:
        problems.append(f'{exempt} process-exempt caches, ceiling {ceiling}: lower "exempt_ceiling" '
                        f'to {exempt} to lock in the improvement')
    for ident in module_caches:
        if found.aliases.get(ident, ident) not in entries:
            problems.append(f'tests/conftest.py _MODULE_CACHES lists {ident}, which the manifest does not')
    return problems


def main(argv: List[str]) -> int:
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    found = scan()
    module_caches = conftest_module_caches(CONFTEST.read_text(encoding='utf-8')) if CONFTEST.exists() else []
    if '-v' in argv:
        for ident, site in sorted(found.sites.items()):
            owner = manifest.get('caches', {}).get(ident, {}).get('owner', '-')
            print(f'{site.kind:13} {owner:15} {ident}')
    problems = check(manifest, found, module_caches)
    for problem in problems:
        print(problem)
    if problems:
        return 1
    owners: Dict[str, int] = {}
    for entry in manifest['caches'].values():
        owners[entry['owner']] = owners.get(entry['owner'], 0) + 1
    print('cache registration ratchet OK (' + ', '.join(f'{o} {n}' for o, n in sorted(owners.items())) + ')')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
