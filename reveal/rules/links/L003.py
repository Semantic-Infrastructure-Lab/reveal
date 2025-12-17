"""L003: Framework routing mismatch detector.

Detects links that use framework-specific routing conventions (FastHTML, Jekyll, Hugo)
but don't resolve correctly to the expected files.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import os

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class L003(BaseRule):
    """Detect framework routing mismatches in Markdown files."""

    code = "L003"
    message = "Framework routing mismatch"
    category = RulePrefix.L
    severity = Severity.MEDIUM
    file_patterns = ['.md', '.markdown']
    version = "1.0.0"

    # Markdown link pattern: [text](url)
    LINK_PATTERN = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')

    def __init__(self):
        super().__init__()
        # Framework configuration (could be loaded from config file)
        self.framework = self._detect_framework()
        self.docs_root = None  # Will be set based on first file processed

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check for framework routing mismatches in Markdown files.

        Args:
            file_path: Path to markdown file
            structure: Parsed structure (not used)
            content: File content to parse for links

        Returns:
            List of detections for routing mismatches
        """
        detections = []
        lines = content.splitlines()

        # Set docs_root based on file path if not already set
        if self.docs_root is None:
            self.docs_root = self._find_docs_root(file_path)

        base_path = Path(file_path).parent

        for line_num, line in enumerate(lines, start=1):
            # Find all markdown links in this line
            for match in self.LINK_PATTERN.finditer(line):
                text = match.group(1)
                url = match.group(2)

                # Only check absolute web paths (framework routing)
                if not url.startswith('/'):
                    continue

                # Skip external protocol-relative URLs (//example.com)
                if url.startswith('//'):
                    continue

                # Check if this framework route has a mismatch
                is_broken, reason, expected_path = self._is_broken_route(base_path, url)

                if is_broken:
                    message = f"{self.message}: {url}"
                    suggestion = self._suggest_fix(url, reason, expected_path)

                    detections.append(Detection(
                        file_path=file_path,
                        line=line_num,
                        rule_code=self.code,
                        message=message,
                        column=match.start() + 1,  # 1-indexed
                        suggestion=suggestion,
                        context=line.strip(),
                        severity=self.severity,
                        category=self.category
                    ))

        return detections

    def _detect_framework(self) -> str:
        """Auto-detect framework type based on project structure.

        Returns:
            Framework name ('fasthtml', 'jekyll', 'hugo', 'static')
        """
        # Look for framework indicators in current directory tree
        cwd = Path.cwd()

        # Check for FastHTML indicators
        if (cwd / "main.py").exists() or (cwd / "app.py").exists():
            # Check for FastHTML imports
            for py_file in cwd.glob("*.py"):
                try:
                    content = py_file.read_text()
                    if 'fasthtml' in content.lower():
                        return 'fasthtml'
                except Exception:
                    pass

        # Check for Jekyll
        if (cwd / "_config.yml").exists() or (cwd / "Gemfile").exists():
            return 'jekyll'

        # Check for Hugo
        if (cwd / "config.toml").exists() or (cwd / "hugo.toml").exists():
            return 'hugo'

        # Default to FastHTML (SIL's primary framework)
        return 'fasthtml'

    def _find_docs_root(self, file_path: str) -> Path:
        """Find documentation root directory.

        Args:
            file_path: Path to current file

        Returns:
            Path to docs root
        """
        path = Path(file_path).resolve()

        # Look for common docs directory names
        for parent in [path.parent] + list(path.parents):
            if parent.name in ('docs', 'documentation', 'content', '_docs'):
                return parent
            # Check if this directory contains a docs/ subdirectory
            if (parent / 'docs').exists():
                return parent / 'docs'

        # Fallback: use parent directory of the file
        return path.parent

    def _is_broken_route(self, base_path: Path, url: str) -> Tuple[bool, str, Optional[str]]:
        """Check if a framework route is broken.

        Args:
            base_path: Directory containing the markdown file
            url: Absolute URL path (e.g., /foundations/GLOSSARY)

        Returns:
            Tuple of (is_broken, reason, expected_path)
        """
        # Split path and anchor
        if '#' in url:
            path_part, anchor = url.split('#', 1)
        else:
            path_part = url
            anchor = None

        # Remove leading slash
        relative_path = path_part.lstrip('/')

        if self.framework == 'fasthtml':
            return self._check_fasthtml_route(relative_path)
        elif self.framework == 'jekyll':
            return self._check_jekyll_route(relative_path)
        elif self.framework == 'hugo':
            return self._check_hugo_route(relative_path)
        else:
            return self._check_static_route(relative_path)

    def _check_fasthtml_route(self, path: str) -> Tuple[bool, str, Optional[str]]:
        """Check FastHTML routing conventions.

        FastHTML conventions:
        - /path/FILE → serves from path/FILE.md (case-insensitive)
        - /path/file → serves from path/file.md
        - Missing .md extension is handled automatically

        Args:
            path: Relative path without leading slash

        Returns:
            Tuple of (is_broken, reason, expected_path)
        """
        if not self.docs_root:
            return (False, "", None)

        # Try exact match with .md
        exact = self.docs_root / f"{path}.md"
        if exact.exists():
            return (False, "", str(exact))

        # Try lowercase match (FastHTML is case-insensitive)
        lowercase = self.docs_root / f"{path.lower()}.md"
        if lowercase.exists():
            return (False, "", str(lowercase))

        # Try case-insensitive search in the target directory
        path_obj = Path(path)
        target_dir = self.docs_root / path_obj.parent
        target_name = path_obj.name

        if target_dir.exists():
            for file in target_dir.iterdir():
                # Check if filename matches (case-insensitive, with or without .md)
                if file.suffix in ('.md', '.markdown'):
                    stem = file.stem
                    if stem.lower() == target_name.lower():
                        return (False, "", str(file))

        # Not found
        expected = str(exact)
        return (True, "file_not_found", expected)

    def _check_jekyll_route(self, path: str) -> Tuple[bool, str, Optional[str]]:
        """Check Jekyll routing conventions.

        Jekyll conventions:
        - /path/file.html → serves from path/file.md
        - Permalinks in frontmatter override

        Args:
            path: Relative path without leading slash

        Returns:
            Tuple of (is_broken, reason, expected_path)
        """
        if not self.docs_root:
            return (False, "", None)

        # Remove .html extension if present
        if path.endswith('.html'):
            path = path[:-5]

        # Try with .md extension
        md_path = self.docs_root / f"{path}.md"
        if md_path.exists():
            return (False, "", str(md_path))

        # Try in _posts directory
        posts_dir = self.docs_root / '_posts'
        if posts_dir.exists():
            # Jekyll posts follow YYYY-MM-DD-title.md format
            for post in posts_dir.glob('*.md'):
                # Extract title from filename (remove date prefix)
                parts = post.stem.split('-', 3)
                if len(parts) >= 4:
                    title = parts[3]
                    if title.lower() in path.lower():
                        return (False, "", str(post))

        expected = str(md_path)
        return (True, "file_not_found", expected)

    def _check_hugo_route(self, path: str) -> Tuple[bool, str, Optional[str]]:
        """Check Hugo routing conventions.

        Hugo conventions:
        - /path/file/ → serves from content/path/file/index.md
        - /path/file → serves from content/path/file.md

        Args:
            path: Relative path without leading slash

        Returns:
            Tuple of (is_broken, reason, expected_path)
        """
        if not self.docs_root:
            return (False, "", None)

        # Hugo uses content/ directory
        content_dir = self.docs_root.parent / 'content'
        if not content_dir.exists():
            content_dir = self.docs_root

        # Try as file
        file_path = content_dir / f"{path}.md"
        if file_path.exists():
            return (False, "", str(file_path))

        # Try as directory with index
        index_path = content_dir / path / "index.md"
        if index_path.exists():
            return (False, "", str(index_path))

        # Try _index.md (section page)
        section_path = content_dir / path / "_index.md"
        if section_path.exists():
            return (False, "", str(section_path))

        expected = str(file_path)
        return (True, "file_not_found", expected)

    def _check_static_route(self, path: str) -> Tuple[bool, str, Optional[str]]:
        """Check static site routing (simple file mapping).

        Args:
            path: Relative path without leading slash

        Returns:
            Tuple of (is_broken, reason, expected_path)
        """
        if not self.docs_root:
            return (False, "", None)

        # Try with .md extension
        md_path = self.docs_root / f"{path}.md"
        if md_path.exists():
            return (False, "", str(md_path))

        # Try as index file
        index_path = self.docs_root / path / "index.md"
        if index_path.exists():
            return (False, "", str(index_path))

        expected = str(md_path)
        return (True, "file_not_found", expected)

    def _suggest_fix(self, url: str, reason: str, expected_path: Optional[str]) -> str:
        """Generate helpful suggestion for fixing routing mismatch.

        Args:
            url: The broken URL
            reason: Reason why route is broken
            expected_path: Expected file path

        Returns:
            Suggestion string
        """
        suggestions = []

        if reason == "file_not_found":
            suggestions.append(f"Expected file not found: {expected_path}")

            # Check for similar files
            if expected_path and self.docs_root:
                expected = Path(expected_path)
                target_dir = expected.parent

                if target_dir.exists():
                    # Find files with similar names
                    similar = []
                    target_stem = expected.stem.lower()

                    for file in target_dir.glob('*.md'):
                        if file.stem.lower().startswith(target_stem[:3]):
                            similar.append(file.name)

                    if similar:
                        suggestions.append(f"Similar files: {', '.join(similar[:3])}")

            # Framework-specific suggestions
            if self.framework == 'fasthtml':
                suggestions.append("FastHTML routes are case-insensitive - check file exists")
            elif self.framework == 'jekyll':
                suggestions.append("Check _posts/ directory or frontmatter permalinks")
            elif self.framework == 'hugo':
                suggestions.append("Check content/ directory or index.md files")

        if suggestions:
            return " | ".join(suggestions)
        return "Framework route does not resolve to expected file"
