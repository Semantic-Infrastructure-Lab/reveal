"""V001: Help documentation completeness.

Validates that every supported file type has help documentation.
This would have caught Issue #2 from the markdown bugs analysis.

Example violation:
    - Analyzer: reveal/analyzers/markdown.py
    - No help topic: help://markdown (missing before fix)
    - Static help file: MARKDOWN_GUIDE.md (missing before fix)
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
import re

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root


class V001(BaseRule):
    """Validate that all supported file types have help documentation."""

    code = "V001"
    message = "File type analyzer missing help documentation"
    category = RulePrefix.M  # Maintainability
    severity = Severity.MEDIUM
    file_patterns = ['*']  # Runs on any target (checks reveal internals)

    # Known file types that should have help (paths relative to reveal/docs/)
    EXPECTED_HELP_TOPICS = {
        'markdown': 'MARKDOWN_GUIDE.md',
        'python': 'PYTHON_ADAPTER_GUIDE.md',
        # Add more as they're documented
    }

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check for missing help documentation."""
        # Only run this check for reveal:// URIs
        if not file_path.startswith('reveal://'):
            return []

        # Find reveal root
        reveal_root = find_reveal_root()
        if not reveal_root:
            return []

        # Get all analyzers and static help
        analyzers = self._get_analyzers(reveal_root)
        static_help = self._get_static_help(reveal_root)

        # Run validation checks
        detections = []
        detections.extend(self._check_analyzers_have_help(analyzers, static_help))
        detections.extend(self._validate_help_files_exist(static_help, reveal_root))

        return detections

    def _check_analyzers_have_help(
        self, analyzers: Dict[str, Path], static_help: Dict[str, str]
    ) -> List[Detection]:
        """Check that expected analyzers have help documentation."""
        detections = []

        for analyzer_name, analyzer_path in analyzers.items():
            if analyzer_name in static_help:
                continue  # Has help, OK

            # Missing from help system - check if expected
            if analyzer_name in self.EXPECTED_HELP_TOPICS:
                expected_file = self.EXPECTED_HELP_TOPICS[analyzer_name]
                detections.append(self.create_detection(
                    file_path=str(analyzer_path),
                    line=1,
                    message=f"Analyzer '{analyzer_name}' missing from help system",
                    suggestion=f"Add '{analyzer_name}': '{expected_file}' to STATIC_HELP in reveal/adapters/help.py",
                    context=f"Expected help file: {expected_file}"
                ))

        return detections

    def _validate_help_files_exist(
        self, static_help: Dict[str, str], reveal_root: Path
    ) -> List[Detection]:
        """Check that referenced help files actually exist."""
        detections = []

        # Help docs are in reveal/docs/ subdirectory
        docs_dir = reveal_root / 'docs'

        for topic, help_file in static_help.items():
            help_path = docs_dir / help_file
            if not help_path.exists():
                detections.append(self.create_detection(
                    file_path="reveal/adapters/help.py",
                    line=1,
                    message=f"Help file '{help_file}' referenced but does not exist",
                    suggestion=f"Either create {help_file} or remove '{topic}' from STATIC_HELP",
                    context=f"Referenced in STATIC_HELP for topic '{topic}'"
                ))

        return detections

    def _get_analyzers(self, reveal_root: Path) -> Dict[str, Path]:
        """Get all analyzer files.

        Returns:
            Dict mapping analyzer name to file path
        """
        analyzers = {}
        analyzers_dir = reveal_root / 'analyzers'

        if not analyzers_dir.exists():
            return analyzers

        for file in analyzers_dir.glob('*.py'):
            if file.stem.startswith('_'):
                continue
            analyzers[file.stem] = file

        return analyzers

    def _get_static_help(self, reveal_root: Path) -> Dict[str, str]:
        """Extract STATIC_HELP dict from help.py.

        Returns:
            Dict mapping topic name to help file path
        """
        help_file = reveal_root / 'adapters' / 'help.py'
        if not help_file.exists():
            return {}

        try:
            content = help_file.read_text()
            dict_content = self._find_static_help_dict(content)
            if not dict_content:
                return {}

            return self._parse_dict_entries(dict_content)

        except Exception:
            return {}

    def _find_static_help_dict(self, content: str) -> Optional[str]:
        """Find STATIC_HELP dict content using regex.

        Returns:
            The dict content string, or None if not found
        """
        # Pattern: STATIC_HELP = { ... }
        pattern = r"STATIC_HELP\s*=\s*\{([^}]+)\}"
        match = re.search(pattern, content, re.DOTALL)
        return match.group(1) if match else None

    def _parse_dict_entries(self, dict_content: str) -> Dict[str, str]:
        """Parse dict entries from STATIC_HELP content.

        Args:
            dict_content: The inner content of the STATIC_HELP dict

        Returns:
            Dict mapping topic name to help file path
        """
        static_help = {}

        for line in dict_content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Pattern: 'topic': 'file.md',
            entry_match = re.match(r"'([^']+)':\s*'([^']+)'", line)
            if entry_match:
                topic, file_path = entry_match.groups()
                static_help[topic] = file_path

        return static_help
