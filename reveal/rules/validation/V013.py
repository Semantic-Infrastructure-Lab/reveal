"""V013: Adapter count accuracy in documentation.

Validates that documented adapter counts match the registered URI adapters.
Prevents documentation drift when adapters are added (see BACK-388).

Example violation:
    - A doc claims: "22 adapters"
    - Actually registered: 25 production adapters
    - Result: Documentation out of sync

Counting:
    - Production adapters only — list_supported_schemes() minus the 'test' and
      'demo' scaffold schemes that leak in during test runs. Strict equality:
      both overclaims and stale underclaims are drift and are flagged.

Scope:
    - Checks every current-claim doc (README, ARCHITECTURE, QUICK_START,
      WHY_REVEAL), skipping version-history lines.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root, iter_current_claim_docs, scan_doc_for_counts


class V013(BaseRule):
    """Validate documented adapter counts match registered adapters."""

    code = "V013"
    message = "Adapter count mismatch in documentation"
    category = RulePrefix.V
    severity = Severity.MEDIUM  # Important for releases
    file_patterns = []  # No file-extension form; reveal:// self-check only
    uri_patterns = ['^reveal://.*']
    internal = True  # reveal-internal self-check, never applies to external user code
    # "5 minutes to configure 22 adapters" can't misattribute the count.
    _ADAPTER_PATTERNS = [
        r'(\d+)\s+adapters?\b',                 # "22 adapters"
        r'(\d+)\s+URI\s+adapters?\b',           # "25 URI adapters"
        r'(\d+)\s+Built-in\s+Adapters?\b',      # "25 Built-in Adapters"
    ]

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check adapter count accuracy across documentation files."""
        if not file_path.startswith('reveal://'):
            return []

        detections: List[Detection] = []

        reveal_root = find_reveal_root()
        if not reveal_root:
            return detections
        project_root = reveal_root.parent

        actual_count = self._count_production_adapters()
        if actual_count is None:
            return detections

        for rel_path, doc_path in iter_current_claim_docs(project_root):
            seen: set = set()
            for line_num, claimed in scan_doc_for_counts(doc_path, self._ADAPTER_PATTERNS):
                # A line matching both "N adapters" and "N URI adapters" yields
                # the same (line, count) twice — dedupe.
                if (line_num, claimed) in seen:
                    continue
                seen.add((line_num, claimed))
                if claimed != actual_count:
                    detections.append(self.create_detection(
                        file_path=rel_path,
                        line=line_num,
                        message=f"Adapter count mismatch: claims {claimed}, actual {actual_count}",
                        suggestion=f"Update {rel_path} line {line_num} to '{actual_count} adapters' (see `reveal --adapters`)",
                        context=f"Claimed: {claimed}, Actual: {actual_count} registered URI adapters"
                    ))

        return detections

    def _count_production_adapters(self) -> Optional[int]:
        """Count production URI adapters, excluding test/demo scaffold schemes."""
        try:
            from reveal.adapters.base import list_supported_schemes
            schemes = set(list_supported_schemes())
            schemes.discard('test')
            schemes.discard('demo')
            return len(schemes)
        except Exception:
            return None
