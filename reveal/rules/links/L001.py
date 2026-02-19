"""L001: Broken internal links detector.

Detects internal links in Markdown files that point to non-existent files or anchors.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)

# Module-level cache: file_path → list of anchor slugs.
# _extract_anchors_from_markdown re-runs the full tree-sitter markdown parse;
# without caching it is called once per anchor link in a file (O(n) parses per file).
_anchor_cache: Dict[Path, List[str]] = {}


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
        detections: List[Detection] = []
        base_path = Path(file_path).parent

        # Get links from structure (analyzer already parsed them)
        if structure and 'links' in structure:
            links = structure['links']
        else:
            # Fallback: extract links if not in structure
            from ...registry import get_analyzer
            analyzer_class = get_analyzer(file_path)
            if analyzer_class:
                analyzer = analyzer_class(file_path)
                links = analyzer._extract_links()
            else:
                return detections

        # Pre-compute anchor slugs from structure headings once, so that
        # _validate_anchor_only_link doesn't need to re-parse the file per link.
        if structure and 'headings' in structure:
            source_path = Path(file_path)
            anchors = self._headings_to_anchors(structure['headings'])
            _anchor_cache[source_path] = anchors

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

    def _headings_to_anchors(self, headings: List[Dict[str, Any]]) -> List[str]:
        """Convert heading dicts to GitHub-Flavored Markdown anchor slugs."""
        anchors = []
        for heading in headings:
            heading_text = heading.get('name', '').strip()
            if not heading_text:
                continue
            anchor = heading_text.lower()
            anchor = re.sub(r'[^\w\s-]', '', anchor)
            anchor = re.sub(r'[\s_]+', '-', anchor)
            anchor = re.sub(r'-+', '-', anchor)
            anchor = anchor.strip('-')
            if anchor:
                anchors.append(anchor)
        return anchors

    def _extract_anchors_from_markdown(self, file_path: Path) -> List[str]:
        """Extract valid anchor IDs from markdown headings.

        Results are cached by file path so the tree-sitter parse runs once per
        file per process rather than once per anchor link in the file.
        When check() pre-populates the cache from structure['headings'], this
        fallback is never reached for files processed via --check.

        Args:
            file_path: Path to markdown file

        Returns:
            List of anchor IDs (e.g., ['my-heading', 'another-section'])
        """
        if file_path in _anchor_cache:
            return _anchor_cache[file_path]

        try:
            from ...registry import get_analyzer
            analyzer_class = get_analyzer(str(file_path))
            if not analyzer_class:
                return []

            analyzer = analyzer_class(str(file_path))
            headings = analyzer._extract_headings()
        except Exception as e:
            logger.debug(f"Failed to extract headings from {file_path}: {e}")
            return []

        anchors = self._headings_to_anchors(headings)
        _anchor_cache[file_path] = anchors
        return anchors

    def _validate_anchor_only_link(self, url: str, source_file: str) -> Tuple[bool, str]:
        """Validate anchor-only link (#heading).

        Args:
            url: Anchor-only URL (starts with #)
            source_file: Path to source file

        Returns:
            Tuple of (is_broken, reason)
        """
        anchor = url[1:]  # Remove # prefix
        if source_file:
            source_path = Path(source_file)
            valid_anchors = self._extract_anchors_from_markdown(source_path)
            if anchor not in valid_anchors:
                return (True, "anchor_not_found")
        return (False, "")

    def _check_file_case_mismatch(self, target: Path) -> Tuple[bool, str]:
        """Check for case mismatch in file path.

        Args:
            target: Target file path

        Returns:
            Tuple of (is_broken, reason)
        """
        try:
            # Get actual filename from parent directory by comparing lowercase names
            if target.parent.exists():
                for actual_file in target.parent.iterdir():
                    # Compare lowercase names (works on case-insensitive filesystems)
                    if actual_file.name.lower() == target.name.lower():
                        # Found the file - check if case matches exactly
                        if actual_file.name != target.name:
                            return (True, "case_mismatch")
                        break
        except Exception:
            pass  # If we can't check, assume it's ok
        return (False, "")

    def _validate_target_file(self, target: Path, anchor: Optional[str]) -> Tuple[bool, str]:
        """Validate target file exists and anchor is valid.

        Args:
            target: Target file path
            anchor: Optional anchor

        Returns:
            Tuple of (is_broken, reason)
        """
        if not target.exists():
            # Try with .md extension if not already present
            if not target.suffix:
                md_target = target.parent / f"{target.name}.md"
                if md_target.exists():
                    return (False, "")  # Would work with .md extension
            return (True, "file_not_found")

        if target.is_dir():
            return (True, "target_is_directory")

        # Check for case mismatch
        is_broken, reason = self._check_file_case_mismatch(target)
        if is_broken:
            return (is_broken, reason)

        # Validate anchor if present
        if anchor:
            valid_anchors = self._extract_anchors_from_markdown(target)
            if anchor not in valid_anchors:
                return (True, "anchor_not_found")

        return (False, "")

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
            return self._validate_anchor_only_link(url, source_file)

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

        # Resolve relative path and validate
        target = base_dir / file_part
        return self._validate_target_file(target, anchor)

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
        except OSError:
            pass
        return None

    def _suggestions_for_reason(self, reason: str, target_path: Path, file_part: str, broken_url: str) -> list:
        """Return reason-specific suggestions for a broken link."""
        if reason == "target_is_directory":
            suggestions = ["Link points to a directory, not a file"]
            if (target_path / "index.md").exists():
                suggestions.append(f"Use: {file_part}/index.md")
            return suggestions
        if reason == "case_mismatch":
            case_match = self._find_case_mismatch(target_path)
            return [f"Fix case to match actual file: {case_match}" if case_match
                    else "Fix filename case to match actual file"]
        if reason == "file_not_found":
            suggestions = []
            if not target_path.suffix:
                md_path = target_path.parent / f"{target_path.name}.md"
                if md_path.exists():
                    suggestions.append(f"Add .md extension: {broken_url}.md")
            case_match = self._find_case_mismatch(target_path)
            if case_match:
                suggestions.append(f"Fix case: {case_match}")
            if '../' in file_part:
                suggestions.append("Check relative path (../) is correct")
            return suggestions
        return []

    def _suggest_fix(self, base_dir: Path, broken_url: str, reason: str) -> str:
        """Generate helpful suggestion for fixing broken link."""
        file_part, _, anchor = broken_url.partition('#')
        if not anchor:
            anchor = None  # type: ignore[assignment]

        target_path = base_dir / file_part
        suggestions = self._suggestions_for_reason(reason, target_path, file_part, broken_url)

        if anchor:
            suggestions.append(f"Verify anchor '#{anchor}' exists in target")

        return " | ".join(suggestions) if suggestions else "File not found - verify path is correct"
