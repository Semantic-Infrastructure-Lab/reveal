"""surface:// language x category coverage matrix (BACK-1332).

A surface count of 0 means two different things: "scanned, found nothing" and
"this language has no detector for that category". This module says which cells
are which, so a scan can report `not implemented` instead of a silent 0.

Each cell has one of four statuses:

- `rules`: driven by a rule table (`surface_rules.rule_categories`). Derived live,
  never declared here, so a migrated category cannot go stale.
- `scanner`: detected by the language's hand-coded scanner. Declared in
  `_HAND_CODED`; `tests/test_surface_matrix.py` re-derives the same set from the
  scanner source, so the declaration cannot drift from the code.
- `not_applicable`: cannot exist for the language. Declared in `_NOT_APPLICABLE`.
- `not_implemented`: everything else.

Moving a category onto a rule table (BACK-1333/1334) means deleting its name from
that language's `_HAND_CODED` entry in the same change.
"""

from typing import Dict, Iterable, List, Tuple

from .surface_rules import rule_categories

CATEGORIES: Tuple[str, ...] = ('cli', 'http', 'mcp', 'env', 'network', 'db', 'sdk', 'fs', 'subprocess')

RULES = 'rules'
SCANNER = 'scanner'
NOT_APPLICABLE = 'not_applicable'
NOT_IMPLEMENTED = 'not_implemented'

# Matrix column -> the scanner module that owns it. `typescript` covers
# .ts/.tsx/.js/.jsx; rule tables call the same column `typescript`/`tsx`.
SCANNER_MODULES: Dict[str, str] = {
    'python': 'nav_surface',
    'typescript': 'nav_surface_ts',
    'java': 'nav_surface_java',
    'csharp': 'nav_surface_csharp',
    'php': 'nav_surface_php',
    'swift': 'nav_surface_swift',
    'kotlin': 'nav_surface_kotlin',
    'ruby': 'nav_surface_ruby',
    'go': 'nav_surface_go',
    'rust': 'nav_surface_rust',
    'cpp': 'nav_surface_cpp',
}

_IMPORT_TAXONOMY = ('network', 'db', 'sdk')

_HAND_CODED: Dict[str, frozenset] = {
    'python': frozenset({'cli', 'http', 'mcp', 'env', 'fs', *_IMPORT_TAXONOMY}),
    'typescript': frozenset({'cli', 'http', 'mcp', 'env', 'fs', 'subprocess', *_IMPORT_TAXONOMY}),
    'java': frozenset({'cli', 'http', *_IMPORT_TAXONOMY}),
    'csharp': frozenset({'cli', 'http', *_IMPORT_TAXONOMY}),
    'php': frozenset({'http', 'env', 'fs', 'subprocess', *_IMPORT_TAXONOMY}),
    'swift': frozenset({'cli', 'http', 'env', *_IMPORT_TAXONOMY}),
    'kotlin': frozenset({'cli', 'http', *_IMPORT_TAXONOMY}),
    'ruby': frozenset({'http', 'env', *_IMPORT_TAXONOMY}),
    'go': frozenset({'cli', 'http', *_IMPORT_TAXONOMY}),
    'rust': frozenset({'cli', 'http', *_IMPORT_TAXONOMY}),
    'cpp': frozenset({'cli', 'http', 'env', 'fs', 'subprocess', *_IMPORT_TAXONOMY}),
}

# Nothing is declared impossible yet: every category has a plausible form in every
# language, and a wrong "cannot exist" would hide a real gap. Add a cell here only
# with a reason.
_NOT_APPLICABLE: Dict[str, frozenset] = {}


def cell_status(lang: str, category: str) -> str:
    if category in rule_categories(lang):
        return RULES
    if category in _HAND_CODED.get(lang, ()):
        return SCANNER
    if category in _NOT_APPLICABLE.get(lang, ()):
        return NOT_APPLICABLE
    return NOT_IMPLEMENTED


def language_row(lang: str, categories: Iterable[str] = CATEGORIES) -> Dict[str, str]:
    return {c: cell_status(lang, c) for c in categories}


def coverage_matrix(languages: Iterable[str], categories: Iterable[str] = CATEGORIES) -> Dict[str, object]:
    """The matrix for the languages a scan actually met.

    `cells` is total over (language, category); `not_implemented` inverts it to
    {category: [languages]} for the cells a reader would otherwise mistake for a clean 0.
    """
    cats = tuple(categories)
    langs = sorted(set(languages))
    cells = {lang: language_row(lang, cats) for lang in langs}
    missing: Dict[str, List[str]] = {}
    for lang, row in cells.items():
        for cat, status in row.items():
            if status == NOT_IMPLEMENTED:
                missing.setdefault(cat, []).append(lang)
    return {'cells': cells, 'not_implemented': {c: missing[c] for c in cats if c in missing}}
