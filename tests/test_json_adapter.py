"""Tests for JSON adapter (json://)."""

import unittest
import json
import tempfile
import os
from pathlib import Path

from reveal.adapters.json_adapter import JsonAdapter


class TestJsonAdapter(unittest.TestCase):
    """Test JSON navigation adapter."""

    @classmethod
    def setUpClass(cls):
        """Create test JSON files."""
        cls.temp_dir = tempfile.mkdtemp()

        # Simple JSON file
        cls.simple_json = Path(cls.temp_dir) / 'simple.json'
        cls.simple_json.write_text(json.dumps({
            'name': 'test',
            'version': '1.0.0',
            'count': 42,
            'enabled': True,
            'tags': ['a', 'b', 'c']
        }))

        # Nested JSON file
        cls.nested_json = Path(cls.temp_dir) / 'nested.json'
        cls.nested_json.write_text(json.dumps({
            'users': [
                {'name': 'alice', 'age': 30},
                {'name': 'bob', 'age': 25},
                {'name': 'charlie', 'age': 35}
            ],
            'config': {
                'debug': True,
                'settings': {
                    'theme': 'dark',
                    'timeout': 30
                }
            }
        }))

    @classmethod
    def tearDownClass(cls):
        """Clean up test files."""
        import shutil
        shutil.rmtree(cls.temp_dir)

    def test_basic_load(self):
        """Should load JSON file and return structure."""
        adapter = JsonAdapter(str(self.simple_json), None)
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'json-value')
        self.assertEqual(result['path'], '(root)')
        self.assertEqual(result['value']['name'], 'test')

    def test_path_navigation_simple(self):
        """Should navigate to simple key."""
        adapter = JsonAdapter(f'{self.simple_json}/name', None)
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'json-value')
        self.assertEqual(result['value'], 'test')
        self.assertEqual(result['value_type'], 'str')

    def test_path_navigation_nested(self):
        """Should navigate to nested keys."""
        adapter = JsonAdapter(f'{self.nested_json}/config/settings/theme', None)
        result = adapter.get_structure()

        self.assertEqual(result['value'], 'dark')

    def test_path_navigation_array_index(self):
        """Should access array by index."""
        adapter = JsonAdapter(f'{self.nested_json}/users/0', None)
        result = adapter.get_structure()

        self.assertEqual(result['value']['name'], 'alice')

    def test_path_navigation_array_negative_index(self):
        """Should support negative array indices."""
        adapter = JsonAdapter(f'{self.nested_json}/users/-1', None)
        result = adapter.get_structure()

        self.assertEqual(result['value']['name'], 'charlie')

    def test_path_navigation_bracket_index(self):
        """Should support [n] bracket notation."""
        adapter = JsonAdapter(f'{self.nested_json}/users[1]', None)
        result = adapter.get_structure()

        self.assertEqual(result['value']['name'], 'bob')

    def test_array_slice(self):
        """Should support array slicing."""
        adapter = JsonAdapter(f'{self.nested_json}/users[0:2]', None)
        result = adapter.get_structure()

        self.assertEqual(len(result['value']), 2)
        self.assertEqual(result['value'][0]['name'], 'alice')
        self.assertEqual(result['value'][1]['name'], 'bob')

    def test_query_schema(self):
        """Should return schema for ?schema query."""
        adapter = JsonAdapter(str(self.simple_json), 'schema')
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'json-schema')
        self.assertIn('schema', result)
        self.assertEqual(result['schema']['name'], 'str')
        self.assertEqual(result['schema']['count'], 'int')
        self.assertEqual(result['schema']['enabled'], 'bool')

    def test_query_flatten(self):
        """Should return flattened output for ?flatten query."""
        adapter = JsonAdapter(f'{self.simple_json}/tags', 'flatten')
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'json-flatten')
        self.assertIn('lines', result)
        # Should have lines like: json[0] = "a"
        self.assertTrue(any('json[0]' in line for line in result['lines']))

    def test_query_gron_alias(self):
        """Should accept ?gron as alias for ?flatten."""
        adapter = JsonAdapter(f'{self.simple_json}/tags', 'gron')
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'json-flatten')  # Same type as flatten

    def test_query_type(self):
        """Should return type info for ?type query."""
        adapter = JsonAdapter(f'{self.nested_json}/users', 'type')
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'json-type')
        self.assertIn('Array', result['value_type'])
        self.assertEqual(result['length'], 3)

    def test_query_keys_object(self):
        """Should return keys for object."""
        adapter = JsonAdapter(f'{self.simple_json}', 'keys')
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'json-keys')
        self.assertIn('keys', result)
        self.assertIn('name', result['keys'])
        self.assertIn('version', result['keys'])

    def test_query_keys_array(self):
        """Should return indices for array."""
        adapter = JsonAdapter(f'{self.nested_json}/users', 'keys')
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'json-keys')
        self.assertIn('indices', result)
        self.assertEqual(result['count'], 3)

    def test_query_length(self):
        """Should return length for ?length query."""
        adapter = JsonAdapter(f'{self.nested_json}/users', 'length')
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'json-length')
        self.assertEqual(result['length'], 3)

    def test_query_invalid(self):
        """Should return error for invalid query."""
        adapter = JsonAdapter(str(self.simple_json), 'invalid')
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'json-error')
        self.assertIn('valid_queries', result)

    def test_path_not_found(self):
        """Should return error for non-existent path."""
        adapter = JsonAdapter(f'{self.simple_json}/nonexistent', None)
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'json-error')
        self.assertIn('not found', result['error'].lower())

    def test_file_not_found(self):
        """Should raise error for non-existent file."""
        with self.assertRaises(FileNotFoundError):
            JsonAdapter('/nonexistent/file.json', None)

    def test_get_help(self):
        """Should provide comprehensive help documentation."""
        help_data = JsonAdapter.get_help()

        self.assertIsInstance(help_data, dict)
        self.assertEqual(help_data['name'], 'json')
        self.assertIn('description', help_data)
        self.assertIn('syntax', help_data)
        self.assertIn('queries', help_data)
        self.assertIn('examples', help_data)

        # Check queries
        self.assertIn('schema', help_data['queries'])
        self.assertIn('flatten', help_data['queries'])
        self.assertIn('gron', help_data['queries'])

    def test_get_metadata(self):
        """Should return file metadata."""
        adapter = JsonAdapter(str(self.simple_json), None)
        metadata = adapter.get_metadata()

        self.assertTrue(metadata['exists'])
        self.assertGreater(metadata['size'], 0)
        self.assertIn('Object', metadata['root_type'])

    def test_type_inference_array(self):
        """Should correctly infer array element types."""
        adapter = JsonAdapter(f'{self.simple_json}/tags', 'type')
        result = adapter.get_structure()

        self.assertIn('Array', result['value_type'])
        self.assertIn('str', result['value_type'])


class TestJsonAdapterEdgeCases(unittest.TestCase):
    """Test edge cases for JSON adapter."""

    @classmethod
    def setUpClass(cls):
        """Create edge case test files."""
        cls.temp_dir = tempfile.mkdtemp()

        # Empty object
        cls.empty_obj = Path(cls.temp_dir) / 'empty_obj.json'
        cls.empty_obj.write_text('{}')

        # Empty array
        cls.empty_arr = Path(cls.temp_dir) / 'empty_arr.json'
        cls.empty_arr.write_text('[]')

        # Null value
        cls.null_json = Path(cls.temp_dir) / 'null.json'
        cls.null_json.write_text(json.dumps({'value': None}))

        # Deep nesting
        cls.deep_json = Path(cls.temp_dir) / 'deep.json'
        cls.deep_json.write_text(json.dumps({
            'a': {'b': {'c': {'d': {'e': 'deep'}}}}
        }))

        # Special keys
        cls.special_keys = Path(cls.temp_dir) / 'special.json'
        cls.special_keys.write_text(json.dumps({
            'normal-key': 1,
            'key with spaces': 2,
            '123numeric': 3
        }))

    @classmethod
    def tearDownClass(cls):
        """Clean up test files."""
        import shutil
        shutil.rmtree(cls.temp_dir)

    def test_empty_object(self):
        """Should handle empty object."""
        adapter = JsonAdapter(str(self.empty_obj), None)
        result = adapter.get_structure()

        self.assertEqual(result['value'], {})
        self.assertIn('0 keys', result['value_type'])

    def test_empty_array(self):
        """Should handle empty array."""
        adapter = JsonAdapter(str(self.empty_arr), None)
        result = adapter.get_structure()

        self.assertEqual(result['value'], [])
        self.assertIn('empty', result['value_type'])

    def test_null_value(self):
        """Should handle null values."""
        adapter = JsonAdapter(f'{self.null_json}/value', None)
        result = adapter.get_structure()

        self.assertIsNone(result['value'])
        self.assertEqual(result['value_type'], 'null')

    def test_deep_navigation(self):
        """Should navigate deeply nested paths."""
        adapter = JsonAdapter(f'{self.deep_json}/a/b/c/d/e', None)
        result = adapter.get_structure()

        self.assertEqual(result['value'], 'deep')

    def test_special_keys_flatten(self):
        """Should handle special keys in flatten output."""
        adapter = JsonAdapter(str(self.special_keys), 'flatten')
        result = adapter.get_structure()

        # Keys with special chars should use bracket notation
        lines = result['lines']
        self.assertTrue(any('["key with spaces"]' in line for line in lines))


if __name__ == '__main__':
    unittest.main()
