"""Tests for reveal.defaults module."""

import os
import pytest
from unittest.mock import patch
from reveal.defaults import (
    RuleDefaults,
    AnalyzerDefaults,
    AdapterDefaults,
    DisplayDefaults,
    ENV_OVERRIDES,
)


class TestRuleDefaults:
    """Tests for RuleDefaults class."""

    def test_complexity_defaults_values(self):
        """Should have reasonable complexity threshold values."""
        assert RuleDefaults.CYCLOMATIC_COMPLEXITY == 10
        assert RuleDefaults.NESTING_DEPTH_MAX == 4
        assert RuleDefaults.FUNCTION_LENGTH_WARN == 50
        assert RuleDefaults.FUNCTION_LENGTH_ERROR == 100

    def test_file_quality_defaults_values(self):
        """Should have reasonable file quality values."""
        assert RuleDefaults.FILE_LENGTH_WARN == 500
        assert RuleDefaults.FILE_LENGTH_ERROR == 1000
        assert RuleDefaults.MAX_LINE_LENGTH == 100

    def test_code_smell_defaults_values(self):
        """Should have reasonable code smell values."""
        assert RuleDefaults.MAX_FUNCTION_ARGUMENTS == 5
        assert RuleDefaults.MAX_PROPERTY_LINES == 8

    def test_duplication_defaults_values(self):
        """Should have reasonable duplication detection values."""
        assert RuleDefaults.MIN_FUNCTION_SIZE == 8
        assert RuleDefaults.MIN_SIMILARITY == 0.50
        assert RuleDefaults.MAX_DUPLICATE_CANDIDATES == 5

    def test_duplication_similarity_range(self):
        """MIN_SIMILARITY should be a ratio between 0 and 1."""
        assert 0.0 <= RuleDefaults.MIN_SIMILARITY <= 1.0

    def test_maintainability_defaults_values(self):
        """Should have reasonable maintainability values."""
        assert RuleDefaults.MIN_LIST_SIZE == 5
        assert RuleDefaults.MIN_DICT_VALUE_SIZE == 3

    def test_link_defaults_values(self):
        """Should have reasonable link validation values."""
        assert RuleDefaults.LINK_TIMEOUT == 5
        assert RuleDefaults.MIN_CROSS_REFS == 2

    def test_function_length_error_greater_than_warn(self):
        """ERROR threshold should be stricter than WARN."""
        assert RuleDefaults.FUNCTION_LENGTH_ERROR > RuleDefaults.FUNCTION_LENGTH_WARN

    def test_file_length_error_greater_than_warn(self):
        """ERROR threshold should be stricter than WARN."""
        assert RuleDefaults.FILE_LENGTH_ERROR > RuleDefaults.FILE_LENGTH_WARN


class TestAnalyzerDefaults:
    """Tests for AnalyzerDefaults class."""

    def test_analyzer_defaults_values(self):
        """Should have reasonable analyzer limit values."""
        assert AnalyzerDefaults.JSONL_PREVIEW_LIMIT == 10
        assert AnalyzerDefaults.DIRECTORY_MAX_ENTRIES == 50
        assert AnalyzerDefaults.RELATED_DOCS_LIMIT == 100

    def test_analyzer_defaults_positive(self):
        """All analyzer limits should be positive."""
        assert AnalyzerDefaults.JSONL_PREVIEW_LIMIT > 0
        assert AnalyzerDefaults.DIRECTORY_MAX_ENTRIES > 0
        assert AnalyzerDefaults.RELATED_DOCS_LIMIT > 0


class TestAdapterDefaults:
    """Tests for AdapterDefaults class."""

    def test_adapter_defaults_values(self):
        """Should have reasonable adapter limit values."""
        assert AdapterDefaults.STATS_MAX_FILES == 1000
        assert AdapterDefaults.CLAUDE_SESSION_SCAN_LIMIT == 50
        assert AdapterDefaults.GIT_COMMIT_HISTORY_LIMIT == 20
        assert AdapterDefaults.SSL_EXPIRY_WARNING_DAYS == 30
        assert AdapterDefaults.SSL_EXPIRY_CRITICAL_DAYS == 7

    def test_adapter_defaults_positive(self):
        """All adapter limits should be positive."""
        assert AdapterDefaults.STATS_MAX_FILES > 0
        assert AdapterDefaults.CLAUDE_SESSION_SCAN_LIMIT > 0
        assert AdapterDefaults.GIT_COMMIT_HISTORY_LIMIT > 0
        assert AdapterDefaults.SSL_EXPIRY_WARNING_DAYS > 0
        assert AdapterDefaults.SSL_EXPIRY_CRITICAL_DAYS > 0

    def test_ssl_warning_greater_than_critical(self):
        """Warning threshold should be earlier than critical."""
        assert AdapterDefaults.SSL_EXPIRY_WARNING_DAYS > AdapterDefaults.SSL_EXPIRY_CRITICAL_DAYS


class TestDisplayDefaults:
    """Tests for DisplayDefaults class."""

    def test_display_defaults_values(self):
        """Should have reasonable display limit values."""
        assert DisplayDefaults.TREE_DIR_LIMIT == 50
        assert DisplayDefaults.TREE_MAX_ENTRIES == 200
        assert DisplayDefaults.SNIPPET_CONTEXT_LINES == 3

    def test_display_defaults_positive(self):
        """All display limits should be positive."""
        assert DisplayDefaults.TREE_DIR_LIMIT > 0
        assert DisplayDefaults.TREE_MAX_ENTRIES > 0
        assert DisplayDefaults.SNIPPET_CONTEXT_LINES > 0


class TestEnvOverrides:
    """Tests for ENV_OVERRIDES mapping."""

    def test_env_overrides_structure(self):
        """Each mapping should be env_var -> (class_name, attribute_name)."""
        for env_var, mapping in ENV_OVERRIDES.items():
            assert isinstance(env_var, str), f"Key {env_var} should be string"
            assert isinstance(mapping, tuple), f"Value for {env_var} should be tuple"
            assert len(mapping) == 2, f"Mapping for {env_var} should have 2 elements"
            class_name, attr_name = mapping
            assert isinstance(class_name, str), f"Class name in {env_var} should be string"
            assert isinstance(attr_name, str), f"Attr name in {env_var} should be string"

    def test_env_overrides_keys_prefixed(self):
        """All env var names should start with REVEAL_."""
        for env_var in ENV_OVERRIDES.keys():
            assert env_var.startswith('REVEAL_'), f"{env_var} should start with REVEAL_"

    def test_env_overrides_valid_classes(self):
        """All class names should reference existing default classes."""
        valid_classes = {'RuleDefaults', 'AnalyzerDefaults', 'AdapterDefaults', 'DisplayDefaults'}
        for env_var, (class_name, _) in ENV_OVERRIDES.items():
            assert class_name in valid_classes, f"Unknown class {class_name} in {env_var}"

    def test_env_overrides_valid_attributes(self):
        """All attributes should exist on their referenced classes."""
        class_map = {
            'RuleDefaults': RuleDefaults,
            'AnalyzerDefaults': AnalyzerDefaults,
            'AdapterDefaults': AdapterDefaults,
            'DisplayDefaults': DisplayDefaults,
        }

        for env_var, (class_name, attr_name) in ENV_OVERRIDES.items():
            cls = class_map[class_name]
            assert hasattr(cls, attr_name), f"{class_name}.{attr_name} not found (from {env_var})"

    def test_env_overrides_documented_mappings(self):
        """Should map known environment variables correctly."""
        assert ENV_OVERRIDES['REVEAL_C901_THRESHOLD'] == ('RuleDefaults', 'CYCLOMATIC_COMPLEXITY')
        assert ENV_OVERRIDES['REVEAL_C905_MAX_DEPTH'] == ('RuleDefaults', 'NESTING_DEPTH_MAX')
        assert ENV_OVERRIDES['REVEAL_E501_MAX_LENGTH'] == ('RuleDefaults', 'MAX_LINE_LENGTH')
        assert ENV_OVERRIDES['REVEAL_M101_WARN'] == ('RuleDefaults', 'FILE_LENGTH_WARN')
        assert ENV_OVERRIDES['REVEAL_M101_ERROR'] == ('RuleDefaults', 'FILE_LENGTH_ERROR')
        assert ENV_OVERRIDES['REVEAL_DIR_LIMIT'] == ('DisplayDefaults', 'TREE_DIR_LIMIT')

    def test_env_overrides_exact_count(self):
        """Should have exactly the expected number of overrides — catches both accidental removal and undocumented additions."""
        # The 6 documented overrides: C901, C905, E501, M101 warn/error, DIR_LIMIT
        assert len(ENV_OVERRIDES) == 6, (
            f"Expected 6 ENV_OVERRIDES entries, got {len(ENV_OVERRIDES)}. "
            "Add a new entry to test_env_overrides_documented_mappings if you add a new override."
        )


class TestDefaultsIntegration:
    """Integration tests for defaults module."""

    def test_no_mutable_defaults(self):
        """Default values should not be mutable (avoid shared state bugs)."""
        for attr in dir(RuleDefaults):
            if not attr.startswith('_'):
                value = getattr(RuleDefaults, attr)
                # Should be immutable types (int, float, str)
                assert isinstance(value, (int, float, str)), \
                    f"RuleDefaults.{attr} is mutable type {type(value)}"

    def test_reasonable_threshold_ranges(self):
        """Thresholds should be in reasonable ranges."""
        # Complexity thresholds should be reasonable
        assert 1 <= RuleDefaults.CYCLOMATIC_COMPLEXITY <= 50
        assert 1 <= RuleDefaults.NESTING_DEPTH_MAX <= 10
        assert 10 <= RuleDefaults.FUNCTION_LENGTH_WARN <= 200
        assert 50 <= RuleDefaults.FUNCTION_LENGTH_ERROR <= 500

        # File thresholds should be reasonable
        assert 100 <= RuleDefaults.FILE_LENGTH_WARN <= 2000
        assert 500 <= RuleDefaults.FILE_LENGTH_ERROR <= 5000
        assert 80 <= RuleDefaults.MAX_LINE_LENGTH <= 120

        # Timeouts should be reasonable
        assert 1 <= RuleDefaults.LINK_TIMEOUT <= 30
