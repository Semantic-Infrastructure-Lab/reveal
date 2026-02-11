"""U502: URL consistency detector.

Detects URLs in code/docs that don't match the canonical URLs in pyproject.toml.
Catches issues like personal repo URLs that should be organization URLs.
"""

import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # Python < 3.11 fallback

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class U502(BaseRule):
    """Detect URLs inconsistent with pyproject.toml canonical URLs."""

    code = "U502"
    message = "URL doesn't match canonical project URL"
    category = RulePrefix.U
    severity = Severity.MEDIUM
    file_patterns = ['.py', '.md', '.rst', '.txt', '.sh', '.yaml', '.yml', '.toml']
    version = "1.0.0"

    # Pattern to find GitHub URLs
    GITHUB_URL_PATTERN = re.compile(
        r'https?://(?:www\.)?github\.com/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_.-]+)',
        re.IGNORECASE
    )

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """
        Check for URLs that don't match pyproject.toml canonical URLs.

        Args:
            file_path: Path to file
            structure: Parsed structure (not used)
            content: File content

        Returns:
            List of detections
        """
        detections: List[Dict[str, Any]] = []
        path = Path(file_path)

        # Skip pyproject.toml itself (it's the source of truth)
        if path.name == 'pyproject.toml':
            return detections

        # Find pyproject.toml
        pyproject_path = self._find_pyproject(path)
        if not pyproject_path:
            return detections

        # Get canonical URLs from pyproject.toml
        canonical_urls = self._get_canonical_urls(pyproject_path)
        if not canonical_urls:
            return detections

        # Extract owner/repo from canonical URLs
        canonical_repos = self._extract_repos(canonical_urls)
        if not canonical_repos:
            return detections

        # Check file content for inconsistent URLs
        lines = content.splitlines()
        for i, line in enumerate(lines, start=1):
            for match in self.GITHUB_URL_PATTERN.finditer(line):
                found_url = match.group(0)
                found_owner = match.group(1)
                found_repo = match.group(2)

                # Normalize repo name (remove .git suffix)
                found_repo = found_repo.rstrip('.git')

                # Check if this matches any canonical repo
                found_key = f"{found_owner}/{found_repo}".lower()
                is_consistent = any(
                    found_key == canonical.lower()
                    for canonical in canonical_repos
                )

                if not is_consistent:
                    # Find the canonical URL to suggest
                    canonical_suggestion = self._get_canonical_suggestion(
                        canonical_repos, found_repo
                    )

                    detections.append(self.create_detection(
                        file_path=file_path,
                        line=i,
                        column=match.start() + 1,
                        message=f"URL '{found_url}' doesn't match canonical project URL",
                        suggestion=(
                            f"Update to canonical URL: https://github.com/{canonical_suggestion}"
                            if canonical_suggestion else
                            f"Check if this URL should match pyproject.toml URLs"
                        ),
                        context=line.strip()[:100]
                    ))

        return detections

    def _find_pyproject(self, path: Path) -> Optional[Path]:
        """Find pyproject.toml by walking up the directory tree."""
        current = path.parent if path.is_file() else path

        for _ in range(10):  # Max 10 levels up
            pyproject = current / 'pyproject.toml'
            if pyproject.exists():
                return pyproject
            if current.parent == current:
                break
            current = current.parent

        return None

    def _get_canonical_urls(self, pyproject_path: Path) -> Set[str]:
        """Extract canonical URLs from pyproject.toml."""
        urls = set()

        try:
            content = pyproject_path.read_text(encoding='utf-8')
            data = tomllib.loads(content)

            # Check [project.urls] section
            project_urls = data.get('project', {}).get('urls', {})
            for key, url in project_urls.items():
                if isinstance(url, str) and 'github.com' in url.lower():
                    urls.add(url)

            # Check [tool.poetry.urls] section (Poetry projects)
            poetry_urls = data.get('tool', {}).get('poetry', {}).get('urls', {})
            for key, url in poetry_urls.items():
                if isinstance(url, str) and 'github.com' in url.lower():
                    urls.add(url)

            # Check homepage, repository fields
            for field in ['homepage', 'repository', 'documentation']:
                url = data.get('project', {}).get(field, '')
                if isinstance(url, str) and 'github.com' in url.lower():
                    urls.add(url)

        except Exception as e:
            logger.debug(f"Error reading pyproject.toml: {e}")

        return urls

    def _extract_repos(self, urls: Set[str]) -> Set[str]:
        """Extract owner/repo pairs from URLs."""
        repos = set()

        for url in urls:
            match = self.GITHUB_URL_PATTERN.search(url)
            if match:
                owner = match.group(1)
                repo = match.group(2).rstrip('.git')
                repos.add(f"{owner}/{repo}")

        return repos

    def _get_canonical_suggestion(self, canonical_repos: Set[str],
                                   found_repo: str) -> Optional[str]:
        """Get the canonical owner/repo that matches the found repo name."""
        found_repo_lower = found_repo.lower()

        for canonical in canonical_repos:
            _, repo = canonical.split('/', 1)
            if repo.lower() == found_repo_lower:
                return canonical

        # Return first canonical if no match found
        return next(iter(canonical_repos), None)
