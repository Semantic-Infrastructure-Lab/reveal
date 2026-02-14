"""Tests for reveal.utils.safe_operations module."""

import sys
import json
import logging
import pytest
from pathlib import Path
from reveal.utils.safe_operations import (
    safe_operation,
    safe_read_file,
    safe_json_loads,
    safe_yaml_loads,
    SafeContext
)


class TestSafeOperation:
    """Tests for safe_operation decorator."""

    def test_successful_operation_returns_value(self):
        """Should return result when no exception occurs."""
        @safe_operation()
        def successful_func():
            return "success"

        result = successful_func()
        assert result == "success"

    def test_failed_operation_returns_fallback(self):
        """Should return fallback when exception occurs."""
        @safe_operation(fallback="default")
        def failing_func():
            raise ValueError("test error")

        result = failing_func()
        assert result == "default"

    def test_custom_fallback_value(self):
        """Should support custom fallback values."""
        @safe_operation(fallback=[])
        def failing_func():
            raise RuntimeError("error")

        result = failing_func()
        assert result == []

    def test_none_fallback_default(self):
        """Should use None as default fallback."""
        @safe_operation()
        def failing_func():
            raise Exception("error")

        result = failing_func()
        assert result is None

    def test_logs_exception_at_debug_level(self, caplog):
        """Should log exception at DEBUG level by default."""
        @safe_operation()
        def failing_func():
            raise ValueError("test error")

        with caplog.at_level(logging.DEBUG):
            failing_func()

        assert "failing_func failed gracefully" in caplog.text
        assert "test error" in caplog.text

    def test_custom_log_level(self, caplog):
        """Should support custom log levels."""
        @safe_operation(log_level=logging.WARNING)
        def failing_func():
            raise ValueError("warning test")

        with caplog.at_level(logging.WARNING):
            failing_func()

        assert "failing_func failed gracefully" in caplog.text
        assert "warning test" in caplog.text

    def test_specific_exception_types(self):
        """Should only catch specified exception types."""
        @safe_operation(fallback="caught", exceptions=(ValueError,))
        def value_error_func():
            raise ValueError("caught")

        result = value_error_func()
        assert result == "caught"

    def test_unspecified_exception_propagates(self):
        """Should propagate exceptions not in the catch list."""
        @safe_operation(fallback="fallback", exceptions=(ValueError,))
        def runtime_error_func():
            raise RuntimeError("not caught")

        with pytest.raises(RuntimeError, match="not caught"):
            runtime_error_func()

    def test_preserves_function_metadata(self):
        """Should preserve original function name and docstring."""
        @safe_operation()
        def documented_func():
            """Original docstring."""
            pass

        assert documented_func.__name__ == "documented_func"
        assert documented_func.__doc__ == "Original docstring."

    def test_with_function_arguments(self):
        """Should work with functions that take arguments."""
        @safe_operation(fallback=0)
        def add(a, b):
            if a < 0:
                raise ValueError("negative not allowed")
            return a + b

        # Successful case
        assert add(2, 3) == 5

        # Error case
        assert add(-1, 3) == 0

    def test_with_keyword_arguments(self):
        """Should work with keyword arguments."""
        @safe_operation(fallback={})
        def create_dict(key=None, value=None):
            if key is None:
                raise ValueError("key required")
            return {key: value}

        assert create_dict(key="test", value="value") == {"test": "value"}
        assert create_dict(value="orphan") == {}


class TestSafeReadFile:
    """Tests for safe_read_file function."""

    def test_reads_existing_file(self, tmp_path):
        """Should read and return file contents."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World", encoding="utf-8")

        result = safe_read_file(str(test_file))
        assert result == "Hello World"

    def test_nonexistent_file_returns_fallback(self):
        """Should return fallback for nonexistent file."""
        result = safe_read_file("/nonexistent/file.txt")
        assert result == ""

    def test_custom_fallback(self):
        """Should support custom fallback value."""
        result = safe_read_file("/nonexistent/file.txt", fallback="NOT FOUND")
        assert result == "NOT FOUND"

    def test_custom_encoding(self, tmp_path):
        """Should support custom encoding."""
        test_file = tmp_path / "utf16.txt"
        test_file.write_text("UTF-16 content", encoding="utf-16")

        result = safe_read_file(str(test_file), encoding="utf-16")
        assert result == "UTF-16 content"

    @pytest.mark.skipif(sys.platform == 'win32', reason="chmod doesn't work the same on Windows")
    def test_permission_error_returns_fallback(self, tmp_path):
        """Should return fallback on permission errors."""
        import os
        test_file = tmp_path / "restricted.txt"
        test_file.write_text("secret")

        # Make file unreadable
        os.chmod(test_file, 0o000)

        result = safe_read_file(str(test_file), fallback="ACCESS DENIED")

        # Restore permissions for cleanup
        os.chmod(test_file, 0o644)

        assert result == "ACCESS DENIED"

    def test_logs_error(self, tmp_path, caplog):
        """Should log error when read fails."""
        with caplog.at_level(logging.DEBUG):
            safe_read_file("/nonexistent/file.txt")

        assert "Failed to read" in caplog.text


class TestSafeJsonLoads:
    """Tests for safe_json_loads function."""

    def test_parses_valid_json(self):
        """Should parse valid JSON."""
        result = safe_json_loads('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parses_json_array(self):
        """Should parse JSON arrays."""
        result = safe_json_loads('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_invalid_json_returns_fallback(self):
        """Should return fallback for invalid JSON."""
        result = safe_json_loads('{"invalid": }')
        assert result is None

    def test_custom_fallback(self):
        """Should support custom fallback."""
        result = safe_json_loads('invalid', fallback={})
        assert result == {}

    def test_none_input_returns_fallback(self):
        """Should handle None input gracefully."""
        result = safe_json_loads(None, fallback="ERROR")
        assert result == "ERROR"

    def test_logs_parse_error(self, caplog):
        """Should log JSON parse errors."""
        with caplog.at_level(logging.DEBUG):
            safe_json_loads('{"bad": json}')

        assert "JSON parse failed" in caplog.text

    def test_handles_type_error(self):
        """Should handle TypeError (e.g., wrong input type)."""
        result = safe_json_loads(123, fallback="TYPE_ERROR")
        assert result == "TYPE_ERROR"


class TestSafeYamlLoads:
    """Tests for safe_yaml_loads function."""

    def test_parses_valid_yaml(self):
        """Should parse valid YAML."""
        yaml_content = """
        key: value
        number: 42
        """
        result = safe_yaml_loads(yaml_content)
        assert result == {"key": "value", "number": 42}

    def test_parses_yaml_list(self):
        """Should parse YAML lists."""
        yaml_content = """
        - item1
        - item2
        - item3
        """
        result = safe_yaml_loads(yaml_content)
        assert result == ["item1", "item2", "item3"]

    def test_invalid_yaml_returns_fallback(self):
        """Should return fallback for invalid YAML."""
        result = safe_yaml_loads("invalid: yaml: structure:")
        assert result is None

    def test_custom_fallback(self):
        """Should support custom fallback."""
        result = safe_yaml_loads("bad:\n\tyaml", fallback={})
        assert result == {}

    def test_logs_parse_error(self, caplog):
        """Should log YAML parse errors."""
        with caplog.at_level(logging.DEBUG):
            safe_yaml_loads("bad:\n\tyaml")

        assert "YAML parse failed" in caplog.text

    def test_empty_yaml(self):
        """Should handle empty YAML."""
        result = safe_yaml_loads("")
        # Empty YAML returns None, which is falsy but valid
        assert result is None

    def test_yaml_with_special_types(self):
        """Should handle YAML special types."""
        yaml_content = """
        enabled: true
        count: 10
        name: test
        """
        result = safe_yaml_loads(yaml_content)
        assert result == {"enabled": True, "count": 10, "name": "test"}


class TestSafeContext:
    """Tests for SafeContext context manager."""

    def test_successful_operation_preserves_value(self):
        """Should preserve value when no exception occurs."""
        with SafeContext() as ctx:
            ctx.value = "success"

        assert ctx.value == "success"
        assert ctx.exception is None

    def test_exception_sets_value_to_fallback(self):
        """Should set value to fallback when exception occurs."""
        with SafeContext(fallback="default") as ctx:
            ctx.value = "temporary"
            raise ValueError("test error")

        assert ctx.value == "default"
        assert ctx.exception is not None

    def test_exception_is_suppressed(self):
        """Should suppress exceptions (not propagate)."""
        # Should not raise
        with SafeContext() as ctx:
            raise RuntimeError("suppressed")

        assert ctx.exception is not None

    def test_none_fallback_default(self):
        """Should use None as default fallback."""
        with SafeContext() as ctx:
            raise Exception("error")

        assert ctx.value is None

    def test_logs_exception_at_debug_level(self, caplog):
        """Should log exceptions at DEBUG level by default."""
        with caplog.at_level(logging.DEBUG):
            with SafeContext() as ctx:
                raise ValueError("logged error")

        assert "SafeContext caught" in caplog.text
        assert "logged error" in caplog.text

    def test_custom_log_level(self, caplog):
        """Should support custom log levels."""
        with caplog.at_level(logging.WARNING):
            with SafeContext(log_level=logging.WARNING) as ctx:
                raise RuntimeError("warning level")

        assert "SafeContext caught" in caplog.text

    def test_stores_exception_reference(self):
        """Should store the caught exception."""
        with SafeContext() as ctx:
            raise ValueError("stored")

        assert isinstance(ctx.exception, ValueError)
        assert str(ctx.exception) == "stored"

    def test_multiple_operations_in_context(self):
        """Should handle multiple operations before exception."""
        with SafeContext(fallback=0) as ctx:
            ctx.value = 1
            ctx.value = 2
            ctx.value = 3
            raise RuntimeError("error")

        assert ctx.value == 0  # Fallback

    def test_no_exception_no_fallback(self):
        """Should not use fallback when no exception."""
        with SafeContext(fallback="unused") as ctx:
            ctx.value = "actual"

        assert ctx.value == "actual"

    def test_initial_value_is_fallback(self):
        """Should initialize value to fallback."""
        ctx = SafeContext(fallback="initial")
        assert ctx.value == "initial"

    def test_custom_fallback_types(self):
        """Should work with different fallback types."""
        # List fallback
        with SafeContext(fallback=[]) as ctx:
            raise Exception()
        assert ctx.value == []

        # Dict fallback
        with SafeContext(fallback={}) as ctx:
            raise Exception()
        assert ctx.value == {}

        # Number fallback
        with SafeContext(fallback=0) as ctx:
            raise Exception()
        assert ctx.value == 0
