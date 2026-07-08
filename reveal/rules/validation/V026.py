"""
V026: Path-handling convention (portability).

Flags two Windows/macOS portability bug classes fixed by BACK-493 so they
cannot silently creep back in:

1. ``str(x.relative_to(...))`` (or any ``str(...)`` wrapping a
   ``.relative_to(`` call) — emits backslashes on Windows. Use
   ``to_posix()`` from ``reveal/utils/path_utils.py`` instead.
2. Hardcoded POSIX system-root literals (``'/tmp'``, ``'/var'``, ``'/'``, ...)
   compared or collected outside ``path_utils.py`` itself — silently no-ops
   on Windows/macOS. Use ``is_unsafe_scan_root()`` instead.

Examples:
    reveal reveal://. --check --select V026  # Check reveal's own source
"""

import re
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root, is_dev_checkout
from ...utils.path_utils import to_posix, _STATIC_UNSAFE_ROOTS

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


class V026(BaseRule):
    """Detect path-str-portability and hardcoded-root regressions.

    Severity: HIGH — this is a silent cross-platform correctness bug, not a
    style nit; it passes every test on Linux and only breaks on Windows/macOS.
    Category: Validation

    Detects:
    - ``str(x.relative_to(...))`` instead of ``to_posix(x.relative_to(...))``
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
        for lineno, line in enumerate(content.splitlines(), start=1):
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
