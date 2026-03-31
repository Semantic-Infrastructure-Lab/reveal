"""Scan test files for patterns that break on Windows.

Catches two categories of antipattern before they reach CI:

  1. ``.path = Path('/...')`` assignments — assigning a POSIX absolute Path to
     a mock's ``.path`` attribute.  Production code stringifies it with
     ``str(path)`` which yields backslashes on Windows.  Use
     ``Path(native('/fake/x.py'))`` or set ``.path`` to the result of
     ``Path(native(...))`` so the mock carries a native Path.

  2. POSIX absolute path literals in assertions that compare filesystem paths —
     e.g. ``assert result['file'] == '/fake/x.py'``.  Use
     ``native('/fake/x.py')`` from ``tests/conftest.py`` instead.

False-positive suppression:
  Append ``# noqa: win-path`` to any line the checker flags incorrectly.
  Common safe patterns the checker may still flag:
    - ``assertEqual(x, Path('/...')`` — Path-to-Path comparison (already safe)
    - String values that production code stores as-is (not via Path)
    - URI path components (not filesystem paths)

Run:
    python scripts/check_windows_compat.py          # exits 1 on findings
    python scripts/check_windows_compat.py --warn   # exits 0 (non-blocking)
    python scripts/check_windows_compat.py --strict # same as default
"""

import re
import sys
import argparse
from pathlib import Path


# Test files whose path assertions are intentionally POSIX data content
# (nginx configs, SSL certs, ZIP archives, URI specs — never filesystem paths):
SAFE_FILES = {
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
}

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
# e.g. assertEqual(some_path, Path('/home/user/...'))
RE_PATH_TO_PATH = re.compile(
    r"""(?:assertEqual|==)\s*\(?.*?Path\("""
)

# ── Pattern 1: .path = Path('/...')  on a mock/object ────────────────────────
# Only flags Path() objects (not plain strings) assigned to .path
RE_PATH_ASSIGN = re.compile(
    r"""\.path\s*=\s*Path\(['"]/(fake|tmp|home|var|src|usr)"""
)

# ── Pattern 2: assertion with absolute POSIX filesystem path literal ──────────
# Matches == '/fake/...' or '/tmp/...' in x  but NOT:
#   - URI-style paths (/api/v1/users — no file extension and no subdir depth ≥ 3)
#   - Single-segment paths (/etc)
#   - Decorator/route strings: @app.route('/...')
# Heuristic: path must contain at least 2 segments AND look like a filesystem path
# (ends with .py/.sh/.md/.db/.conf/.pem etc, or contains /fake/ /tmp/ /home/ /var/)
RE_FS_PATH_LITERAL = re.compile(
    r"""['"]"""                          # opening quote
    r"""(/(?:fake|tmp|home|var|src|usr)"""  # starts with a filesystem-root segment
    r"""(?:/[^'"]+)+)"""                 # at least one more segment
    r"""['"]"""                          # closing quote
)


def check_file(path: Path) -> list[tuple[int, str, str]]:
    """Return list of (lineno, pattern_name, line) findings."""
    findings = []
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except (OSError, UnicodeDecodeError):
        return findings

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if any(s in line for s in SAFE_INDICATORS):
            continue
        # Skip Path-to-Path comparisons
        if RE_PATH_TO_PATH.search(line) and 'Path(' in line and '.path' not in line:
            continue
        # Skip string assignments (only flag Path() object assignments)
        # e.g. analyzer.path = '/tmp/...' is safe (string, not Path object)

        if RE_PATH_ASSIGN.search(line):
            findings.append((i, 'path-assign', line.rstrip()))
        elif RE_FS_PATH_LITERAL.search(line) and (
            'assert' in line or 'assertEqual' in line or 'assertIn' in line
        ):
            findings.append((i, 'posix-literal', line.rstrip()))

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--warn', action='store_true',
                        help='Print warnings but exit 0 (non-blocking)')
    parser.add_argument('--strict', action='store_true',
                        help='Exit 1 on any finding (default behaviour)')
    parser.add_argument('paths', nargs='*',
                        help='Files or directories to scan (default: tests/)')
    args = parser.parse_args()

    root = Path(__file__).parent.parent
    scan_roots = [Path(p) for p in args.paths] if args.paths else [root / 'tests']

    total = 0
    for scan_root in scan_roots:
        test_files = (
            [scan_root] if scan_root.is_file()
            else sorted(scan_root.rglob('test_*.py'))
        )
        for tf in test_files:
            if tf.name in SAFE_FILES:
                continue
            findings = check_file(tf)
            if findings:
                rel = tf.relative_to(root)
                for lineno, pattern, line in findings:
                    label = (
                        'POSIX path literal in assertion'
                        if pattern == 'posix-literal'
                        else '.path = Path(\'/...\') assigns POSIX Path to mock'
                    )
                    print(f'{rel}:{lineno}: [{label}]')
                    print(f'  {line.strip()}')
                    if pattern == 'posix-literal':
                        print(f'  → use native(\'/...\') from tests/conftest.py')
                    else:
                        print(f'  → use Path(native(\'/...\')) so str(path) is native')
                    print()
                    total += 1

    blocking = not args.warn
    if total:
        severity = 'ERROR' if blocking else 'WARNING'
        print(f'{severity}: {total} Windows path antipattern(s) found.')
        if blocking:
            print('Suppress false positives with  # noqa: win-path')
        return 1 if blocking else 0

    print('✓ No Windows path antipatterns found.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
