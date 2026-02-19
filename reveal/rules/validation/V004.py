"""V004: Test coverage gaps.

Validates that each analyzer has a corresponding test file.
Helps prevent untested analyzers from being deployed.

Example violation:
    - Analyzer: reveal/analyzers/newanalyzer.py
    - Missing: tests/test_newanalyzer.py
    - Result: No tests for this analyzer
"""

from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root, is_dev_checkout


class V004(BaseRule):
    """Validate that analyzers have corresponding test files."""

    code = "V004"
    message = "Analyzer missing test file"
    category = RulePrefix.V
    severity = Severity.LOW  # Nice to have but not critical
    file_patterns = ['*']

    # Analyzers that are known to not need separate test files
    # (e.g., tested via integration tests or shared test suites)
    EXEMPT_ANALYZERS = {
        '__init__',
        'base',
    }

    # Analyzers tested in shared test files
    # Format: {analyzer_name: shared_test_file_name}
    SHARED_TEST_FILES = {
        'bash': 'test_new_analyzers.py',
        'javascript': 'test_new_analyzers.py',
        'typescript': 'test_new_analyzers.py',
        'python': 'test_treesitter_utf8.py',  # Also in test_shebang_detection.py
    }

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check for missing test files."""
        detections: List[Detection] = []

        # Only run for reveal:// URIs
        if not file_path.startswith('reveal://'):
            return detections

        # Find reveal root
        reveal_root = find_reveal_root()
        if not reveal_root:
            return detections

        # Test coverage checks only make sense for dev checkouts
        # (installed packages don't have tests/ directory)
        if not is_dev_checkout(reveal_root):
            return detections

        # Find project root (parent of reveal/)
        project_root = reveal_root.parent
        tests_dir = project_root / 'tests'

        if not tests_dir.exists():
            # No tests directory at all - report once
            detections.append(self.create_detection(
                file_path=".",
                line=1,
                message="No tests/ directory found in project",
                suggestion="Create tests/ directory for test files",
                context=f"Expected: {tests_dir}"
            ))
            return detections

        # Get all analyzer files
        analyzers_dir = reveal_root / 'analyzers'
        if not analyzers_dir.exists():
            return detections

        for analyzer_file in analyzers_dir.glob('*.py'):
            detection = self._check_analyzer_test_coverage(analyzer_file, tests_dir, reveal_root)
            if detection:
                detections.append(detection)

        return detections

    def _check_analyzer_test_coverage(self, analyzer_file, tests_dir, reveal_root):
        """Check if a single analyzer file has test coverage. Returns Detection or None."""
        analyzer_name = analyzer_file.stem
        if analyzer_name in self.EXEMPT_ANALYZERS:
            return None
        if analyzer_name in self.SHARED_TEST_FILES:
            if (tests_dir / self.SHARED_TEST_FILES[analyzer_name]).exists():
                return None
        expected = [
            tests_dir / f'test_{analyzer_name}.py',
            tests_dir / f'test_{analyzer_name}_analyzer.py',
        ]
        if any(tf.exists() for tf in expected):
            return None
        return self.create_detection(
            file_path=str(analyzer_file.relative_to(reveal_root)),
            line=1,
            message=f"Analyzer '{analyzer_name}' has no test file",
            suggestion=f"Create tests/test_{analyzer_name}.py or add to shared test suite",
            context=f"Analyzer: {analyzer_file.name}"
        )
