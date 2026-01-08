"""I004: Standard library shadowing detector.

Detects when a local Python file has the same name as a standard library module,
which can cause import confusion and subtle bugs.

Example problems:
    - logging.py in your project shadows the stdlib logging module
    - json.py shadows the stdlib json module
    - typing.py shadows the stdlib typing module

When you have a local 'logging.py' and another file does 'import logging',
Python may import your local file instead of the stdlib, causing:
    - AttributeError when stdlib functions are missing
    - Circular imports when your logging.py tries to import stdlib logging
    - Confusing behavior that only manifests in certain import orders
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from . import STDLIB_MODULES

logger = logging.getLogger(__name__)


class I004(BaseRule):
    """Detect local files that shadow standard library modules."""

    code = "I004"
    message = "Local file shadows standard library module"
    category = RulePrefix.I
    severity = Severity.MEDIUM
    file_patterns = ['.py']
    version = "1.0.0"

    # Common legitimate cases where shadowing is intentional
    # (e.g., compatibility shims, test fixtures)
    ALLOWED_CONTEXTS = frozenset({
        'test_',      # Test files (test_logging.py is fine)
        'tests/',     # Test directories
        '_test',      # Test suffix (logging_test.py is fine)
        'conftest',   # Pytest config
        'setup',      # Setup files (though setup.py is stdlib too)
    })

    def _is_allowed_context(self, file_path: str) -> bool:
        """Check if file is in an allowed context where shadowing is expected.

        Args:
            file_path: Path to file being checked

        Returns:
            True if shadowing is likely intentional (test files, etc.)
        """
        path_lower = file_path.lower()
        name = Path(file_path).stem.lower()

        # Test files are allowed to shadow (test_json.py, json_test.py)
        if name.startswith('test_') or name.endswith('_test'):
            return True

        # Files in test directories
        if '/tests/' in path_lower or '/test/' in path_lower:
            return True

        # Conftest files
        if name == 'conftest':
            return True

        return False

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check if this file shadows a standard library module.

        Args:
            file_path: Path to Python file
            structure: Parsed structure (not used)
            content: File content (not used for this check)

        Returns:
            List containing one detection if file shadows stdlib, empty otherwise
        """
        path = Path(file_path)
        file_stem = path.stem  # filename without extension

        # Check if filename matches a stdlib module
        if file_stem not in STDLIB_MODULES:
            return []

        # Allow test files and other legitimate contexts
        if self._is_allowed_context(file_path):
            return []

        # Check for noqa comment at file level (first few lines)
        lines = content.split('\n')[:5] if content else []
        for line in lines:
            if '# noqa' in line.lower() and ('i004' in line.lower() or ':' not in line):
                return []

        # Build helpful suggestion based on module
        suggestion = self._build_suggestion(file_stem, path)

        return [self.create_detection(
            file_path=file_path,
            line=1,  # File-level issue
            column=1,
            suggestion=suggestion,
            context=f"File '{path.name}' shadows 'import {file_stem}' from stdlib"
        )]

    def _build_suggestion(self, module_name: str, file_path: Path) -> str:
        """Build a helpful suggestion for renaming the file.

        Args:
            module_name: The stdlib module being shadowed
            file_path: Path to the shadowing file

        Returns:
            Suggestion text with rename recommendation
        """
        # Suggest common naming patterns
        parent_name = file_path.parent.name if file_path.parent.name != '.' else 'app'

        alternatives = [
            f"{parent_name}_{module_name}.py",
            f"my_{module_name}.py",
            f"{module_name}_utils.py",
            f"{module_name}_config.py",
        ]

        # Pick the most appropriate suggestion based on module type
        if module_name == 'logging':
            preferred = f"{parent_name}_logging.py or logger.py"
        elif module_name == 'types':
            preferred = "type_defs.py or models.py"
        elif module_name == 'json':
            preferred = "json_utils.py or serialization.py"
        elif module_name == 'config':
            preferred = "app_config.py or settings.py"
        else:
            preferred = f"{alternatives[0]} or {alternatives[2]}"

        return f"Rename to avoid shadowing stdlib '{module_name}': consider {preferred}"
