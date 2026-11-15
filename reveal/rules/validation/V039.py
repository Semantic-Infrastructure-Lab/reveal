"""
V039: POSIX path literal in a test that breaks on Windows.

Flags, in reveal's own tests/, three line patterns that hold on Linux and macOS
and fail on Windows (where ``str(path)`` has backslashes):

* ``path-assign``: ``.path = Path('/fake/...')`` -- a POSIX absolute Path assigned
  to a mock's ``.path``, which production code stringifies;
* ``posix-literal``: an ``assert`` line holding a ``'/fake/...'``-style filesystem
  path literal (rooted at ``/fake``, ``/tmp``, ``/home``, ``/var``, ``/src``, ``/usr``);
* ``path-split-on-slash``: ``r['file'].rsplit('/', 1)`` -- a basename on POSIX, a
  no-op on Windows.

This is ``scripts/check_windows_compat.py`` (BACK-1470) moved into the V-series
(BACK-1707): same regexes, same exempt files and indicators, same findings.

Suppress a false positive with ``# noqa: win-path`` (the spelling the repo already
uses) or ``# noqa: V039`` on the line.

BACK-2590 also checks locally proven native Path expectations in envelope source
and stderr assertions. These AST checks are strict; explicit string sources,
negative leakage guards and native stdout expectations remain valid.

Examples:
    reveal reveal:// --check --select V039
"""

import ast
import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from ..base import BaseRule, Detection, RulePrefix, Severity, RuleScope
from .utils import has_noqa, load_sources, parse_test_module
from reveal.utils.lines import split_lines
from reveal.utils.pyparse import statement_index

# Test files whose path assertions are intentionally POSIX data content
# (nginx configs, SSL certs, ZIP archives, URI specs -- never filesystem paths):
SAFE_FILES = frozenset({
    'test_nginx_analyzer_pytest.py',
    'test_nginx_adapter.py',
    'test_nginx_uri_adapter.py',
    'test_nginx_renderer.py',
    'test_ssl_adapter.py',
    'test_cpanel_adapter.py',
    'test_xlsx_adapter.py',
    'test_windows_compat.py',
    'test_letsencrypt_adapter.py',  # cert/renewal paths are POSIX data
    'test_uri.py',                  # URI path components are always POSIX
})

# Lines containing these strings are already safe or are known non-filesystem paths
SAFE_INDICATORS = (
    'native(',           # already using the helper
    'str(Path(',         # explicit normalization
    '.as_posix()',       # explicit normalization
    '# noqa: win-path',  # manual suppression
    'http://',
    'https://',
    '://',
)

# Lines that look risky but are Path-to-Path comparisons (safe: Path.__eq__ normalises)
RE_PATH_TO_PATH = re.compile(r"""(?:assertEqual|==)\s*\(?.*?Path\(""")

# Only flags Path() objects (not plain strings) assigned to .path
RE_PATH_ASSIGN = re.compile(r"""\.path\s*=\s*Path\(['"]/(fake|tmp|home|var|src|usr)""")

# == '/fake/...' or '/tmp/...' in x  but NOT URI-style paths or single-segment paths.
RE_FS_PATH_LITERAL = re.compile(
    r"""['"]"""                             # opening quote
    r"""(/(?:fake|tmp|home|var|src|usr)"""  # starts with a filesystem-root segment
    r"""(?:/[^'"]+)+)"""                    # at least one more segment
    r"""['"]"""                             # closing quote
)

# `r['file'].rsplit('/', 1)[-1]` is a basename on POSIX but a no-op on Windows, where the
# path uses backslashes (test_conventions rank_by_callers, 2026-09).
RE_PATH_SPLIT = re.compile(
    r"""(?:file|path|dir)\w*['"]?\]?\.(?:r?split)\(\s*['"]/['"]""", re.IGNORECASE
)

_LABELS = {
    'native-source': ("Native Path spelling in an envelope source assertion",
                      "compare Path sources with .as_posix(); explicitly supplied string sources keep their spelling"),
    'native-stderr': ("Native Path spelling in a stderr containment assertion",
                      "compare path parts (directory component and filename); OSError repr doubles Windows backslashes"),
    'posix-literal': ("POSIX path literal in assertion",
                      "use native('/...') from tests/conftest.py"),
    'path-split-on-slash': ("path split on '/' (backslashes on Windows)",
                            "use PureWindowsPath(x).name / os.path.basename(x)"),
    'path-assign': (".path = Path('/...') assigns POSIX Path to mock",
                    "use Path(native('/...')) so str(path) is native"),
}


def find_windows_path_hazards(lines: List[str]) -> List[Tuple[int, str, str]]:
    """(lineno, pattern_name, line) for each Windows path antipattern in *lines*."""
    findings = []
    for i, line in enumerate(lines, 1):
        if line.strip().startswith('#'):
            continue
        if any(s in line for s in SAFE_INDICATORS):
            continue
        # Skip Path-to-Path comparisons
        if RE_PATH_TO_PATH.search(line) and 'Path(' in line and '.path' not in line:
            continue
        if RE_PATH_ASSIGN.search(line):
            findings.append((i, 'path-assign', line.rstrip()))
        elif RE_PATH_SPLIT.search(line):
            findings.append((i, 'path-split-on-slash', line.rstrip()))
        elif RE_FS_PATH_LITERAL.search(line) and (
            'assert' in line or 'assertEqual' in line or 'assertIn' in line
        ):
            findings.append((i, 'posix-literal', line.rstrip()))
    return findings


_PATH_CONSTRUCTORS = frozenset({'Path', 'PurePath', 'PureWindowsPath', 'PurePosixPath'})
_PATH_METHODS = frozenset({'resolve', 'absolute', 'expanduser', 'joinpath',
                           'with_suffix', 'with_name', 'relative_to'})
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_SCOPES = (*_FUNCTIONS, ast.ClassDef)


def _path_constructor(expr: ast.AST, facts: Dict[str, str]) -> bool:
    if isinstance(expr, ast.Name):
        return facts.get(expr.id) == 'constructor'
    return (isinstance(expr, ast.Attribute) and expr.attr in _PATH_CONSTRUCTORS
            and isinstance(expr.value, ast.Name) and facts.get(expr.value.id) == 'pathlib')


def _is_path(expr: Optional[ast.AST], facts: Dict[str, str]) -> bool:
    """Bounded local Path proof, not a variable-name heuristic or fixture inference."""
    if isinstance(expr, ast.Name):
        return facts.get(expr.id) == 'path'
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Div):
        return _is_path(expr.left, facts)
    if isinstance(expr, ast.Attribute) and expr.attr == 'parent':
        return _is_path(expr.value, facts)
    if isinstance(expr, ast.Call):
        return (_path_constructor(expr.func, facts)
                or (isinstance(expr.func, ast.Attribute) and expr.func.attr in _PATH_METHODS
                    and _is_path(expr.func.value, facts)))
    return False


def _envelope_call(expr: ast.AST, facts: Dict[str, str]) -> bool:
    if not isinstance(expr, ast.Call):
        return False
    func = expr.func
    builder = (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
               and func.value.id == 'ResultBuilder' and func.attr in {'create', 'create_error'})
    cli_builder = isinstance(func, ast.Name) and func.id == 'add_cli_contract_fields'
    if not (builder or cli_builder):
        return False
    source = next((kw.value for kw in expr.keywords if kw.arg == 'source'), None)
    if source is None and builder and len(expr.args) > 1:
        source = expr.args[1]
    # A string source is deliberately kept as given, including str(Path).
    return _is_path(source, facts)


def _bind_target(target: ast.AST, value: Optional[ast.AST], facts: Dict[str, str]) -> None:
    if isinstance(target, ast.Name):
        kind = 'path' if _is_path(value, facts) else 'other'
        if value is not None and _envelope_call(value, facts):
            kind = 'envelope'
        facts[target.id] = kind
    elif isinstance(target, (ast.Tuple, ast.List)):
        values = value.elts if isinstance(value, (ast.Tuple, ast.List)) else []
        for index, item in enumerate(target.elts):
            _bind_target(item, values[index] if index < len(values) else None, facts)


def _bind_import(node: ast.AST, facts: Dict[str, str], direct: bool) -> None:
    """Recognize pathlib constructor aliases in this lexical scope."""
    if isinstance(node, ast.ImportFrom) and node.module == 'pathlib':
        for alias in node.names:
            facts[alias.asname or alias.name] = (
                'constructor' if direct and alias.name in _PATH_CONSTRUCTORS else 'other')
    elif isinstance(node, ast.Import):
        for alias in node.names:
            facts[alias.asname or alias.name] = 'pathlib' if direct and alias.name == 'pathlib' else 'other'


def _bind_statement(node: ast.AST, facts: Dict[str, str], direct: bool) -> None:
    """Forget reassigned values; conditional assignments do not establish a proof."""
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        _bind_import(node, facts, direct)
    elif isinstance(node, ast.Assign):
        for target in node.targets:
            _bind_target(target, node.value if direct else None, facts)
    elif isinstance(node, ast.AnnAssign):
        _bind_target(node.target, node.value if direct else None, facts)
    elif isinstance(node, ast.AugAssign):
        _bind_target(node.target, None, facts)
    elif isinstance(node, _SCOPES):
        facts[node.name] = 'other'


def _assertion_pairs(node: ast.AST) -> Iterator[Tuple[ast.cmpop, ast.expr, ast.expr]]:
    """Only the assertion's expressions: no additional whole-file AST traversal."""
    if isinstance(node, ast.Assert):
        value = node.test
        if isinstance(value, ast.Compare):
            parts = [value.left, *value.comparators]
            yield from zip(value.ops, parts, parts[1:])
        elif isinstance(value, ast.BoolOp):
            for part in value.values:
                yield from _assertion_pairs(ast.Assert(test=part))
    elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        call = node.value
        if isinstance(call.func, ast.Attribute) and len(call.args) >= 2:
            operations = {'assertEqual': ast.Eq, 'assertIn': ast.In}
            op = operations.get(call.func.attr)
            if op is not None:
                yield op(), call.args[0], call.args[1]


def _native_path(expr: ast.AST, facts: Dict[str, str]) -> bool:
    return (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name)
            and expr.func.id == 'str' and 'str' not in facts and len(expr.args) == 1
            and _is_path(expr.args[0], facts))


def _source_field(expr: ast.AST, facts: Dict[str, str]) -> bool:
    return (isinstance(expr, ast.Subscript) and isinstance(expr.value, ast.Name)
            and facts.get(expr.value.id) == 'envelope' and isinstance(expr.slice, ast.Constant)
            and expr.slice.value == 'source')


def _native_assertions(node: ast.AST, facts: Dict[str, str]) -> Iterator[Tuple[int, str]]:
    for op, left, right in _assertion_pairs(node):
        if isinstance(op, ast.In) and _native_path(left, facts):
            if isinstance(right, ast.Attribute) and right.attr == 'stderr':
                yield left.lineno, 'native-stderr'
        elif isinstance(op, ast.Eq):
            for native, output in ((left, right), (right, left)):
                if _native_path(native, facts) and _source_field(output, facts):
                    yield native.lineno, 'native-source'


def _statement_scopes(tree: ast.Module) -> Tuple[
    Dict[ast.AST, List[ast.AST]], Dict[ast.AST, ast.AST], Dict[ast.AST, ast.AST]
]:
    nodes, parents = statement_index(tree)
    owners: Dict[ast.AST, ast.AST] = {tree: tree}
    groups: Dict[ast.AST, List[ast.AST]] = {tree: []}
    enclosing: Dict[ast.AST, ast.AST] = {}
    for node in nodes:
        owner = owners[parents[node]]
        groups[owner].append(node)
        owners[node] = owner
        if isinstance(node, _SCOPES):
            enclosing[node] = owner
            owners[node] = node
            groups[node] = []
    return groups, enclosing, parents


def find_native_output_hazards(tree: ast.Module, lines: List[str]) -> List[Tuple[int, str, str]]:
    """Strict native-path output checks, sharing the statement index and V039 exclusions."""
    groups, enclosing, parents = _statement_scopes(tree)
    contexts: Dict[ast.AST, Dict[str, str]] = {}
    found = []
    for scope, nodes in groups.items():
        facts = contexts[enclosing[scope]].copy() if scope in enclosing else {}
        if isinstance(scope, _FUNCTIONS):
            for arg in (*scope.args.posonlyargs, *scope.args.args, *scope.args.kwonlyargs):
                facts[arg.arg] = 'path' if arg.arg in {'tmp_path', 'tmpdir'} else 'other'
        for node in sorted(nodes, key=lambda item: (getattr(item, 'lineno', 0), getattr(item, 'col_offset', 0))):
            for lineno, pattern in _native_assertions(node, facts):
                line = lines[lineno - 1]
                if not (has_noqa(line, 'V039') or has_noqa(line, 'win-path')):
                    found.append((lineno, pattern, line.rstrip()))
            _bind_statement(node, facts, parents[node] is scope)
        contexts[scope] = facts
    return sorted(set(found))


def _is_scanned(path: Path) -> bool:
    return (path.name.startswith('test_') and path.suffix == '.py'
            and path.name not in SAFE_FILES)


class V039(BaseRule):
    """Detect POSIX path literals and slash-splits in tests that break on Windows.

    Severity: MEDIUM -- green on Linux and macOS, red in Windows CI.
    Category: Validation

    Detects (in ``tests/test_*.py``):
    - ``.path = Path('/fake/...')`` on a mock
    - an ``assert`` line holding a ``/fake``/``/tmp``/``/home``/``/var``/``/src``/``/usr`` path literal
    - ``x['file'].rsplit('/', 1)`` style basename extraction
    - native Path expectations about known envelope sources or positive stderr containment

    Passes:
    - ``native('/...')``, ``str(Path(...))``, ``.as_posix()``, URLs, Path-to-Path comparisons
    - explicit string-source echoes, negative leakage guards and native stdout
    - ``# noqa: win-path`` (or ``# noqa: V039``) lines and the POSIX-data test files

    The legacy literal check's str(Path(...)) exemption does not exempt a native
    Path expectation about an envelope source from the new AST check.
    """

    code = "V039"
    scope = RuleScope.CROSS_FILE
    message = "POSIX path pattern in a test that breaks on Windows"
    category = RulePrefix.V
    severity = Severity.MEDIUM
    file_patterns = ['.py']
    uri_patterns = ['^reveal://.*']
    internal = True
    version = "1.0.0"

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        if not file_path.startswith('reveal://'):
            return []
        detections: List[Detection] = []
        modules = load_sources(self, ('tests',), _is_scanned)
        for display, source in modules:
            lines = split_lines(source)
            findings = find_windows_path_hazards(lines)
            if re.search(r'\bstr\s*\(', source):
                tree = parse_test_module(self, display, source)
                if tree is not None:
                    findings.extend(find_native_output_hazards(tree, lines))
            for lineno, pattern, line in findings:
                if has_noqa(line, self.code):
                    continue
                label, advice = _LABELS[pattern]
                detections.append(self.create_detection(
                    display, lineno,
                    message=label,
                    suggestion=advice,
                    context=line.strip(),
                ))
        return detections
