"""V031: capabilities.py measured-recall data traceable to VALIDATION.md (BACK-880).

`LanguageCapability.validation` (BACK-880) carries measured recall/precision
numbers transcribed from VALIDATION.md's "Validation status at a glance"
table, so they're queryable via `--capabilities`/`--language-info` instead of
stuck in prose. Two hand-maintained copies of the same numbers is exactly the
drift class BACK-388 was filed to prevent (see STABILITY.md, BACK-886) — this
rule is that same pattern applied to BACK-880's data.

Direction checked: every percentage capabilities.py claims for a
(language, signal) must appear somewhere in VALIDATION.md's corresponding
table cell. This is deliberately one-directional (like V012/V013's floor
semantics) rather than a strict set-equality diff — VALIDATION.md's cells
contain free-text caveats that legitimately include percentages beyond the
tracked measurement (e.g. Dart's import cell notes "100% of *real* edges" as
prose alongside the two tracked per-corpus numbers), so a symmetric check
would false-positive on exactly the nuance this data exists to preserve. The
dangerous direction — a number in capabilities.py that VALIDATION.md's table
no longer backs — is what this catches.

Scope: reveal:// self-check only, not applicable to external user code.
"""

import re
from typing import Any, Dict, List, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root

# VALIDATION.md's "at a glance" table language labels -> capabilities.py's
# LanguageCapability.language values. "TSX, plain JS" is one combined row
# covering two separate capabilities.py entries (see capabilities.py's own
# comment on JavaScriptAnalyzer/TSXAnalyzer's validation= for why).
_DOC_LANGUAGE_TO_CAPABILITY_LANGUAGES = {
    'Python': ['python'],
    'TypeScript': ['typescript'],
    'Java': ['java'],
    'Go': ['go'],
    'Ruby': ['ruby'],
    'Kotlin': ['kotlin'],
    'Rust': ['rust'],
    'C#': ['csharp'],
    'PHP': ['php'],
    'Swift': ['swift'],
    'Scala': ['scala'],
    'C++': ['cpp'],
    'C': ['c'],
    'Lua': ['lua'],
    'Dart': ['dart'],
    'GDScript': ['gdscript'],
    'Zig': ['zig'],
    'TSX, plain JS': ['tsx', 'javascript'],
}

_COLUMN_TO_SIGNAL = {
    1: 'import_recall',
    2: 'side_effect_recall',
    3: 'call_graph_recall',
}

_PCT_PATTERN = re.compile(r'(\d+(?:\.\d+)?)\s*%')
_TABLE_HEADER = re.compile(r'^\|\s*Language\s*\|\s*Import recall\s*\|')
_TABLE_SEPARATOR = re.compile(r'^\|[\s:-]+\|')


class V031(BaseRule):
    """Validate capabilities.py's measured-recall numbers trace to VALIDATION.md."""

    code = "V031"
    message = "capabilities.py validation data not traceable to VALIDATION.md"
    category = RulePrefix.V
    severity = Severity.MEDIUM
    file_patterns = []  # No file-extension form; reveal:// self-check only
    uri_patterns = ['^reveal://.*']
    internal = True  # reveal-internal self-check, never applies to external user code

    _VALIDATION_MD_REL_PATH = 'VALIDATION.md'
    _CAPABILITIES_PY_REL_PATH = 'reveal/capabilities.py'

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check capabilities.py validation= data against VALIDATION.md's table."""
        if not file_path.startswith('reveal://'):
            return []

        reveal_root = find_reveal_root()
        if not reveal_root:
            return []
        project_root = reveal_root.parent

        doc_path = project_root / self._VALIDATION_MD_REL_PATH
        if not doc_path.exists():
            return []

        try:
            doc_lines = doc_path.read_text(encoding='utf-8').split('\n')
        except Exception:
            return []

        doc_cells_by_language = self._parse_table(doc_lines)
        if not doc_cells_by_language:
            return []

        registry_by_language = self._load_registry()
        if registry_by_language is None:
            return []

        detections: List[Detection] = []
        for language, signals in registry_by_language.items():
            doc_cells = doc_cells_by_language.get(language)
            if doc_cells is None:
                # A language with validation= data but no matching table row
                # at all is itself drift, but a rename/removal on the doc
                # side is rare enough, and the per-number check below already
                # covers the common case — skip rather than double-report.
                continue
            for signal, claimed_pcts in signals.items():
                cell_text = doc_cells.get(signal, '')
                doc_pcts = {float(m) for m in _PCT_PATTERN.findall(cell_text)}
                missing = sorted(p for p in claimed_pcts if not self._pct_in(p, doc_pcts))
                if not missing:
                    continue
                detections.append(self.create_detection(
                    file_path=self._CAPABILITIES_PY_REL_PATH,
                    line=1,
                    message=(
                        f"{language}/{signal}: capabilities.py claims "
                        f"{missing}% not found in VALIDATION.md's table cell"
                    ),
                    suggestion=(
                        f"Re-check VALIDATION.md's \"{language}\" row, "
                        f"{signal.replace('_', ' ')} column — either "
                        f"capabilities.py has a stale/typo'd number, or "
                        f"VALIDATION.md's table was updated without it"
                    ),
                    context=f"capabilities.py claims: {sorted(claimed_pcts)}, doc cell: {cell_text[:200]}",
                ))

        return detections

    @staticmethod
    def _pct_in(value: float, haystack: set) -> bool:
        return any(abs(value - h) < 1e-6 for h in haystack)

    def _parse_table(self, lines: List[str]) -> Optional[Dict[str, Dict[str, str]]]:
        """Parse the 'Validation status at a glance' table into
        {capability_language: {signal: cell_text}}."""
        header_idx = None
        for i, line in enumerate(lines):
            if _TABLE_HEADER.match(line):
                header_idx = i
                break
        if header_idx is None:
            return None

        result: Dict[str, Dict[str, str]] = {}
        for line in lines[header_idx + 1:]:
            if _TABLE_SEPARATOR.match(line):
                continue
            if not line.startswith('|'):
                break  # table ended
            cells = [c.strip() for c in line.strip('|').split('|')]
            if len(cells) < 4:
                continue
            doc_language = cells[0]
            capability_languages = _DOC_LANGUAGE_TO_CAPABILITY_LANGUAGES.get(doc_language)
            if not capability_languages:
                continue
            for cap_language in capability_languages:
                result[cap_language] = {
                    signal: cells[col] for col, signal in _COLUMN_TO_SIGNAL.items()
                }
        return result

    def _load_registry(self) -> Optional[Dict[str, Dict[str, set]]]:
        """Build {language: {signal: {claimed_pct, ...}}} from capabilities.py."""
        try:
            from reveal.capabilities import get_all_capabilities
        except Exception:
            return None

        registry: Dict[str, Dict[str, set]] = {}
        for cap in get_all_capabilities().values():
            if not cap.validation:
                continue
            signals = registry.setdefault(cap.language, {})
            for m in cap.validation:
                pcts = signals.setdefault(m.signal, set())
                pcts.add(m.recall_pct)
                if m.pre_fix_pct is not None:
                    pcts.add(m.pre_fix_pct)
        return registry
