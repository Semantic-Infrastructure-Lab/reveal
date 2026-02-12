"""U501: Insecure GitHub URL detector.

Detects GitHub URLs using insecure http:// protocol instead of https://.
"""

import re
import logging
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class U501(BaseRule):
    """Detect insecure http:// GitHub URLs."""

    code = "U501"
    message = "GitHub URL uses insecure http:// protocol"
    category = RulePrefix.U
    severity = Severity.LOW
    file_patterns = ['*']  # Check all files for GitHub URLs
    uri_patterns = [r'^http://github\.com/.*', r'^http://.*\.github\.com/.*']
    version = "1.0.0"

    # Pattern to match GitHub URLs with http://
    GITHUB_HTTP_PATTERN = re.compile(
        r'http://(www\.)?github\.com/[^\s\'"<>]+',
        re.IGNORECASE
    )

    # Pattern to match GitHub subdomains with http://
    GITHUB_SUBDOMAIN_PATTERN = re.compile(
        r'http://[a-zA-Z0-9-]+\.github\.(com|io)/[^\s\'"<>]+',
        re.IGNORECASE
    )

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check for insecure GitHub URLs.

        Args:
            file_path: Path to file or URI
            structure: Parsed structure (not used)
            content: File content

        Returns:
            List of detections
        """
        if file_path.startswith('http://'):
            return self._check_uri(file_path)
        else:
            return self._check_file(file_path, content)

    def _check_file(self, file_path: str, content: str) -> List[Detection]:
        """Check file content for insecure GitHub URLs."""
        detections: List[Detection] = []
        lines = content.splitlines()

        for i, line in enumerate(lines, start=1):
            # Find all GitHub URLs with http://
            matches = list(self.GITHUB_HTTP_PATTERN.finditer(line))
            matches.extend(self.GITHUB_SUBDOMAIN_PATTERN.finditer(line))

            for match in matches:
                insecure_url = match.group(0)
                secure_url = insecure_url.replace('http://', 'https://')
                column = match.start() + 1  # 1-indexed

                detections.append(Detection(
                    file_path=file_path,
                    line=i,
                    rule_code=self.code,
                    message=f"{self.message}: {insecure_url}",
                    column=column,
                    suggestion=f"Use HTTPS: {secure_url}",
                    context=line.strip(),
                    severity=self.severity,
                    category=self.category
                ))

        return detections

    def _check_uri(self, uri: str) -> List[Detection]:
        """Check if URI itself is insecure GitHub URL."""
        if uri.startswith('http://') and ('github.com' in uri or 'github.io' in uri):
            secure_url = uri.replace('http://', 'https://')
            return [Detection(
                file_path=uri,
                line=0,
                rule_code=self.code,
                message=f"{self.message}: {uri}",
                column=0,
                suggestion=f"Use HTTPS: {secure_url}",
                severity=self.severity,
                category=self.category
            )]
        return []
