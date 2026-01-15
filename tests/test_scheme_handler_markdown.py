"""
Tests for reveal/cli/scheme_handlers/markdown.py

Tests the Markdown scheme handler functionality including:
- URI parsing (path and query extraction)
- Adapter instantiation with correct parameters
- Element retrieval (specific file frontmatter)
- Structure retrieval (all files matching query)
- Error handling for missing files
- Warning for unsupported --check flag
"""

import unittest
import sys
from io import StringIO
from argparse import Namespace
from unittest.mock import Mock, patch, call

from reveal.cli.scheme_handlers.markdown import handle_markdown


class TestHandleMarkdownURIParsing(unittest.TestCase):
    """Test URI parsing in handle_markdown()."""

    @patch('reveal.rendering.adapters.markdown_query.render_markdown_query')
    def test_empty_resource_uses_current_dir(self, mock_render):
        """Test empty resource defaults to current directory."""
        # Mock adapter class
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter.get_structure.return_value = {'files': []}
        mock_adapter_class.return_value = mock_adapter

        # Create args
        args = Namespace(format='text', check=False)

        # Call handler with empty resource
        handle_markdown(mock_adapter_class, '', None, args)

        # Verify adapter created with '.' as base_path
        mock_adapter_class.assert_called_once_with(base_path='.', query=None)

    @patch('reveal.rendering.adapters.markdown_query.render_markdown_query')
    def test_path_only_resource(self, mock_render):
        """Test resource with path only (no query)."""
        # Mock adapter class
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter.get_structure.return_value = {'files': []}
        mock_adapter_class.return_value = mock_adapter

        # Create args
        args = Namespace(format='text', check=False)

        # Call handler with path only
        handle_markdown(mock_adapter_class, 'docs/', None, args)

        # Verify adapter created with correct path
        mock_adapter_class.assert_called_once_with(base_path='docs', query=None)

    @patch('reveal.rendering.adapters.markdown_query.render_markdown_query')
    def test_query_only_resource(self, mock_render):
        """Test resource with query only (no path)."""
        # Mock adapter class
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter.get_structure.return_value = {'files': []}
        mock_adapter_class.return_value = mock_adapter

        # Create args
        args = Namespace(format='text', check=False)

        # Call handler with query only
        handle_markdown(mock_adapter_class, '?topics=reveal', None, args)

        # Verify adapter created with current dir and query
        mock_adapter_class.assert_called_once_with(base_path='.', query='topics=reveal')

    @patch('reveal.rendering.adapters.markdown_query.render_markdown_query')
    def test_path_and_query_resource(self, mock_render):
        """Test resource with both path and query."""
        # Mock adapter class
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter.get_structure.return_value = {'files': []}
        mock_adapter_class.return_value = mock_adapter

        # Create args
        args = Namespace(format='text', check=False)

        # Call handler with path and query
        handle_markdown(mock_adapter_class, 'docs/?topics=testing', None, args)

        # Verify adapter created with correct path and query
        mock_adapter_class.assert_called_once_with(base_path='docs', query='topics=testing')

    @patch('reveal.rendering.adapters.markdown_query.render_markdown_query')
    def test_path_trailing_slash_stripped(self, mock_render):
        """Test that trailing slashes are stripped from path."""
        # Mock adapter class
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter.get_structure.return_value = {'files': []}
        mock_adapter_class.return_value = mock_adapter

        # Create args
        args = Namespace(format='text', check=False)

        # Call handler with path having trailing slash
        handle_markdown(mock_adapter_class, 'docs/guides/', None, args)

        # Verify trailing slash removed
        mock_adapter_class.assert_called_once_with(base_path='docs/guides', query=None)


class TestHandleMarkdownStructure(unittest.TestCase):
    """Test handle_markdown() when querying structure (no element)."""

    @patch('reveal.rendering.adapters.markdown_query.render_markdown_query')
    def test_get_structure_called_without_element(self, mock_render):
        """Test that get_structure() is called when no element provided."""
        # Mock adapter class
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        result = {'files': [{'path': 'test.md', 'frontmatter': {}}]}
        mock_adapter.get_structure.return_value = result
        mock_adapter_class.return_value = mock_adapter

        # Create args
        args = Namespace(format='text', check=False)

        # Call handler without element
        handle_markdown(mock_adapter_class, '', None, args)

        # Verify
        mock_adapter.get_structure.assert_called_once()
        mock_render.assert_called_once_with(result, 'text')

    @patch('reveal.rendering.adapters.markdown_query.render_markdown_query')
    def test_render_with_json_format(self, mock_render):
        """Test rendering structure with JSON format."""
        # Mock adapter class
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        result = {'files': []}
        mock_adapter.get_structure.return_value = result
        mock_adapter_class.return_value = mock_adapter

        # Create args with JSON format
        args = Namespace(format='json', check=False)

        # Call handler
        handle_markdown(mock_adapter_class, '', None, args)

        # Verify JSON format passed to renderer
        mock_render.assert_called_once_with(result, 'json')


class TestHandleMarkdownElement(unittest.TestCase):
    """Test handle_markdown() when retrieving specific element."""

    @patch('reveal.rendering.adapters.markdown_query.render_markdown_query')
    def test_get_element_called_with_element(self, mock_render):
        """Test that get_element() is called when element provided."""
        # Mock adapter class
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        result = {'path': 'test.md', 'frontmatter': {'title': 'Test'}}
        mock_adapter.get_element.return_value = result
        mock_adapter_class.return_value = mock_adapter

        # Create args
        args = Namespace(format='text', check=False)

        # Call handler with element
        handle_markdown(mock_adapter_class, '', 'test.md', args)

        # Verify
        mock_adapter.get_element.assert_called_once_with('test.md')
        mock_render.assert_called_once_with(result, 'text', single_file=True)

    @patch('reveal.rendering.adapters.markdown_query.render_markdown_query')
    def test_get_element_with_json_format(self, mock_render):
        """Test retrieving element with JSON format."""
        # Mock adapter class
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        result = {'path': 'test.md', 'frontmatter': {}}
        mock_adapter.get_element.return_value = result
        mock_adapter_class.return_value = mock_adapter

        # Create args with JSON format
        args = Namespace(format='json', check=False)

        # Call handler with element
        handle_markdown(mock_adapter_class, 'docs/', 'readme.md', args)

        # Verify
        mock_render.assert_called_once_with(result, 'json', single_file=True)


class TestHandleMarkdownErrors(unittest.TestCase):
    """Test handle_markdown() error handling."""

    @patch('reveal.rendering.adapters.markdown_query.render_markdown_query')
    def test_element_not_found_exits_with_error(self, mock_render):
        """Test that missing element causes sys.exit(1)."""
        # Mock adapter class
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter.get_element.return_value = None  # File not found
        mock_adapter_class.return_value = mock_adapter

        # Create args
        args = Namespace(format='text', check=False)

        # Capture stderr
        output = StringIO()
        sys.stderr = output
        try:
            # Call handler and expect sys.exit
            with self.assertRaises(SystemExit) as cm:
                handle_markdown(mock_adapter_class, '', 'missing.md', args)

            # Verify exit code and error message
            self.assertEqual(cm.exception.code, 1)
            stderr_output = output.getvalue()
            self.assertIn('Error:', stderr_output)
            self.assertIn('missing.md', stderr_output)
            self.assertIn('not found', stderr_output)

            # Verify render was NOT called
            mock_render.assert_not_called()
        finally:
            sys.stderr = sys.__stderr__


class TestHandleMarkdownCheckWarning(unittest.TestCase):
    """Test handle_markdown() --check flag warning."""

    @patch('reveal.rendering.adapters.markdown_query.render_markdown_query')
    def test_check_flag_prints_warning(self, mock_render):
        """Test that --check flag prints warning to stderr."""
        # Mock adapter class
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter.get_structure.return_value = {'files': []}
        mock_adapter_class.return_value = mock_adapter

        # Create args WITH check=True
        args = Namespace(format='text', check=True)

        # Capture stderr
        output = StringIO()
        sys.stderr = output
        try:
            # Call handler
            handle_markdown(mock_adapter_class, '', None, args)

            # Verify warning printed
            stderr_output = output.getvalue()
            self.assertIn('Warning:', stderr_output)
            self.assertIn('--check', stderr_output)
            self.assertIn('not supported', stderr_output)
            self.assertIn('markdown://', stderr_output)
        finally:
            sys.stderr = sys.__stderr__

    @patch('reveal.rendering.adapters.markdown_query.render_markdown_query')
    def test_no_warning_without_check_flag(self, mock_render):
        """Test that no warning is printed without --check flag."""
        # Mock adapter class
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter.get_structure.return_value = {'files': []}
        mock_adapter_class.return_value = mock_adapter

        # Create args WITHOUT check flag
        args = Namespace(format='text', check=False)

        # Capture stderr
        output = StringIO()
        sys.stderr = output
        try:
            # Call handler
            handle_markdown(mock_adapter_class, '', None, args)

            # Verify no warning printed
            stderr_output = output.getvalue()
            self.assertEqual(stderr_output, '')
        finally:
            sys.stderr = sys.__stderr__


if __name__ == '__main__':
    unittest.main()
