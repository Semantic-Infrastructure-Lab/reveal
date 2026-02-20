"""V009: Documentation cross-reference validation.

Validates that internal documentation links point to existing files.
Prevents broken references in ROADMAP.md, planning docs, etc.

Example violation:
    - File: ROADMAP.md
    - Link: [spec](internal-docs/planning/PRACTICAL_CODE_ANALYSIS_ADAPTERS.md)
    - Issue: Target file doesn't exist
    - Suggestion: Create file or update link
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root


class V009(BaseRule):
    """Validate internal documentation cross-references."""

    code = "V009"
    message = "Broken documentation cross-reference"
    category = RulePrefix.V
    severity = Severity.MEDIUM
    file_patterns = ['*.md']  # Only check markdown files

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check for broken documentation links."""
        detections: List[Detection] = []

        # Get file path context (early returns handled here)
        context = self._get_file_path_context(file_path)
        if not context:
            return detections

        actual_file_path, project_root = context

        # Extract and validate links
        links = self._extract_markdown_links(content)
        for link_info in links:
            detection = self._validate_link(
                link_info,
                actual_file_path,
                project_root,
                file_path,
                content
            )
            if detection:
                detections.append(detection)

        return detections

    def _get_file_path_context(
            self, file_path: str) -> Optional[Tuple[Path, Path]]:
        """Get file path context for validation.

        Returns:
            Tuple of (actual_file_path, project_root) or None if invalid
        """
        # Only run for reveal:// URIs
        if not file_path.startswith('reveal://'):
            return None

        # Find reveal root
        reveal_root = find_reveal_root()
        if not reveal_root:
            return None

        project_root = reveal_root.parent

        # Convert reveal:// URI to actual file path
        actual_file_path = self._uri_to_path(
            file_path, reveal_root, project_root
        )
        if not actual_file_path or not actual_file_path.exists():
            return None

        return (actual_file_path, project_root)

    def _extract_markdown_links(self, content: str) -> List[Dict[str, Any]]:
        """Extract internal markdown links from content.

        Returns:
            List of dicts with keys: text, target, match_obj
        """
        links = []
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'

        for match in re.finditer(link_pattern, content):
            link_text = match.group(1)
            link_target = match.group(2)

            # Filter out non-internal links
            link_info = self._process_link(link_text, link_target, match)
            if link_info:
                links.append(link_info)

        return links

    def _process_link(
            self,
            link_text: str,
            link_target: str,
            match: re.Match) -> Optional[Dict[str, Any]]:
        """Process a single link and determine if it should be validated.

        Returns:
            Link info dict or None if link should be skipped
        """
        # Skip external links
        if self._is_external_link(link_target):
            return None

        # Skip anchor-only links (#heading)
        if link_target.startswith('#'):
            return None

        # Skip mailto: links
        if link_target.startswith('mailto:'):
            return None

        # Remove anchor fragments (file.md#heading -> file.md)
        link_target_clean = link_target.split('#')[0]
        if not link_target_clean:
            return None

        return {
            'text': link_text,
            'target': link_target,
            'target_clean': link_target_clean,
            'match': match
        }

    def _is_external_link(self, link_target: str) -> bool:
        """Check if link is external (http/https)."""
        return (link_target.startswith('http://') or
                link_target.startswith('https://'))

    def _validate_link(
            self,
            link_info: Dict[str, Any],
            source_file: Path,
            project_root: Path,
            file_path: str,
            content: str) -> Optional[Detection]:
        """Validate a single link and return detection if broken.

        Args:
            link_info: Dict with link metadata
            source_file: Source file containing the link
            project_root: Project root directory
            file_path: Original file path (for detection)
            content: File content (to calculate line number)

        Returns:
            Detection if link is broken, None otherwise
        """
        resolved = self._resolve_link(
            source_file,
            link_info['target_clean'],
            project_root
        )

        if not resolved or not resolved.exists():
            line_num = content[:link_info['match'].start()].count('\n') + 1
            return self.create_detection(
                file_path=file_path,
                line=line_num,
                message=f"Broken link: {link_info['target']}",
                suggestion=(
                    f"Create {link_info['target_clean']} or update link"
                ),
                context=f"Link text: '{link_info['text']}'"
            )

        return None

    def _uri_to_path(
            self,
            uri: str,
            reveal_root: Path,
            project_root: Path) -> Optional[Path]:
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

    def _resolve_link(
            self,
            source_file: Path,
            link: str,
            project_root: Path) -> Optional[Path]:
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
            # Reject links with null bytes (invalid in filesystem paths)
            if '\x00' in link:
                return None
            # Use normpath (not resolve) to avoid following symlinks.
            # On macOS, /var is a symlink to /private/var; resolve() would
            # change the prefix and break relative_to() checks.
            resolved = Path(os.path.normpath(source_dir / link))

            # Check if resolved path is within project
            try:
                resolved.relative_to(project_root)
                return resolved
            except ValueError:
                # Path is outside project root
                return None

        except Exception:
            return None
