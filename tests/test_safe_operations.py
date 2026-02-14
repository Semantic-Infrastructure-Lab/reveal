"""Tests for reveal/utils/safe_operations.py - safe operation utilities."""

import pytest
import logging
import json
from pathlib import Path
from reveal.utils.safe_operations import (
    safe_operation,
    safe_read_file,
    safe_json_loads,
    safe_yaml_loads,
    SafeContext
)


class TestSafeOperation:
    """Test safe_operation decorator."""

    def test_successful_operation(self):
        """Decorator returns result on success."""
        @safe_operation(fallback="error")
        def successful_func():
            return "success"

        result = successful_func()

        assert result == "success"

    def test_exception_returns_fallback(self):
        """Decorator returns fallback on exception."""
        @safe_operation(fallback="fallback_value")
        def failing_func():
            raise ValueError("something wrong")

        result = failing_func()

        assert result == "fallback_value"

    def test_default_fallback_none(self):
        """Default fallback is None."""
        @safe_operation()
        def failing_func():
            raise Exception("error")

        result = failing_func()

        assert result is None

    def test_custom_fallback(self):
        """Support custom fallback values."""
        @safe_operation(fallback=[])
        def failing_func():
            raise Exception("error")

        result = failing_func()

        assert result == []

    def test_specific_exception_types(self):
        """Catch only specific exception types."""
        @safe_operation(fallback="caught", exceptions=(ValueError,))
        def raise_valueerror():
            raise ValueError("error")

        result = raise_valueerror()
        assert result == "caught"

    def test_uncaught_exception_propagates(self):
        """Uncaught exceptions propagate."""
        @safe_operation(fallback="caught", exceptions=(ValueError,))
        def raise_typeerror():
            raise TypeError("error")

        with pytest.raises(TypeError):
            raise_typeerror()

    def test_preserves_function_metadata(self):
        """Decorator preserves function name and docstring."""
        @safe_operation()
        def my_function():
            """My docstring."""
            pass

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."

    def test_with_arguments(self):
        """Decorator works with function arguments."""
        @safe_operation(fallback=0)
        def add(a, b):
            if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
                raise TypeError("Need numbers")
            return a + b

        assert add(2, 3) == 5
        assert add("a", "b") == 0  # Fallback on error

    def test_with_kwargs(self):
        """Decorator works with keyword arguments."""
        @safe_operation(fallback={})
        def create_dict(key=None, value=None):
            if key is None:
                raise ValueError("key required")
            return {key: value}

        assert create_dict(key="name", value="Alice") == {"name": "Alice"}
        assert create_dict() == {}  # Fallback on error

    def test_logging(self, caplog):
        """Decorator logs exceptions."""
        caplog.set_level(logging.DEBUG)

        @safe_operation(fallback=None, log_level=logging.DEBUG)
        def failing_func():
            raise ValueError("test error")

        failing_func()

        assert "failing_func failed gracefully" in caplog.text
        assert "test error" in caplog.text

    def test_custom_log_level(self, caplog):
        """Support custom log levels."""
        caplog.set_level(logging.WARNING)

        @safe_operation(fallback=None, log_level=logging.WARNING)
        def failing_func():
            raise Exception("warning error")

        failing_func()

        assert "warning error" in caplog.text


class TestSafeReadFile:
    """Test safe_read_file function."""

    def test_read_existing_file(self, tmp_path):
        """Read file successfully."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        result = safe_read_file(str(test_file))

        assert result == "Hello, World!"

    def test_nonexistent_file_returns_fallback(self, tmp_path):
        """Return fallback for nonexistent file."""
        result = safe_read_file(str(tmp_path / "missing.txt"))

        assert result == ""  # Default fallback

    def test_custom_fallback(self, tmp_path):
        """Use custom fallback value."""
        result = safe_read_file(
            str(tmp_path / "missing.txt"),
            fallback="FILE NOT FOUND"
        )

        assert result == "FILE NOT FOUND"

    def test_custom_encoding(self, tmp_path):
        """Support custom encoding."""
        test_file = tmp_path / "utf16.txt"
        test_file.write_text("Unicode: 世界", encoding="utf-16")

        result = safe_read_file(str(test_file), encoding="utf-16")

        assert result == "Unicode: 世界"

    def test_encoding_error_returns_fallback(self, tmp_path):
        """Return fallback on encoding errors."""
        test_file = tmp_path / "binary.dat"
        test_file.write_bytes(b"\x80\x81\x82")  # Invalid UTF-8

        result = safe_read_file(str(test_file), fallback="ENCODING ERROR")

        assert result == "ENCODING ERROR"

    def test_permission_error_returns_fallback(self, tmp_path):
        """Return fallback on permission errors."""
        import os
        if os.name == 'posix':
            test_file = tmp_path / "restricted.txt"
            test_file.write_text("secret")
            test_file.chmod(0o000)  # No read permissions

            result = safe_read_file(str(test_file), fallback="NO ACCESS")

            assert result == "NO ACCESS"

            # Cleanup
            test_file.chmod(0o644)


class TestSafeJsonLoads:
    """Test safe_json_loads function."""

    def test_valid_json(self):
        """Parse valid JSON."""
        result = safe_json_loads('{"key": "value", "number": 42}')

        assert result == {"key": "value", "number": 42}

    def test_invalid_json_returns_fallback(self):
        """Return fallback for invalid JSON."""
        result = safe_json_loads('{invalid json}')

        assert result is None  # Default fallback

    def test_custom_fallback(self):
        """Use custom fallback value."""
        result = safe_json_loads('{bad}', fallback={})

        assert result == {}

    def test_empty_string(self):
        """Handle empty string."""
        result = safe_json_loads('', fallback="EMPTY")

        assert result == "EMPTY"

    def test_null_value(self):
        """Parse JSON null."""
        result = safe_json_loads('null')

        assert result is None

    def test_json_array(self):
        """Parse JSON array."""
        result = safe_json_loads('[1, 2, 3]')

        assert result == [1, 2, 3]

    def test_nested_json(self):
        """Parse nested JSON."""
        result = safe_json_loads('{"nested": {"key": "value"}}')

        assert result == {"nested": {"key": "value"}}

    def test_type_error_fallback(self):
        """Handle TypeError (non-string input)."""
        result = safe_json_loads(None, fallback="TYPE ERROR")

        assert result == "TYPE ERROR"


class TestSafeYamlLoads:
    """Test safe_yaml_loads function."""

    def test_valid_yaml(self):
        """Parse valid YAML."""
        yaml_content = """
        key: value
        number: 42
        """
        result = safe_yaml_loads(yaml_content)

        assert result == {"key": "value", "number": 42}

    def test_invalid_yaml_returns_fallback(self):
        """Return fallback for invalid YAML."""
        result = safe_yaml_loads('{ invalid: yaml: : }')

        assert result is None  # Default fallback

    def test_custom_fallback(self):
        """Use custom fallback value."""
        # Use actually invalid YAML (tabs not allowed for indentation)
        result = safe_yaml_loads('key:\n\tvalue', fallback={})

        assert result == {}

    def test_yaml_list(self):
        """Parse YAML list."""
        yaml_content = """
        - item1
        - item2
        - item3
        """
        result = safe_yaml_loads(yaml_content)

        assert result == ["item1", "item2", "item3"]

    def test_nested_yaml(self):
        """Parse nested YAML."""
        yaml_content = """
        parent:
          child: value
        """
        result = safe_yaml_loads(yaml_content)

        assert result == {"parent": {"child": "value"}}

    def test_yaml_with_types(self):
        """Parse YAML with different types."""
        yaml_content = """
        string: hello
        number: 123
        boolean: true
        null_value: null
        """
        result = safe_yaml_loads(yaml_content)

        assert result["string"] == "hello"
        assert result["number"] == 123
        assert result["boolean"] is True
        assert result["null_value"] is None

    def test_empty_yaml(self):
        """Handle empty YAML."""
        result = safe_yaml_loads('')

        assert result is None


class TestSafeContext:
    """Test SafeContext context manager."""

    def test_successful_operation(self):
        """Context manager preserves value on success."""
        with SafeContext() as ctx:
            ctx.value = "success"

        assert ctx.value == "success"
        assert ctx.exception is None

    def test_exception_caught(self):
        """Context manager catches exceptions."""
        with SafeContext() as ctx:
            ctx.value = "initial"
            raise ValueError("test error")

        # Exception caught, value reset to fallback
        assert ctx.value is None  # Default fallback
        assert isinstance(ctx.exception, ValueError)

    def test_custom_fallback(self):
        """Use custom fallback value."""
        with SafeContext(fallback="error") as ctx:
            ctx.value = "success"
            raise Exception("fail")

        assert ctx.value == "error"

    def test_exception_suppressed(self):
        """Context manager suppresses exceptions."""
        # Should not raise
        with SafeContext() as ctx:
            raise RuntimeError("This should be caught")

        # Execution continues
        assert ctx.exception is not None

    def test_no_exception(self):
        """Context manager returns False when no exception."""
        with SafeContext() as ctx:
            ctx.value = "normal"

        assert ctx.value == "normal"
        assert ctx.exception is None

    def test_logging(self, caplog):
        """Context manager logs exceptions."""
        caplog.set_level(logging.DEBUG)

        with SafeContext(log_level=logging.DEBUG):
            raise ValueError("logged error")

        assert "SafeContext caught" in caplog.text
        assert "logged error" in caplog.text

    def test_custom_log_level(self, caplog):
        """Support custom log levels."""
        caplog.set_level(logging.WARNING)

        with SafeContext(log_level=logging.WARNING):
            raise Exception("warning level")

        assert "warning level" in caplog.text

    def test_complex_operation(self):
        """Use context for complex operations."""
        with SafeContext(fallback=[]) as ctx:
            data = [1, 2, 3]
            data.append(4)
            ctx.value = data

        assert ctx.value == [1, 2, 3, 4]

    def test_partial_execution(self):
        """Context captures state at point of exception."""
        with SafeContext() as ctx:
            ctx.value = "partial"
            # Some work done
            # Exception before completion
            raise Exception("interrupted")

        # Value was set but then reset to fallback
        assert ctx.value is None
        assert ctx.exception is not None

    def test_multiple_exceptions(self):
        """Only first exception is caught and stored."""
        with SafeContext() as ctx:
            raise ValueError("first error")
            # This line never executes
            raise TypeError("second error")

        assert isinstance(ctx.exception, ValueError)

    def test_context_manager_protocol(self):
        """Verify __enter__ and __exit__ protocol."""
        ctx = SafeContext(fallback="default")

        # __enter__ returns self
        result = ctx.__enter__()
        assert result is ctx

        # __exit__ with no exception returns False
        returns_false = ctx.__exit__(None, None, None)
        assert returns_false is False

        # __exit__ with exception returns True (suppresses)
        returns_true = ctx.__exit__(ValueError, ValueError("test"), None)
        assert returns_true is True
