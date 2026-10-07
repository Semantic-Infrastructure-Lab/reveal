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

Examples:
    reveal reveal:// --check --select V039
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import has_noqa, load_sources

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

    Passes:
    - ``native('/...')``, ``str(Path(...))``, ``.as_posix()``, URLs, Path-to-Path comparisons
    - ``# noqa: win-path`` (or ``# noqa: V039``) lines and the POSIX-data test files
    """

    code = "V039"
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
        for display, source in load_sources(self, ('tests',), _is_scanned):
            for lineno, pattern, line in find_windows_path_hazards(source.splitlines()):
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
