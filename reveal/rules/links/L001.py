"""L001: Broken internal links detector.

Detects internal links in Markdown files that point to non-existent files or anchors.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class L001(BaseRule):
    """Detect broken internal links in Markdown files."""

    code = "L001"
    message = "Broken internal link"
    category = RulePrefix.L
    severity = Severity.MEDIUM
    file_patterns = ['.md', '.markdown']
    version = "1.0.0"

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check for broken internal links in Markdown files.

        Args:
            file_path: Path to markdown file
            structure: Parsed structure from markdown analyzer
            content: File content (used as fallback)

        Returns:
            List of detections for broken links
        """
        detections = []
        base_path = Path(file_path).parent

        # Get links from structure (analyzer already parsed them)
        if structure and 'links' in structure:
            links = structure['links']
        else:
            # Fallback: extract links if not in structure
            from ...base import get_analyzer
            analyzer_class = get_analyzer(file_path)
            if analyzer_class:
                analyzer = analyzer_class(file_path)
                links = analyzer._extract_links()
            else:
                return detections

        # Check each link for issues
        for link in links:
            text = link.get('text', '')
            url = link.get('url', '')
            line_num = link.get('line', 1)

            # Skip external links (http://, https://, mailto:)
            if url.startswith(('http://', 'https://', 'mailto:', 'ftp://', '//')):
                continue

            # Check if this internal link is broken
            is_broken, reason = self._is_broken_link(base_path, url, file_path)

            if is_broken:
                message = f"{self.message}: {url}"
                suggestion = self._suggest_fix(base_path, url, reason)

                detections.append(Detection(
                    file_path=file_path,
                    line=line_num,
                    rule_code=self.code,
                    message=message,
                    column=1,  # Column not available from structure
                    suggestion=suggestion,
                    context=f"[{text}]({url})",
                    severity=self.severity,
                    category=self.category
                ))

        return detections

    def _extract_anchors_from_markdown(self, file_path: Path) -> List[str]:
        """Extract valid anchor IDs from markdown headings.

        Args:
            file_path: Path to markdown file

        Returns:
            List of anchor IDs (e.g., ['my-heading', 'another-section'])
        """
        try:
            # Use analyzer to extract headings (uses AST, not regex)
            from ...base import get_analyzer
            analyzer_class = get_analyzer(str(file_path))
            if not analyzer_class:
                return []

            analyzer = analyzer_class(str(file_path))
            headings = analyzer._extract_headings()
        except Exception as e:
            logger.debug(f"Failed to extract headings from {file_path}: {e}")
            return []

        # Convert headings to anchor slugs (GitHub Flavored Markdown style)
        anchors = []
        for heading in headings:
            heading_text = heading.get('name', '').strip()
            if not heading_text:
                continue

            # Convert heading to anchor slug
            anchor = heading_text.lower()
            anchor = re.sub(r'[^\w\s-]', '', anchor)  # Remove special chars except spaces and hyphens
            anchor = re.sub(r'[\s_]+', '-', anchor)   # Replace spaces/underscores with hyphens
            anchor = re.sub(r'-+', '-', anchor)       # Collapse multiple hyphens
            anchor = anchor.strip('-')                # Remove leading/trailing hyphens
            if anchor:
                anchors.append(anchor)

        return anchors

    def _is_broken_link(self, base_dir: Path, url: str, source_file: str = "") -> Tuple[bool, str]:
        """Check if an internal link is broken.

        Args:
            base_dir: Directory containing the markdown file
            url: Link URL (relative or absolute)
            source_file: Path to the source markdown file (for anchor-only links)

        Returns:
            Tuple of (is_broken, reason)
        """
        # Handle anchor-only links (#heading)
        if url.startswith('#'):
            # Validate anchor exists in current file
            anchor = url[1:]  # Remove # prefix
            if source_file:
                source_path = Path(source_file)
                valid_anchors = self._extract_anchors_from_markdown(source_path)
                if anchor not in valid_anchors:
                    return (True, "anchor_not_found")
            return (False, "")

        # Split file path and anchor
        if '#' in url:
            file_part, anchor = url.split('#', 1)
        else:
            file_part = url
            anchor = None

        # Skip absolute paths starting with / (web paths)
        if file_part.startswith('/'):
            # TODO: Handle in L003 with framework routing
            return (False, "")

        # Resolve relative path
        target = base_dir / file_part

        # Try both as-is and with common extensions
        if target.exists():
            if target.is_dir():
                return (True, "target_is_directory")

            # Check for case mismatch (important on case-insensitive filesystems like macOS)
            actual_name = target.name
            try:
                # Get actual filename from parent directory
                if target.parent.exists():
                    for actual_file in target.parent.iterdir():
                        if actual_file == target:
                            actual_name = actual_file.name
                            break

                # If link case doesn't match actual file case, it's an error
                if actual_name != target.name:
                    return (True, "case_mismatch")
            except Exception:
                pass  # If we can't check, assume it's ok

            # Validate anchor if present
            if anchor:
                valid_anchors = self._extract_anchors_from_markdown(target)
                if anchor not in valid_anchors:
                    return (True, "anchor_not_found")
            return (False, "")

        # Try with .md extension if not already present
        if not target.suffix:
            md_target = target.parent / f"{target.name}.md"
            if md_target.exists():
                return (False, "")  # Would work with .md extension

        return (True, "file_not_found")

    def _find_case_mismatch(self, target_path: Path) -> Optional[str]:
        """Find file with case-insensitive match.

        Args:
            target_path: Path to check for case mismatch

        Returns:
            Correct filename if found, None otherwise
        """
        try:
            target_dir = target_path.parent
            if not target_dir.exists():
                return None

            for file in target_dir.iterdir():
                if file.name.lower() == target_path.name.lower() and file.name != target_path.name:
                    return file.name
        except Exception:
            pass
        return None

    def _suggest_fix(self, base_dir: Path, broken_url: str, reason: str) -> str:
        """Generate helpful suggestion for fixing broken link.

        Args:
            base_dir: Directory containing the markdown file
            broken_url: The broken URL
            reason: Reason why link is broken

        Returns:
            Suggestion string
        """
        # Split file path and anchor
        if '#' in broken_url:
            file_part, anchor = broken_url.split('#', 1)
        else:
            file_part = broken_url
            anchor = None

        target_path = base_dir / file_part
        suggestions = []

        # Reason-specific suggestions
        if reason == "target_is_directory":
            suggestions.append("Link points to a directory, not a file")
            # Check for index.md in that directory
            index_file = target_path / "index.md"
            if index_file.exists():
                suggestions.append(f"Use: {file_part}/index.md")

        elif reason == "case_mismatch":
            # Find the correct case
            case_match = self._find_case_mismatch(target_path)
            if case_match:
                suggestions.append(f"Fix case to match actual file: {case_match}")
            else:
                suggestions.append("Fix filename case to match actual file")

        elif reason == "file_not_found":
            # Check if file exists with .md extension
            if not target_path.suffix:
                md_path = target_path.parent / f"{target_path.name}.md"
                if md_path.exists():
                    suggestions.append(f"Add .md extension: {broken_url}.md")

            # Check for case mismatch
            case_match = self._find_case_mismatch(target_path)
            if case_match:
                suggestions.append(f"Fix case: {case_match}")

            # Check for common typos in path
            if '../' in file_part:
                suggestions.append("Check relative path (../) is correct")

        # Add anchor-specific suggestion
        if anchor:
            suggestions.append(f"Verify anchor '#{anchor}' exists in target")

        if suggestions:
            return " | ".join(suggestions)
        return "File not found - verify path is correct"
