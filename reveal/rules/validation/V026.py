"""
V026: Path-handling convention (portability).

Flags two Windows/macOS portability bug classes fixed by BACK-493 so they
cannot silently creep back in:

1. ``str(x.relative_to(...))`` (or any ``str(...)`` wrapping a
   ``.relative_to(`` call) — emits backslashes on Windows. Use
   ``to_posix()`` from ``reveal/utils/path_utils.py`` instead.
   The same leak one hop away is flagged too (BACK-1739): inside one function,
   ``rel = x.relative_to(...)`` followed by ``str(rel)`` or ``f"{rel}"``.
   Suppress a same-platform, non-output use with ``# noqa: V026 -- reason``.
2. Hardcoded POSIX system-root literals (``'/tmp'``, ``'/var'``, ``'/'``, ...)
   compared or collected outside ``path_utils.py`` itself — silently no-ops
   on Windows/macOS. Use ``is_unsafe_scan_root()`` instead.

Examples:
    reveal reveal://. --check --select V026  # Check reveal's own source
"""

import ast
import re
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root, has_noqa, is_dev_checkout
from ...utils.path_utils import to_posix, _STATIC_UNSAFE_ROOTS
from reveal.utils.lines import split_lines

# Files exempt from these checks: they're the canonical implementation the
# rule tells everyone else to route through, or this rule's own source
# (whose docstrings/comments quote the very patterns it detects as examples).
_EXEMPT_FILENAMES = {'path_utils.py', '__init__.py', 'V026.py'}

# str(...) wrapping a .relative_to( call, e.g. str(p.relative_to(root)).
_STR_RELATIVE_TO_RE = re.compile(r'\bstr\([^)\n]*\.relative_to\(')

# A hardcoded root literal used in an equality/membership comparison, e.g.
# `path == '/tmp'` or `'/tmp' == path` or `{'/tmp', '/var', ...}`. The bare
# anchor '/' is deliberately excluded — it's indistinguishable from a URL/URI
# path root (e.g. nginx `location == '/'`) by regex alone, and
# is_unsafe_scan_root() already checks the platform anchor via
# Path(path).anchor rather than a literal comparison.
_ROOT_LITERALS = sorted(
    (r for r in _STATIC_UNSAFE_ROOTS if r != '/'), key=len, reverse=True
)
_ROOT_LITERAL_RE = re.compile(
    r'''(?:==\s*['"](%s)['"]|['"](%s)['"]\s*==)'''
    % ('|'.join(re.escape(r) for r in _ROOT_LITERALS),
       '|'.join(re.escape(r) for r in _ROOT_LITERALS))
)


_Block = Tuple[int, ...]
_Event = Tuple[int, int, str, str, _Block]  # (lineno, col, kind, name, block)


def _own_scope_nodes(fn: ast.AST) -> Iterator[Tuple[ast.AST, _Block]]:
    """Yield ``(node, block)`` for *fn*'s body without entering nested scopes.

    *block* identifies the statement list the node sits in, as a tuple of
    enclosing statement-list ids, so a caller can tell whether one statement
    is guaranteed to run before another (its block is a prefix of the other's).
    """
    stack: List[Tuple[ast.AST, _Block]] = [(fn, ())]
    while stack:
        parent, block = stack.pop()
        for _name, value in ast.iter_fields(parent):
            is_stmts = isinstance(value, list) and value and isinstance(value[0], ast.stmt)
            child_block = block + (id(value),) if is_stmts else block
            for child in (value if isinstance(value, list) else [value]):
                if not isinstance(child, ast.AST):
                    continue
                yield child, child_block
                if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    stack.append((child, child_block))


def _is_relative_to_call(value: ast.AST) -> bool:
    return (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
            and value.func.attr == 'relative_to')


def _scope_events(fn: ast.AST) -> List[_Event]:
    """Assignments to names and str()/f-string uses of bare names in one function."""
    events: List[_Event] = []
    for node, block in _own_scope_nodes(fn):
        if isinstance(node, ast.Assign):
            kind = 'taint' if _is_relative_to_call(node.value) else 'clear'
            for target in node.targets:
                if isinstance(target, ast.Name):
                    events.append((node.lineno, node.col_offset, kind, target.id, block))
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id == 'str' and len(node.args) == 1
              and isinstance(node.args[0], ast.Name)):
            events.append((node.lineno, node.col_offset, 'use', node.args[0].id, block))
        elif isinstance(node, ast.FormattedValue) and isinstance(node.value, ast.Name):
            events.append((node.lineno, node.col_offset, 'use', node.value.id, block))
    return sorted(events, key=lambda e: e[:4])


def _leak_lines(events: List[_Event]) -> List[int]:
    tainted: Set[str] = set()
    cleared: Dict[str, List[_Block]] = {}
    lines: List[int] = []
    for lineno, _col, kind, name, block in events:
        if kind == 'taint':
            tainted.add(name)
            cleared[name] = []
        elif kind == 'clear':
            cleared.setdefault(name, []).append(block)
        elif name in tainted and not any(block[:len(c)] == c for c in cleared[name]):
            lines.append(lineno)
    return lines


def relative_to_leaks(content: str) -> List[int]:
    """Line numbers where a ``.relative_to()`` local is str()'d or f-string'd.

    One hop, one function: ``rel = a.relative_to(b)`` makes ``rel`` a leak
    candidate until a rebinding that is guaranteed to run before the use (same
    or enclosing block, so an ``except`` branch's ``rel = fpath`` does not
    count); ``str(rel)`` and ``f"{rel}"`` on a candidate leak the separator.
    """
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return []
    lines: List[int] = []
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lines.extend(_leak_lines(_scope_events(fn)))
    return sorted(set(lines))


class V026(BaseRule):
    """Detect path-str-portability and hardcoded-root regressions.

    Severity: HIGH — this is a silent cross-platform correctness bug, not a
    style nit; it passes every test on Linux and only breaks on Windows/macOS.
    Category: Validation

    Detects:
    - ``str(x.relative_to(...))`` instead of ``to_posix(x.relative_to(...))``
    - the same through a local (``rel = x.relative_to(...); str(rel)`` or
      ``f"{rel}"``) inside one function (BACK-1739)
    - Hardcoded POSIX root-literal comparisons instead of
      ``is_unsafe_scan_root()``

    Passes:
    - ``reveal/utils/path_utils.py`` itself (the canonical implementation)
    - Files with neither pattern
    """

    code = "V026"
    message = "Path-handling convention violation (use to_posix()/is_unsafe_scan_root())"
    category = RulePrefix.V
    severity = Severity.HIGH
    file_patterns = ['.py']
    uri_patterns = ['^reveal://.*']
    internal = True
    version = "1.0.0"

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        if file_path.startswith('reveal://'):
            return self._check_reveal_source()
        return []

    def _check_reveal_source(self) -> List[Detection]:
        reveal_root = find_reveal_root()
        if not reveal_root or not is_dev_checkout(reveal_root):
            return []

        detections: List[Detection] = []
        # boundary-ok: walker -- V-series: reveal's own source
        for py_file in sorted(reveal_root.rglob('*.py')):
            if py_file.name in _EXEMPT_FILENAMES:
                continue
            try:
                content = py_file.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue

            try:
                display_path = to_posix(py_file.relative_to(reveal_root.parent))
            except ValueError:
                display_path = str(py_file)

            detections.extend(self._scan_content(display_path, content))

        return detections

    def _scan_content(self, display_path: str, content: str) -> List[Detection]:
        detections: List[Detection] = []
        source_lines = split_lines(content)
        for lineno in relative_to_leaks(content):
            line = source_lines[lineno - 1] if lineno <= len(source_lines) else ''
            if has_noqa(line, self.code):
                continue
            detections.append(self.create_detection(
                display_path, lineno,
                message="A .relative_to() result is rendered with str()/f-string "
                        "— emits backslashes on Windows",
                suggestion="Use to_posix(rel) (or as_spelled) from "
                           "reveal/utils/path_utils.py, or add "
                           "'# noqa: V026 -- <reason>' for a same-platform "
                           "non-output use",
                context=line.strip(),
            ))
        for lineno, line in enumerate(source_lines, start=1):
            if has_noqa(line, self.code):
                continue
            if _STR_RELATIVE_TO_RE.search(line):
                detections.append(self.create_detection(
                    display_path, lineno,
                    message="str() wraps a .relative_to() call — emits "
                            "backslashes on Windows",
                    suggestion="Use to_posix(x.relative_to(...)) from "
                               "reveal/utils/path_utils.py instead of str(...)",
                    context=line.strip(),
                ))
            if _ROOT_LITERAL_RE.search(line):
                detections.append(self.create_detection(
                    display_path, lineno,
                    message="Hardcoded POSIX system-root literal compared "
                            "directly — no-ops on Windows/macOS",
                    suggestion="Use is_unsafe_scan_root(path) from "
                               "reveal/utils/path_utils.py instead of "
                               "comparing against a literal root string",
                    context=line.strip(),
                ))
        return detections
