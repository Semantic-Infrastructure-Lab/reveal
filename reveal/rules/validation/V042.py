"""
V042: Test reads an env:// variable that only POSIX sets.

Flags, in reveal's own tests/, a string literal naming ``env://HOME``, ``env://USER``,
``env://SHELL``, ``env://TERM`` or ``env://LOGNAME``. Windows runners have none of
them, so a test that reads one fails there only (BACK-1554 in 69408a70, BACK-1556 in
c95b2478); worse, a test that never checks the URI succeeded passes there while its
assertions check nothing. Set a variable the test owns (``monkeypatch.setenv`` /
``patch.dict(os.environ)``) and read that, or read ``env://PATH``.

This is the scan of ``tests/test_portable_env_vars.py`` moved into the V-series
(BACK-1707): same literal matcher (docstrings are not flagged; a rendered
``env://HOME:/home/user`` line is not an input URI; ``env://HOMEDRIVE`` is another
variable), same files (``test_*.py`` and ``conftest.py`` outside ``tests/fixtures/``).

Suppress a reviewed site with ``# noqa: V042 <why>`` on the reported line (the
literal's first line).

Examples:
    reveal reveal:// --check --select V042
"""

import ast
import re
from pathlib import PurePath
from typing import Any, Dict, List, Optional, Set, Tuple

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import has_noqa, load_sources, parse_test_module
from reveal.utils.lines import split_lines

POSIX_ONLY_VARS = ('HOME', 'USER', 'SHELL', 'TERM', 'LOGNAME')

# An input URI: the variable name is not followed by ':' (a rendered
# "env://HOME:/home/user" line from mocked data reads no environment).
_POSIX_ENV_URI = re.compile(r'env://(' + '|'.join(POSIX_ONLY_VARS) + r')(?![\w:])')


def _docstring_nodes(tree: ast.AST) -> Set[ast.AST]:
    nodes: Set[ast.AST] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                nodes.add(body[0].value)
    return nodes


def find_posix_env_uris(tree: ast.Module) -> List[Tuple[int, str]]:
    """(lineno, var) for each non-docstring string literal naming a POSIX-only env:// URI."""
    docstrings = _docstring_nodes(tree)
    found = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and node not in docstrings):
            for match in _POSIX_ENV_URI.finditer(node.value):
                found.append((node.lineno, match.group(1)))
    return sorted(found)


def _is_scanned(rel: PurePath) -> bool:
    # fixtures are sample sources, not tests
    return ((rel.name.startswith('test_') or rel.name == 'conftest.py')
            and rel.parts[:2] != ('tests', 'fixtures'))


class V042(BaseRule):
    """Detect tests that feed reveal an env:// URI for a variable Windows does not set.

    Severity: MEDIUM -- green on Linux and macOS, red (or vacuous) on Windows.
    Category: Validation

    Detects (in ``tests/test_*.py`` and ``conftest.py``, not ``tests/fixtures/``):
    - a non-docstring string literal containing ``env://HOME``, ``USER``, ``SHELL``,
      ``TERM`` or ``LOGNAME``

    Passes:
    - ``env://PATH`` or a variable the test sets; docstrings; rendered
      ``env://HOME:/value`` lines; other variables sharing a prefix (``env://HOMEDRIVE``)
    """

    code = "V042"
    message = "Test reads an env:// variable that only POSIX sets"
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
        for display, source in load_sources(self, ('tests',), _is_scanned):
            tree = parse_test_module(self, display, source)
            if tree is None:
                continue
            lines = split_lines(source)
            for lineno, var in find_posix_env_uris(tree):
                line = lines[lineno - 1]
                if has_noqa(line, self.code):
                    continue
                detections.append(self.create_detection(
                    display, lineno,
                    message=f"env://{var} is not set on Windows runners",
                    suggestion="Set a variable the test owns (monkeypatch.setenv / "
                               "patch.dict(os.environ)) and read that, or read env://PATH",
                    context=line.strip(),
                ))
        return detections
