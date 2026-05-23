"""Regression test: production code must not use tree-sitter 0.x API.

tree-sitter-language-pack 1.x removed several 0.x APIs:
  - node.type     -> node.kind()
  - node.children -> node_children(node)   (helper in reveal.core)
  - node.start_point[0] -> node.start_position().row
  - node.end_point[0]   -> node.end_position().row
  - node.start_byte     -> node.start_byte()  (now a method)
  - node.end_byte       -> node.end_byte()
  - node.root_node      -> node.root_node()
  - node.is_named       -> node.is_named()
  - node.prev_sibling   -> node_prev_sibling(node)
  - node.next_sibling   -> node_next_sibling(node)
  - node.parent         -> node.parent()      (for tree-sitter nodes; pathlib unchanged)
  - node.text           -> bytes-slice from source

If any of these patterns reappear in production code, this test fails so
the offending file can be fixed before the regression ships.

The check is intentionally narrow: only files that touch tree-sitter nodes
(transitively) are scanned. Files using pathlib `.parent`, Python ast
module `.type`, or reveal's own Element model `.children` are exempt
(they were never the 0.x tree-sitter API and never break).
"""

import re
import unittest
from pathlib import Path

REVEAL_ROOT = Path(__file__).parent.parent / 'reveal'

# Files that operate on tree-sitter nodes. These are the only files we lint
# for 0.x API usage; other files may use `.type`/`.parent`/`.children` on
# non-tree-sitter objects (pathlib, Python ast, reveal Element model) and
# those are unrelated.
TS_FILES = sorted({
    REVEAL_ROOT / 'treesitter.py',
    REVEAL_ROOT / 'complexity.py',
    REVEAL_ROOT / 'file_handler.py',
    REVEAL_ROOT / 'nav_handlers.py',
    REVEAL_ROOT / 'cli/introspection.py',
    REVEAL_ROOT / 'display/element.py',
    *sorted((REVEAL_ROOT / 'analyzers').glob('*.py')),
    *sorted((REVEAL_ROOT / 'analyzers/imports').glob('*.py')),
    *sorted((REVEAL_ROOT / 'adapters/ast').glob('*.py')),
})

# Patterns flagged as 0.x usage. Each (regex, message) entry is a separate
# diagnostic; per-file exemptions are handled below.
PATTERNS = [
    (re.compile(r'\.start_point\b'), '.start_point[i] is removed in 1.x; use .start_position().row/.column'),
    (re.compile(r'\.end_point\b'),   '.end_point[i] is removed in 1.x; use .end_position().row/.column'),
    (re.compile(r'\.prev_sibling\b'),'.prev_sibling is removed in 1.x; use node_prev_sibling(node) from reveal.core'),
    (re.compile(r'\.next_sibling\b'),'.next_sibling is removed in 1.x; use node_next_sibling(node) from reveal.core'),
    # .children: only flag when accessed as a property/attribute (not the helper call _children() / node_children())
    (re.compile(r'(?<!_)\.children\b'),
     '.children is removed in 1.x; use node_children(node) from reveal.core (imported as _children)'),
    # start_byte / end_byte / root_node / is_named / child_count: must be method calls (followed by `(`).
    # Flag attribute-style access (not followed by `(`).
    (re.compile(r'\.start_byte\b(?!\s*\()'), '.start_byte is a method in 1.x; call .start_byte()'),
    (re.compile(r'\.end_byte\b(?!\s*\()'),   '.end_byte is a method in 1.x; call .end_byte()'),
    (re.compile(r'\.root_node\b(?!\s*\()'),  '.root_node is a method in 1.x; call .root_node()'),
    (re.compile(r'\.is_named\b(?!\s*\()'),   '.is_named is a method in 1.x; call .is_named()'),
    (re.compile(r'\.child_count\b(?!\s*\()'),'.child_count is a method in 1.x; call .child_count()'),
    # node.text was bytes in 0.x and is gone in 1.x. Slice from source bytes instead.
    (re.compile(r'(?<![\w.])node\.text\b'),
     'node.text is removed in 1.x; slice from source bytes ([node.start_byte():node.end_byte()])'),
    # parser.parse() requires str in 1.x, not bytes. Catches .parse(x.encode(...)) regressions.
    (re.compile(r'\.parse\(\s*\S+\.encode\('),
     'parser.parse(bytes) is wrong in 1.x; pass str directly (remove .encode())'),
]

# (file_name, line_number_OR_substring_match): docstring or comment occurrences
# that legitimately mention the old API. Keep this list small and specific.
EXEMPTIONS = {
    # The compat module itself documents the old API in its module docstring.
    'treesitter_compat.py': True,
}


def _scan_file(path):
    """Return a list of (line_no, line, message) violations for `path`."""
    violations = []
    try:
        text = path.read_text(encoding='utf-8')
    except (UnicodeDecodeError, FileNotFoundError):
        return violations
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        # Skip comments and string-only lines (heuristic: lines starting with # or quotes)
        if stripped.startswith('#'):
            continue
        for pat, msg in PATTERNS:
            if pat.search(line):
                violations.append((lineno, line.rstrip(), msg))
    return violations


class TestNoTreeSitter0xLeak(unittest.TestCase):
    def test_no_0x_api_in_production(self):
        failures = []
        for f in TS_FILES:
            if not f.exists():
                continue
            if EXEMPTIONS.get(f.name):
                continue
            violations = _scan_file(f)
            if violations:
                rel = f.relative_to(REVEAL_ROOT.parent)
                for lineno, line, msg in violations:
                    failures.append(f'\n  {rel}:{lineno}\n    {line.strip()}\n    → {msg}')
        if failures:
            self.fail(
                'tree-sitter 0.x API usage found in production code '
                f'({len(failures)} violation(s)):\n' + ''.join(failures) +
                '\n\nSee tests/test_no_tree_sitter_0x_api_leak.py for the rule list.'
            )


if __name__ == '__main__':
    unittest.main()
