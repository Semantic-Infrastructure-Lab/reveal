"""V030 checks any quoted README language total against the live registry.

The README may instead delegate to live language discovery (BACK-2604).
An unrecognized rewording with neither a count nor a discovery pointer still
fails, so an accidental pattern miss cannot masquerade as a checked claim.
"""

import logging
import re
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity, RuleScope
from .utils import find_reveal_root

logger = logging.getLogger(__name__)


class V030(BaseRule):
    """Validate the README.md headline language count against the live registry."""

    code = "V030"
    scope = RuleScope.CROSS_FILE
    message = "README headline language count mismatch"
    category = RulePrefix.V
    severity = Severity.MEDIUM  # Important for releases
    file_patterns = []  # No file-extension form; reveal:// self-check only
    uri_patterns = ['^reveal://.*']
    internal = True  # reveal-internal self-check, never applies to external user code

    _README_REL_PATH = 'README.md'
    _CLAIM = re.compile(r'\b(\d+)\s+languages and file formats\b', re.IGNORECASE)
    _DISCOVERY = re.compile(r'\breveal\s+(?:--languages|help://languages)\b')

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
        except (OSError, UnicodeDecodeError) as e:
            return self.unavailable(f"V030: failed to read {readme_path}: {e}")

        text = '\n'.join(lines)
        if not self._CLAIM.search(text) and self._DISCOVERY.search(text):
            return self.not_applicable('README delegates the count to live language discovery', 'README.md')

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
                suggestion="Point to reveal help://languages, or quote a checked 'N languages and file formats' total",
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
        except Exception as e:  # boundary-ok: broad-except -- list_supported_languages() imports and introspects every analyzer (arbitrary import-time failures); recorded as an unavailable outcome
            logger.warning(f"V030: failed to count supported languages: {e}")
            self.unavailable(f"required input unavailable: {type(e).__name__}: {e}")
            return None
