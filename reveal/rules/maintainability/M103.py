"""M103: Version consistency detector.

Detects version mismatches between pyproject.toml and __init__.py.
Critical for releases - prevents version confusion.

Example violation:
    - pyproject.toml: version = "1.2.0"
    - src/mypackage/__init__.py: __version__ = "1.1.0"
    - Result: Version mismatch detected

This is a general rule that works on any Python project.
For reveal-specific version checks, see V007.
"""

import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # Python < 3.11 fallback

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class M103(BaseRule):
    """Detect version mismatches in Python projects."""

    code = "M103"
    message = "Version mismatch between pyproject.toml and source code"
    category = RulePrefix.M
    severity = Severity.HIGH
    file_patterns = ['__init__.py']  # Trigger on __init__.py files
    version = "1.0.0"

    # Pattern to find __version__ in Python files
    VERSION_PATTERN = re.compile(
        r'^__version__\s*=\s*["\']([0-9]+\.[0-9]+\.[0-9]+(?:[.-][\w.]+)?)["\']',
        re.MULTILINE
    )

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """
        Check for version consistency between pyproject.toml and __init__.py.

        Args:
            file_path: Path to __init__.py file
            structure: Parsed structure (not used)
            content: File content

        Returns:
            List of detections for version mismatches
        """
        detections = []
        path = Path(file_path)

        # Only check __init__.py files
        if path.name != '__init__.py':
            return detections

        # Extract __version__ from this file
        init_version = self._extract_init_version(content)
        if not init_version:
            return detections  # No __version__ to check

        # Skip dynamic version (e.g., from importlib.metadata)
        if 'version(' in content or 'importlib' in content:
            # Check for fallback version which is often outdated
            if '__version__ = "' in content or "__version__ = '" in content:
                # There's a hardcoded fallback - check it
                pass
            else:
                return detections  # Dynamic version, can't check statically

        # Find pyproject.toml
        pyproject_path = self._find_pyproject(path)
        if not pyproject_path:
            return detections

        # Get version from pyproject.toml
        pyproject_version = self._extract_pyproject_version(pyproject_path)
        if not pyproject_version:
            return detections

        # Compare versions
        if init_version != pyproject_version:
            # Find the line number of __version__
            line_num = self._find_version_line(content)

            detections.append(self.create_detection(
                file_path=file_path,
                line=line_num,
                message=(
                    f"__version__ = '{init_version}' doesn't match "
                    f"pyproject.toml version = '{pyproject_version}'"
                ),
                suggestion=(
                    f"Update __version__ to '{pyproject_version}' or use dynamic versioning: "
                    f"from importlib.metadata import version; __version__ = version('package-name')"
                ),
                context=f"pyproject.toml: {pyproject_version}, __init__.py: {init_version}"
            ))

        return detections

    def _extract_init_version(self, content: str) -> Optional[str]:
        """Extract __version__ from Python file content."""
        match = self.VERSION_PATTERN.search(content)
        if match:
            return match.group(1)
        return None

    def _find_version_line(self, content: str) -> int:
        """Find the line number containing __version__."""
        for i, line in enumerate(content.splitlines(), start=1):
            if '__version__' in line and '=' in line:
                return i
        return 1

    def _find_pyproject(self, path: Path) -> Optional[Path]:
        """Find pyproject.toml by walking up the directory tree."""
        current = path.parent

        for _ in range(10):  # Max 10 levels up
            pyproject = current / 'pyproject.toml'
            if pyproject.exists():
                return pyproject
            if current.parent == current:
                break
            current = current.parent

        return None

    def _extract_pyproject_version(self, pyproject_path: Path) -> Optional[str]:
        """Extract version from pyproject.toml."""
        try:
            content = pyproject_path.read_text(encoding='utf-8')
            data = tomllib.loads(content)

            # Check [project] section (PEP 621)
            version = data.get('project', {}).get('version')
            if version:
                return version

            # Check [tool.poetry] section (Poetry)
            version = data.get('tool', {}).get('poetry', {}).get('version')
            if version:
                return version

            # Fallback: regex for version = "X.Y.Z"
            match = re.search(
                r'^version\s*=\s*["\']([0-9]+\.[0-9]+\.[0-9]+(?:[.-][\w.]+)?)["\']',
                content,
                re.MULTILINE
            )
            if match:
                return match.group(1)

        except Exception as e:
            logger.debug(f"Error reading pyproject.toml: {e}")

        return None
