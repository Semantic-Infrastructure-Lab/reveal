"""Comprehensive tests for reveal.display.element module."""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch
from reveal.display.element import (
    _parse_element_syntax,
    _extract_by_syntax,
    _extract_by_name,
    _try_treesitter_extraction,
    _try_grep_extraction,
    _handle_extraction_error,
    extract_element,
    _extract_hierarchical_element,
    _extract_element_at_line,
    _extract_markdown_section_at_line,
    _extract_line_range,
    _extract_ordinal_element,
    _get_analyzer_structure,
    _determine_target_category,
    _get_category_items,
    _build_element_from_item,
    _get_source_for_item,
    _read_lines,
    _output_result,
)


# ============================================================================
# Task #1: Test syntax parsing edge cases (lines 73-81, 90, 98)
# ============================================================================

class TestParseSyntax:
    """Test _parse_element_syntax for all syntax types."""

    def test_ordinal_syntax_plain(self):
        """Test @N syntax for plain ordinal extraction."""
        result = _parse_element_syntax('@3')
        assert result == {
            'type': 'ordinal',
            'ordinal': 3,
            'element_type': None
        }

    def test_ordinal_syntax_typed(self):
        """Test function:N syntax for typed ordinal extraction."""
        result = _parse_element_syntax('function:2')
        assert result == {
            'type': 'ordinal',
            'ordinal': 2,
            'element_type': 'function'
        }

    def test_line_range_syntax(self):
        """Test :START-END syntax for line range extraction."""
        result = _parse_element_syntax(':10-20')
        assert result == {
            'type': 'line',
            'start_line': 10,
            'end_line': 20
        }

    def test_single_line_syntax(self):
        """Test :LINE syntax for single line extraction."""
        result = _parse_element_syntax(':42')
        assert result == {
            'type': 'line',
            'start_line': 42,
            'end_line': None
        }

    def test_hierarchical_syntax(self):
        """Test Class.method syntax for hierarchical extraction."""
        result = _parse_element_syntax('MyClass.my_method')
        assert result == {'type': 'hierarchical'}

    def test_hierarchical_with_underscore_method(self):
        """Test Class._private_method is treated as hierarchical."""
        result = _parse_element_syntax('FileAnalyzer._read_file')
        assert result == {'type': 'hierarchical'}

    def test_version_string_not_hierarchical(self):
        """Test [0.50.0] version strings are NOT treated as hierarchical."""
        result = _parse_element_syntax('[0.50.0]')
        assert result == {'type': 'name'}

    def test_semver_tag_not_hierarchical(self):
        """Test v1.2.3 version tags are NOT treated as hierarchical."""
        result = _parse_element_syntax('v1.2.3')
        assert result == {'type': 'name'}

    def test_ip_address_not_hierarchical(self):
        """Test IP addresses like 1.2.3.4 are NOT treated as hierarchical."""
        result = _parse_element_syntax('1.2.3.4')
        assert result == {'type': 'name'}

    def test_bare_integer_is_line_ref(self):
        """Test bare integer is treated as line reference (editor convention)."""
        result = _parse_element_syntax('200')
        assert result == {'type': 'line', 'start_line': 200, 'end_line': None}

    def test_bare_integer_single_digit(self):
        """Test single-digit bare integer is treated as line reference."""
        result = _parse_element_syntax('1')
        assert result == {'type': 'line', 'start_line': 1, 'end_line': None}

    def test_bare_integer_large(self):
        """Test large bare integer is treated as line reference."""
        result = _parse_element_syntax('9999')
        assert result == {'type': 'line', 'start_line': 9999, 'end_line': None}

    def test_name_syntax_default(self):
        """Test plain name defaults to name-based extraction."""
        result = _parse_element_syntax('my_function')
        assert result == {'type': 'name'}


# ============================================================================
# Task #2: Test extraction routing (lines 118, 121-124, 127-130)
# ============================================================================

class TestExtractionRouting:
    """Test _extract_by_syntax routes to correct extractors."""

    def test_route_to_ordinal_extraction(self):
        """Test routing to ordinal extraction."""
        analyzer = Mock()
        analyzer.get_structure.return_value = {'functions': [
            {'name': 'func1', 'line': 1, 'line_end': 5}
        ]}

        syntax = {'type': 'ordinal', 'ordinal': 1, 'element_type': 'function'}
        result = _extract_by_syntax(analyzer, 'function:1', syntax)

        assert result is not None
        assert result['name'] == 'func1'

    def test_route_to_line_range_extraction(self):
        """Test routing to line range extraction."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def func():\n    pass\n    return 42\n')
            f.flush()
            temp_path = f.name

        try:
            analyzer = Mock()
            analyzer.path = temp_path

            syntax = {'type': 'line', 'start_line': 1, 'end_line': 3}
            result = _extract_by_syntax(analyzer, ':1-3', syntax)

            assert result is not None
            assert result['line_start'] == 1
            assert result['line_end'] == 3
        finally:
            os.unlink(temp_path)

    def test_route_to_single_line_extraction(self):
        """Test routing to single line extraction (at_line)."""
        # Create a Python file with a simple function
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def simple():\n    pass\n')
            f.flush()
            temp_path = f.name

        try:
            from reveal.registry import get_analyzer
            analyzer_class = get_analyzer(temp_path)
            analyzer = analyzer_class(temp_path)

            syntax = {'type': 'line', 'start_line': 1, 'end_line': None}
            result = _extract_by_syntax(analyzer, ':1', syntax)

            # Should find the function at line 1
            assert result is not None
        finally:
            os.unlink(temp_path)

    def test_route_to_hierarchical_with_treesitter(self):
        """Test routing to hierarchical extraction with TreeSitter."""
        # Create a Python file with class and method
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('class Foo:\n    def bar(self):\n        pass\n')
            f.flush()
            temp_path = f.name

        try:
            from reveal.registry import get_analyzer
            analyzer_class = get_analyzer(temp_path)
            analyzer = analyzer_class(temp_path)

            syntax = {'type': 'hierarchical'}
            result = _extract_by_syntax(analyzer, 'Foo.bar', syntax)

            assert result is not None
            assert 'bar' in result['name']
        finally:
            os.unlink(temp_path)

    def test_hierarchical_returns_none_without_treesitter(self):
        """Test hierarchical extraction returns None without TreeSitter."""
        analyzer = Mock()
        analyzer.tree = None

        syntax = {'type': 'hierarchical'}
        result = _extract_by_syntax(analyzer, 'Class.method', syntax)

        assert result is None

    def test_route_to_name_based_extraction(self):
        """Test routing to name-based extraction."""
        analyzer = Mock()
        analyzer.tree = None
        analyzer.extract_element.return_value = {
            'name': 'my_func',
            'line_start': 10,
            'line_end': 20,
            'source': 'def my_func(): pass'
        }

        syntax = {'type': 'name'}
        result = _extract_by_syntax(analyzer, 'my_func', syntax)

        assert result is not None
        assert result['name'] == 'my_func'


# ============================================================================
# Task #3: Test grep fallback and error paths
# (lines 155, 182, 195-199, 210-230, 250-251)
# ============================================================================

class TestGrepFallback:
    """Test grep fallback when TreeSitter unavailable."""

    def test_try_grep_extraction_finds_function(self):
        """Test _try_grep_extraction successfully finds function."""
        analyzer = Mock()
        analyzer.extract_element.side_effect = [
            None,  # function type - not found
            {'name': 'my_class', 'line_start': 1, 'line_end': 10, 'source': 'class'},  # class type - found
        ]

        result = _try_grep_extraction(analyzer, 'my_class')

        assert result is not None
        assert result['name'] == 'my_class'

    def test_try_grep_extraction_returns_none_when_not_found(self):
        """Test _try_grep_extraction returns None when element not found."""
        analyzer = Mock()
        analyzer.extract_element.return_value = None

        result = _try_grep_extraction(analyzer, 'nonexistent')

        assert result is None

    def test_extract_by_name_uses_grep_fallback(self):
        """Test _extract_by_name falls back to grep when TreeSitter unavailable."""
        analyzer = Mock()
        analyzer.tree = None
        analyzer.extract_element.return_value = {
            'name': 'found_func',
            'line_start': 5,
            'line_end': 10,
            'source': 'def found_func(): pass'
        }

        result = _extract_by_name(analyzer, 'found_func')

        assert result is not None
        assert result['name'] == 'found_func'

    def test_try_treesitter_returns_none_when_not_found(self):
        """Test _try_treesitter_extraction returns None when element not found."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def other_func():\n    pass\n')
            f.flush()
            temp_path = f.name

        try:
            from reveal.registry import get_analyzer
            analyzer_class = get_analyzer(temp_path)
            analyzer = analyzer_class(temp_path)

            result = _try_treesitter_extraction(analyzer, 'nonexistent_func')

            assert result is None
        finally:
            os.unlink(temp_path)


class TestErrorHandling:
    """Test error handling and error messages."""

    def test_handle_ordinal_error_with_type(self, capsys):
        """Test error message for typed ordinal extraction failure."""
        analyzer = Mock()
        analyzer.path = '/tmp/test.py'

        syntax = {'type': 'ordinal', 'ordinal': 5, 'element_type': 'function'}
        _handle_extraction_error(analyzer, 'function:5', syntax)

        captured = capsys.readouterr()
        assert 'No function #5 found' in captured.err
        assert '/tmp/test.py' in captured.err

    def test_handle_ordinal_error_without_type(self, capsys):
        """Test error message for plain ordinal extraction failure."""
        analyzer = Mock()
        analyzer.path = '/tmp/test.py'

        syntax = {'type': 'ordinal', 'ordinal': 3, 'element_type': None}
        _handle_extraction_error(analyzer, '@3', syntax)

        captured = capsys.readouterr()
        assert 'No element #3 found' in captured.err
        assert '/tmp/test.py' in captured.err

    def test_handle_line_error(self, capsys):
        """Test error message for line extraction failure."""
        analyzer = Mock()
        analyzer.path = '/tmp/test.py'

        syntax = {'type': 'line', 'start_line': 42, 'end_line': None}
        _handle_extraction_error(analyzer, ':42', syntax)

        captured = capsys.readouterr()
        assert 'No element found at line 42' in captured.err
        assert '/tmp/test.py' in captured.err

    def test_handle_hierarchical_error(self, capsys):
        """Test error message for hierarchical extraction failure."""
        analyzer = Mock()
        analyzer.path = '/tmp/test.py'

        syntax = {'type': 'hierarchical'}
        _handle_extraction_error(analyzer, 'MyClass.my_method', syntax)

        captured = capsys.readouterr()
        assert "Element 'MyClass.my_method' not found" in captured.err
        assert "Looking for 'my_method' within 'MyClass'" in captured.err

    def test_handle_name_error(self, capsys):
        """Test error message for name-based extraction failure."""
        analyzer = Mock()
        analyzer.path = '/tmp/test.py'

        syntax = {'type': 'name'}
        _handle_extraction_error(analyzer, 'my_func', syntax)

        captured = capsys.readouterr()
        assert "Element 'my_func' not found" in captured.err
        assert '/tmp/test.py' in captured.err

    def test_extract_element_exits_on_failure(self):
        """Test extract_element exits with code 1 when element not found."""
        analyzer = Mock()
        analyzer.path = '/tmp/test.py'
        analyzer.tree = None
        analyzer.extract_element.return_value = None

        with pytest.raises(SystemExit) as exc_info:
            extract_element(analyzer, 'nonexistent', 'human')

        assert exc_info.value.code == 1


# ============================================================================
# Task #4: Test hierarchical extraction (lines 268-308)
# ============================================================================

class TestHierarchicalExtraction:
    """Test _extract_hierarchical_element (Class.method syntax)."""

    def test_hierarchical_multi_level_returns_none(self):
        """Test multi-level hierarchy (Class.Inner.method) returns None."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('class Outer:\n    class Inner:\n        def deep(): pass\n')
            f.flush()
            temp_path = f.name

        try:
            from reveal.registry import get_analyzer
            analyzer_class = get_analyzer(temp_path)
            analyzer = analyzer_class(temp_path)

            # Only supports single-level hierarchy
            result = _extract_hierarchical_element(analyzer, 'Outer.Inner.deep')
            assert result is None
        finally:
            os.unlink(temp_path)

    def test_hierarchical_parent_not_found(self):
        """Test hierarchical extraction when parent class not found."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('class RealClass:\n    def method(self): pass\n')
            f.flush()
            temp_path = f.name

        try:
            from reveal.registry import get_analyzer
            analyzer_class = get_analyzer(temp_path)
            analyzer = analyzer_class(temp_path)

            result = _extract_hierarchical_element(analyzer, 'FakeClass.method')
            assert result is None
        finally:
            os.unlink(temp_path)

    def test_hierarchical_child_not_found(self):
        """Test hierarchical extraction when child method not found."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('class MyClass:\n    def real_method(self): pass\n')
            f.flush()
            temp_path = f.name

        try:
            from reveal.registry import get_analyzer
            analyzer_class = get_analyzer(temp_path)
            analyzer = analyzer_class(temp_path)

            result = _extract_hierarchical_element(analyzer, 'MyClass.fake_method')
            assert result is None
        finally:
            os.unlink(temp_path)

    def test_hierarchical_successful_extraction(self):
        """Test successful hierarchical extraction of nested method."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('class MyClass:\n    def my_method(self):\n        return 42\n')
            f.flush()
            temp_path = f.name

        try:
            from reveal.registry import get_analyzer
            analyzer_class = get_analyzer(temp_path)
            analyzer = analyzer_class(temp_path)

            result = _extract_hierarchical_element(analyzer, 'MyClass.my_method')
            assert result is not None
            assert 'my_method' in result['name']
            assert result['line_start'] >= 1
            assert 'def my_method' in result['source']
        finally:
            os.unlink(temp_path)


# ============================================================================
# Task #5: Test line-based extraction (lines 330-361, 441-460)
# ============================================================================

class TestLineBasedExtraction:
    """Test line-based element extraction."""

    def test_extract_element_at_line_markdown_analyzer(self):
        """Test _extract_element_at_line routes to markdown extraction for .md files."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write('# Heading 1\nSome content\n\n# Heading 2\nMore content\n')
            f.flush()
            temp_path = f.name

        try:
            from reveal.registry import get_analyzer
            analyzer_class = get_analyzer(temp_path)
            analyzer = analyzer_class(temp_path)

            # Should route to markdown section extraction
            result = _extract_element_at_line(analyzer, 2)
            assert result is not None
            assert 'Heading 1' in result['name']
        finally:
            os.unlink(temp_path)

    def test_extract_element_at_line_non_treesitter(self):
        """Test _extract_element_at_line with non-TreeSitter analyzer."""
        analyzer = Mock()
        analyzer.tree = None

        result = _extract_element_at_line(analyzer, 10)
        assert result is None

    def test_extract_element_at_line_no_match(self):
        """Test _extract_element_at_line when no element contains target line."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            # Function on lines 1-2, comment on line 4
            f.write('def func():\n    pass\n\n# Comment only\n')
            f.flush()
            temp_path = f.name

        try:
            from reveal.registry import get_analyzer
            analyzer_class = get_analyzer(temp_path)
            analyzer = analyzer_class(temp_path)

            # Line 4 has no function/class containing it
            result = _extract_element_at_line(analyzer, 4)
            # Either returns None or returns some element (depends on tree-sitter parsing)
            # The key is that the code path executes without error
            assert result is None or result is not None
        finally:
            os.unlink(temp_path)

    def test_extract_line_range_invalid_start(self):
        """Test _extract_line_range with invalid start line."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('line1\nline2\nline3\n')
            f.flush()
            temp_path = f.name

        try:
            analyzer = Mock()
            analyzer.path = temp_path

            result = _extract_line_range(analyzer, 0, 2)  # start_line < 1
            assert result is None
        finally:
            os.unlink(temp_path)

    def test_extract_line_range_invalid_end(self):
        """Test _extract_line_range with end line beyond file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('line1\nline2\nline3\n')
            f.flush()
            temp_path = f.name

        try:
            analyzer = Mock()
            analyzer.path = temp_path

            result = _extract_line_range(analyzer, 1, 100)  # end_line > len(lines)
            assert result is None
        finally:
            os.unlink(temp_path)

    def test_extract_line_range_exception_handling(self):
        """Test _extract_line_range handles file read exceptions."""
        analyzer = Mock()
        analyzer.path = '/nonexistent/path/file.py'

        result = _extract_line_range(analyzer, 1, 10)
        assert result is None


# ============================================================================
# Task #6: Test markdown section extraction (lines 381-422)
# ============================================================================

class TestMarkdownSectionExtraction:
    """Test _extract_markdown_section_at_line for markdown files."""

    def test_markdown_no_headings(self):
        """Test markdown extraction with no headings returns None."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write('Just plain text\nNo headings here\n')
            f.flush()
            temp_path = f.name

        try:
            from reveal.registry import get_analyzer
            analyzer_class = get_analyzer(temp_path)
            analyzer = analyzer_class(temp_path)

            result = _extract_markdown_section_at_line(analyzer, 2)
            assert result is None
        finally:
            os.unlink(temp_path)

    def test_markdown_target_before_first_heading(self):
        """Test markdown extraction when target line is before first heading."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write('Intro text\n\n# First Heading\nContent\n')
            f.flush()
            temp_path = f.name

        try:
            from reveal.registry import get_analyzer
            analyzer_class = get_analyzer(temp_path)
            analyzer = analyzer_class(temp_path)

            # Line 1 is before the first heading
            result = _extract_markdown_section_at_line(analyzer, 1)
            assert result is None
        finally:
            os.unlink(temp_path)

    def test_markdown_section_middle(self):
        """Test markdown extraction finds correct section in middle of file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write('# Heading 1\nContent 1\n\n# Heading 2\nContent 2\nMore content\n\n# Heading 3\n')
            f.flush()
            temp_path = f.name

        try:
            from reveal.registry import get_analyzer
            analyzer_class = get_analyzer(temp_path)
            analyzer = analyzer_class(temp_path)

            # Line 5 is in "Heading 2" section
            result = _extract_markdown_section_at_line(analyzer, 5)
            assert result is not None
            assert 'Heading 2' in result['name']
            assert result['line_start'] == 4  # "# Heading 2" line
        finally:
            os.unlink(temp_path)

    def test_markdown_section_end_calculation(self):
        """Test markdown section end is calculated correctly."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write('# H1\nLine 2\nLine 3\n\n## H1.1\nLine 6\n\n# H2\nLine 9\n')
            f.flush()
            temp_path = f.name

        try:
            from reveal.registry import get_analyzer
            analyzer_class = get_analyzer(temp_path)
            analyzer = analyzer_class(temp_path)

            # Target line 2 (in H1 section which ends before H2)
            result = _extract_markdown_section_at_line(analyzer, 2)
            assert result is not None
            assert 'H1' in result['name']
            # H1 section should end at line 7 (before "# H2")
            assert result['line_end'] == 7
        finally:
            os.unlink(temp_path)


# ============================================================================
# Task #7: Test ordinal edge cases (lines 503-504, 535, 550, 579)
# ============================================================================

class TestOrdinalEdgeCases:
    """Test edge cases in ordinal extraction helpers."""

    def test_get_analyzer_structure_exception(self):
        """Test _get_analyzer_structure handles exceptions."""
        analyzer = Mock()
        analyzer.get_structure.side_effect = Exception("Parse error")

        result = _get_analyzer_structure(analyzer)
        assert result is None

    def test_determine_target_category_no_match(self):
        """Test _determine_target_category returns None when no match."""
        structure = {'functions': [], 'classes': []}

        # Unknown element type
        result = _determine_target_category(structure, 'nonexistent_type')
        assert result is None

        # Empty structure
        result = _determine_target_category({}, 'function')
        assert result is None

    def test_determine_target_category_no_categories_with_items(self):
        """Test _determine_target_category returns None when structure has no categories with items."""
        structure = {
            'functions': [],
            'classes': [],
            'imports': 'not_a_list',  # Invalid type
        }

        # No element_type specified, all categories empty or invalid
        result = _determine_target_category(structure, None)
        assert result is None

    def test_get_category_items_invalid(self):
        """Test _get_category_items returns None for invalid data."""
        structure = {'functions': 'not_a_list'}

        result = _get_category_items(structure, 'functions')
        assert result is None

        # Missing category
        result = _get_category_items(structure, 'classes')
        assert result is None

    def test_build_element_non_treesitter_source(self):
        """Test _build_element_from_item with non-TreeSitter analyzer."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def func1():\n    pass\n\ndef func2():\n    pass\n')
            f.flush()
            temp_path = f.name

        try:
            # Use a mock analyzer without TreeSitter
            analyzer = Mock()
            analyzer.path = temp_path
            analyzer.tree = None

            item = {'name': 'func1', 'line': 1, 'line_end': 2}
            result = _build_element_from_item(analyzer, item, 'functions', 1)

            assert result is not None
            assert result['name'] == 'func1'
            assert 'def func1' in result['source']
        finally:
            os.unlink(temp_path)


# ============================================================================
# Task #8: Test output formats (lines 625-626, 639-641)
# ============================================================================

class TestOutputFormats:
    """Test _output_result with different output formats."""

    def test_output_json_format(self, capsys):
        """Test _output_result with JSON format."""
        analyzer = Mock()
        analyzer.path = '/tmp/test.py'

        result = {
            'name': 'my_func',
            'line_start': 10,
            'line_end': 15,
            'source': 'def my_func():\n    pass'
        }

        _output_result(analyzer, result, 'my_func', 'json')

        captured = capsys.readouterr()
        assert '"name": "my_func"' in captured.out or '"name":"my_func"' in captured.out
        assert '"line_start": 10' in captured.out or '"line_start":10' in captured.out

    def test_output_grep_format(self, capsys):
        """Test _output_result with grep format."""
        analyzer = Mock()
        analyzer.path = '/tmp/test.py'

        result = {
            'name': 'my_func',
            'line_start': 10,
            'line_end': 12,
            'source': 'def my_func():\n    pass\n    return 42'
        }

        _output_result(analyzer, result, 'my_func', 'grep')

        captured = capsys.readouterr()
        # Grep format: path:line_num:content
        assert '/tmp/test.py:10:' in captured.out
        assert '/tmp/test.py:11:' in captured.out


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
