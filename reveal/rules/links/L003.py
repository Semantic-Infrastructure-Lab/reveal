"""L003: Framework routing mismatch detector.

Detects links that use framework-specific routing conventions (FastHTML, Jekyll, Hugo)
but don't resolve correctly to the expected files.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

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
            structure: Parsed structure from markdown analyzer
            content: File content (used as fallback)

        Returns:
            List of detections for routing mismatches
        """
        detections = []

        # Set docs_root based on file path if not already set
        if self.docs_root is None:
            self.docs_root = self._find_docs_root(file_path)

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

        # Check each framework routing link for issues
        for link in links:
            text = link.get('text', '')
            url = link.get('url', '')
            line_num = link.get('line', 1)

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
                    column=1,  # Column not available from structure
                    suggestion=suggestion,
                    context=f"[{text}]({url})",
                    severity=self.severity,
                    category=self.category
                ))

        return detections

    def _has_fasthtml_indicators(self, cwd: Path) -> bool:
        """Check if directory has FastHTML framework indicators.

        Args:
            cwd: Current working directory

        Returns:
            True if FastHTML indicators found
        """
        # Check for Python app files
        if not ((cwd / "main.py").exists() or (cwd / "app.py").exists()):
            return False

        # Check for FastHTML imports in Python files
        for py_file in cwd.glob("*.py"):
            try:
                content = py_file.read_text()
                if 'fasthtml' in content.lower():
                    return True
            except Exception:
                continue

        return False

    def _detect_framework(self) -> str:
        """Auto-detect framework type based on project structure.

        Returns:
            Framework name ('fasthtml', 'jekyll', 'hugo', 'static')
        """
        cwd = Path.cwd()

        # Check for FastHTML
        if self._has_fasthtml_indicators(cwd):
            return 'fasthtml'

        # Check for Jekyll
        if (cwd / "_config.yml").exists() or (cwd / "Gemfile").exists():
            return 'jekyll'

        # Check for Hugo
        if (cwd / "config.toml").exists() or (cwd / "hugo.toml").exists():
            return 'hugo'

        # Default to FastHTML
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

    def _is_broken_route(
        self, base_path: Path, url: str
    ) -> Tuple[bool, str, Optional[str]]:
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

    def _find_case_insensitive_match(
        self, target_dir: Path, target_name: str
    ) -> Optional[Path]:
        """Find case-insensitive file match in directory.

        Args:
            target_dir: Directory to search
            target_name: Target filename (without extension)

        Returns:
            Matching file path or None
        """
        if not target_dir.exists():
            return None

        for file in target_dir.iterdir():
            if file.suffix not in ('.md', '.markdown'):
                continue
            if file.stem.lower() == target_name.lower():
                return file

        return None

    def _check_fasthtml_route(
        self, path: str
    ) -> Tuple[bool, str, Optional[str]]:
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

        match = self._find_case_insensitive_match(target_dir, target_name)
        if match:
            return (False, "", str(match))

        # Not found
        return (True, "file_not_found", str(exact))

    def _find_jekyll_post(self, path: str) -> Optional[Path]:
        """Find matching post in Jekyll _posts directory.

        Args:
            path: Path to match against post titles

        Returns:
            Matching post file or None
        """
        if not self.docs_root:
            return None

        posts_dir = self.docs_root / '_posts'
        if not posts_dir.exists():
            return None

        # Jekyll posts follow YYYY-MM-DD-title.md format
        for post in posts_dir.glob('*.md'):
            # Extract title from filename (remove date prefix)
            parts = post.stem.split('-', 3)
            if len(parts) >= 4:
                title = parts[3]
                if title.lower() in path.lower():
                    return post

        return None

    def _check_jekyll_route(
        self, path: str
    ) -> Tuple[bool, str, Optional[str]]:
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
        post = self._find_jekyll_post(path)
        if post:
            return (False, "", str(post))

        return (True, "file_not_found", str(md_path))

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

    def _find_similar_files(self, expected_path: str) -> List[str]:
        """Find files with similar names to expected path.

        Args:
            expected_path: Expected file path

        Returns:
            List of similar filenames (up to 3)
        """
        if not expected_path or not self.docs_root:
            return []

        expected = Path(expected_path)
        target_dir = expected.parent

        if not target_dir.exists():
            return []

        # Find files with similar names
        similar = []
        target_stem = expected.stem.lower()

        for file in target_dir.glob('*.md'):
            if file.stem.lower().startswith(target_stem[:3]):
                similar.append(file.name)

        return similar[:3]  # Return max 3

    def _get_framework_suggestion(self) -> str:
        """Get framework-specific routing suggestion.

        Returns:
            Framework-specific suggestion string
        """
        if self.framework == 'fasthtml':
            return "FastHTML routes are case-insensitive - check file exists"
        elif self.framework == 'jekyll':
            return "Check _posts/ directory or frontmatter permalinks"
        elif self.framework == 'hugo':
            return "Check content/ directory or index.md files"
        return ""

    def _suggest_fix(
        self, url: str, reason: str, expected_path: Optional[str]
    ) -> str:
        """Generate helpful suggestion for fixing routing mismatch.

        Args:
            url: The broken URL
            reason: Reason why route is broken
            expected_path: Expected file path

        Returns:
            Suggestion string
        """
        if reason != "file_not_found":
            return "Framework route does not resolve to expected file"

        suggestions = [f"Expected file not found: {expected_path}"]

        # Add similar files if found
        similar = self._find_similar_files(expected_path)
        if similar:
            suggestions.append(f"Similar files: {', '.join(similar)}")

        # Add framework-specific suggestion
        framework_suggestion = self._get_framework_suggestion()
        if framework_suggestion:
            suggestions.append(framework_suggestion)

        return " | ".join(suggestions)
