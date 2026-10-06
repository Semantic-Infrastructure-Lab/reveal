"""V030: the README headline language count matches `reveal --languages`.

BACK-1441 option (b): the README headline ("... N languages and file formats ...")
is the ONE hand-written total of supported languages. Every other doc points at
`reveal --languages` instead of repeating a number, so there is nothing else to
drift. V012 only flags overclaims (floor semantics, any "N languages" in the
current-claim docs); V030 is the exact check on the headline, so an underclaim
fails too.

Scope:
    - README.md only, every "N languages and file formats" occurrence.
    - The rule fails loudly if README.md is missing the claim: a rule whose target
      text was reworded away matches nothing and reports clean (that is how
      V030's earlier AGENT_HELP pattern went blind after 2eaf0d31). If the
      headline is deliberately removed or reworded, update `_CLAIM` here.
"""

import logging
import re
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root

logger = logging.getLogger(__name__)


class V030(BaseRule):
    """Validate the README.md headline language count against the live registry."""

    code = "V030"
    message = "README headline language count mismatch"
    category = RulePrefix.V
    severity = Severity.MEDIUM  # Important for releases
    file_patterns = []  # No file-extension form; reveal:// self-check only
    uri_patterns = ['^reveal://.*']
    internal = True  # reveal-internal self-check, never applies to external user code

    _README_REL_PATH = 'README.md'
    _CLAIM = re.compile(r'\b(\d+)\s+languages and file formats\b', re.IGNORECASE)

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check every README.md "N languages and file formats" claim against the live count."""
        if not file_path.startswith('reveal://'):
            return []

        reveal_root = find_reveal_root()
        if not reveal_root:
            return self.unavailable("reveal source root unavailable")
        readme_path = reveal_root.parent / self._README_REL_PATH
        if not readme_path.exists():
            return self.unavailable("required source or documentation missing", readme_path.as_posix())

        try:
            lines = readme_path.read_text(encoding='utf-8').split('\n')
        except Exception as e:
            return self.unavailable(f"V030: failed to read {readme_path}: {e}")

        actual = self._count_supported_languages()
        if actual is None:
            return []  # _count_supported_languages already recorded why

        detections: List[Detection] = []
        found = False
        for i, line in enumerate(lines, 1):
            for match in self._CLAIM.finditer(line):
                found = True
                claimed = int(match.group(1))
                if claimed == actual:
                    continue
                detections.append(self.create_detection(
                    file_path=self._README_REL_PATH,
                    line=i,
                    message=f"Languages count mismatch: claims {claimed}, actual {actual}",
                    suggestion=f"Update {self._README_REL_PATH} line {i} to '{actual} languages and file formats' (see `reveal --languages`)",
                    context=f"Claimed: {claimed}, Actual: {actual} languages"
                ))

        if not found:
            detections.append(self.create_detection(
                file_path=self._README_REL_PATH,
                line=1,
                message="README headline language count not found: V030 has nothing to check",
                suggestion="Restore the 'N languages and file formats' headline, or update V030._CLAIM to the new wording",
                context=f"Pattern: {self._CLAIM.pattern}"
            ))
        return detections

    def _count_supported_languages(self) -> Optional[int]:
        """Count supported languages the same way `reveal --languages` does."""
        try:
            from reveal.cli.languages import list_supported_languages
            listing = list_supported_languages()
            match = re.search(r'Total:\s*(\d+)\s+languages?\s+supported', listing)
            return int(match.group(1)) if match else None
        except Exception as e:
            logger.warning(f"V030: failed to count supported languages: {e}")
            self.unavailable(f"required input unavailable: {type(e).__name__}: {e}")
            return None
