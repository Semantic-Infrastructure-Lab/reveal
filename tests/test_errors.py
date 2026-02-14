"""Tests for reveal.errors module."""
import pytest
from reveal.errors import (
    RevealError,
    AnalyzerNotFoundError,
    InvalidPathError,
    ConfigurationError,
    AdapterError,
    QuerySyntaxError,
    RuleError,
)


class TestRevealError:
    """Tests for RevealError base class."""

    def test_simple_error(self):
        """Simple error with just message."""
        error = RevealError("Something went wrong")
        assert error.message == "Something went wrong"
        assert error.details is None
        assert error.suggestions == []
        assert error.context == {}

    def test_error_with_details(self):
        """Error with details."""
        error = RevealError("Error", details="More information")
        assert error.details == "More information"

    def test_error_with_suggestions(self):
        """Error with suggestions."""
        suggestions = ["Try this", "Or that"]
        error = RevealError("Error", suggestions=suggestions)
        assert error.suggestions == suggestions

    def test_error_with_context(self):
        """Error with context."""
        context = {"file": "test.py", "line": 42}
        error = RevealError("Error", context=context)
        assert error.context == context

    def test_str_simple(self):
        """String representation of simple error."""
        error = RevealError("Test error")
        assert str(error) == "Error: Test error"

    def test_str_with_details(self):
        """String representation with details."""
        error = RevealError("Test error", details="Additional info")
        output = str(error)
        assert "Error: Test error" in output
        assert "Details: Additional info" in output

    def test_str_with_context(self):
        """String representation with context."""
        error = RevealError("Test error", context={"key": "value"})
        output = str(error)
        assert "Error: Test error" in output
        assert "Context:" in output
        assert "  key: value" in output

    def test_str_with_suggestions(self):
        """String representation with suggestions."""
        error = RevealError("Test error", suggestions=["Fix A", "Fix B"])
        output = str(error)
        assert "Error: Test error" in output
        assert "Suggestions:" in output
        assert "  - Fix A" in output
        assert "  - Fix B" in output

    def test_str_with_all_fields(self):
        """String representation with all fields."""
        error = RevealError(
            "Test error",
            details="More info",
            suggestions=["Suggestion 1"],
            context={"file": "test.py"}
        )
        output = str(error)
        assert "Error: Test error" in output
        assert "Details: More info" in output
        assert "Context:" in output
        assert "  file: test.py" in output
        assert "Suggestions:" in output
        assert "  - Suggestion 1" in output

    def test_exception_inheritance(self):
        """RevealError inherits from Exception."""
        error = RevealError("Test")
        assert isinstance(error, Exception)

    def test_can_be_raised(self):
        """RevealError can be raised and caught."""
        with pytest.raises(RevealError) as exc_info:
            raise RevealError("Test error")
        assert exc_info.value.message == "Test error"


class TestAnalyzerNotFoundError:
    """Tests for AnalyzerNotFoundError."""

    def test_basic_initialization(self):
        """Basic error initialization."""
        error = AnalyzerNotFoundError("test.xyz")
        assert "test.xyz" in error.message
        assert ".xyz" in error.message
        assert len(error.suggestions) > 0

    def test_file_with_extension(self):
        """File with extension."""
        error = AnalyzerNotFoundError("test.unknown")
        assert "test.unknown" in error.message
        assert ".unknown" in error.message

    def test_file_without_extension(self):
        """File without extension."""
        error = AnalyzerNotFoundError("test")
        assert "(no extension)" in error.message

    def test_allow_fallback_true(self):
        """allow_fallback=True suggestions."""
        error = AnalyzerNotFoundError("test.xyz", allow_fallback=True)
        # Should NOT suggest enabling fallback if already enabled
        assert not any("Enable tree-sitter fallback" in s for s in error.suggestions)

    def test_allow_fallback_false(self):
        """allow_fallback=False adds fallback suggestion."""
        error = AnalyzerNotFoundError("test.xyz", allow_fallback=False)
        assert any("Enable tree-sitter fallback" in s for s in error.suggestions)

    def test_similar_extensions(self):
        """Similar extensions appear in suggestions."""
        error = AnalyzerNotFoundError("test.xyz", similar_extensions=[".py", ".js", ".ts"])
        suggestions_str = " ".join(error.suggestions)
        assert ".py" in suggestions_str or "Similar supported extensions" in suggestions_str

    def test_context_includes_path(self):
        """Context includes file path."""
        error = AnalyzerNotFoundError("test.xyz")
        assert error.context["file"] == "test.xyz"
        assert "extension" in error.context
        assert "fallback_enabled" in error.context

    def test_suggestions_include_common_actions(self):
        """Suggestions include common actions."""
        error = AnalyzerNotFoundError("test.xyz")
        suggestions_str = " ".join(error.suggestions)
        assert "reveal" in suggestions_str.lower()
        assert "--list-supported" in suggestions_str or "github" in suggestions_str.lower()


class TestInvalidPathError:
    """Tests for InvalidPathError."""

    def test_basic_initialization(self):
        """Basic error initialization."""
        error = InvalidPathError("/path/to/file")
        assert "/path/to/file" in error.message
        assert len(error.suggestions) > 0

    def test_custom_reason(self):
        """Custom reason appears in details."""
        error = InvalidPathError("/path/to/file", reason="File is corrupted")
        assert error.details == "File is corrupted"

    def test_default_reason(self):
        """Default reason is used."""
        error = InvalidPathError("/path/to/file")
        assert error.details == "Path does not exist"

    def test_context_includes_path(self):
        """Context includes path."""
        error = InvalidPathError("/path/to/file")
        assert error.context["path"] == "/path/to/file"

    def test_suggestions_include_common_actions(self):
        """Suggestions include common path actions."""
        error = InvalidPathError("/path/to/file")
        suggestions_str = " ".join(error.suggestions)
        assert "path" in suggestions_str.lower()
        assert "absolute" in suggestions_str.lower() or "readable" in suggestions_str.lower()


class TestConfigurationError:
    """Tests for ConfigurationError."""

    def test_basic_initialization(self):
        """Basic error initialization."""
        error = ConfigurationError("Invalid config")
        assert "Invalid config" in error.message
        assert len(error.suggestions) > 0

    def test_with_config_file(self):
        """Error with config file."""
        error = ConfigurationError("Invalid config", config_file=".reveal.yaml")
        assert any(".reveal.yaml" in s for s in error.suggestions)
        assert error.context["config_file"] == ".reveal.yaml"

    def test_with_config_key(self):
        """Error with config key."""
        error = ConfigurationError("Invalid config", config_key="rules.max_depth")
        assert any("rules.max_depth" in s for s in error.suggestions)
        assert error.context["config_key"] == "rules.max_depth"

    def test_with_both_file_and_key(self):
        """Error with both config file and key."""
        error = ConfigurationError(
            "Invalid config",
            config_file="config.yaml",
            config_key="timeout"
        )
        assert error.context["config_file"] == "config.yaml"
        assert error.context["config_key"] == "timeout"

    def test_suggestions_include_reveal_commands(self):
        """Suggestions include reveal config commands."""
        error = ConfigurationError("Invalid config")
        suggestions_str = " ".join(error.suggestions)
        assert "reveal config" in suggestions_str.lower()


class TestAdapterError:
    """Tests for AdapterError."""

    def test_basic_initialization(self):
        """Basic error initialization."""
        error = AdapterError("mysql", "Connection failed")
        assert "Connection failed" in error.message
        assert len(error.suggestions) > 0

    def test_adapter_name_in_suggestions(self):
        """Adapter name appears in suggestions."""
        error = AdapterError("mysql", "Connection failed")
        suggestions_str = " ".join(error.suggestions)
        assert "mysql" in suggestions_str.lower()

    def test_with_details(self):
        """Error with details."""
        error = AdapterError("ssl", "Connection timeout", details="Host unreachable")
        assert error.details == "Host unreachable"

    def test_context_includes_adapter(self):
        """Context includes adapter name."""
        error = AdapterError("git", "Repository not found")
        assert error.context["adapter"] == "git"

    def test_suggestions_include_help_commands(self):
        """Suggestions include help commands."""
        error = AdapterError("mysql", "Error")
        suggestions_str = " ".join(error.suggestions)
        assert "--explain" in suggestions_str or "--adapters" in suggestions_str


class TestQuerySyntaxError:
    """Tests for QuerySyntaxError."""

    def test_basic_initialization(self):
        """Basic error initialization."""
        error = QuerySyntaxError("invalid query")
        assert "invalid query" in error.message
        assert len(error.suggestions) > 0

    def test_with_position(self):
        """Error with position."""
        error = QuerySyntaxError("invalid query", position=5)
        assert "position 5" in error.message
        assert error.context["position"] == 5

    def test_with_expected(self):
        """Error with expected token."""
        error = QuerySyntaxError("invalid query", expected="identifier")
        assert error.details == "Expected: identifier"

    def test_with_position_and_expected(self):
        """Error with both position and expected."""
        error = QuerySyntaxError("invalid query", position=10, expected=")")
        assert "position 10" in error.message
        assert error.details == "Expected: )"
        assert error.context["position"] == 10

    def test_context_includes_query(self):
        """Context includes query string."""
        error = QuerySyntaxError("SELECT * FROM")
        assert error.context["query"] == "SELECT * FROM"

    def test_suggestions_include_query_help(self):
        """Suggestions include query help."""
        error = QuerySyntaxError("invalid")
        suggestions_str = " ".join(error.suggestions)
        assert "query" in suggestions_str.lower() or "help" in suggestions_str.lower()


class TestRuleError:
    """Tests for RuleError."""

    def test_basic_initialization(self):
        """Basic error initialization."""
        error = RuleError("C901", "Complexity too high")
        assert "Complexity too high" in error.message
        assert len(error.suggestions) > 0

    def test_rule_code_in_suggestions(self):
        """Rule code appears in suggestions."""
        error = RuleError("C901", "Error")
        suggestions_str = " ".join(error.suggestions)
        assert "C901" in suggestions_str

    def test_with_file_path(self):
        """Error with file path."""
        error = RuleError("M101", "File too large", file_path="large_file.py")
        assert any("large_file.py" in s for s in error.suggestions)
        assert error.context["file"] == "large_file.py"

    def test_without_file_path(self):
        """Error without file path."""
        error = RuleError("C905", "Nesting too deep")
        # Should still have suggestions
        assert len(error.suggestions) > 0
        # But no file in context
        assert "file" not in error.context

    def test_context_includes_rule_code(self):
        """Context includes rule code."""
        error = RuleError("D002", "Duplicate code detected")
        assert error.context["rule"] == "D002"

    def test_suggestions_include_rule_actions(self):
        """Suggestions include rule-specific actions."""
        error = RuleError("C901", "Error")
        suggestions_str = " ".join(error.suggestions)
        assert "--explain-rule" in suggestions_str or "--disable" in suggestions_str


class TestErrorInheritance:
    """Tests for error inheritance hierarchy."""

    def test_all_errors_inherit_from_reveal_error(self):
        """All custom errors inherit from RevealError."""
        errors = [
            AnalyzerNotFoundError("test.xyz"),
            InvalidPathError("/path"),
            ConfigurationError("error"),
            AdapterError("adapter", "error"),
            QuerySyntaxError("query"),
            RuleError("R001", "error"),
        ]
        for error in errors:
            assert isinstance(error, RevealError)
            assert isinstance(error, Exception)

    def test_all_errors_can_be_raised_as_exception(self):
        """All errors can be raised and caught as Exception."""
        with pytest.raises(Exception):
            raise InvalidPathError("/test")

    def test_can_catch_by_base_class(self):
        """Can catch specific errors by RevealError base class."""
        with pytest.raises(RevealError):
            raise AdapterError("test", "error")


class TestErrorMessages:
    """Tests for error message formatting."""

    def test_error_messages_are_informative(self):
        """Error messages contain useful information."""
        errors = [
            AnalyzerNotFoundError("test.xyz"),
            InvalidPathError("/nonexistent"),
            ConfigurationError("Bad config"),
            AdapterError("mysql", "Connection failed"),
            QuerySyntaxError("bad query"),
            RuleError("C901", "Too complex"),
        ]
        for error in errors:
            # Message should not be empty
            assert len(str(error)) > 10
            # Should contain "Error:"
            assert "Error:" in str(error)

    def test_suggestions_are_actionable(self):
        """All errors provide actionable suggestions."""
        errors = [
            AnalyzerNotFoundError("test.xyz"),
            InvalidPathError("/nonexistent"),
            ConfigurationError("Bad config"),
            AdapterError("mysql", "Connection failed"),
            QuerySyntaxError("bad query"),
            RuleError("C901", "Too complex"),
        ]
        for error in errors:
            # All should have at least one suggestion
            assert len(error.suggestions) > 0
            # Suggestions should not be empty strings
            assert all(len(s.strip()) > 0 for s in error.suggestions)


class TestEdgeCases:
    """Tests for edge cases and unusual inputs."""

    def test_reveal_error_empty_suggestions_list(self):
        """RevealError with empty suggestions list."""
        error = RevealError("Error", suggestions=[])
        output = str(error)
        assert "Suggestions:" not in output

    def test_reveal_error_empty_context(self):
        """RevealError with empty context dict."""
        error = RevealError("Error", context={})
        output = str(error)
        assert "Context:" not in output

    def test_long_error_message(self):
        """Error with very long message."""
        long_msg = "Error: " + "x" * 1000
        error = RevealError(long_msg)
        assert len(str(error)) > 1000

    def test_special_characters_in_message(self):
        """Error message with special characters."""
        error = RevealError("Error: 'test' <broken> & \"quoted\"")
        assert "'test'" in str(error)
        assert "<broken>" in str(error)

    def test_multiline_details(self):
        """Error with multiline details."""
        error = RevealError("Error", details="Line 1\nLine 2\nLine 3")
        output = str(error)
        assert "Line 1" in output
        assert "Line 2" in output

    def test_none_values_in_context(self):
        """Error with None values in context."""
        error = RevealError("Error", context={"key": None, "value": "test"})
        output = str(error)
        assert "key: None" in output
        assert "value: test" in output
