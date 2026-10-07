"""Ratchet: shared infrastructure is called through its seam, never re-implemented.

Reliability program (BACK-1512), phase 1. Each rule below is a concern that should have
one home. Copies of it outside that home are where recurring bug classes come from:
24+ directory walkers each apply ``--exclude``/``REVEAL_IGNORE``/dot-dir skipping their
own way; direct ``get_parser`` calls skip the parse cache and the missing-grammar check;
``sys.exit`` and ``print`` outside the CLI/rendering layer force ``mcp_server`` to
capture stdout under a global lock and catch ``SystemExit`` as control flow.

Existing offenders are frozen per rule and per file in ``scripts/boundary_baseline.json``.
A file may not rise above its count (a regression) or sit below it without the baseline
being lowered (``--update-baseline``), so each count only ever falls. The removal task
behind each rule drives its count to zero.

Rules (home = where the concern is allowed to live):

``walker`` (BACK-1515 -> BACK-1223)
    ``os.walk``, ``.rglob()``, ``.glob()`` / ``glob.glob()`` with ``**`` or
    ``recursive=True``, and a one-level listing (``iterdir``/``scandir``/``listdir``) in a
    function that recurses (directly or through other functions in the module), in a
    helper such a function calls, or in a ``while`` loop that grows a worklist (BACK-1573).
    Home: ``reveal/utils/path_utils.py`` (``_walk_code_files``, ``walk_tree``,
    ``list_dir``). A walk over something that is not the user's target (reveal's own
    package, its cache, ~/.claude) is legitimate: mark it ``# boundary-ok: walker -- <why>``.
``tree-sitter-import`` (BACK-1046 -> BACK-1045)
    ``import tree_sitter*`` / ``from tree_sitter* import``. Home:
    ``reveal/core/treesitter*.py``. Imports under ``if TYPE_CHECKING:`` are exempt.
``exit`` (BACK-1368 -> BACK-916)
    ``sys.exit``, ``os._exit``, builtin ``exit()``/``quit()``, ``raise SystemExit``.
    Home: ``reveal/cli/`` and the console-script entry points (``main.py``,
    ``__main__.py``, ``mcp_server.py``).
``print`` (BACK-1368 -> BACK-916)
    ``print()``, ``sys.stdout.write``, ``sys.stderr.write``. Home: the rendering layer --
    ``reveal/cli/``, ``reveal/rendering/``, ``reveal/display/``, ``render*.py`` modules,
    ``*Renderer`` classes -- and ``main.py``/``__main__.py``. (BACK-916 merges those
    rendering homes and retires the print-based contract; this rule only keeps print out
    of analysis code meanwhile.) ``mcp_server.py`` is NOT a home: stdout is its JSON-RPC
    stream.
``argv`` (BACK-1058)
    ``sys.argv`` (and ``from sys import argv``). Home: ``reveal/main.py::main``, which parses
    it once into a ``reveal.cli.invocation.Invocation``; everything else asks
    ``current_invocation()``. A raw re-read is how ``reveal --format json overview`` missed
    the subcommand, ``-qc`` copied nothing, and MCP provenance named the server as the command.
``subcommand-output`` (BACK-1544 -> BACK-1059)
    ``add_cli_contract_fields()``: a ``reveal <name>`` result's JSON envelope. Home:
    ``reveal/cli/routing/subcommand.py::emit_subcommand_result``, which also acts on the
    result's outcome (a failed result exits 1, a cut list is printed), and the envelope
    builder it prints, ``subcommand_json`` (also what check's ``--also-json`` writes). A
    runner that built its own envelope never acted on the outcome, which is how ``reveal
    overview`` lost its cut line.

``display-path`` (BACK-1635)
    An f-string field in the rendering layer whose expression is a bare path
    (``{path}``, ``{file_path}``, ``{x.path}``). ``str(Path)`` prints ``\\`` on Windows, and
    ``--matrix`` is Linux-only, so nothing else catches it. Scope: ``reveal/display/`` and
    ``reveal/cli/routing/``, the file views that print a ``Path`` they were handed. Adapter
    renderers print a ``path`` out of a result dict, which the router already spells with ``/``
    (BACK-1530 path pass), so they are out of scope. Write the path
    with ``to_posix()``/``as_spelled()`` (``reveal/utils/path_utils.py``); a field that is
    already a ``/`` string (a URI, a relative name built with ``as_posix()``) takes
    ``# boundary-ok: display-path -- <why>``.

``silent-except`` (BACK-1638 -> BACK-1059)
    Uses B006's Python handler policy for broad catches, including computed fallbacks,
    assignments and debug-only logs. Required failures must be re-raised, returned as
    explicit diagnostics, or logged at WARNING or above. Narrow expected exceptions.
    Documented intentional fallbacks and deferred visible signals follow the same
    B006 policy. Bare catches and optional-import probes retain boundary-specific
    handling; boundary-ok markers require a concrete reason.

``splitlines`` (BACK-1722)
    ``.splitlines()`` on anything. ``str.splitlines()`` ends a line at form feed, vertical tab,
    FS/GS/RS, NEL and U+2028/U+2029 as well as at ``\\n``, so every line number after a GNU C
    ``^L`` page break was one too high against tree-sitter, ``grep -n`` and editors. File content
    is split with ``reveal.utils.lines.split_lines``. A site that splits something that is not
    file content (subprocess output, a rendered or help string) is marked
    ``# boundary-ok: splitlines -- <why>``.

Code under ``if __name__ == '__main__':`` is exempt from ``exit`` and ``print``.
Suppress one deliberate site with ``# boundary-ok: <rule> -- <why>`` on any line of the
call, or on a comment line directly above it.
Not detected: aliased callables (``w = os.walk``), ``Path.walk`` (3.12+, and reveal
supports 3.10), and recursion across modules.

Run:
    python scripts/check_boundaries.py                   # exits 1 on regression or stale baseline
    python scripts/check_boundaries.py -v                # list every site
    python scripts/check_boundaries.py --update-baseline # lower the baseline after a fix
"""

import ast
import json
import sys
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from reveal.rules.bugs.B006 import B006

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / 'scripts' / 'boundary_baseline.json'
TREE = 'reveal'

# A home is ('prefix', path-prefix), ('func', file, function) -- the site is anywhere inside
# that function --, ('basename', glob) or ('class', glob on an enclosing class name).
Home = Tuple[str, ...]
_ENTRY_POINTS: Tuple[Home, ...] = (('prefix', 'reveal/main.py'), ('prefix', 'reveal/__main__.py'))

RULES: Dict[str, Dict[str, Any]] = {
    'walker': {
        'task': 'BACK-1515 (removal: BACK-1223)',
        'fix': 'walk through reveal.utils.path_utils (_walk_code_files, walk_tree, walk_with_causes, list_dir)',
        'home': tuple(('func', 'reveal/utils/path_utils.py', f)
                      for f in ('_walk_code_files', 'walk_tree', 'walk_with_causes',
                                'list_dir')),
    },
    'tree-sitter-import': {
        'task': 'BACK-1046 (removal: BACK-1045)',
        'fix': 'go through reveal.core.treesitter_compat (ts_parse / the parser seam)',
        'home': (('prefix', 'reveal/core/treesitter'),),
    },
    'exit': {
        'task': 'BACK-1368 (removal: BACK-916)',
        'fix': 'raise an exception or return an error result; let the CLI choose the exit code',
        'home': (('prefix', 'reveal/cli/'), ('prefix', 'reveal/mcp_server.py')) + _ENTRY_POINTS,
    },
    'argv': {
        'task': 'BACK-1058',
        'fix': 'ask reveal.cli.invocation.current_invocation() (the command line, parsed once)',
        'home': (('func', 'reveal/main.py', 'main'),),
    },
    'subcommand-output': {
        'task': 'BACK-1544 (removal: BACK-1059)',
        'fix': 'print the result through reveal.cli.routing.subcommand.emit_subcommand_result',
        'home': (('func', 'reveal/cli/routing/subcommand.py', 'emit_subcommand_result'),
                 ('func', 'reveal/cli/routing/subcommand.py', 'subcommand_json')),
    },
    'display-path': {
        'task': 'BACK-1635',
        'fix': 'write the path with to_posix()/as_spelled() (reveal.utils.path_utils); '
               'str(Path) prints backslashes on Windows',
        'home': (),
        'scope': (('prefix', 'reveal/display/'), ('prefix', 'reveal/cli/routing/')),
    },
    'silent-except': {
        'task': 'BACK-1614 (removal: BACK-1059)',
        'fix': 'log it (logger.debug), narrow the exception type, or return a result marker -- '
               'a swallowed failure reads as a clean empty result',
        'home': (),
    },
    'splitlines': {
        'task': 'BACK-1722',
        'fix': 'split file content with reveal.utils.lines.split_lines (a line ends at \\n only); '
               'mark non-file text # boundary-ok: splitlines -- <why>',
        'home': (),
    },
    'print': {
        'task': 'BACK-1368 (removal: BACK-916)',
        'fix': 'return data and print it from a renderer (reveal/rendering, reveal/display, '
               'an adapter *Renderer)',
        'home': (('prefix', 'reveal/cli/'), ('prefix', 'reveal/rendering/'),
                 ('prefix', 'reveal/display/'), ('basename', 'render*.py'),
                 ('class', '*Renderer')) + _ENTRY_POINTS,
    },
}

Sites = Dict[str, List[int]]  # rule -> sorted line numbers


def _is_home(rule: str, rel: str, funcs: List[str], classes: List[str]) -> bool:
    for kind, *spec in RULES[rule]['home']:
        if kind == 'prefix' and rel.startswith(spec[0]):
            return True
        if kind == 'func' and rel == spec[0] and spec[1] in funcs:
            return True
        if kind == 'basename' and fnmatch(rel.rsplit('/', 1)[-1], spec[0]):
            return True
        if kind == 'class' and any(fnmatch(c, spec[0]) for c in classes):
            return True
    return False


def _in_scope(rule: str, rel: str) -> bool:
    scope = RULES[rule].get('scope')
    if scope is None:
        return True
    return any((kind == 'prefix' and rel.startswith(spec[0]))
               or (kind == 'basename' and fnmatch(rel.rsplit('/', 1)[-1], spec[0]))
               for kind, *spec in scope)


_PATH_NAMES = frozenset({'path', 'file_path', 'filepath', 'target_path'})


def _is_bare_path(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id in _PATH_NAMES
    return isinstance(node, ast.Attribute) and node.attr in _PATH_NAMES


def _dotted(node: ast.AST) -> str:
    """'os.walk' for os.walk, 'sys.stdout.write' for sys.stdout.write, '' otherwise."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return '.'.join(reversed(parts))
    return ''


def _has_double_star(arg: ast.AST) -> bool:
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return '**' in arg.value
    if isinstance(arg, ast.JoinedStr):
        return any(_has_double_star(v) for v in arg.values)
    return False


def _kw_true(call: ast.Call, name: str) -> bool:
    return any(k.arg == name and isinstance(k.value, ast.Constant) and k.value.value is True
               for k in call.keywords)


def _is_type_checking(test: ast.AST) -> bool:
    return _dotted(test) in ('TYPE_CHECKING', 'typing.TYPE_CHECKING')


def _is_main_guard(test: ast.AST) -> bool:
    return (isinstance(test, ast.Compare) and _dotted(test.left) == '__name__'
            and len(test.comparators) == 1 and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value == '__main__')


class _Scanner(ast.NodeVisitor):
    def __init__(self, rel: str, lines: List[str]):
        self.rel = rel
        self.lines = lines
        self.sites: Dict[str, Set[int]] = {rule: set() for rule in RULES}
        self.func_stack: List[str] = []
        self.class_stack: List[str] = []
        self.type_checking = 0
        self.main_guard = 0
        self.from_os: Dict[str, str] = {}
        self.from_sys: Dict[str, str] = {}
        self.walk_listings: Set[int] = set()
        self.parent_map: Dict[ast.AST, ast.AST] = {}
        self.silent_rule = B006()

    # -- bookkeeping --------------------------------------------------------
    def _add(self, rule: str, node: Any) -> None:
        if rule in ('exit', 'print') and self.main_guard:
            return
        if not _in_scope(rule, self.rel):
            return
        if _is_home(rule, self.rel, self.func_stack, self.class_stack):
            return
        first, last = node.lineno, getattr(node, 'end_lineno', None) or node.lineno
        span = self.lines[first - 1:last]
        above = self.lines[first - 2].strip() if first >= 2 else ''
        if above.startswith('#'):
            span.append(above)
        if any(f'boundary-ok: {rule}' in line for line in span):
            return
        self.sites[rule].add(node.lineno)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def _visit_func(self, node) -> None:
        self.func_stack.append(node.name)
        self.generic_visit(node)
        self.func_stack.pop()

    visit_FunctionDef = _visit_func
    visit_AsyncFunctionDef = _visit_func

    def visit_If(self, node: ast.If) -> None:
        if _is_type_checking(node.test):
            self.type_checking += 1
            for child in node.body:
                self.visit(child)
            self.type_checking -= 1
            for child in node.orelse:
                self.visit(child)
            return
        if _is_main_guard(node.test):
            self.main_guard += 1
            self.generic_visit(node)
            self.main_guard -= 1
            return
        self.generic_visit(node)

    # -- rules --------------------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        if not self.type_checking and any(a.name.split('.')[0].startswith('tree_sitter')
                                          for a in node.names):
            self._add('tree-sitter-import', node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ''
        if module.split('.')[0].startswith('tree_sitter') and not node.level:
            if not self.type_checking:
                self._add('tree-sitter-import', node)
        elif module == 'os':
            for a in node.names:
                if a.name in ('walk', '_exit'):
                    self.from_os[a.asname or a.name] = f'os.{a.name}'
        elif module == 'sys':
            for a in node.names:
                if a.name == 'exit':
                    self.from_sys[a.asname or a.name] = 'sys.exit'
                elif a.name == 'argv':
                    self._add('argv', node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if _dotted(node) == 'sys.argv':
            self._add('argv', node)
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        probe = all(isinstance(s, (ast.Import, ast.ImportFrom)) for s in node.body)
        for handler in node.handlers:
            if not probe and (handler.type is None or
                              self.silent_rule.is_silent_handler(handler, self.lines, self.parent_map)):
                self._add('silent-except', handler)
        self.generic_visit(node)

    visit_TryStar = visit_Try

    def visit_FormattedValue(self, node: ast.FormattedValue) -> None:
        if _is_bare_path(node.value):
            self._add('display-path', node)
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        if exc is not None and _dotted(exc) == 'SystemExit':
            self._add('exit', node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _dotted(node.func)
        if isinstance(node.func, ast.Name):
            name = self.from_os.get(name) or self.from_sys.get(name) or name
        attr = node.func.attr if isinstance(node.func, ast.Attribute) else ''

        if name == 'os.walk' or attr == 'rglob' or id(node) in self.walk_listings:
            self._add('walker', node)
        elif name in ('glob.glob', 'glob.iglob') and _kw_true(node, 'recursive'):
            self._add('walker', node)
        elif attr == 'glob' and node.args and _has_double_star(node.args[0]):
            self._add('walker', node)

        if name in ('sys.exit', 'os._exit', 'exit', 'quit'):
            self._add('exit', node)
        if name in ('print', 'sys.stdout.write', 'sys.stderr.write'):
            self._add('print', node)
        if attr == 'splitlines':
            self._add('splitlines', node)
        if name.rsplit('.', 1)[-1] == 'add_cli_contract_fields':
            self._add('subcommand-output', node)
        self.generic_visit(node)


def _calls_name(call: ast.Call, name: str) -> bool:
    """Does `call` invoke `name` directly or as self./cls. method?"""
    f = call.func
    if isinstance(f, ast.Name):
        return f.id == name
    return isinstance(f, ast.Attribute) and f.attr == name \
        and isinstance(f.value, ast.Name) and f.value.id in ('self', 'cls')


_LISTING = ('iterdir', 'scandir', 'listdir')
_WORKLIST_GROW = ('append', 'appendleft', 'extend', 'put')


def _is_listing(node: ast.AST) -> bool:
    """``p.iterdir()``, ``os.scandir(d)``, ``os.listdir(d)`` (or a bare imported name)."""
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    return (isinstance(f, ast.Attribute) and f.attr in _LISTING) or \
        (isinstance(f, ast.Name) and f.id in ('scandir', 'listdir'))


def _walk_listings(tree: ast.AST) -> Set[int]:
    """``id()`` of every one-level listing call that is really a recursive walk (BACK-1573).

    A listing call walks a tree when it sits in a function that recurses -- itself, or
    through other functions in the module (tree_view's renderer recursed through
    ``_process_dir_entry``) -- or in a helper such a function calls (``_get_sorted_entries``),
    or in a ``while`` loop that grows a worklist (D005's ``scandir`` stack).
    """
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    names = {f.name for f in funcs}
    calls: Dict[str, Set[str]] = {}
    for f in funcs:
        calls.setdefault(f.name, set()).update(
            name for n in ast.walk(f) if isinstance(n, ast.Call)
            for name in names if _calls_name(n, name))

    def recursive(name: str) -> bool:
        seen, todo = set(), list(calls.get(name, ()))
        while todo:
            callee = todo.pop()
            if callee == name:
                return True
            if callee not in seen:
                seen.add(callee)
                todo.extend(calls.get(callee, ()))
        return False

    walkers = {n for n in names if recursive(n)}
    walkers |= {callee for n in walkers for callee in calls.get(n, ())}
    found = {id(n) for f in funcs if f.name in walkers for n in ast.walk(f) if _is_listing(n)}
    for loop in ast.walk(tree):
        if isinstance(loop, ast.While):
            inner = [n for n in ast.walk(loop) if isinstance(n, ast.Call)]
            if any(isinstance(n.func, ast.Attribute) and n.func.attr in _WORKLIST_GROW
                   for n in inner):
                found.update(id(n) for n in inner if _is_listing(n))
    return found


def find_sites(source: str, rel: str) -> Sites:
    """Rule -> sorted line numbers of every out-of-home site in one file."""
    scanner = _Scanner(rel, source.splitlines())
    tree = ast.parse(source)
    scanner.walk_listings = _walk_listings(tree)
    scanner.parent_map = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    scanner.visit(tree)
    return {rule: sorted(lines) for rule, lines in scanner.sites.items()}


def scan() -> Dict[str, Dict[str, List[int]]]:
    """Rule -> {file: lines} across the package."""
    found: Dict[str, Dict[str, List[int]]] = {rule: {} for rule in RULES}
    for path in sorted((ROOT / TREE).rglob('*.py')):
        rel = path.relative_to(ROOT).as_posix()
        try:
            sites = find_sites(path.read_text(encoding='utf-8'), rel)
        except (SyntaxError, UnicodeDecodeError):
            continue
        for rule, lines in sites.items():
            if lines:
                found[rule][rel] = lines
    return found


def compare(baseline: Dict[str, Dict[str, int]], counts: Dict[str, Dict[str, int]]
            ) -> Tuple[List[Tuple[str, str, int, int]], List[Tuple[str, str, int, int]]]:
    """(regressions, stale) as (rule, file, baseline, now) tuples."""
    regressions, stale = [], []
    for rule in RULES:
        base, now = baseline.get(rule, {}), counts.get(rule, {})
        for f in sorted(set(base) | set(now)):
            b, n = base.get(f, 0), now.get(f, 0)
            if n > b:
                regressions.append((rule, f, b, n))
            elif n < b:
                stale.append((rule, f, b, n))
    return regressions, stale


def _counts(found: Dict[str, Dict[str, List[int]]]) -> Dict[str, Dict[str, int]]:
    return {rule: {f: len(v) for f, v in files.items()} for rule, files in found.items()}


def _totals(counts: Dict[str, Dict[str, int]]) -> str:
    return ', '.join(f'{rule} {sum(files.values())} in {len(files)} files'
                     for rule, files in counts.items())


def main(argv: List[str]) -> int:
    found = scan()
    counts = _counts(found)
    baseline = json.loads(BASELINE.read_text(encoding='utf-8')) if BASELINE.exists() else {}
    regressions, stale = compare(baseline, counts)

    if '-v' in argv:
        for rule, files in found.items():
            for f, lines in files.items():
                print(f'{rule:20} {f}: {lines}')

    if '--update-baseline' in argv:
        if regressions and baseline:
            print('refusing to raise the baseline; fix these or mark a deliberate site '
                  '# boundary-ok: <rule> -- <why>:')
            for rule, f, b, n in regressions:
                print(f'  {rule}: {f}: {b} -> {n}  lines {found[rule][f]}')
            return 1
        BASELINE.write_text(json.dumps(counts, indent=1, sort_keys=True) + '\n', encoding='utf-8')
        print(f'baseline written: {_totals(counts)}')
        return 0

    if regressions:
        print('New code re-implements shared infrastructure outside its seam:')
        for rule, f, b, n in regressions:
            meta = RULES[rule]
            print(f"  [{rule}] {f}: {b} -> {n}  lines {found[rule][f]}\n"
                  f"      fix: {meta['fix']}  ({meta['task']})")
        print('A deliberate exception takes # boundary-ok: <rule> -- <why>. '
              'See scripts/check_boundaries.py.')
    if stale:
        print('Sites were removed but the baseline still allows them (it must only fall):')
        for rule, f, b, n in stale:
            print(f'  [{rule}] {f}: {b} -> {n}')
        print('Lock in the improvement: python scripts/check_boundaries.py --update-baseline')
    if regressions or stale:
        return 1
    print(f'boundary ratchet OK ({_totals(counts)})')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
