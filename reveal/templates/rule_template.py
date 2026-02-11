"""Templates for quality rule scaffolding."""

RULE_TEMPLATE = '''"""{code}: {name}.

{description}
"""

import logging
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class {code}(BaseRule):
    """{name}."""

    code = "{code}"
    message = "{name}"
    category = {category_value}
    severity = Severity.{severity}
    file_patterns = {file_patterns}  # File patterns to match (e.g., ['*.py'], ['*'])
    version = "1.0.0"

    # Configuration defaults
    # Can be overridden in .reveal.yaml:
    #   rules:
    #     {code}:
    #       threshold: 10
    DEFAULT_THRESHOLD = 10

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check for {name}.

        Args:
            file_path: Path to file being checked
            structure: Parsed structure (from reveal analyzer)
            content: Raw file content

        Returns:
            List of detections (violations found)
        """
        detections = []

        # TODO: Implement detection logic
        # Examples:
        #
        # 1. Check content directly:
        #    lines = content.splitlines()
        #    for i, line in enumerate(lines, start=1):
        #        if some_condition(line):
        #            detections.append(Detection(...))
        #
        # 2. Check structure (if available):
        #    if structure:
        #        for func in structure.get('functions', []):
        #            if some_condition(func):
        #                detections.append(Detection(...))
        #
        # 3. Use configuration:
        #    threshold = self.get_threshold('threshold', self.DEFAULT_THRESHOLD)

        # Example detection:
        # detections.append(Detection(
        #     file_path=file_path,
        #     line=line_number,
        #     rule_code=self.code,
        #     message=f"{{self.message}}: specific issue found",
        #     column=column_number,  # Optional
        #     suggestion="How to fix this",  # Optional
        #     context=context_string,  # Optional
        #     severity=self.severity,
        #     category=self.category
        # ))

        return detections
'''

TEST_TEMPLATE = '''"""Tests for {code} rule."""

import pytest
from pathlib import Path
from reveal.rules.{category}.{code} import {code}


class Test{code}Init:
    """Test rule initialization."""

    def test_rule_attributes(self):
        """Test rule has correct attributes."""
        rule = {code}()

        assert rule.code == "{code}"
        assert rule.message == "{name}"
        assert rule.version == "1.0.0"
        assert rule.file_patterns == {file_patterns}


class Test{code}Detection:
    """Test rule detection logic."""

    def test_no_violations(self, tmp_path):
        """Test file with no violations."""
        # TODO: Add clean sample code
        clean_code = """
        # Add code that should pass
        """

        test_file = tmp_path / "test.txt"
        test_file.write_text(clean_code)

        rule = {code}()
        detections = rule.check(str(test_file), None, clean_code)

        assert len(detections) == 0

    def test_detects_violation(self, tmp_path):
        """Test file with violation is detected."""
        # TODO: Add code that should trigger detection
        bad_code = """
        # Add code that should fail
        """

        test_file = tmp_path / "test.txt"
        test_file.write_text(bad_code)

        rule = {code}()
        detections = rule.check(str(test_file), None, bad_code)

        # TODO: Update assertions based on expected behavior
        assert len(detections) > 0
        assert detections[0].rule_code == "{code}"


class Test{code}Configuration:
    """Test rule configuration."""

    def test_default_threshold(self):
        """Test default threshold is used."""
        rule = {code}()
        threshold = rule.get_threshold('threshold', rule.DEFAULT_THRESHOLD)

        assert threshold == rule.DEFAULT_THRESHOLD

    def test_custom_threshold(self):
        """Test custom threshold can be set."""
        rule = {code}()
        rule.thresholds = {{'threshold': 20}}
        threshold = rule.get_threshold('threshold', rule.DEFAULT_THRESHOLD)

        assert threshold == 20
'''

DOC_TEMPLATE = '''# {code}: {name}

## Overview

{description}

## Rule Details

- **Code**: {code}
- **Category**: {category}
- **Severity**: {severity}
- **File Patterns**: {file_patterns}

## Configuration

Configure this rule in `.reveal.yaml`:

```yaml
rules:
  {code}:
    enabled: true
    threshold: 10  # Adjust threshold
```

## Examples

### ❌ Bad (Triggers {code})

```
# TODO: Add example code that violates this rule
```

### ✅ Good (Passes {code})

```
# TODO: Add example code that passes this rule
```

## Rationale

TODO: Explain why this pattern is problematic and what the rule prevents.

## See Also

- Related rules: (list related rule codes)
- Documentation: (link to relevant docs)

## Development

### Testing

```bash
pytest tests/test_{code}_rule.py -v
```

### Implementation Notes

TODO: Document any special implementation details, edge cases, or considerations.
'''
