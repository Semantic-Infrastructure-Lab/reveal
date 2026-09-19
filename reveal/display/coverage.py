"""Outline coverage: how much of a code file the structure actually describes.

BACK-1113. Reveal indexes declarations (functions, classes, ...). A file whose
substance is top-level script code -- PHP scripts, Python/Ruby scripts, module
bodies -- outlines as a confidently small handful of entries while most of it is
invisible. This measures the share of non-blank lines that sit inside an
indexed declaration, so renderers can say "partial" instead of looking complete
(same principle as the "No structure available" message for structure-less files).
"""

from typing import Any, Dict, List, Optional, Set

# Categories that describe code declarations. A structure with any other key
# (headings, frontmatter, rows, ...) is not code-shaped and is never assessed.
_DECLARATION_CATEGORIES = frozenset({'functions', 'classes', 'structs', 'interfaces', 'enums', 'traits'})
_LISTED_CATEGORIES = _DECLARATION_CATEGORIES | {'imports', 'constants', 'variables', 'types'}

_PHP_TAGS = frozenset({'<?php', '<?', '?>'})

# Flag only when the gap is both large and dominant: a 40-line script with one
# helper is fine, and a class-heavy file with some module-level glue is fine.
MIN_UNCOVERED_LINES = 100
MAX_COVERED_FRACTION = 0.5


def outline_coverage(structure: Dict[str, Any], lines: List[str]) -> Optional[Dict[str, Any]]:
    """Return a coverage record when the outline is partial, else None.

    `lines` is the file's source split into lines. The record has `code_lines`
    (non-blank), `covered_lines`, `uncovered_lines`, `covered_fraction` and
    `first_uncovered_line` (1-based).
    """
    if not structure or not any(structure.get(c) for c in _DECLARATION_CATEGORIES):
        return None
    if any(key not in _LISTED_CATEGORIES for key in structure):
        return None

    covered: Set[int] = set()
    for category in _LISTED_CATEGORIES:
        items = structure.get(category)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get('line'), int):
                continue
            end = item.get('line_end')
            end = end if isinstance(end, int) and end >= item['line'] else item['line']
            covered.update(range(item['line'], end + 1))

    code = [n for n, text in enumerate(lines, 1) if text.strip() and text.strip() not in _PHP_TAGS]
    if not code:
        return None
    uncovered = [n for n in code if n not in covered]
    fraction = 1 - len(uncovered) / len(code)
    if len(uncovered) < MIN_UNCOVERED_LINES or fraction >= MAX_COVERED_FRACTION:
        return None
    return {
        'code_lines': len(code),
        'covered_lines': len(code) - len(uncovered),
        'uncovered_lines': len(uncovered),
        'covered_fraction': round(fraction, 3),
        'first_uncovered_line': uncovered[0],
    }


def format_coverage_warning(cov: Dict[str, Any], path: Any) -> List[str]:
    """Text-mode lines for a coverage record from `outline_coverage`."""
    pct = min(99, round(100 * cov['uncovered_lines'] / cov['code_lines']))
    return [
        f"⚠️  Partial outline: {cov['uncovered_lines']} of {cov['code_lines']} code lines "
        f"({pct}%) are top-level code outside any listed function/class "
        f"(first at line {cov['first_uncovered_line']}).",
        f"   Read it with: reveal \"{path}\" :{cov['first_uncovered_line']}-<end>  |  "
        f"reveal \"{path}\" --grep 'pattern'",
    ]
