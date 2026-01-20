"""Tests for @N ordinal extraction syntax.

Tests the ability to extract elements by their ordinal position:
- @N: Extract Nth element of dominant category (functions for code, headings for markdown)
- type:N: Extract Nth element of specific type (e.g., function:3, class:1)
"""

import pytest
import tempfile
import os

from reveal.registry import get_analyzer
from reveal.display.element import (
    _extract_ordinal_element,
    _extract_element_at_line,
    _read_lines,
)


def create_analyzer(path):
    """Create an analyzer instance for the given path."""
    AnalyzerClass = get_analyzer(path)
    return AnalyzerClass(path)


# === Test Fixtures ===

@pytest.fixture
def python_file():
    """Create a temporary Python file with multiple functions and classes."""
    content = '''"""Test module."""

def first_function():
    """First function."""
    pass

def second_function():
    """Second function."""
    return 42

class MyClass:
    """A class."""

    def method_one(self):
        pass

    def method_two(self):
        pass

def third_function():
    """Third function."""
    return "hello"

class AnotherClass:
    """Another class."""
    pass
'''
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(content)
        f.flush()
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def markdown_file():
    """Create a temporary Markdown file with multiple headings."""
    content = '''# First Heading

Some content here.

## Second Heading

More content.

### Third Heading

Deep content.

## Fourth Heading

Final content.
'''
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(content)
        f.flush()
        yield f.name
    os.unlink(f.name)


# === Tests for @N Ordinal Extraction ===

class TestOrdinalExtraction:
    """Test @N ordinal extraction for dominant category."""

    def test_python_at_1_extracts_first_function(self, python_file):
        """@1 on Python file extracts first function."""
        analyzer = create_analyzer(python_file)
        result = _extract_ordinal_element(analyzer, 1)

        assert result is not None
        assert result['name'] == 'first_function'
        assert 'def first_function' in result['source']

    def test_python_at_2_extracts_second_function(self, python_file):
        """@2 on Python file extracts second function."""
        analyzer = create_analyzer(python_file)
        result = _extract_ordinal_element(analyzer, 2)

        assert result is not None
        assert result['name'] == 'second_function'
        assert 'return 42' in result['source']

    def test_python_at_3_extracts_third_function_entry(self, python_file):
        """@3 on Python file extracts 3rd function entry (includes methods)."""
        analyzer = create_analyzer(python_file)
        result = _extract_ordinal_element(analyzer, 3)

        # Structure includes class methods in functions, so @3 = method_one
        assert result is not None
        assert result['name'] == 'method_one'

    def test_python_at_5_extracts_fifth_function(self, python_file):
        """@5 on Python file extracts fifth function (third_function)."""
        analyzer = create_analyzer(python_file)
        result = _extract_ordinal_element(analyzer, 5)

        assert result is not None
        assert result['name'] == 'third_function'
        assert 'return "hello"' in result['source']

    def test_python_invalid_ordinal_returns_none(self, python_file):
        """@99 on Python file with fewer elements returns None."""
        analyzer = create_analyzer(python_file)
        result = _extract_ordinal_element(analyzer, 99)

        assert result is None

    def test_python_ordinal_zero_returns_none(self, python_file):
        """@0 returns None (1-indexed)."""
        analyzer = create_analyzer(python_file)
        result = _extract_ordinal_element(analyzer, 0)

        assert result is None

    def test_markdown_at_1_extracts_first_heading(self, markdown_file):
        """@1 on Markdown file extracts first heading."""
        analyzer = create_analyzer(markdown_file)
        result = _extract_ordinal_element(analyzer, 1)

        assert result is not None
        assert 'First Heading' in result['name']

    def test_markdown_at_2_extracts_second_heading(self, markdown_file):
        """@2 on Markdown file extracts second heading."""
        analyzer = create_analyzer(markdown_file)
        result = _extract_ordinal_element(analyzer, 2)

        assert result is not None
        assert 'Second Heading' in result['name']


class TestTypedOrdinalExtraction:
    """Test type:N explicit ordinal extraction."""

    def test_function_colon_1(self, python_file):
        """function:1 extracts first function."""
        analyzer = create_analyzer(python_file)
        result = _extract_ordinal_element(analyzer, 1, 'function')

        assert result is not None
        assert result['name'] == 'first_function'

    def test_function_colon_2(self, python_file):
        """function:2 extracts second function."""
        analyzer = create_analyzer(python_file)
        result = _extract_ordinal_element(analyzer, 2, 'function')

        assert result is not None
        assert result['name'] == 'second_function'

    def test_class_colon_1(self, python_file):
        """class:1 extracts first class."""
        analyzer = create_analyzer(python_file)
        result = _extract_ordinal_element(analyzer, 1, 'class')

        assert result is not None
        assert result['name'] == 'MyClass'

    def test_class_colon_2(self, python_file):
        """class:2 extracts second class."""
        analyzer = create_analyzer(python_file)
        result = _extract_ordinal_element(analyzer, 2, 'class')

        assert result is not None
        assert result['name'] == 'AnotherClass'

    def test_invalid_type_returns_none(self, python_file):
        """unknown:1 returns None for invalid type."""
        analyzer = create_analyzer(python_file)
        result = _extract_ordinal_element(analyzer, 1, 'unknown_type')

        assert result is None

    def test_section_colon_1_on_markdown(self, markdown_file):
        """section:1 on Markdown extracts first heading."""
        analyzer = create_analyzer(markdown_file)
        result = _extract_ordinal_element(analyzer, 1, 'section')

        assert result is not None
        assert 'First Heading' in result['name']


class TestOrdinalEdgeCases:
    """Test edge cases for ordinal extraction."""

    def test_empty_file(self):
        """Empty file returns None for any ordinal."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('')
            f.flush()
            try:
                analyzer = create_analyzer(f.name)
                result = _extract_ordinal_element(analyzer, 1)
                assert result is None
            finally:
                os.unlink(f.name)

    def test_file_with_only_imports(self):
        """File with only imports has no dominant category functions."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('import os\nimport sys\n')
            f.flush()
            try:
                analyzer = create_analyzer(f.name)
                # No functions, so @1 for dominant (functions) returns None
                result = _extract_ordinal_element(analyzer, 1)
                # Might fall back to imports or return None depending on structure
                # The important thing is it doesn't crash
                assert result is None or 'import' in str(result.get('source', ''))
            finally:
                os.unlink(f.name)


class TestReadLines:
    """Test _read_lines helper function."""

    def test_read_valid_range(self, python_file):
        """Read valid line range."""
        result = _read_lines(python_file, 1, 3)
        assert result is not None
        assert '"""Test module."""' in result

    def test_read_invalid_start(self, python_file):
        """Invalid start line returns None."""
        result = _read_lines(python_file, 0, 5)
        assert result is None

    def test_read_invalid_end(self, python_file):
        """End line beyond file returns None."""
        result = _read_lines(python_file, 1, 10000)
        assert result is None

    def test_read_nonexistent_file(self):
        """Nonexistent file returns None."""
        result = _read_lines('/nonexistent/file.py', 1, 5)
        assert result is None
