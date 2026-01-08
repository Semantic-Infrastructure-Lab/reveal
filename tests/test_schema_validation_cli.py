"""Integration tests for schema validation CLI.

Tests the --validate-schema flag and end-to-end validation workflows.
Covers CLI flag parsing, schema loading, validation execution, and output formatting.
"""

import pytest
import tempfile
import subprocess
import json
from pathlib import Path


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def valid_session_readme(temp_dir):
    """Create a valid Beth session README."""
    readme = temp_dir / "README.md"
    readme.write_text("""---
session_id: test-session-0102
date: 2026-01-02
badge: "Test Session"
topics: [testing, validation]
type: testing
---

# Test Session

This is a test session README.
""")
    return readme


@pytest.fixture
def invalid_session_readme(temp_dir):
    """Create an invalid Beth session README (missing required fields)."""
    readme = temp_dir / "README.md"
    readme.write_text("""---
date: 2026-01-02
badge: "Test Session"
---

# Test Session

Missing session_id and topics.
""")
    return readme


@pytest.fixture
def empty_frontmatter_readme(temp_dir):
    """Create README with empty front matter."""
    readme = temp_dir / "README.md"
    readme.write_text("""---
---

# Test Session

Empty front matter.
""")
    return readme


@pytest.fixture
def no_frontmatter_readme(temp_dir):
    """Create README without front matter."""
    readme = temp_dir / "README.md"
    readme.write_text("""# Test Session

No front matter at all.
""")
    return readme


@pytest.fixture
def type_mismatch_readme(temp_dir):
    """Create README with type mismatches."""
    readme = temp_dir / "README.md"
    readme.write_text("""---
session_id: test-session-0102
date: 2026-01-02
badge: "Test Session"
topics: "should be a list"
type: 123
---

# Test Session

Type mismatches.
""")
    return readme


@pytest.fixture
def custom_schema(temp_dir):
    """Create a custom schema file."""
    schema = temp_dir / "custom.yaml"
    schema.write_text("""name: "Custom Test Schema"
required_fields:
  - title
  - author
field_types:
  title: string
  author: string
  tags: list
  published: boolean
validation_rules:
  - field: title
    check: "len(value) > 0"
    message: "Title cannot be empty"
  - field: tags
    check: "len(value) >= 1"
    message: "At least one tag required"
""")
    return schema


@pytest.fixture
def custom_schema_readme(temp_dir):
    """Create README matching custom schema."""
    readme = temp_dir / "custom.md"
    readme.write_text("""---
title: "My Article"
author: "John Doe"
tags: [tech, tutorial]
published: true
---

# My Article

Content here.
""")
    return readme


# ============================================================================
# Helper Functions
# ============================================================================

def run_reveal(args, check=True):
    """Run reveal command with given arguments.

    Args:
        args: List of command arguments
        check: Whether to raise on non-zero exit (default True)

    Returns:
        CompletedProcess with stdout, stderr, returncode
    """
    cmd = ['reveal'] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding='utf-8',
        check=False  # We'll check manually
    )

    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, result.stdout, result.stderr
        )

    return result


# ============================================================================
# CLI Flag Tests
# ============================================================================

class TestCLIFlagParsing:
    """Test --validate-schema flag parsing."""

    def test_validate_schema_flag_exists(self):
        """Test that --validate-schema flag is recognized."""
        result = run_reveal(['--help'], check=True)
        assert '--validate-schema' in result.stdout
        assert 'SCHEMA' in result.stdout

    def test_validate_schema_requires_argument(self, valid_session_readme):
        """Test that --validate-schema requires a schema argument."""
        result = run_reveal([str(valid_session_readme), '--validate-schema'], check=False)
        assert result.returncode != 0
        # argparse should complain about missing argument

    def test_validate_schema_with_builtin(self, valid_session_readme):
        """Test --validate-schema with built-in schema name."""
        result = run_reveal([str(valid_session_readme), '--validate-schema', 'session'], check=False)
        # Should succeed (valid readme)
        assert result.returncode == 0 or 'F00' not in result.stdout

    def test_validate_schema_with_path(self, custom_schema_readme, custom_schema):
        """Test --validate-schema with custom schema path."""
        result = run_reveal(
            [str(custom_schema_readme), '--validate-schema', str(custom_schema)],
            check=False
        )
        # Should succeed (valid readme)
        assert result.returncode == 0 or 'F00' not in result.stdout


# ============================================================================
# Built-in Schema Tests
# ============================================================================

class TestBethSchemaValidation:
    """Test validation against built-in session schema."""

    def test_valid_session_readme_passes(self, valid_session_readme):
        """Test that valid Beth README passes validation."""
        result = run_reveal([str(valid_session_readme), '--validate-schema', 'session'])
        assert result.returncode == 0
        # Should have no F-series detections or only info-level

    def test_missing_required_fields(self, invalid_session_readme):
        """Test detection of missing required fields."""
        result = run_reveal([str(invalid_session_readme), '--validate-schema', 'session'], check=False)
        # Should detect F003 (missing required fields)
        assert 'F003' in result.stdout or result.returncode != 0

    def test_type_mismatch_detection(self, type_mismatch_readme):
        """Test detection of type mismatches."""
        result = run_reveal([str(type_mismatch_readme), '--validate-schema', 'session'], check=False)
        # Should detect F004 (type mismatch)
        assert 'F004' in result.stdout or result.returncode != 0

    def test_empty_frontmatter_detection(self, empty_frontmatter_readme):
        """Test detection of empty front matter."""
        result = run_reveal([str(empty_frontmatter_readme), '--validate-schema', 'session'], check=False)
        # Should detect F002 (empty) or F003 (missing required)
        assert 'F00' in result.stdout or result.returncode != 0

    def test_missing_frontmatter_detection(self, no_frontmatter_readme):
        """Test detection of missing front matter."""
        result = run_reveal([str(no_frontmatter_readme), '--validate-schema', 'session'], check=False)
        # Should detect F001 (missing front matter)
        assert 'F001' in result.stdout or result.returncode != 0


# ============================================================================
# Custom Schema Tests
# ============================================================================

class TestCustomSchemaValidation:
    """Test validation against custom schemas."""

    def test_custom_schema_loads(self, custom_schema_readme, custom_schema):
        """Test that custom schema can be loaded."""
        result = run_reveal(
            [str(custom_schema_readme), '--validate-schema', str(custom_schema)],
            check=False
        )
        # Should run without error (may have detections)
        assert result.returncode in [0, 1]  # 0=pass, 1=detections

    def test_custom_schema_validates_required_fields(self, temp_dir, custom_schema):
        """Test custom schema required field validation."""
        readme = temp_dir / "missing_fields.md"
        readme.write_text("""---
title: "Article"
---

# Article

Missing author field.
""")

        result = run_reveal([str(readme), '--validate-schema', str(custom_schema)], check=False)
        # Should detect F003 (missing author)
        assert 'F003' in result.stdout or 'author' in result.stdout.lower()

    def test_custom_schema_validates_types(self, temp_dir, custom_schema):
        """Test custom schema type validation."""
        readme = temp_dir / "wrong_types.md"
        readme.write_text("""---
title: "Article"
author: "John Doe"
tags: "should be a list"
published: "not a boolean"
---

# Article
""")

        result = run_reveal([str(readme), '--validate-schema', str(custom_schema)], check=False)
        # Should detect F004 (type mismatches)
        assert 'F004' in result.stdout or result.returncode != 0

    def test_custom_schema_validates_custom_rules(self, temp_dir, custom_schema):
        """Test custom schema validation rules."""
        readme = temp_dir / "invalid_rules.md"
        readme.write_text("""---
title: ""
author: "John Doe"
tags: []
---

# Article

Empty title and tags.
""")

        result = run_reveal([str(readme), '--validate-schema', str(custom_schema)], check=False)
        # Should detect F005 (custom validation failures)
        assert 'F005' in result.stdout or result.returncode != 0


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_nonexistent_schema(self, valid_session_readme):
        """Test error when schema doesn't exist."""
        result = run_reveal(
            [str(valid_session_readme), '--validate-schema', 'nonexistent'],
            check=False
        )
        assert result.returncode != 0
        assert 'not found' in result.stderr.lower() or 'error' in result.stderr.lower()

    def test_invalid_schema_file(self, valid_session_readme, temp_dir):
        """Test error when schema file is invalid YAML."""
        bad_schema = temp_dir / "bad.yaml"
        bad_schema.write_text("{ invalid yaml [")

        result = run_reveal(
            [str(valid_session_readme), '--validate-schema', str(bad_schema)],
            check=False
        )
        assert result.returncode != 0

    def test_schema_missing_name(self, valid_session_readme, temp_dir):
        """Test error when schema missing required 'name' field."""
        bad_schema = temp_dir / "no_name.yaml"
        bad_schema.write_text("""required_fields:
  - title
""")

        result = run_reveal(
            [str(valid_session_readme), '--validate-schema', str(bad_schema)],
            check=False
        )
        assert result.returncode != 0

    def test_nonexistent_file(self, temp_dir):
        """Test error when file doesn't exist."""
        nonexistent = temp_dir / "doesnt_exist.md"

        result = run_reveal([str(nonexistent), '--validate-schema', 'session'], check=False)
        assert result.returncode != 0
        assert 'not found' in result.stderr.lower() or 'error' in result.stderr.lower()

    def test_lists_available_schemas_on_error(self, valid_session_readme):
        """Test that available schemas are listed when schema not found."""
        result = run_reveal(
            [str(valid_session_readme), '--validate-schema', 'nonexistent'],
            check=False
        )
        assert result.returncode != 0
        # Should list available built-in schemas
        assert 'available' in result.stderr.lower() or 'session' in result.stderr.lower()


# ============================================================================
# Output Format Tests
# ============================================================================

class TestOutputFormats:
    """Test different output formats."""

    def test_text_format_output(self, invalid_session_readme):
        """Test text format output (default)."""
        result = run_reveal([str(invalid_session_readme), '--validate-schema', 'session'], check=False)
        # Text format should be human-readable
        assert 'F00' in result.stdout
        # Should show line numbers or positions

    def test_json_format_output(self, invalid_session_readme):
        """Test JSON format output."""
        result = run_reveal(
            [str(invalid_session_readme), '--validate-schema', 'session', '--format', 'json'],
            check=False
        )

        # Should be valid JSON
        try:
            data = json.loads(result.stdout)
            assert 'structure' in data or 'detections' in data or 'frontmatter' in data
        except json.JSONDecodeError:
            pytest.fail("Output is not valid JSON")

    def test_grep_format_output(self, invalid_session_readme):
        """Test grep format output."""
        result = run_reveal(
            [str(invalid_session_readme), '--validate-schema', 'session', '--format', 'grep'],
            check=False
        )

        # Grep format should be: filename:line:column:message or similar
        lines = result.stdout.strip().split('\n')
        if lines and lines[0]:  # If there are detections
            # Should contain file path
            assert str(invalid_session_readme) in result.stdout or 'README.md' in result.stdout


# ============================================================================
# Integration with Other Flags
# ============================================================================

class TestFlagCombinations:
    """Test --validate-schema with other flags."""

    def test_with_select_flag(self, invalid_session_readme):
        """Test --validate-schema with --select."""
        result = run_reveal(
            [str(invalid_session_readme), '--validate-schema', 'session', '--select', 'F003'],
            check=False
        )
        # Should only show F003 detections
        if 'F00' in result.stdout:
            assert 'F003' in result.stdout
            assert 'F004' not in result.stdout

    def test_with_ignore_flag(self, invalid_session_readme):
        """Test --validate-schema with --ignore."""
        result = run_reveal(
            [str(invalid_session_readme), '--validate-schema', 'session', '--ignore', 'F003'],
            check=False
        )
        # Should not show F003 detections
        if 'F00' in result.stdout:
            assert 'F003' not in result.stdout

    def test_defaults_to_f_series_rules(self, invalid_session_readme):
        """Test that --validate-schema defaults to F-series rules."""
        result = run_reveal([str(invalid_session_readme), '--validate-schema', 'session'], check=False)
        # Should run F-series rules, not B/S/C/etc.
        if result.stdout:
            # If there are detections, they should be F-series
            assert 'F00' in result.stdout or result.returncode == 0

    def test_mutually_exclusive_with_check(self, valid_session_readme):
        """Test behavior when both --validate-schema and --check are used."""
        # --validate-schema should take precedence (check routing.py order)
        result = run_reveal(
            [str(valid_session_readme), '--validate-schema', 'session', '--check'],
            check=False
        )
        # Should run schema validation (not general --check)
        # This is based on routing order: validate_schema checked before check


# ============================================================================
# End-to-End Workflow Tests
# ============================================================================

class TestEndToEndWorkflows:
    """Test complete validation workflows."""

    def test_validate_before_commit_workflow(self, temp_dir):
        """Test pre-commit validation workflow."""
        # Create session README
        readme = temp_dir / "README.md"
        readme.write_text("""---
session_id: production-session-0102
date: 2026-01-02
badge: "Production Session"
topics: [reveal, schema-validation]
type: production-execution
---

# Production Session
""")

        # Validate
        result = run_reveal([str(readme), '--validate-schema', 'session'])
        assert result.returncode == 0

    def test_ci_pipeline_workflow(self, temp_dir):
        """Test CI/CD pipeline validation workflow."""
        # Create multiple files
        readmes = []
        for i in range(3):
            readme = temp_dir / f"session_{i}.md"
            readme.write_text(f"""---
session_id: session-test-{i:04d}
date: 2026-01-02
topics: [topic{i}]
---

# Session {i}
""")
            readmes.append(readme)

        # Validate each file
        for readme in readmes:
            result = run_reveal([str(readme), '--validate-schema', 'session'])
            assert result.returncode == 0

    def test_bulk_validation_workflow(self, temp_dir):
        """Test validating multiple files in batch."""
        # Create mix of valid and invalid files
        valid = temp_dir / "valid.md"
        valid.write_text("""---
session_id: valid-test-0102
topics: [test]
---
# Valid
""")

        invalid = temp_dir / "invalid.md"
        invalid.write_text("""---
date: 2026-01-02
---
# Invalid
""")

        # Validate valid
        result1 = run_reveal([str(valid), '--validate-schema', 'session'])
        assert result1.returncode == 0

        # Validate invalid
        result2 = run_reveal([str(invalid), '--validate-schema', 'session'], check=False)
        assert result2.returncode != 0 or 'F00' in result2.stdout

    def test_documentation_generation_workflow(self, custom_schema_readme, custom_schema):
        """Test documentation site validation workflow."""
        # Validate article before publishing
        result = run_reveal(
            [str(custom_schema_readme), '--validate-schema', str(custom_schema)],
            check=True
        )
        assert result.returncode == 0


# ============================================================================
# Performance and Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and unusual inputs."""

    def test_large_frontmatter(self, temp_dir):
        """Test validation with large front matter."""
        readme = temp_dir / "large.md"
        # Create front matter with many fields
        fields = {f"field_{i}": f"value_{i}" for i in range(100)}
        fields['session_id'] = 'large-test-0102'
        fields['topics'] = ['test']

        import yaml
        frontmatter = yaml.dump(fields)
        readme.write_text(f"---\n{frontmatter}---\n\n# Large\n")

        result = run_reveal([str(readme), '--validate-schema', 'session'])
        assert result.returncode == 0

    def test_unicode_in_frontmatter(self, temp_dir):
        """Test validation with Unicode characters."""
        readme = temp_dir / "unicode.md"
        readme.write_text("""---
session_id: unicode-test-0102
topics: [测试, тест, テスト]
badge: "Unicode 🎉 Test"
---

# Unicode Test
""", encoding='utf-8')

        result = run_reveal([str(readme), '--validate-schema', 'session'])
        assert result.returncode == 0

    def test_multiline_values(self, temp_dir):
        """Test validation with multiline YAML values."""
        readme = temp_dir / "multiline.md"
        readme.write_text("""---
session_id: multiline-test-0102
topics: [test]
badge: |
  This is a
  multiline
  badge
---

# Multiline
""")

        result = run_reveal([str(readme), '--validate-schema', 'session'])
        assert result.returncode == 0

    def test_special_yaml_types(self, temp_dir):
        """Test validation with special YAML types."""
        readme = temp_dir / "special.md"
        readme.write_text("""---
session_id: special-types-0102
topics: [test]
date: 2026-01-02
null_field: null
bool_field: true
int_field: 42
float_field: 3.14
---

# Special Types
""")

        result = run_reveal([str(readme), '--validate-schema', 'session'])
        assert result.returncode == 0
