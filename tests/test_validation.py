"""Tests for reveal.utils.validation module."""
import sys
import pytest
import tempfile
from pathlib import Path
from reveal.utils.validation import (
    require_path_exists,
    require_file,
    require_directory,
    validate_port,
    require_package,
    require_type,
    require_non_empty,
    validate_range,
    validate_one_of,
    validate_callable,
    require_readable_file,
    require_writable_directory,
)


class TestRequirePathExists:
    """Tests for require_path_exists() function."""

    def test_existing_path(self, tmp_path):
        """Existing path returns the path."""
        test_file = tmp_path / "test.txt"
        test_file.touch()
        result = require_path_exists(test_file)
        assert result == test_file

    def test_nonexistent_path_raises(self, tmp_path):
        """Nonexistent path raises FileNotFoundError."""
        nonexistent = tmp_path / "does_not_exist.txt"
        with pytest.raises(FileNotFoundError, match="Path not found"):
            require_path_exists(nonexistent)

    def test_custom_error_message(self, tmp_path):
        """Custom path type appears in error message."""
        nonexistent = tmp_path / "config.yaml"
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            require_path_exists(nonexistent, "Configuration file")

    def test_directory_path(self, tmp_path):
        """Directory path works."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()
        result = require_path_exists(test_dir)
        assert result == test_dir


class TestRequireFile:
    """Tests for require_file() function."""

    def test_existing_file(self, tmp_path):
        """Existing file returns the path."""
        test_file = tmp_path / "test.txt"
        test_file.touch()
        result = require_file(test_file)
        assert result == test_file

    def test_nonexistent_file_raises(self, tmp_path):
        """Nonexistent file raises FileNotFoundError."""
        nonexistent = tmp_path / "does_not_exist.txt"
        with pytest.raises(FileNotFoundError, match="File not found"):
            require_file(nonexistent)

    def test_directory_raises(self, tmp_path):
        """Directory raises ValueError."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()
        with pytest.raises(ValueError, match="File is not a file"):
            require_file(test_dir)

    def test_custom_error_message(self, tmp_path):
        """Custom file type appears in error message."""
        test_dir = tmp_path / "data"
        test_dir.mkdir()
        with pytest.raises(ValueError, match="Data file is not a file"):
            require_file(test_dir, "Data file")


class TestRequireDirectory:
    """Tests for require_directory() function."""

    def test_existing_directory(self, tmp_path):
        """Existing directory returns the path."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()
        result = require_directory(test_dir)
        assert result == test_dir

    def test_nonexistent_directory_raises(self, tmp_path):
        """Nonexistent directory raises FileNotFoundError."""
        nonexistent = tmp_path / "does_not_exist"
        with pytest.raises(FileNotFoundError, match="Directory not found"):
            require_directory(nonexistent)

    def test_file_raises(self, tmp_path):
        """File raises ValueError."""
        test_file = tmp_path / "test.txt"
        test_file.touch()
        with pytest.raises(ValueError, match="Directory is not a directory"):
            require_directory(test_file)

    def test_custom_error_message(self, tmp_path):
        """Custom directory type appears in error message."""
        test_file = tmp_path / "config.yaml"
        test_file.touch()
        with pytest.raises(ValueError, match="Source directory is not a directory"):
            require_directory(test_file, "Source directory")


class TestValidatePort:
    """Tests for validate_port() function."""

    def test_valid_port(self):
        """Valid port returns the port."""
        assert validate_port(3306) == 3306
        assert validate_port(80) == 80
        assert validate_port(65535) == 65535

    def test_port_below_range_raises(self):
        """Port below range raises ValueError."""
        with pytest.raises(ValueError, match="Port must be between 1 and 65535, got 0"):
            validate_port(0)

    def test_port_above_range_raises(self):
        """Port above range raises ValueError."""
        with pytest.raises(ValueError, match="Port must be between 1 and 65535, got 65536"):
            validate_port(65536)

    def test_custom_port_range(self):
        """Custom port range works."""
        assert validate_port(5000, port_range=(1024, 49151)) == 5000

    def test_custom_range_violation(self):
        """Custom range violation raises ValueError."""
        with pytest.raises(ValueError, match="Port must be between 1024 and 49151, got 80"):
            validate_port(80, port_range=(1024, 49151))

    def test_custom_port_name(self):
        """Custom port name appears in error message."""
        with pytest.raises(ValueError, match="MySQL port must be between"):
            validate_port(0, name="MySQL port")

    def test_non_integer_raises(self):
        """Non-integer port raises TypeError."""
        with pytest.raises(TypeError, match="Port must be an integer, got str"):
            validate_port("3306")

    def test_float_raises(self):
        """Float port raises TypeError."""
        with pytest.raises(TypeError, match="Port must be an integer, got float"):
            validate_port(3306.5)


class TestRequirePackage:
    """Tests for require_package() function."""

    def test_installed_package(self):
        """Installed package doesn't raise."""
        # pytest is definitely installed if tests are running
        require_package('pytest', 'pip install pytest')

    def test_missing_package_raises(self):
        """Missing package raises ImportError."""
        with pytest.raises(ImportError, match="fake_nonexistent_package is required but not installed"):
            require_package('fake_nonexistent_package', 'pip install fake_nonexistent_package')

    def test_install_command_in_message(self):
        """Install command appears in error message."""
        with pytest.raises(ImportError, match="Install with: pip install fake_package"):
            require_package('fake_package', 'pip install fake_package')

    def test_different_import_name(self):
        """Different import name works."""
        # Test with a hypothetical package where import name differs
        with pytest.raises(ImportError, match="fake-package is required"):
            require_package('fake-package', 'pip install fake-package', import_name='fake_module')


class TestRequireType:
    """Tests for require_type() function."""

    def test_correct_type(self):
        """Correct type returns the value."""
        assert require_type(42, int, 'value') == 42
        assert require_type('test', str, 'value') == 'test'
        assert require_type([1, 2], list, 'value') == [1, 2]

    def test_wrong_type_raises(self):
        """Wrong type raises TypeError."""
        with pytest.raises(TypeError, match="limit must be int, got str"):
            require_type('10', int, 'limit')

    def test_none_type_check(self):
        """None type check raises TypeError."""
        with pytest.raises(TypeError, match="value must be str, got NoneType"):
            require_type(None, str, 'value')

    def test_subclass_fails(self):
        """Subclass check uses isinstance (which accepts subclasses)."""
        # bool is a subclass of int
        assert require_type(True, int, 'value') is True


class TestRequireNonEmpty:
    """Tests for require_non_empty() function."""

    def test_non_empty_string(self):
        """Non-empty string returns the value."""
        assert require_non_empty('test', 'param') == 'test'
        assert require_non_empty('a', 'param') == 'a'

    def test_empty_string_raises(self):
        """Empty string raises ValueError."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            require_non_empty('', 'name')

    def test_whitespace_only_raises(self):
        """Whitespace-only string raises ValueError."""
        with pytest.raises(ValueError, match="query cannot be empty"):
            require_non_empty('   ', 'query')

    def test_newline_only_raises(self):
        """Newline-only string raises ValueError."""
        with pytest.raises(ValueError, match="param cannot be empty"):
            require_non_empty('\n\t', 'param')


class TestValidateRange:
    """Tests for validate_range() function."""

    def test_value_in_range(self):
        """Value in range returns the value."""
        assert validate_range(5.0, 0.0, 10.0) == 5.0
        assert validate_range(0.0, 0.0, 10.0) == 0.0
        assert validate_range(10.0, 0.0, 10.0) == 10.0

    def test_value_below_minimum_raises(self):
        """Value below minimum raises ValueError."""
        with pytest.raises(ValueError, match="Value must be >= 0.0, got -1.0"):
            validate_range(-1.0, min_value=0.0)

    def test_value_above_maximum_raises(self):
        """Value above maximum raises ValueError."""
        with pytest.raises(ValueError, match="Value must be <= 1.0, got 1.5"):
            validate_range(1.5, max_value=1.0)

    def test_no_minimum(self):
        """No minimum allows any low value."""
        assert validate_range(-1000.0, max_value=10.0) == -1000.0

    def test_no_maximum(self):
        """No maximum allows any high value."""
        assert validate_range(1000.0, min_value=0.0) == 1000.0

    def test_custom_param_name(self):
        """Custom parameter name appears in error message."""
        with pytest.raises(ValueError, match="confidence must be >= 0.0, got -0.5"):
            validate_range(-0.5, min_value=0.0, param_name='confidence')

    def test_integer_values(self):
        """Integer values work."""
        assert validate_range(5, 0, 10) == 5


class TestValidateOneOf:
    """Tests for validate_one_of() function."""

    def test_value_in_list(self):
        """Value in allowed list returns the value."""
        assert validate_one_of('a', ['a', 'b', 'c']) == 'a'
        assert validate_one_of(2, [1, 2, 3]) == 2

    def test_value_not_in_list_raises(self):
        """Value not in list raises ValueError."""
        with pytest.raises(ValueError, match="Value must be one of"):
            validate_one_of('d', ['a', 'b', 'c'])

    def test_custom_param_name(self):
        """Custom parameter name appears in error message."""
        with pytest.raises(ValueError, match="mode must be one of"):
            validate_one_of('invalid', ['development', 'production'], 'mode')

    def test_allowed_values_in_message(self):
        """Allowed values appear in error message."""
        with pytest.raises(ValueError, match=r"\['a', 'b', 'c'\]"):
            validate_one_of('d', ['a', 'b', 'c'], 'option')

    def test_none_value(self):
        """None can be in allowed values."""
        assert validate_one_of(None, [None, 'a', 'b']) is None


class TestValidateCallable:
    """Tests for validate_callable() function."""

    def test_function_is_callable(self):
        """Function is callable."""
        def test_func():
            pass
        assert validate_callable(test_func, 'callback') == test_func

    def test_lambda_is_callable(self):
        """Lambda is callable."""
        func = lambda x: x * 2
        assert validate_callable(func, 'handler') == func

    def test_class_is_callable(self):
        """Class is callable."""
        class TestClass:
            pass
        assert validate_callable(TestClass, 'factory') == TestClass

    def test_non_callable_raises(self):
        """Non-callable raises TypeError."""
        with pytest.raises(TypeError, match="callback must be callable, got str"):
            validate_callable('not_callable', 'callback')

    def test_integer_not_callable(self):
        """Integer is not callable."""
        with pytest.raises(TypeError, match="handler must be callable, got int"):
            validate_callable(42, 'handler')


class TestRequireReadableFile:
    """Tests for require_readable_file() function."""

    def test_readable_file(self, tmp_path):
        """Readable file returns the path."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        result = require_readable_file(test_file)
        assert result == test_file

    def test_nonexistent_file_raises(self, tmp_path):
        """Nonexistent file raises FileNotFoundError."""
        nonexistent = tmp_path / "does_not_exist.txt"
        with pytest.raises(FileNotFoundError):
            require_readable_file(nonexistent)

    def test_directory_raises(self, tmp_path):
        """Directory raises ValueError."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()
        with pytest.raises(ValueError, match="is not a file"):
            require_readable_file(test_dir)

    @pytest.mark.skipif(sys.platform == 'win32', reason="chmod does not restrict access on Windows")
    def test_unreadable_file_raises(self, tmp_path):
        """Unreadable file raises PermissionError."""
        # This test is platform-dependent and may be skipped on Windows
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        test_file.chmod(0o000)

        try:
            with pytest.raises(PermissionError, match="is not readable"):
                require_readable_file(test_file)
        finally:
            # Restore permissions for cleanup
            test_file.chmod(0o644)


class TestRequireWritableDirectory:
    """Tests for require_writable_directory() function."""

    def test_writable_directory(self, tmp_path):
        """Writable directory returns the path."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()
        result = require_writable_directory(test_dir)
        assert result == test_dir

    def test_nonexistent_directory_raises(self, tmp_path):
        """Nonexistent directory raises FileNotFoundError."""
        nonexistent = tmp_path / "does_not_exist"
        with pytest.raises(FileNotFoundError):
            require_writable_directory(nonexistent)

    def test_file_raises(self, tmp_path):
        """File raises ValueError."""
        test_file = tmp_path / "test.txt"
        test_file.touch()
        with pytest.raises(ValueError, match="is not a directory"):
            require_writable_directory(test_file)

    @pytest.mark.skipif(sys.platform == 'win32', reason="chmod does not restrict access on Windows")
    def test_read_only_directory_raises(self, tmp_path):
        """Read-only directory raises PermissionError."""
        # This test is platform-dependent and may be skipped on Windows
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()
        test_dir.chmod(0o444)

        try:
            with pytest.raises(PermissionError, match="is not writable"):
                require_writable_directory(test_dir)
        finally:
            # Restore permissions for cleanup
            test_dir.chmod(0o755)


class TestChaining:
    """Tests for chaining validators."""

    def test_require_file_returns_path(self, tmp_path):
        """require_file can be chained."""
        test_file = tmp_path / "test.txt"
        test_file.touch()
        # Chain with Path methods
        result = require_file(test_file).absolute()
        assert result.is_absolute()

    def test_validate_port_chaining(self):
        """validate_port can be used in expressions."""
        port = validate_port(3306) + 1
        assert port == 3307

    def test_require_type_chaining(self):
        """require_type can be chained."""
        value = require_type(42, int, 'value') * 2
        assert value == 84


class TestEdgeCases:
    """Tests for edge cases and unusual inputs."""

    def test_validate_port_boundary_values(self):
        """Port validation at boundaries."""
        assert validate_port(1) == 1
        assert validate_port(65535) == 65535

    def test_validate_range_exact_boundaries(self):
        """Range validation at exact boundaries."""
        assert validate_range(0.0, 0.0, 1.0) == 0.0
        assert validate_range(1.0, 0.0, 1.0) == 1.0

    def test_require_non_empty_with_spaces(self):
        """Non-empty with leading/trailing spaces."""
        assert require_non_empty('  test  ', 'param') == '  test  '

    def test_validate_one_of_empty_list(self):
        """validate_one_of with empty list always fails."""
        with pytest.raises(ValueError):
            validate_one_of('value', [], 'param')

    def test_validate_one_of_single_item(self):
        """validate_one_of with single item list."""
        assert validate_one_of('only', ['only'], 'param') == 'only'
