"""V030: AGENT_HELP.md main-body aggregate-count accuracy.

Validates hand-written aggregate-count claims in AGENT_HELP.md's main body
against live registries (BACK-686). V012/V013/V029 already guard these same
counts (languages/adapters/rules) everywhere else, but all three deliberately
exclude AGENT_HELP.md from `CURRENT_CLAIM_DOCS` — its "What Changed in This
Guide" changelog section is full of historically-correct per-version counts
(e.g. "v0.59.0 - 20 adapters support help://schemas/") that a whole-file
guard would wrongly try to "fix". V030 closes that gap the other direction:
it checks only AGENT_HELP.md, and only the portion above the changelog
heading, so history stays untouched while the main-body claims stay honest.

Example violation:
    - AGENT_HELP.md main body claims: "Programming Languages (85 total ...)"
    - `reveal --languages` reports: 87
    - Result: an agent reading the guide undercounts what reveal can parse

Scope:
    - reveal/docs/AGENT_HELP.md only, content above the "## What Changed in
      This Guide" heading. Everything at or past that heading is skipped —
      see BACK-686's corrected scope note.
    - Currently only one main-body pattern carries a total-count claim:
      "Programming Languages (N total ...)". Extend `_TOTAL_PATTERNS` if an
      equivalent adapters/rules total-count claim is ever added to the body.
"""

import re
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root


class V030(BaseRule):
    """Validate AGENT_HELP.md main-body aggregate counts match live registries."""

    code = "V030"
    message = "Aggregate-count mismatch in AGENT_HELP.md main body"
    category = RulePrefix.V
    severity = Severity.MEDIUM  # Important for releases
    file_patterns = []  # No file-extension form; reveal:// self-check only
    uri_patterns = ['^reveal://.*']
    internal = True  # reveal-internal self-check, never applies to external user code

    _AGENT_HELP_REL_PATH = 'reveal/docs/AGENT_HELP.md'
    _CHANGELOG_HEADING = re.compile(r'^##\s+What Changed in This Guide', re.IGNORECASE)

    _TOTAL_PATTERNS = [
        (re.compile(r'Programming Languages\s*\((\d+)\+?\s*total\b', re.IGNORECASE),
         'languages'),
    ]

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check AGENT_HELP.md main-body aggregate counts against live registries."""
        if not file_path.startswith('reveal://'):
            return []

        reveal_root = find_reveal_root()
        if not reveal_root:
            return []
        project_root = reveal_root.parent

        agent_help_path = project_root / self._AGENT_HELP_REL_PATH
        if not agent_help_path.exists():
            return []

        try:
            lines = agent_help_path.read_text(encoding='utf-8').split('\n')
        except Exception:
            return []

        actual_counts = {'languages': self._count_supported_languages()}

        detections: List[Detection] = []
        for i, line in enumerate(lines, 1):
            if self._CHANGELOG_HEADING.match(line):
                break  # everything from here down is version history — stop scanning
            for pattern, metric in self._TOTAL_PATTERNS:
                match = pattern.search(line)
                if not match:
                    continue
                actual = actual_counts.get(metric)
                if actual is None:
                    continue
                claimed = int(match.group(1))
                if claimed == actual:
                    continue
                detections.append(self.create_detection(
                    file_path=self._AGENT_HELP_REL_PATH,
                    line=i,
                    message=f"{metric.capitalize()} count mismatch: claims {claimed}, actual {actual}",
                    suggestion=f"Update {self._AGENT_HELP_REL_PATH} line {i} to '{actual} total'",
                    context=f"Claimed: {claimed}, Actual: {actual} {metric}"
                ))

        return detections

    def _count_supported_languages(self) -> Optional[int]:
        """Count supported languages the same way `reveal --languages` does."""
        try:
            from reveal.cli.languages import list_supported_languages
            listing = list_supported_languages()
            match = re.search(r'Total:\s*(\d+)\s+languages?\s+supported', listing)
            return int(match.group(1)) if match else None
        except Exception:
            return None
