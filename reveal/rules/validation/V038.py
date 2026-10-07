"""
V038: Raw subprocess bytes asserted on newlines without normalising.

Flags a tests/ module that runs a subprocess in byte mode (no ``text=``,
``universal_newlines=`` or ``encoding=``) and asserts on the bytes it captured
with a ``\\r`` or ``\\n`` literal -- ``b'\\r' not in r.stdout``,
``r.stdout.count(b'\\n')``, ``r.stdout == b'a\\r\\n'`` -- in a module with neither a
Windows guard (``sys.platform == 'win32'``, ``os.name == 'nt'``) nor a
``.replace(b'\\r\\n', ...)`` that drops the platform's own terminator.

Windows text-mode stdout writes every ``\\n`` as ``\\r\\n``, even for LF input, so
such a test passes on Linux and macOS and fails on every Windows job
(BACK-1706's tests/test_crlf_sources_back1706.py, fixed by 79a576c9 with
``_own_newlines``). The rule is a module-level heuristic: it does not trace
which captured bytes reach which assertion beyond names assigned from a
subprocess call or its ``.stdout``/``.stderr``.

Suppress a reviewed site with ``# noqa: V038 <why>`` on the reported line.

Examples:
    reveal reveal:// --check --select V038
"""

import ast
import re
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import has_noqa, load_test_suite, parse_test_module
from reveal.utils.lines import split_lines

# A Windows guard, or the normalising replace of the platform's own pair.
_GUARD_RE = re.compile(
    r'''sys\.platform\s*[!=]=\s*['"]win|sys\.platform\.startswith\(\s*['"]win'''
    r'''|os\.name\s*[!=]=\s*['"]nt['"]|platform\.system\(\)\s*[!=]=\s*['"]Windows'''
    r'''|\.replace\(\s*b['"]\\r\\n['"]''')

# Cheap source pre-filters: only a module with a subprocess call and a bytes
# literal holding a newline escape (or a ``splitlines(`` call) is parsed.
_SUBPROCESS_HINT = re.compile(r'\bsubprocess\b|\bcheck_output\b|\bPopen\b')
_BYTES_NEWLINE_HINT = re.compile(
    r'''\bb(?:'[^'\n]*\\[rn]|"[^"\n]*\\[rn])|splitlines\(''')

_SUBPROCESS_FUNCS = frozenset({'run', 'check_output', 'Popen', 'call', 'check_call'})
_TEXT_KEYWORDS = frozenset({'text', 'universal_newlines', 'encoding', 'errors'})
_PIPE_ATTRS = frozenset({'stdout', 'stderr'})
# bytes methods whose literal argument is compared with the captured bytes
_LITERAL_METHODS = frozenset({'count', 'split', 'rsplit', 'partition', 'rpartition',
                              'startswith', 'endswith', 'find', 'rfind', 'index'})
_EXACT_METHODS = frozenset({'count', 'split', 'rsplit', 'partition', 'rpartition',
                            'startswith'})


def _is_raw_subprocess_call(node: ast.AST) -> bool:
    """A subprocess.run/check_output/Popen/... call with no text-mode keyword and no
    ``**kwargs`` (which may carry one)."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, 'id', '')
    if name not in _SUBPROCESS_FUNCS:
        return False
    if isinstance(func, ast.Attribute) and not (
            isinstance(func.value, ast.Name) and func.value.id == 'subprocess'):
        return False
    return all(kw.arg is not None and kw.arg not in _TEXT_KEYWORDS for kw in node.keywords)


def _is_pipe_read(node: ast.AST) -> bool:
    """``x.stdout`` / ``x.stderr`` (also ``x.stdout.read()``'s receiver)."""
    return isinstance(node, ast.Attribute) and node.attr in _PIPE_ATTRS


def _captured_names(fn: ast.AST) -> Set[str]:
    """Names assigned, in this scope, from a subprocess call or a ``.stdout``/``.stderr``."""
    names: Set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and node.value:
            value = node.value
            if any(_is_pipe_read(n) or _is_raw_subprocess_call(n) for n in ast.walk(value)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names.update(n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name))
    return names


def _touches_capture(node: ast.AST, names: Set[str]) -> bool:
    return any(_is_pipe_read(n) or _is_raw_subprocess_call(n)
               or (isinstance(n, ast.Name) and n.id in names) for n in ast.walk(node))


def _bytes_newline(node: ast.AST) -> Optional[bytes]:
    if isinstance(node, ast.Constant) and isinstance(node.value, bytes):
        return node.value if (b'\r' in node.value or b'\n' in node.value) else None
    return None


def _platform_sensitive(literal: bytes, exact: bool) -> bool:
    """A literal whose match depends on how the platform ends a line: any CR, or a LF
    that is not just a trailing terminator (``b'\\n' in out`` holds on Windows too);
    an exact comparison/count/split is sensitive to a bare LF as well."""
    return b'\r' in literal or (b'\n' in literal if exact else b'\n' in literal.strip(b'\n'))


def _comparisons(node: ast.Compare, names: Set[str]) -> Iterator[Tuple[int, str]]:
    operands = [node.left, *node.comparators]
    for op, left, right in zip(node.ops, operands, operands[1:]):
        exact = isinstance(op, (ast.Eq, ast.NotEq))
        if not (exact or isinstance(op, (ast.In, ast.NotIn))):
            continue
        for lit_side, other in ((left, right), (right, left)):
            literal = _bytes_newline(lit_side)
            if (literal is not None and _platform_sensitive(literal, exact)
                    and _touches_capture(other, names)):
                yield node.lineno, f"comparison with {literal!r}"


def _method_calls(node: ast.Call, names: Set[str]) -> Iterator[Tuple[int, str]]:
    method = node.func.attr  # type: ignore[attr-defined]
    if not _touches_capture(node.func.value, names):  # type: ignore[attr-defined]
        return
    if method in _LITERAL_METHODS and node.args:
        literal = _bytes_newline(node.args[0])
        if literal is not None and _platform_sensitive(literal, method in _EXACT_METHODS):
            yield node.lineno, f".{method}({literal!r})"
    elif method == 'splitlines' and (
            any(isinstance(a, ast.Constant) and a.value is True for a in node.args)
            or any(k.arg == 'keepends' for k in node.keywords)):
        yield node.lineno, ".splitlines(keepends=True)"


def _assertions(scope: ast.AST, names: Set[str]) -> Iterator[Tuple[int, str]]:
    for node in ast.walk(scope):
        if isinstance(node, ast.Compare):
            yield from _comparisons(node, names)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            yield from _method_calls(node, names)


def _scopes(tree: ast.Module) -> Iterator[ast.AST]:
    """Each function (its own capture names), then module-level code once."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node
    yield tree


class V038(BaseRule):
    """Detect tests asserting on raw subprocess bytes' newlines without normalising.

    Severity: MEDIUM -- green on Linux and macOS, red in every Windows CI job.
    Category: Validation

    Detects:
    - A tests/ module with a byte-mode subprocess call AND an assertion on the
      captured bytes against a ``\\r``/``\\n`` literal AND no Windows guard and no
      ``.replace(b'\\r\\n', ...)``

    Passes:
    - Modules that guard on ``sys.platform``/``os.name`` or normalise the pair
    - Text-mode runs (``text=True``, ``encoding=``), assertions on parsed (JSON)
      values, bytes that never came from a subprocess
    - ``b'\\n' in out`` and trailing-terminator checks (true on Windows too)
    """

    code = "V038"
    message = "Raw subprocess bytes asserted on newlines without normalising \\r\\n"
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
        for display, source in load_test_suite(self):
            if (_GUARD_RE.search(source) or not _SUBPROCESS_HINT.search(source)
                    or not _BYTES_NEWLINE_HINT.search(source)):
                continue
            tree = parse_test_module(self, display, source)
            if tree is None or not any(_is_raw_subprocess_call(n) for n in ast.walk(tree)):
                continue
            lines = split_lines(source)
            found = sorted({hit for scope in _scopes(tree)
                            for hit in _assertions(scope, _captured_names(scope))})
            for lineno, what in found:
                line = lines[lineno - 1]
                if has_noqa(line, self.code):
                    continue
                detections.append(self.create_detection(
                    display, lineno,
                    message=f"{what} on raw subprocess bytes: Windows text-mode stdout "
                            "writes every \\n as \\r\\n, even for LF input",
                    suggestion="Drop the platform's own pair first "
                               "(data.replace(b'\\r\\n', b'\\n') when sys.platform == 'win32'), "
                               "or run with text=True, or assert on parsed (JSON) values",
                    context=line.strip(),
                ))
        return detections
