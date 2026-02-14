"""V022: Package manifest file inclusion validation.

Validates that files referenced in CLI handlers and critical paths are
properly included in package manifests (MANIFEST.in, pyproject.toml).

Prevents deployment bugs where files work in development but are excluded
from PyPI packages.

Example violation:
    - CLI handler: Path(__file__).parent.parent / 'docs' / 'AGENT_HELP.md'
    - MANIFEST.in: include reveal/AGENT_HELP.md  (wrong path!)
    - Result: Works locally, breaks on PyPI install

Checks:
    - Files referenced in reveal/cli/handlers.py exist
    - MANIFEST.in includes paths that exist
    - Critical docs are included in package manifest
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root


class V022(BaseRule):
    """Validate package manifest includes all necessary files."""

    code = "V022"
    message = "Package manifest missing critical files"
    category = RulePrefix.V
    severity = Severity.HIGH  # Blocks deployment
    file_patterns = ['*']

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check package manifest accuracy."""
        # Only run for reveal:// URIs
        if not file_path.startswith('reveal://'):
            return []

        reveal_root = find_reveal_root()
        if not reveal_root:
            return []

        project_root = reveal_root.parent
        detections: List[Detection] = []

        # Run three independent validation checks
        detections.extend(self._check_cli_handler_paths(reveal_root))
        detections.extend(self._check_manifest_paths(project_root))
        detections.extend(self._check_critical_files(project_root))

        return detections

    def _check_cli_handler_paths(self, reveal_root: Path) -> List[Detection]:
        """Validate CLI handlers reference existing files."""
        detections: List[Detection] = []
        handlers_file = reveal_root / 'cli' / 'handlers.py'

        if not handlers_file.exists():
            return detections

        handler_content = handlers_file.read_text(encoding='utf-8')

        # Find Path(...) / 'docs' / 'AGENT_HELP*.md' patterns
        path_patterns = re.findall(
            r"Path\(__file__\)\.parent\.parent\s*/\s*['\"](\S+)['\"]",
            handler_content
        )

        for path_part in path_patterns:
            # Skip wildcards
            if any(c in path_part for c in ['*', '?']):
                continue

            # Path from CLI handler is relative to reveal/ directory
            check_path = reveal_root / path_part

            # Check if it exists (file or directory)
            if not check_path.exists():
                detections.append(self.create_detection(
                    file_path=f"reveal/cli/handlers.py",
                    line=1,
                    message=f"CLI handler references non-existent path: {path_part}",
                    suggestion=f"Update handler path or create file/directory",
                    context=f"Path: reveal/{path_part}"
                ))

        return detections

    def _check_manifest_paths(self, project_root: Path) -> List[Detection]:
        """Validate MANIFEST.in references existing paths."""
        detections: List[Detection] = []
        manifest_file = project_root / 'MANIFEST.in'

        if not manifest_file.exists():
            return detections

        manifest_content = manifest_file.read_text(encoding='utf-8')

        for line_num, line in enumerate(manifest_content.split('\n'), 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Check "include path/to/file" directives
            if not line.startswith('include ') or 'include-package-data' in line:
                continue

            parts = line.split(None, 1)  # Split on whitespace
            if len(parts) <= 1:
                continue

            path = parts[1].strip()
            if '*' in path or '?' in path:
                continue

            full_path = project_root / path
            if not full_path.exists():
                detections.append(self.create_detection(
                    file_path="MANIFEST.in",
                    line=line_num,
                    message=f"MANIFEST.in references non-existent file: {path}",
                    suggestion=f"Update path to correct location or remove line",
                    context=f"Line: {line}"
                ))

        return detections

    def _check_critical_files(self, project_root: Path) -> List[Detection]:
        """Validate critical files are included in package manifest."""
        detections: List[Detection] = []
        manifest_file = project_root / 'MANIFEST.in'

        if not manifest_file.exists():
            return detections

        critical_files = [
            'reveal/docs/AGENT_HELP.md',
            'reveal/docs/AGENT_HELP_FULL.md',
        ]

        manifest_content = manifest_file.read_text(encoding='utf-8')

        for critical in critical_files:
            file_exists = (project_root / critical).exists()
            if not file_exists:
                continue

            # Check if file is covered by manifest
            # Look for either direct include or recursive-include
            file_dir = Path(critical).parent.as_posix()
            file_ext = Path(critical).suffix

            covered = (
                f"include {critical}" in manifest_content or
                f"recursive-include {file_dir} *{file_ext}" in manifest_content
            )

            if not covered:
                detections.append(self.create_detection(
                    file_path="MANIFEST.in",
                    line=1,
                    message=f"Critical file not included in package: {critical}",
                    suggestion=f"Add: recursive-include {file_dir} *{file_ext}",
                    context=f"File: {critical}"
                ))

        return detections
