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
    file_patterns = []  # No file-extension form; reveal:// self-check only
    uri_patterns = ['^reveal://.*']
    internal = True  # reveal-internal self-check, never applies to external user code

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check package manifest accuracy."""
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

    # Matches Path(__file__) followed by one or more .parent hops, e.g.
    # Path(__file__).parent.parent or Path(__file__).parent.parent.parent
    _FILE_PARENT_PATTERN = re.compile(r"Path\(__file__\)((?:\.parent)+)")
    # A single chained `/ 'segment'` path-join operator following it. Matched
    # repeatedly so a full `.parent.parent / 'docs' / 'AGENT_HELP.md'` chain
    # resolves to the joined path, not just its first segment ('docs') — the
    # original single-capture regex silently could only ever validate that
    # the first path component existed, never the actual target file.
    _PATH_SEGMENT_PATTERN = re.compile(r"\s*/\s*['\"]([^'\"]+)['\"]")

    def _check_cli_handler_paths(self, reveal_root: Path) -> List[Detection]:
        """Validate CLI handler modules reference existing files.

        CLI handlers used to live in a single flat reveal/cli/handlers.py;
        that was split into a reveal/cli/handlers/ package (introspection.py,
        batch.py, ...) plus reveal/cli/handlers_scaffold.py. This check used
        to hardcode the now-nonexistent handlers.py path and an exact
        `.parent.parent` hop count, so it went 100% silently dead after the
        reorg — reveal/cli/handlers/introspection.py's real
        `Path(__file__).parent.parent.parent / 'docs' / 'AGENT_HELP.md'`
        (one hop deeper, since it's nested one directory further) was never
        even looked at (BACK-432 tranche 7). Scan every .py file under
        reveal/cli/ instead of one hardcoded path, and resolve however many
        .parent hops each match actually uses from that file's real location,
        so this keeps working across future reorganizations too.
        """
        detections: List[Detection] = []
        cli_dir = reveal_root / 'cli'

        if not cli_dir.exists():
            return detections

        for handlers_file in sorted(cli_dir.rglob('*.py')):
            try:
                handler_content = handlers_file.read_text(encoding='utf-8')
            except OSError:
                continue

            for match in self._FILE_PARENT_PATTERN.finditer(handler_content):
                parent_hops = match.group(1).count('.parent')

                # Walk forward from the end of the .parent chain, collecting
                # every contiguous `/ 'segment'` join on the same statement.
                segments: List[str] = []
                cursor = match.end()
                while True:
                    seg_match = self._PATH_SEGMENT_PATTERN.match(handler_content, cursor)
                    if not seg_match:
                        break
                    segments.append(seg_match.group(1))
                    cursor = seg_match.end()

                if not segments:
                    continue

                # Skip wildcards
                if any(c in seg for seg in segments for c in ['*', '?']):
                    continue

                # Path(__file__).parent is the file's own directory (1 hop);
                # each additional .parent walks up one more level from there.
                base = handlers_file.parent
                for _ in range(parent_hops - 1):
                    base = base.parent
                check_path = base.joinpath(*segments)
                path_part = '/'.join(segments)

                # Check if it exists (file or directory)
                if not check_path.exists():
                    rel_path = handlers_file.relative_to(reveal_root.parent).as_posix()
                    detections.append(self.create_detection(
                        file_path=rel_path,
                        line=1,
                        message=f"CLI handler references non-existent path: {path_part}",
                        suggestion="Update handler path or create file/directory",
                        context=f"Path: {check_path}"
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
                    suggestion="Update path to correct location or remove line",
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
            # AGENT_HELP_FULL.md was consolidated into AGENT_HELP.md (commit 9292da3)
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
