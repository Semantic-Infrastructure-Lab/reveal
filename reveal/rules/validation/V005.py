"""V005: Static help file synchronization.

Validates that all help files referenced in STATIC_HELP dict actually exist.
Prevents broken `reveal help://topic` commands from deployed code.

Example violation:
    - STATIC_HELP entry: 'markdown': 'MARKDOWN_GUIDE.md'
    - File missing: reveal/docs/MARKDOWN_GUIDE.md doesn't exist
    - Result: `reveal help://markdown` fails
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
import re

from ..base import BaseRule, Detection, RulePrefix, Severity


class V005(BaseRule):
    """Validate that all STATIC_HELP references point to existing files."""

    code = "V005"
    message = "Help file referenced in STATIC_HELP but does not exist"
    category = RulePrefix.V
    severity = Severity.HIGH  # Broken help commands are serious
    file_patterns = ['*']

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check that all static help files exist."""
        detections: List[Detection] = []

        # Only run for reveal:// URIs
        if not file_path.startswith('reveal://'):
            return detections

        # Find reveal root
        reveal_root = self._find_reveal_root()
        if not reveal_root:
            return detections

        # Get STATIC_HELP dict from help.py
        static_help = self._get_static_help(reveal_root)

        if not static_help:
            detections.append(self.create_detection(
                file_path="reveal/adapters/help.py",
                line=1,
                message="Could not parse STATIC_HELP dict from help.py",
                suggestion="Verify STATIC_HELP dict syntax in reveal/adapters/help.py",
                context="Unable to validate help file references"
            ))
            return detections

        # Check each referenced file (help docs are in reveal/docs/)
        docs_dir = reveal_root / 'docs'
        for topic, file_path_str in static_help.items():
            help_file = docs_dir / file_path_str

            if not help_file.exists():
                detections.append(self.create_detection(
                    file_path="reveal/adapters/help.py",
                    line=self._find_line_in_static_help(reveal_root, topic),
                    message=f"Help file '{file_path_str}' for topic '{topic}' does not exist",
                    suggestion=f"Either create {file_path_str} or remove '{topic}' from STATIC_HELP",
                    context=f"Expected path: {help_file}"
                ))

        # Reverse check: Find .md files that could be help but aren't registered
        self._check_unregistered_guides(reveal_root, static_help, detections)

        return detections

    def _get_static_help(self, reveal_root: Path) -> Dict[str, str]:
        """Extract STATIC_HELP dict from help.py."""
        help_file = reveal_root / 'adapters' / 'help.py'
        if not help_file.exists():
            return {}

        try:
            content = help_file.read_text(encoding='utf-8')

            # Find STATIC_HELP dict
            pattern = r"STATIC_HELP\s*=\s*\{([^}]+)\}"
            match = re.search(pattern, content, re.DOTALL)

            if not match:
                return {}

            dict_content = match.group(1)

            # Parse the dict entries
            static_help = {}
            for line in dict_content.split('\n'):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                entry_match = re.match(r"'([^']+)':\s*'([^']+)'", line)
                if entry_match:
                    topic, file_path = entry_match.groups()
                    static_help[topic] = file_path

            return static_help

        except Exception:
            return {}

    def _find_line_in_static_help(self, reveal_root: Path, topic: str) -> int:
        """Find line number of topic in STATIC_HELP dict."""
        help_file = reveal_root / 'adapters' / 'help.py'
        if not help_file.exists():
            return 1

        try:
            lines = help_file.read_text(encoding='utf-8').split('\n')
            for i, line in enumerate(lines, 1):
                if f"'{topic}':" in line:
                    return i
        except Exception:
            pass

        return 1

    def _check_unregistered_guides(self,
                                    reveal_root: Path,
                                    static_help: Dict[str, str],
                                    detections: List[Detection]):
        """Check for guide files that exist but aren't registered."""
        # Patterns for files that look like help guides
        guide_patterns = [
            '*_GUIDE.md',
            '*GUIDE.md',
        ]

        # Help docs are in reveal/docs/
        docs_dir = reveal_root / 'docs'
        if not docs_dir.exists():
            return

        registered_files = set(static_help.values())

        for pattern in guide_patterns:
            for guide_file in docs_dir.rglob(pattern):
                relative_path = str(guide_file.relative_to(docs_dir))

                # Skip if already registered
                if relative_path in registered_files:
                    continue

                # Skip test files or hidden directories
                if '/test' in relative_path or '/.':
                    continue

                # Suggest registration
                suggested_topic = guide_file.stem.lower().replace('_guide', '').replace('guide', '')

                detections.append(self.create_detection(
                    file_path=relative_path,
                    line=1,
                    message=f"Guide file '{guide_file.name}' exists but not registered in STATIC_HELP",
                    suggestion=f"Consider adding '{suggested_topic}': '{relative_path}' to STATIC_HELP",
                    context="Unregistered guides are not discoverable via help://"
                ))

    def _find_reveal_root(self) -> Optional[Path]:
        """Find reveal's root directory."""
        current = Path(__file__).parent.parent.parent

        if (current / 'analyzers').exists() and (current / 'rules').exists():
            return current

        for _ in range(5):
            if (current / 'reveal' / 'analyzers').exists():
                return current / 'reveal'
            current = current.parent
            if current == current.parent:
                break

        return None
