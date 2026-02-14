"""Tests for reveal.result module."""
import pytest
from reveal.result import (
    Result,
    Success,
    Failure,
    success,
    failure,
    from_optional,
    from_exception
)


class TestSuccess:
    """Tests for Success class."""

    def test_is_success(self):
        """Success returns True for is_success()."""
        result = Success(42)
        assert result.is_success() is True

    def test_is_failure(self):
        """Success returns False for is_failure()."""
        result = Success(42)
        assert result.is_failure() is False

    def test_unwrap(self):
        """Success.unwrap() returns the value."""
        result = Success(42)
        assert result.unwrap() == 42

    def test_unwrap_or(self):
        """Success.unwrap_or() returns the value, ignoring default."""
        result = Success(42)
        assert result.unwrap_or(100) == 42

    def test_map(self):
        """Success.map() transforms the value."""
        result = Success(42)
        mapped = result.map(lambda x: x * 2)
        assert isinstance(mapped, Success)
        assert mapped.value == 84

    def test_map_error(self):
        """Success.map_error() is a no-op."""
        result = Success(42)
        mapped = result.map_error(lambda e: f"Error: {e}")
        assert isinstance(mapped, Success)
        assert mapped.value == 42

    def test_value_attribute(self):
        """Success stores value attribute."""
        result = Success("test")
        assert result.value == "test"

    def test_with_none_value(self):
        """Success can hold None as a value."""
        result = Success(None)
        assert result.value is None
        assert result.is_success()

    def test_with_complex_value(self):
        """Success can hold complex types."""
        data = {"key": "value", "nested": [1, 2, 3]}
        result = Success(data)
        assert result.value == data


class TestFailure:
    """Tests for Failure class."""

    def test_is_success(self):
        """Failure returns False for is_success()."""
        result = Failure("error")
        assert result.is_success() is False

    def test_is_failure(self):
        """Failure returns True for is_failure()."""
        result = Failure("error")
        assert result.is_failure() is True

    def test_unwrap_raises(self):
        """Failure.unwrap() raises ValueError."""
        result = Failure("error")
        with pytest.raises(ValueError, match="Called unwrap\\(\\) on Failure: error"):
            result.unwrap()

    def test_unwrap_or(self):
        """Failure.unwrap_or() returns the default."""
        result = Failure("error")
        assert result.unwrap_or(42) == 42

    def test_map(self):
        """Failure.map() is a no-op."""
        result = Failure("error")
        mapped = result.map(lambda x: x * 2)
        assert isinstance(mapped, Failure)
        assert mapped.error == "error"

    def test_map_error(self):
        """Failure.map_error() transforms the error."""
        result = Failure("error")
        mapped = result.map_error(lambda e: f"Transformed: {e}")
        assert isinstance(mapped, Failure)
        assert mapped.error == "Transformed: error"

    def test_map_error_preserves_metadata(self):
        """Failure.map_error() preserves details, suggestions, context."""
        result = Failure(
            error="error",
            details="some details",
            suggestions=["suggestion1", "suggestion2"],
            context={"key": "value"}
        )
        mapped = result.map_error(lambda e: e.upper())
        assert mapped.error == "ERROR"
        assert mapped.details == "some details"
        assert mapped.suggestions == ["suggestion1", "suggestion2"]
        assert mapped.context == {"key": "value"}

    def test_error_attribute(self):
        """Failure stores error attribute."""
        result = Failure("test error")
        assert result.error == "test error"

    def test_with_details(self):
        """Failure can store details."""
        result = Failure("error", details="detailed information")
        assert result.details == "detailed information"

    def test_with_suggestions(self):
        """Failure can store suggestions."""
        result = Failure("error", suggestions=["try this", "or that"])
        assert result.suggestions == ["try this", "or that"]

    def test_with_context(self):
        """Failure can store context."""
        result = Failure("error", context={"file": "test.py", "line": 42})
        assert result.context == {"file": "test.py", "line": 42}

    def test_str_simple(self):
        """Failure.__str__() formats simple error."""
        result = Failure("something went wrong")
        assert str(result) == "Error: something went wrong"

    def test_str_with_details(self):
        """Failure.__str__() includes details."""
        result = Failure("error", details="more info")
        output = str(result)
        assert "Error: error" in output
        assert "Details: more info" in output

    def test_str_with_suggestions(self):
        """Failure.__str__() includes suggestions."""
        result = Failure("error", suggestions=["fix A", "fix B"])
        output = str(result)
        assert "Error: error" in output
        assert "Suggestions:" in output
        assert "  - fix A" in output
        assert "  - fix B" in output

    def test_str_with_context(self):
        """Failure.__str__() includes context."""
        result = Failure("error", context={"file": "test.py", "line": 42})
        output = str(result)
        assert "Error: error" in output
        assert "Context:" in output
        assert "  file: test.py" in output
        assert "  line: 42" in output

    def test_str_with_everything(self):
        """Failure.__str__() formats all fields."""
        result = Failure(
            "error",
            details="details here",
            suggestions=["suggestion1"],
            context={"key": "value"}
        )
        output = str(result)
        assert "Error: error" in output
        assert "Details: details here" in output
        assert "Suggestions:" in output
        assert "  - suggestion1" in output
        assert "Context:" in output
        assert "  key: value" in output


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_success_function(self):
        """success() creates Success instance."""
        result = success(42)
        assert isinstance(result, Success)
        assert result.value == 42

    def test_failure_function(self):
        """failure() creates Failure instance."""
        result = failure("error")
        assert isinstance(result, Failure)
        assert result.error == "error"

    def test_failure_with_metadata(self):
        """failure() accepts all metadata fields."""
        result = failure(
            "error",
            details="details",
            suggestions=["fix1", "fix2"],
            context={"key": "value"}
        )
        assert result.error == "error"
        assert result.details == "details"
        assert result.suggestions == ["fix1", "fix2"]
        assert result.context == {"key": "value"}


class TestFromOptional:
    """Tests for from_optional() function."""

    def test_some_value(self):
        """from_optional() with value returns Success."""
        result = from_optional(42, "error")
        assert isinstance(result, Success)
        assert result.value == 42

    def test_none_value(self):
        """from_optional() with None returns Failure."""
        result = from_optional(None, "not found")
        assert isinstance(result, Failure)
        assert result.error == "not found"

    def test_zero_is_success(self):
        """from_optional() treats 0 as success."""
        result = from_optional(0, "error")
        assert isinstance(result, Success)
        assert result.value == 0

    def test_empty_string_is_success(self):
        """from_optional() treats empty string as success."""
        result = from_optional("", "error")
        assert isinstance(result, Success)
        assert result.value == ""

    def test_false_is_success(self):
        """from_optional() treats False as success."""
        result = from_optional(False, "error")
        assert isinstance(result, Success)
        assert result.value is False


class TestFromException:
    """Tests for from_exception() function."""

    def test_successful_execution(self):
        """from_exception() returns Success for successful function."""
        result = from_exception(lambda: 42)
        assert isinstance(result, Success)
        assert result.value == 42

    def test_exception_with_default_map(self):
        """from_exception() converts exception to string by default."""
        def failing_function():
            raise ValueError("something broke")

        result = from_exception(failing_function)
        assert isinstance(result, Failure)
        assert result.error == "something broke"

    def test_exception_with_custom_map(self):
        """from_exception() uses custom error mapper."""
        def failing_function():
            raise ValueError("original error")

        def error_mapper(e):
            return f"Caught: {type(e).__name__} - {str(e)}"

        result = from_exception(failing_function, error_mapper)
        assert isinstance(result, Failure)
        assert result.error == "Caught: ValueError - original error"

    def test_different_exception_types(self):
        """from_exception() handles different exception types."""
        def raise_runtime_error():
            raise RuntimeError("runtime issue")

        result = from_exception(raise_runtime_error)
        assert isinstance(result, Failure)
        assert result.error == "runtime issue"

    def test_with_complex_return_type(self):
        """from_exception() works with complex return types."""
        def return_dict():
            return {"key": "value", "data": [1, 2, 3]}

        result = from_exception(return_dict)
        assert isinstance(result, Success)
        assert result.value == {"key": "value", "data": [1, 2, 3]}

    def test_preserves_none_return(self):
        """from_exception() preserves None as success value."""
        result = from_exception(lambda: None)
        assert isinstance(result, Success)
        assert result.value is None


class TestResultChaining:
    """Tests for chaining Result operations."""

    def test_success_chain(self):
        """Chaining operations on Success."""
        result = (
            Success(10)
            .map(lambda x: x * 2)
            .map(lambda x: x + 5)
        )
        assert isinstance(result, Success)
        assert result.value == 25

    def test_failure_chain(self):
        """Chaining operations on Failure."""
        result = (
            Failure("error")
            .map(lambda x: x * 2)  # should be no-op
            .map_error(lambda e: f"prefix: {e}")
        )
        assert isinstance(result, Failure)
        assert result.error == "prefix: error"

    def test_mixed_chain(self):
        """Chaining map and map_error."""
        success_result = (
            Success(42)
            .map(lambda x: x * 2)
            .map_error(lambda e: f"Error: {e}")  # no-op on Success
        )
        assert isinstance(success_result, Success)
        assert success_result.value == 84

        failure_result = (
            Failure("error")
            .map_error(lambda e: e.upper())
            .map(lambda x: x * 2)  # no-op on Failure
        )
        assert isinstance(failure_result, Failure)
        assert failure_result.error == "ERROR"


class TestTypeAnnotations:
    """Tests for type safety (runtime behavior)."""

    def test_success_type_preservation(self):
        """Success preserves value type through operations."""
        result = Success(42).map(str)
        assert isinstance(result, Success)
        assert result.value == "42"
        assert isinstance(result.value, str)

    def test_failure_type_preservation(self):
        """Failure preserves error type through operations."""
        result = Failure(404).map_error(str)
        assert isinstance(result, Failure)
        assert result.error == "404"
        assert isinstance(result.error, str)


class TestEdgeCases:
    """Tests for edge cases and corner scenarios."""

    def test_unwrap_or_with_none_default(self):
        """unwrap_or() works with None as default."""
        result = Failure("error")
        assert result.unwrap_or(None) is None

    def test_map_identity_function(self):
        """map() with identity function preserves value."""
        result = Success(42).map(lambda x: x)
        assert result.value == 42

    def test_map_error_identity_function(self):
        """map_error() with identity function preserves error."""
        result = Failure("error").map_error(lambda e: e)
        assert result.error == "error"

    def test_empty_suggestions_list(self):
        """Failure with empty suggestions list."""
        result = Failure("error", suggestions=[])
        output = str(result)
        # Empty list should not add suggestions section
        assert "Suggestions:" not in output

    def test_empty_context_dict(self):
        """Failure with empty context dict."""
        result = Failure("error", context={})
        output = str(result)
        # Empty dict should not add context section
        assert "Context:" not in output

    def test_unwrap_or_called_twice(self):
        """unwrap_or() can be called multiple times."""
        result = Failure("error")
        assert result.unwrap_or(10) == 10
        assert result.unwrap_or(20) == 20

    def test_map_called_multiple_times(self):
        """map() can be called multiple times."""
        result = Success(5)
        result1 = result.map(lambda x: x * 2)
        result2 = result.map(lambda x: x + 3)
        assert result1.value == 10
        assert result2.value == 8
        assert result.value == 5  # original unchanged
