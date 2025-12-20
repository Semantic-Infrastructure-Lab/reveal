"""Tests for JSON, ENV, AST, and Reveal rendering adapters."""

import unittest
import sys
import io
from pathlib import Path
from contextlib import redirect_stdout

# Add parent directory to path to import reveal
sys.path.insert(0, str(Path(__file__).parent.parent))

from reveal.rendering.adapters.json_adapter import render_json_result
from reveal.rendering.adapters.ast import render_ast_structure
from reveal.rendering.adapters.env import render_env_structure, render_env_variable
from reveal.rendering.adapters.reveal import render_reveal_structure


def capture_stdout(func, *args, **kwargs):
    """Capture stdout from a function call."""
    output = io.StringIO()
    with redirect_stdout(output):
        func(*args, **kwargs)
    return output.getvalue()


class TestRenderJsonResult(unittest.TestCase):
    """Test JSON adapter result rendering."""

    def test_json_output(self):
        """Should render JSON format when requested."""
        data = {'type': 'json-value', 'value': 'test'}
        output = capture_stdout(render_json_result, data, 'json')
        self.assertIn('"type"', output)
        self.assertIn('json-value', output)

    def test_json_error(self):
        """Should handle JSON errors and exit."""
        data = {
            'type': 'json-error',
            'error': 'Invalid path',
            'valid_queries': ['$.foo', '$.bar']
        }
        with self.assertRaises(SystemExit):
            render_json_result(data, 'text')

    def test_json_value_simple(self):
        """Should render simple JSON values."""
        data = {
            'type': 'json-value',
            'file': '/path/to/file.json',
            'path': '$.name',
            'value': 'John Doe',
            'value_type': 'string'
        }
        output = capture_stdout(render_json_result, data, 'text')
        self.assertIn('File: /path/to/file.json', output)
        self.assertIn('Path: $.name', output)
        self.assertIn('Type: string', output)
        self.assertIn('John Doe', output)

    def test_json_value_complex(self):
        """Should render complex JSON values with indentation."""
        data = {
            'type': 'json-value',
            'file': '/path/to/file.json',
            'path': '$.user',
            'value': {'name': 'John', 'age': 30},
            'value_type': 'object'
        }
        output = capture_stdout(render_json_result, data, 'text')
        self.assertIn('File: /path/to/file.json', output)
        self.assertIn('Path: $.user', output)
        self.assertIn('Type: object', output)
        self.assertIn('"name"', output)
        self.assertIn('John', output)

    def test_json_value_array(self):
        """Should render array values with indentation."""
        data = {
            'type': 'json-value',
            'file': '/path/to/file.json',
            'path': '$.items',
            'value': [1, 2, 3],
            'value_type': 'array'
        }
        output = capture_stdout(render_json_result, data, 'text')
        self.assertIn('Type: array', output)
        self.assertIn('[', output)
        self.assertIn('1', output)

    def test_json_schema(self):
        """Should render JSON schema."""
        data = {
            'type': 'json-schema',
            'file': '/path/to/file.json',
            'path': '$.user',
            'schema': {
                'type': 'object',
                'properties': {
                    'name': {'type': 'string'},
                    'age': {'type': 'number'}
                }
            }
        }
        output = capture_stdout(render_json_result, data, 'text')
        self.assertIn('File: /path/to/file.json', output)
        self.assertIn('Path: $.user', output)
        self.assertIn('Schema:', output)
        self.assertIn('"type"', output)
        self.assertIn('object', output)

    def test_json_flatten(self):
        """Should render flattened JSON."""
        data = {
            'type': 'json-flatten',
            'file': '/path/to/file.json',
            'path': '$.data',
            'lines': [
                '$.data.name = "John"',
                '$.data.age = 30',
                '$.data.city = "NYC"'
            ]
        }
        output = capture_stdout(render_json_result, data, 'text')
        self.assertIn('# File: /path/to/file.json', output)
        self.assertIn('# Path: $.data', output)
        self.assertIn('$.data.name = "John"', output)
        self.assertIn('$.data.age = 30', output)

    def test_json_type(self):
        """Should render type information."""
        data = {
            'type': 'json-type',
            'file': '/path/to/file.json',
            'path': '$.items',
            'value_type': 'array',
            'length': 5
        }
        output = capture_stdout(render_json_result, data, 'text')
        self.assertIn('File: /path/to/file.json', output)
        self.assertIn('Path: $.items', output)
        self.assertIn('Type: array', output)
        self.assertIn('Length: 5', output)

    def test_json_type_without_length(self):
        """Should render type without length when not provided."""
        data = {
            'type': 'json-type',
            'file': '/path/to/file.json',
            'path': '$.value',
            'value_type': 'string'
        }
        output = capture_stdout(render_json_result, data, 'text')
        self.assertIn('Type: string', output)
        self.assertNotIn('Length:', output)

    def test_json_keys_object(self):
        """Should render object keys."""
        data = {
            'type': 'json-keys',
            'file': '/path/to/file.json',
            'path': '$.user',
            'count': 3,
            'keys': ['name', 'age', 'city']
        }
        output = capture_stdout(render_json_result, data, 'text')
        self.assertIn('File: /path/to/file.json', output)
        self.assertIn('Path: $.user', output)
        self.assertIn('Count: 3', output)
        self.assertIn('name', output)
        self.assertIn('age', output)
        self.assertIn('city', output)

    def test_json_keys_array_indices(self):
        """Should render array indices."""
        data = {
            'type': 'json-keys',
            'file': '/path/to/file.json',
            'path': '$.items',
            'count': 10,
            'indices': True
        }
        output = capture_stdout(render_json_result, data, 'text')
        self.assertIn('Count: 10', output)
        self.assertIn('[0..9]', output)

    def test_json_length(self):
        """Should render length information."""
        data = {
            'type': 'json-length',
            'file': '/path/to/file.json',
            'path': '$.items',
            'value_type': 'array',
            'length': 42
        }
        output = capture_stdout(render_json_result, data, 'text')
        self.assertIn('File: /path/to/file.json', output)
        self.assertIn('Path: $.items', output)
        self.assertIn('Type: array', output)
        self.assertIn('Length: 42', output)

    def test_unknown_type_fallback(self):
        """Should fallback to JSON dump for unknown types."""
        data = {
            'type': 'unknown-type',
            'custom_field': 'value'
        }
        output = capture_stdout(render_json_result, data, 'text')
        self.assertIn('"type"', output)
        self.assertIn('unknown-type', output)
        self.assertIn('"custom_field"', output)

    def test_default_path_root(self):
        """Should use (root) as default path."""
        data = {
            'type': 'json-value',
            'value': 'test',
            'value_type': 'string'
        }
        output = capture_stdout(render_json_result, data, 'text')
        self.assertIn('Path: (root)', output)


class TestRenderAstStructure(unittest.TestCase):
    """Test AST query results rendering."""

    def test_json_output(self):
        """Should render JSON format when requested."""
        data = {'query': 'lines>50', 'total_results': 5}
        output = capture_stdout(render_ast_structure, data, 'json')
        self.assertIn('"query"', output)
        self.assertIn('lines>50', output)

    def test_grep_format(self):
        """Should render grep format."""
        data = {
            'results': [
                {'file': '/path/to/file.py', 'line': 10, 'name': 'my_function'},
                {'file': '/path/to/other.py', 'line': 25, 'name': 'other_func'}
            ]
        }
        output = capture_stdout(render_ast_structure, data, 'grep')
        self.assertIn('/path/to/file.py:10:my_function', output)
        self.assertIn('/path/to/other.py:25:other_func', output)

    def test_text_format_no_results(self):
        """Should handle empty results."""
        data = {
            'path': '/path/to/search',
            'query': 'lines>100',
            'total_files': 10,
            'total_results': 0,
            'results': []
        }
        output = capture_stdout(render_ast_structure, data, 'text')
        self.assertIn('AST Query: /path/to/search', output)
        self.assertIn('Filter: lines>100', output)
        self.assertIn('Files scanned: 10', output)
        self.assertIn('Results: 0', output)
        self.assertIn('No matches found', output)

    def test_text_format_with_results(self):
        """Should render text format with results."""
        data = {
            'path': '.',
            'query': 'lines>50',
            'total_files': 5,
            'total_results': 2,
            'results': [
                {
                    'file': '/path/to/file.py',
                    'line': 10,
                    'name': 'big_function',
                    'line_count': 75,
                    'complexity': 15
                },
                {
                    'file': '/path/to/file.py',
                    'line': 100,
                    'name': 'another_function',
                    'line_count': 60
                }
            ]
        }
        output = capture_stdout(render_ast_structure, data, 'text')
        self.assertIn('AST Query: .', output)
        self.assertIn('Filter: lines>50', output)
        self.assertIn('Files scanned: 5', output)
        self.assertIn('Results: 2', output)
        self.assertIn('File: /path/to/file.py', output)
        self.assertIn('big_function [75 lines, complexity: 15]', output)
        self.assertIn('another_function [60 lines]', output)

    def test_text_format_query_none(self):
        """Should handle query='none' correctly."""
        data = {
            'path': '.',
            'query': 'none',
            'total_files': 1,
            'total_results': 1,
            'results': [{'file': 'test.py', 'line': 1, 'name': 'test', 'line_count': 10}]
        }
        output = capture_stdout(render_ast_structure, data, 'text')
        self.assertIn('AST Query: .', output)
        self.assertNotIn('Filter:', output)


class TestRenderEnvStructure(unittest.TestCase):
    """Test environment variables structure rendering."""

    def test_json_output(self):
        """Should render JSON format when requested."""
        data = {'total_count': 10, 'categories': {}}
        output = capture_stdout(render_env_structure, data, 'json')
        self.assertIn('"total_count"', output)
        self.assertIn('10', output)

    def test_text_format(self):
        """Should render text format."""
        data = {
            'total_count': 3,
            'categories': {
                'PATH': [
                    {'name': 'PATH', 'value': '/usr/bin:/bin', 'sensitive': False}
                ],
                'USER': [
                    {'name': 'USER', 'value': 'john', 'sensitive': False},
                    {'name': 'HOME', 'value': '/home/john', 'sensitive': False}
                ]
            }
        }
        output = capture_stdout(render_env_structure, data, 'text')
        self.assertIn('Environment Variables (3)', output)
        self.assertIn('PATH (1):', output)
        self.assertIn('PATH', output)
        self.assertIn('/usr/bin:/bin', output)
        self.assertIn('USER (2):', output)
        self.assertIn('USER', output)
        self.assertIn('john', output)

    def test_text_format_sensitive(self):
        """Should mark sensitive variables."""
        data = {
            'total_count': 1,
            'categories': {
                'SECRETS': [
                    {'name': 'API_KEY', 'value': 'secret123', 'sensitive': True}
                ]
            }
        }
        output = capture_stdout(render_env_structure, data, 'text')
        self.assertIn('API_KEY', output)
        self.assertIn('(sensitive)', output)

    def test_grep_format(self):
        """Should render grep format."""
        data = {
            'total_count': 2,
            'categories': {
                'PATH': [
                    {'name': 'PATH', 'value': '/usr/bin', 'sensitive': False},
                    {'name': 'HOME', 'value': '/home/user', 'sensitive': False}
                ]
            }
        }
        output = capture_stdout(render_env_structure, data, 'grep')
        self.assertIn('env://PATH:/usr/bin', output)
        self.assertIn('env://HOME:/home/user', output)

    def test_skips_empty_categories(self):
        """Should skip empty categories."""
        data = {
            'total_count': 1,
            'categories': {
                'EMPTY': [],
                'PATH': [
                    {'name': 'PATH', 'value': '/usr/bin', 'sensitive': False}
                ]
            }
        }
        output = capture_stdout(render_env_structure, data, 'text')
        self.assertIn('PATH (1):', output)
        self.assertNotIn('EMPTY', output)


class TestRenderEnvVariable(unittest.TestCase):
    """Test single environment variable rendering."""

    def test_json_output(self):
        """Should render JSON format when requested."""
        data = {'name': 'PATH', 'value': '/usr/bin', 'category': 'PATH', 'sensitive': False, 'length': 8}
        output = capture_stdout(render_env_variable, data, 'json')
        self.assertIn('"name"', output)
        self.assertIn('PATH', output)

    def test_grep_format(self):
        """Should render grep format."""
        data = {'name': 'PATH', 'value': '/usr/bin', 'category': 'PATH', 'sensitive': False, 'length': 8}
        output = capture_stdout(render_env_variable, data, 'grep')
        self.assertEqual(output.strip(), 'env://PATH:/usr/bin')

    def test_text_format(self):
        """Should render text format."""
        data = {
            'name': 'PATH',
            'value': '/usr/bin:/bin',
            'category': 'PATH',
            'sensitive': False,
            'length': 13
        }
        output = capture_stdout(render_env_variable, data, 'text')
        self.assertIn('Environment Variable: PATH', output)
        self.assertIn('Category: PATH', output)
        self.assertIn('Value: /usr/bin:/bin', output)
        self.assertIn('Length: 13 characters', output)

    def test_text_format_sensitive(self):
        """Should show sensitive warning."""
        data = {
            'name': 'API_KEY',
            'value': '********',
            'category': 'SECRETS',
            'sensitive': True,
            'length': 32
        }
        output = capture_stdout(render_env_variable, data, 'text')
        self.assertIn('Environment Variable: API_KEY', output)
        self.assertIn('Warning: Sensitive', output)
        self.assertIn('--show-secrets', output)


class TestRenderRevealStructure(unittest.TestCase):
    """Test reveal internal structure rendering."""

    def test_json_output(self):
        """Should render JSON format when requested."""
        data = {'analyzers': [], 'adapters': [], 'rules': []}
        output = capture_stdout(render_reveal_structure, data, 'json')
        self.assertIn('"analyzers"', output)
        self.assertIn('"adapters"', output)
        self.assertIn('"rules"', output)

    def test_text_format_complete(self):
        """Should render complete structure."""
        data = {
            'analyzers': [
                {'name': 'PythonAnalyzer', 'path': 'reveal/analyzers/python.py'},
                {'name': 'JsonAnalyzer', 'path': 'reveal/analyzers/json.py'}
            ],
            'adapters': [
                {'scheme': 'ast', 'class': 'AstAdapter', 'has_help': True},
                {'scheme': 'env', 'class': 'EnvAdapter', 'has_help': False}
            ],
            'rules': [
                {'code': 'C901', 'category': 'complexity'},
                {'code': 'C902', 'category': 'complexity'},
                {'code': 'B001', 'category': 'bugs'}
            ],
            'metadata': {
                'root': '/path/to/reveal',
                'analyzers_count': 2,
                'adapters_count': 2,
                'rules_count': 3
            }
        }
        output = capture_stdout(render_reveal_structure, data, 'text')
        self.assertIn('Reveal Internal Structure', output)
        self.assertIn('Analyzers (2):', output)
        self.assertIn('PythonAnalyzer', output)
        self.assertIn('JsonAnalyzer', output)
        self.assertIn('Adapters (2):', output)
        self.assertIn('ast://', output)
        self.assertIn('env://', output)
        self.assertIn('Rules (3):', output)
        self.assertIn('complexity', output)
        self.assertIn('C901, C902', output)
        self.assertIn('bugs', output)
        self.assertIn('B001', output)
        self.assertIn('Metadata:', output)
        self.assertIn('Root: /path/to/reveal', output)
        self.assertIn('2 analyzers, 2 adapters, 3 rules', output)

    def test_help_marker(self):
        """Should mark adapters with help."""
        data = {
            'analyzers': [],
            'adapters': [
                {'scheme': 'ast', 'class': 'AstAdapter', 'has_help': True},
                {'scheme': 'env', 'class': 'EnvAdapter', 'has_help': False}
            ],
            'rules': [],
            'metadata': {'analyzers_count': 0, 'adapters_count': 2, 'rules_count': 0}
        }
        output = capture_stdout(render_reveal_structure, data, 'text')
        lines = output.split('\n')
        ast_line = [l for l in lines if 'ast://' in l][0]
        env_line = [l for l in lines if 'env://' in l][0]
        self.assertTrue(ast_line.strip().startswith('*'))
        self.assertFalse(env_line.strip().startswith('*'))


if __name__ == '__main__':
    unittest.main()
