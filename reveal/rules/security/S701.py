"""S701: Docker :latest tag detector.

Detects use of :latest tag in Docker images (both Dockerfiles and URIs).
"""

import re
import logging
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class S701(BaseRule):
    """Detect :latest tag in Docker images (files and URIs)."""

    code = "S701"
    message = "Docker image uses :latest tag (pin to specific version)"
    category = RulePrefix.S
    severity = Severity.MEDIUM
    file_patterns = ['Dockerfile', '.dockerfile']
    uri_patterns = [
        r'^https?://hub\.docker\.com/r/.*/tags',
        r'^docker\.io/.*',
    ]
    version = "1.0.0"

    # Pattern to match FROM lines with :latest
    LATEST_PATTERN = re.compile(
        r'^\s*FROM\s+(\S+):latest',
        re.IGNORECASE | re.MULTILINE
    )

    # Pattern to match FROM lines without any tag (also problematic)
    NO_TAG_PATTERN = re.compile(
        r'^\s*FROM\s+([a-zA-Z0-9_/-]+)\s*(?:#|$)',
        re.IGNORECASE | re.MULTILINE
    )

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check for :latest tag usage.

        Args:
            file_path: Path to file or URI
            structure: Parsed structure (may be None for URIs)
            content: File content or HTTP response

        Returns:
            List of detections
        """
        if file_path.startswith('http'):
            return self._check_uri(file_path, content)
        else:
            return self._check_file(file_path, content)

    def _check_file(self, file_path: str, content: str) -> List[Detection]:
        """Check Dockerfile content for :latest usage."""
        detections: List[Detection] = []
        lines = content.splitlines()

        for i, line in enumerate(lines, start=1):
            # Check for explicit :latest
            match = re.match(r'^\s*FROM\s+(\S+):latest', line, re.IGNORECASE)
            if match:
                image = match.group(1)
                detections.append(Detection(
                    file_path=file_path,
                    line=i,
                    rule_code=self.code,
                    message=f"{self.message}: {image}:latest",
                    column=1,
                    suggestion=f"Pin to specific version: FROM {image}:1.0.0",
                    context=line.strip(),
                    severity=self.severity,
                    category=self.category
                ))

            # Check for missing tag (defaults to :latest)
            elif re.match(r'^\s*FROM\s+[a-zA-Z0-9_/-]+\s*(?:#|$)', line, re.IGNORECASE):
                # Extract image name
                parts = line.strip().split()
                if len(parts) >= 2:
                    image = parts[1]
                    # Skip multi-stage builds (FROM ... AS ...)
                    if 'AS' not in line.upper():
                        detections.append(Detection(
                            file_path=file_path,
                            line=i,
                            rule_code=self.code,
                            message=f"Docker image missing tag (defaults to :latest): {image}",
                            column=1,
                            suggestion=f"Pin to specific version: FROM {image}:1.0.0",
                            context=line.strip(),
                            severity=self.severity,
                            category=self.category
                        ))

        return detections

    def _check_uri(self, uri: str, content: str) -> List[Detection]:
        """Check Docker Hub page for :latest usage."""
        # For URIs, check if content mentions :latest
        if ':latest' in content or 'latest tag' in content.lower():
            return [Detection(
                file_path=uri,
                line=0,
                rule_code=self.code,
                message="Docker Hub image uses :latest tag",
                column=0,
                suggestion="Use a specific version tag",
                severity=self.severity,
                category=self.category
            )]
        return []
