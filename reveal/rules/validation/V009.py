"""V009: Documentation cross-reference validation.

Validates that internal documentation links point to existing files.
Prevents broken references in ROADMAP.md, planning docs, etc.

Example violation:
    - File: ROADMAP.md
    - Link: [spec](internal-docs/planning/PRACTICAL_CODE_ANALYSIS_ADAPTERS.md)
    - Issue: Target file doesn't exist
    - Suggestion: Create file or update link
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root


class V009(BaseRule):
    """Validate internal documentation cross-references."""

    code = "V009"
    message = "Broken documentation cross-reference"
    category = RulePrefix.M  # Maintainability
    severity = Severity.MEDIUM
    file_patterns = ['*.md']  # Only check markdown files

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check for broken documentation links."""
        detections = []

        # Only run for reveal:// URIs
        if not file_path.startswith('reveal://'):
            return detections

        # Find reveal root
        reveal_root = find_reveal_root()
        if not reveal_root:
            return detections

        project_root = reveal_root.parent

        # Convert reveal:// URI to actual file path
        actual_file_path = self._uri_to_path(file_path, reveal_root, project_root)
        if not actual_file_path or not actual_file_path.exists():
            return detections

        # Extract markdown links: [text](path)
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        for match in re.finditer(link_pattern, content):
            link_text = match.group(1)
            link_target = match.group(2)

            # Skip external links
            if link_target.startswith('http://') or link_target.startswith('https://'):
                continue

            # Skip anchor-only links (#heading)
            if link_target.startswith('#'):
                continue

            # Skip mailto: links
            if link_target.startswith('mailto:'):
                continue

            # Remove anchor fragments (file.md#heading -> file.md)
            link_target_clean = link_target.split('#')[0]
            if not link_target_clean:
                continue

            # Resolve relative path
            resolved = self._resolve_link(actual_file_path, link_target_clean, project_root)
            if not resolved or not resolved.exists():
                line_num = content[:match.start()].count('\n') + 1
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=line_num,
                    message=f"Broken link: {link_target}",
                    suggestion=f"Create {link_target_clean} or update link",
                    context=f"Link text: '{link_text}'"
                ))

        return detections

    def _uri_to_path(self, uri: str, reveal_root: Path, project_root: Path) -> Optional[Path]:
        """Convert reveal:// URI to actual file path.

        Args:
            uri: reveal:// URI (e.g., "reveal://ROADMAP.md")
            reveal_root: Path to reveal/ directory
            project_root: Path to project root (parent of reveal/)

        Returns:
            Actual file path or None
        """
        if not uri.startswith('reveal://'):
            return None

        # Remove reveal:// prefix
        relative_path = uri[len('reveal://'):]

        # Try both reveal_root and project_root
        candidates = [
            project_root / relative_path,
            reveal_root / relative_path,
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        # Return first candidate (for consistency, even if it doesn't exist)
        return candidates[0]

    def _resolve_link(self, source_file: Path, link: str, project_root: Path) -> Optional[Path]:
        """Resolve a relative link to an absolute path.

        Args:
            source_file: File containing the link
            link: Relative link path
            project_root: Project root directory

        Returns:
            Resolved path or None
        """
        try:
            # Handle absolute paths (from project root)
            if link.startswith('/'):
                return project_root / link.lstrip('/')

            # Handle relative paths
            source_dir = source_file.parent
            resolved = (source_dir / link).resolve()

            # Check if resolved path is within project
            try:
                resolved.relative_to(project_root)
                return resolved
            except ValueError:
                # Path is outside project root
                return None

        except Exception:
            return None
