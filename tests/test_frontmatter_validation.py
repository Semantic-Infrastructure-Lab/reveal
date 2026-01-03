"""Tests for front matter validation engine and F-series rules.

Tests validation engine, F001-F005 rules, schema integration, and type checking.
"""

import pytest
from pathlib import Path

from reveal.rules.frontmatter import (
    validate_type,
    safe_eval_validation,
    get_validation_schema,
    set_validation_context,
    clear_validation_context
)
from reveal.rules.frontmatter.F001 import F001
from reveal.rules.frontmatter.F002 import F002
from reveal.rules.frontmatter.F003 import F003
from reveal.rules.frontmatter.F004 import F004
from reveal.rules.frontmatter.F005 import F005
from reveal.schemas.frontmatter import load_schema, clear_cache


class TestValidationType:
    """Test validate_type function."""

    def test_validate_string(self):
        """Test string type validation."""
        assert validate_type("hello", "string") is True
        assert validate_type("", "string") is True
        assert validate_type(123, "string") is False
        assert validate_type([], "string") is False

    def test_validate_list(self):
        """Test list type validation."""
        assert validate_type([], "list") is True
        assert validate_type([1, 2, 3], "list") is True
        assert validate_type("hello", "list") is False
        assert validate_type({}, "list") is False

    def test_validate_dict(self):
        """Test dict type validation."""
        assert validate_type({}, "dict") is True
        assert validate_type({"a": 1}, "dict") is True
        assert validate_type([], "dict") is False
        assert validate_type("hello", "dict") is False

    def test_validate_integer(self):
        """Test integer type validation."""
        assert validate_type(123, "integer") is True
        assert validate_type(0, "integer") is True
        assert validate_type(-5, "integer") is True
        assert validate_type(True, "integer") is False  # bool is not int
        assert validate_type(1.5, "integer") is False
        assert validate_type("123", "integer") is False

    def test_validate_boolean(self):
        """Test boolean type validation."""
        assert validate_type(True, "boolean") is True
        assert validate_type(False, "boolean") is True
        assert validate_type(1, "boolean") is False
        assert validate_type("true", "boolean") is False

    def test_validate_date(self):
        """Test date type validation (YYYY-MM-DD format)."""
        assert validate_type("2024-01-01", "date") is True
        assert validate_type("2026-12-31", "date") is True
        assert validate_type("2024-1-1", "date") is False  # Wrong format
        assert validate_type("01-01-2024", "date") is False  # Wrong order
        assert validate_type("invalid", "date") is False
        assert validate_type(20240101, "date") is False

    def test_validate_unknown_type(self):
        """Test unknown type returns False."""
        assert validate_type("value", "unknown_type") is False


class TestSafeEvalValidation:
    """Test safe_eval_validation function."""

    def test_length_check(self):
        """Test len() validation."""
        assert safe_eval_validation("len(value) >= 1", {"value": ["topic1"]}) is True
        assert safe_eval_validation("len(value) >= 1", {"value": []}) is False
        assert safe_eval_validation("len(value) > 2", {"value": [1, 2, 3]}) is True

    def test_regex_check(self):
        """Test regex validation."""
        check = "re.match(r'^[a-z]+-[a-z]+-\\d{4}$', value)"
        assert safe_eval_validation(check, {"value": "garnet-ember-0102"}) is True
        assert safe_eval_validation(check, {"value": "invalid_format"}) is False

    def test_comparison_check(self):
        """Test comparison validation."""
        assert safe_eval_validation("value > 10", {"value": 15}) is True
        assert safe_eval_validation("value > 10", {"value": 5}) is False
        assert safe_eval_validation("value == 'test'", {"value": "test"}) is True

    def test_invalid_check_returns_false(self):
        """Test invalid check expression returns False."""
        # Syntax error
        assert safe_eval_validation("len(value", {"value": []}) is False
        # Missing variable
        assert safe_eval_validation("undefined_var", {"value": "test"}) is False

    def test_safe_builtins_only(self):
        """Test only safe builtins are available (no eval, exec, import)."""
        # These should fail safely
        assert safe_eval_validation("__import__('os')", {}) is False
        assert safe_eval_validation("eval('1+1')", {}) is False
        assert safe_eval_validation("exec('print(1)')", {}) is False


class TestValidationContext:
    """Test validation context management."""

    def setup_method(self):
        """Clear context before each test."""
        clear_validation_context()
        clear_cache()

    def teardown_method(self):
        """Clear context after each test."""
        clear_validation_context()

    def test_get_validation_schema_when_none(self):
        """Test get_validation_schema returns None when not set."""
        assert get_validation_schema() is None

    def test_set_and_get_validation_schema(self):
        """Test setting and getting validation schema."""
        schema = {"name": "Test Schema", "required_fields": ["field1"]}
        set_validation_context(schema)
        retrieved = get_validation_schema()
        assert retrieved == schema
        assert retrieved['name'] == "Test Schema"

    def test_clear_validation_context(self):
        """Test clearing validation context."""
        schema = {"name": "Test Schema"}
        set_validation_context(schema)
        assert get_validation_schema() is not None
        clear_validation_context()
        assert get_validation_schema() is None

    def test_set_validation_context_to_none(self):
        """Test setting context to None clears it."""
        schema = {"name": "Test Schema"}
        set_validation_context(schema)
        set_validation_context(None)
        assert get_validation_schema() is None


class TestF001MissingFrontmatter:
    """Test F001 rule (missing front matter)."""

    def setup_method(self):
        """Initialize rule."""
        self.rule = F001()

    def test_missing_frontmatter_detected(self):
        """Test detection when frontmatter is missing."""
        structure = {'frontmatter': None, 'headings': []}
        detections = self.rule.check('test.md', structure, '# Content')
        assert len(detections) == 1
        assert detections[0].rule_code == 'F001'
        assert 'missing' in detections[0].message.lower()

    def test_frontmatter_present_no_detection(self):
        """Test no detection when frontmatter exists."""
        structure = {
            'frontmatter': {
                'data': {'title': 'Test'},
                'line_start': 1
            }
        }
        detections = self.rule.check('test.md', structure, '')
        assert len(detections) == 0

    def test_none_structure_no_detection(self):
        """Test no detection when structure is None."""
        detections = self.rule.check('test.md', None, '')
        assert len(detections) == 0

    def test_rule_metadata(self):
        """Test rule has correct metadata."""
        assert self.rule.code == 'F001'
        assert '.md' in self.rule.file_patterns


class TestF002EmptyFrontmatter:
    """Test F002 rule (empty front matter)."""

    def setup_method(self):
        """Initialize rule."""
        self.rule = F002()

    def test_empty_frontmatter_detected(self):
        """Test detection when frontmatter is empty."""
        structure = {
            'frontmatter': {
                'data': {},
                'line_start': 1
            }
        }
        detections = self.rule.check('test.md', structure, '')
        assert len(detections) == 1
        assert detections[0].rule_code == 'F002'
        assert 'empty' in detections[0].message.lower()

    def test_frontmatter_with_fields_no_detection(self):
        """Test no detection when frontmatter has fields."""
        structure = {
            'frontmatter': {
                'data': {'title': 'Test', 'type': 'article'},
                'line_start': 1
            }
        }
        detections = self.rule.check('test.md', structure, '')
        assert len(detections) == 0

    def test_missing_frontmatter_no_detection(self):
        """Test no detection when frontmatter is missing (F001 handles this)."""
        structure = {'frontmatter': None}
        detections = self.rule.check('test.md', structure, '')
        assert len(detections) == 0

    def test_rule_metadata(self):
        """Test rule has correct metadata."""
        assert self.rule.code == 'F002'
        assert '.md' in self.rule.file_patterns


class TestF003RequiredFields:
    """Test F003 rule (required field missing)."""

    def setup_method(self):
        """Initialize rule and clear context."""
        self.rule = F003()
        clear_validation_context()

    def teardown_method(self):
        """Clear context after test."""
        clear_validation_context()

    def test_missing_required_field_detected(self):
        """Test detection when required field is missing."""
        schema = {
            'name': 'Test Schema',
            'required_fields': ['session_id', 'beth_topics']
        }
        set_validation_context(schema)

        structure = {
            'frontmatter': {
                'data': {'beth_topics': ['topic1']},  # Missing session_id
                'line_start': 1
            }
        }
        detections = self.rule.check('test.md', structure, '')
        assert len(detections) == 1
        assert detections[0].rule_code == 'F003'
        assert 'session_id' in detections[0].message

    def test_all_required_fields_present_no_detection(self):
        """Test no detection when all required fields present."""
        schema = {
            'name': 'Test Schema',
            'required_fields': ['session_id', 'beth_topics']
        }
        set_validation_context(schema)

        structure = {
            'frontmatter': {
                'data': {
                    'session_id': 'test-session-0101',
                    'beth_topics': ['topic1']
                },
                'line_start': 1
            }
        }
        detections = self.rule.check('test.md', structure, '')
        assert len(detections) == 0

    def test_no_schema_no_detection(self):
        """Test no detection when no schema is set."""
        structure = {
            'frontmatter': {
                'data': {},
                'line_start': 1
            }
        }
        detections = self.rule.check('test.md', structure, '')
        assert len(detections) == 0

    def test_multiple_missing_fields(self):
        """Test multiple detections for multiple missing fields."""
        schema = {
            'name': 'Test Schema',
            'required_fields': ['field1', 'field2', 'field3']
        }
        set_validation_context(schema)

        structure = {
            'frontmatter': {
                'data': {},
                'line_start': 1
            }
        }
        detections = self.rule.check('test.md', structure, '')
        assert len(detections) == 3

    def test_rule_metadata(self):
        """Test rule has correct metadata."""
        assert self.rule.code == 'F003'
        assert '.md' in self.rule.file_patterns


class TestF004TypeMismatch:
    """Test F004 rule (field type mismatch)."""

    def setup_method(self):
        """Initialize rule and clear context."""
        self.rule = F004()
        clear_validation_context()

    def teardown_method(self):
        """Clear context after test."""
        clear_validation_context()

    def test_type_mismatch_detected(self):
        """Test detection when field type doesn't match."""
        schema = {
            'name': 'Test Schema',
            'field_types': {
                'beth_topics': 'list',
                'session_id': 'string'
            }
        }
        set_validation_context(schema)

        structure = {
            'frontmatter': {
                'data': {
                    'beth_topics': 'single-topic',  # Should be list
                    'session_id': 'test-0101'
                },
                'line_start': 1
            }
        }
        detections = self.rule.check('test.md', structure, '')
        assert len(detections) == 1
        assert detections[0].rule_code == 'F004'
        assert 'beth_topics' in detections[0].message
        assert 'list' in detections[0].message

    def test_correct_types_no_detection(self):
        """Test no detection when types match."""
        schema = {
            'name': 'Test Schema',
            'field_types': {
                'beth_topics': 'list',
                'session_id': 'string',
                'count': 'integer'
            }
        }
        set_validation_context(schema)

        structure = {
            'frontmatter': {
                'data': {
                    'beth_topics': ['topic1', 'topic2'],
                    'session_id': 'test-0101',
                    'count': 5
                },
                'line_start': 1
            }
        }
        detections = self.rule.check('test.md', structure, '')
        assert len(detections) == 0

    def test_multiple_type_mismatches(self):
        """Test multiple detections for multiple type mismatches."""
        schema = {
            'name': 'Test Schema',
            'field_types': {
                'field1': 'string',
                'field2': 'integer',
                'field3': 'list'
            }
        }
        set_validation_context(schema)

        structure = {
            'frontmatter': {
                'data': {
                    'field1': 123,  # Wrong
                    'field2': 'text',  # Wrong
                    'field3': {}  # Wrong
                },
                'line_start': 1
            }
        }
        detections = self.rule.check('test.md', structure, '')
        assert len(detections) == 3

    def test_no_schema_no_detection(self):
        """Test no detection when no schema is set."""
        structure = {
            'frontmatter': {
                'data': {'field': 'wrong_type'},
                'line_start': 1
            }
        }
        detections = self.rule.check('test.md', structure, '')
        assert len(detections) == 0

    def test_rule_metadata(self):
        """Test rule has correct metadata."""
        assert self.rule.code == 'F004'
        assert '.md' in self.rule.file_patterns


class TestF005CustomValidation:
    """Test F005 rule (custom validation failed)."""

    def setup_method(self):
        """Initialize rule and clear context."""
        self.rule = F005()
        clear_validation_context()

    def teardown_method(self):
        """Clear context after test."""
        clear_validation_context()

    def test_custom_validation_failure_detected(self):
        """Test detection when custom validation fails."""
        schema = {
            'name': 'Test Schema',
            'validation_rules': [
                {
                    'code': 'F005',
                    'field': 'beth_topics',
                    'check': 'len(value) >= 1',
                    'message': 'beth_topics must have at least one topic'
                }
            ]
        }
        set_validation_context(schema)

        structure = {
            'frontmatter': {
                'data': {'beth_topics': []},  # Empty list fails validation
                'line_start': 1
            }
        }
        detections = self.rule.check('test.md', structure, '')
        assert len(detections) == 1
        assert detections[0].rule_code == 'F005'
        assert 'at least one topic' in detections[0].message

    def test_custom_validation_pass_no_detection(self):
        """Test no detection when custom validation passes."""
        schema = {
            'name': 'Test Schema',
            'validation_rules': [
                {
                    'code': 'F005',
                    'field': 'session_id',
                    'check': "re.match(r'^[a-z]+-[a-z]+-\\d{4}$', value)",
                    'message': 'Invalid session_id format'
                }
            ]
        }
        set_validation_context(schema)

        structure = {
            'frontmatter': {
                'data': {'session_id': 'garnet-ember-0102'},
                'line_start': 1
            }
        }
        detections = self.rule.check('test.md', structure, '')
        assert len(detections) == 0

    def test_multiple_validation_rules(self):
        """Test multiple custom validation rules."""
        schema = {
            'name': 'Test Schema',
            'validation_rules': [
                {
                    'code': 'F005',
                    'field': 'field1',
                    'check': 'len(value) > 5',
                    'message': 'Field1 too short'
                },
                {
                    'code': 'F005',
                    'field': 'field2',
                    'check': 'value > 10',
                    'message': 'Field2 too small'
                }
            ]
        }
        set_validation_context(schema)

        structure = {
            'frontmatter': {
                'data': {
                    'field1': 'short',  # len=5, fails
                    'field2': 5  # <10, fails
                },
                'line_start': 1
            }
        }
        detections = self.rule.check('test.md', structure, '')
        assert len(detections) == 2

    def test_missing_field_no_detection(self):
        """Test no detection when field not in data."""
        schema = {
            'name': 'Test Schema',
            'validation_rules': [
                {
                    'code': 'F005',
                    'field': 'missing_field',
                    'check': 'len(value) > 0',
                    'message': 'Field required'
                }
            ]
        }
        set_validation_context(schema)

        structure = {
            'frontmatter': {
                'data': {},
                'line_start': 1
            }
        }
        detections = self.rule.check('test.md', structure, '')
        assert len(detections) == 0

    def test_no_schema_no_detection(self):
        """Test no detection when no schema is set."""
        structure = {
            'frontmatter': {
                'data': {'field': []},
                'line_start': 1
            }
        }
        detections = self.rule.check('test.md', structure, '')
        assert len(detections) == 0

    def test_rule_metadata(self):
        """Test rule has correct metadata."""
        assert self.rule.code == 'F005'
        assert '.md' in self.rule.file_patterns


class TestBethSchemaIntegration:
    """Test F-series rules with real beth.yaml schema."""

    def setup_method(self):
        """Load beth schema and clear context."""
        clear_cache()
        clear_validation_context()
        self.schema = load_schema('beth')
        assert self.schema is not None

    def teardown_method(self):
        """Clear context after test."""
        clear_validation_context()

    def test_beth_schema_required_fields(self):
        """Test F003 with beth schema required fields."""
        set_validation_context(self.schema)
        rule = F003()

        structure = {
            'frontmatter': {
                'data': {},  # Missing session_id and beth_topics
                'line_start': 1
            }
        }
        detections = rule.check('README.md', structure, '')
        assert len(detections) == 2
        field_names = [d.message for d in detections]
        assert any('session_id' in msg for msg in field_names)
        assert any('beth_topics' in msg for msg in field_names)

    def test_beth_schema_type_validation(self):
        """Test F004 with beth schema field types."""
        set_validation_context(self.schema)
        rule = F004()

        structure = {
            'frontmatter': {
                'data': {
                    'session_id': 123,  # Should be string
                    'beth_topics': 'single',  # Should be list
                    'files_modified': '5'  # Should be integer
                },
                'line_start': 1
            }
        }
        detections = rule.check('README.md', structure, '')
        assert len(detections) == 3

    def test_beth_schema_custom_validation(self):
        """Test F005 with beth schema custom rules."""
        set_validation_context(self.schema)
        rule = F005()

        structure = {
            'frontmatter': {
                'data': {
                    'session_id': 'invalid_format',  # Bad format
                    'beth_topics': []  # Empty list
                },
                'line_start': 1
            }
        }
        detections = rule.check('README.md', structure, '')
        assert len(detections) == 2

    def test_valid_beth_session(self):
        """Test no detections for valid beth session."""
        set_validation_context(self.schema)

        structure = {
            'frontmatter': {
                'data': {
                    'session_id': 'garnet-ember-0102',
                    'beth_topics': ['reveal', 'testing'],
                    'date': '2026-01-02',
                    'type': 'production',
                    'files_modified': 5
                },
                'line_start': 1
            }
        }

        # Test all rules
        f003 = F003()
        f004 = F004()
        f005 = F005()

        assert len(f003.check('README.md', structure, '')) == 0
        assert len(f004.check('README.md', structure, '')) == 0
        assert len(f005.check('README.md', structure, '')) == 0
