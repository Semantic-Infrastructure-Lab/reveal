"""V012: Language count accuracy in documentation.

Validates that documented language counts match what `reveal --languages`
actually reports. Prevents documentation drift when languages are added.

Example violation:
    - A doc claims: "305+ languages"
    - `reveal --languages` reports: "Total: 84 languages supported"
    - Result: an overclaim the tool itself contradicts (reveal file.f90 errors)

How it counts:
    - Source of truth is the "Total: N languages supported" line printed by
      list_supported_languages() — the exact figure `reveal --languages` shows
      (explicit analyzers + curated tree-sitter fallbacks). This is NOT the raw
      tree-sitter-language-pack grammar count (~306); reveal only maps ~84.

Floor semantics:
    - A documented count is acceptable as long as reveal supports AT LEAST that
      many languages. Only overclaims (doc > actual) are flagged. This catches
      the dangerous direction while tolerating the +1 registry pollution that
      leaks in when the full test suite registers a scratch analyzer.

Scope:
    - Checks every current-claim doc (README, ARCHITECTURE, QUICK_START,
      WHY_REVEAL), skipping version-history lines. See BACK-388.
"""

import re
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root, iter_current_claim_docs, scan_doc_for_counts


class V012(BaseRule):
    """Validate documented language counts match `reveal --languages`."""

    code = "V012"
    message = "Language count mismatch in documentation"
    category = RulePrefix.V
    severity = Severity.MEDIUM  # Important for releases
    file_patterns = []  # No file-extension form; reveal:// self-check only
    uri_patterns = ['^reveal://.*']
    internal = True  # reveal-internal self-check, never applies to external user code
    _LANGUAGE_PATTERNS = [
        r'(\d+)\+?\s+languages?\b',      # "84 languages", "84+ languages"
        r'Built-in\s*\((\d+)\)',          # "Built-in (84)"
    ]

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check language count accuracy across documentation files."""
        if not file_path.startswith('reveal://'):
            return []

        detections: List[Detection] = []

        reveal_root = find_reveal_root()
        if not reveal_root:
            return detections
        project_root = reveal_root.parent

        actual_count = self._count_supported_languages()
        if actual_count is None:
            return detections

        for rel_path, doc_path in iter_current_claim_docs(project_root):
            for line_num, claimed in scan_doc_for_counts(doc_path, self._LANGUAGE_PATTERNS):
                # Floor semantics: only overclaims are wrong.
                if claimed > actual_count:
                    detections.append(self.create_detection(
                        file_path=rel_path,
                        line=line_num,
                        message=f"Language overclaim: claims {claimed}, actual {actual_count}",
                        suggestion=f"Update {rel_path} line {line_num} to '{actual_count} languages' (see `reveal --languages`)",
                        context=f"Claimed: {claimed}, Actual: {actual_count} supported languages"
                    ))

        return detections

    def _count_supported_languages(self) -> Optional[int]:
        """Count supported languages the same way `reveal --languages` does.

        Reads the "Total: N languages supported" line from
        list_supported_languages() — explicit analyzers + curated fallbacks.
        """
        try:
            from reveal.cli.languages import list_supported_languages
            listing = list_supported_languages()
            match = re.search(r'Total:\s*(\d+)\s+languages?\s+supported', listing)
            return int(match.group(1)) if match else None
        except Exception:
            return None
