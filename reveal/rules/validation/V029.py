"""V029: Quality rule count accuracy in documentation.

Validates that documented "N quality rules" claims match the actual number
of enabled rules `reveal check` can fire (BACK-659).

Example violation:
    - WHY_REVEAL.md claims: "80 quality rules via `reveal check`"
    - Actual: 81 enabled rules (a new rule shipped, doc wasn't updated)
    - Result: Documentation out of sync

Counting:
    - All *enabled* rules, including reveal's own internal self-check rules
      (the V-series like V012/V013/this one) — WHY_REVEAL.md's "14 categories"
      list explicitly includes "V" (Reveal's own adapter contract
      validation), so the claimed total is meant to cover them. This matches
      how the 79→80 correction (commit edaf8c2) was derived: len(rules) with
      include_internal=True, filtered to enabled.

Scope:
    - Checks every current-claim doc (README, ARCHITECTURE, QUICK_START,
      WHY_REVEAL), skipping version-history lines. Strict equality — unlike
      V012's floor semantics, both overclaims and stale underclaims are
      flagged. That asymmetry is exactly the gap BACK-659 filed: V012's floor
      check let "79 quality rules" sit silently wrong for a stretch of
      sessions after the actual count passed 80, because floor semantics
      only catch overclaims. A rule count is precise and cheap to compute at
      lint time, so there's no reason to tolerate any drift.
"""

from typing import List, Dict, Any, Optional

from .. import RuleRegistry
from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root, iter_current_claim_docs, scan_doc_for_counts


class V029(BaseRule):
    """Validate documented quality-rule counts match enabled rules."""

    code = "V029"
    message = "Quality rule count mismatch in documentation"
    category = RulePrefix.V
    severity = Severity.MEDIUM  # Important for releases
    file_patterns = []  # No file-extension form; reveal:// self-check only
    uri_patterns = ['^reveal://.*']
    internal = True  # reveal-internal self-check, never applies to external user code
    _RULE_COUNT_PATTERNS = [
        r'(\d+)\+?\s+quality\s+rules?\b',  # "80 quality rules", "80+ quality rules"
    ]

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check quality-rule count accuracy across documentation files."""
        if not file_path.startswith('reveal://'):
            return []

        detections: List[Detection] = []

        reveal_root = find_reveal_root()
        if not reveal_root:
            return detections
        project_root = reveal_root.parent

        actual_count = self._count_enabled_rules()
        if actual_count is None:
            return detections

        for rel_path, doc_path in iter_current_claim_docs(project_root):
            for line_num, claimed in scan_doc_for_counts(doc_path, self._RULE_COUNT_PATTERNS):
                if claimed != actual_count:
                    detections.append(self.create_detection(
                        file_path=rel_path,
                        line=line_num,
                        message=(f"Quality rule count mismatch: claims {claimed}, "
                                 f"actual {actual_count}"),
                        suggestion=(f"Update {rel_path} line {line_num} to "
                                    f"'{actual_count} quality rules' "
                                    f"(see `reveal --rules --all`)"),
                        context=f"Claimed: {claimed}, Actual: {actual_count} enabled rules"
                    ))

        return detections

    def _count_enabled_rules(self) -> Optional[int]:
        """Count enabled rules, including internal V-series self-checks."""
        try:
            rules = RuleRegistry.list_rules(include_internal=True)
            return sum(1 for r in rules if r['enabled'])
        except Exception:
            return None
