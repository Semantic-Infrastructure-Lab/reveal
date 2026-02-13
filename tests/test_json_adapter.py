"""Tests for JSON adapter (json://)."""

import unittest
import json
import tempfile
import os
from pathlib import Path

from reveal.adapters.json import JsonAdapter


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

        self.assertEqual(result['type'], 'json_value')
        self.assertEqual(result['path'], '(root)')
        self.assertEqual(result['value']['name'], 'test')

    def test_path_navigation_simple(self):
        """Should navigate to simple key."""
        adapter = JsonAdapter(f'{self.simple_json}/name', None)
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'json_value')
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

        self.assertEqual(result['type'], 'json_schema')
        self.assertIn('schema', result)
        self.assertEqual(result['schema']['name'], 'str')
        self.assertEqual(result['schema']['count'], 'int')
        self.assertEqual(result['schema']['enabled'], 'bool')

    def test_query_flatten(self):
        """Should return flattened output for ?flatten query."""
        adapter = JsonAdapter(f'{self.simple_json}/tags', 'flatten')
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'json_flatten')
        self.assertIn('lines', result)
        # Should have lines like: json[0] = "a"
        self.assertTrue(any('json[0]' in line for line in result['lines']))

    def test_query_gron_alias(self):
        """Should accept ?gron as alias for ?flatten."""
        adapter = JsonAdapter(f'{self.simple_json}/tags', 'gron')
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'json_flatten')  # Same type as flatten

    def test_query_type(self):
        """Should return type info for ?type query."""
        adapter = JsonAdapter(f'{self.nested_json}/users', 'type')
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'json_type')
        self.assertIn('Array', result['value_type'])
        self.assertEqual(result['length'], 3)

    def test_query_keys_object(self):
        """Should return keys for object."""
        adapter = JsonAdapter(f'{self.simple_json}', 'keys')
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'json_keys')
        self.assertIn('keys', result)
        self.assertIn('name', result['keys'])
        self.assertIn('version', result['keys'])

    def test_query_keys_array(self):
        """Should return indices for array."""
        adapter = JsonAdapter(f'{self.nested_json}/users', 'keys')
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'json_keys')
        self.assertIn('indices', result)
        self.assertEqual(result['count'], 3)

    def test_query_length(self):
        """Should return length for ?length query."""
        adapter = JsonAdapter(f'{self.nested_json}/users', 'length')
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'json_length')
        self.assertEqual(result['length'], 3)

    def test_query_invalid(self):
        """Should return error for invalid query."""
        adapter = JsonAdapter(str(self.simple_json), 'invalid')
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'json_error')
        self.assertIn('valid_queries', result)

    def test_path_not_found(self):
        """Should return error for non-existent path."""
        adapter = JsonAdapter(f'{self.simple_json}/nonexistent', None)
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'json_error')
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


class TestJsonAdapterFiltering(unittest.TestCase):
    """Test JSON adapter filtering with unified query syntax."""

    @classmethod
    def setUpClass(cls):
        """Create test JSON with array data."""
        cls.temp_dir = tempfile.mkdtemp()

        # Users array for filtering tests
        cls.users_json = Path(cls.temp_dir) / 'users.json'
        cls.users_json.write_text(json.dumps({
            'users': [
                {'name': 'Alice', 'age': 30, 'status': 'active', 'score': 85.5},
                {'name': 'Bob', 'age': 25, 'status': 'inactive', 'score': 92.0},
                {'name': 'Charlie', 'age': 35, 'status': 'active', 'score': 78.3},
                {'name': 'David', 'age': 28, 'status': 'active', 'score': 88.7},
                {'name': 'Eve', 'age': 22, 'status': 'inactive', 'score': 95.2}
            ]
        }))

        # Products array for range tests
        cls.products_json = Path(cls.temp_dir) / 'products.json'
        cls.products_json.write_text(json.dumps({
            'products': [
                {'id': 1, 'name': 'Widget', 'price': 15.99, 'category': 'tools'},
                {'id': 2, 'name': 'Gadget', 'price': 25.50, 'category': 'electronics'},
                {'id': 3, 'name': 'Gizmo', 'price': 8.75, 'category': 'toys'},
                {'id': 4, 'name': 'Doohickey', 'price': 45.00, 'category': 'tools'},
                {'id': 5, 'name': 'Thingamabob', 'price': 12.25, 'category': 'household'}
            ]
        }))

    @classmethod
    def tearDownClass(cls):
        """Clean up test files."""
        import shutil
        shutil.rmtree(cls.temp_dir)

    def test_filter_greater_than(self):
        """Should filter array by numeric greater than."""
        adapter = JsonAdapter(f'{self.users_json}/users', 'age>28')
        result = adapter.get_structure()

        self.assertEqual(result['type'], 'json_value')
        users = result['value']
        self.assertEqual(len(users), 2)  # Alice (30), Charlie (35)
        self.assertTrue(all(u['age'] > 28 for u in users))

    def test_filter_less_than(self):
        """Should filter array by numeric less than."""
        adapter = JsonAdapter(f'{self.users_json}/users', 'age<28')
        result = adapter.get_structure()

        users = result['value']
        self.assertEqual(len(users), 2)  # Bob (25), Eve (22)
        self.assertTrue(all(u['age'] < 28 for u in users))

    def test_filter_equals(self):
        """Should filter array by exact match."""
        adapter = JsonAdapter(f'{self.users_json}/users', 'status=active')
        result = adapter.get_structure()

        users = result['value']
        self.assertEqual(len(users), 3)  # Alice, Charlie, David
        self.assertTrue(all(u['status'] == 'active' for u in users))

    def test_filter_not_equals(self):
        """Should filter array by not equals."""
        adapter = JsonAdapter(f'{self.users_json}/users', 'status!=inactive')
        result = adapter.get_structure()

        users = result['value']
        self.assertEqual(len(users), 3)  # Alice, Charlie, David
        self.assertTrue(all(u['status'] != 'inactive' for u in users))

    def test_filter_range_numeric(self):
        """Should filter array by numeric range."""
        adapter = JsonAdapter(f'{self.users_json}/users', 'age=25..30')
        result = adapter.get_structure()

        users = result['value']
        self.assertEqual(len(users), 3)  # Bob (25), David (28), Alice (30)
        self.assertTrue(all(25 <= u['age'] <= 30 for u in users))

    def test_filter_regex(self):
        """Should filter array by regex match."""
        adapter = JsonAdapter(f'{self.users_json}/users', 'name~=^[AC]')
        result = adapter.get_structure()

        users = result['value']
        self.assertEqual(len(users), 2)  # Alice, Charlie
        self.assertTrue(all(u['name'][0] in ['A', 'C'] for u in users))

    def test_filter_greater_equals(self):
        """Should filter array by greater than or equal."""
        adapter = JsonAdapter(f'{self.users_json}/users', 'score>=90')
        result = adapter.get_structure()

        users = result['value']
        self.assertEqual(len(users), 2)  # Bob (92.0), Eve (95.2)
        self.assertTrue(all(u['score'] >= 90 for u in users))

    def test_filter_less_equals(self):
        """Should filter array by less than or equal."""
        adapter = JsonAdapter(f'{self.users_json}/users', 'score<=85.5')
        result = adapter.get_structure()

        users = result['value']
        self.assertEqual(len(users), 2)  # Alice (85.5), Charlie (78.3)
        self.assertTrue(all(u['score'] <= 85.5 for u in users))

    def test_result_control_sort_ascending(self):
        """Should sort array ascending."""
        adapter = JsonAdapter(f'{self.users_json}/users', 'sort=age')
        result = adapter.get_structure()

        users = result['value']
        ages = [u['age'] for u in users]
        self.assertEqual(ages, [22, 25, 28, 30, 35])

    def test_result_control_sort_descending(self):
        """Should sort array descending."""
        adapter = JsonAdapter(f'{self.users_json}/users', 'sort=-age')
        result = adapter.get_structure()

        users = result['value']
        ages = [u['age'] for u in users]
        self.assertEqual(ages, [35, 30, 28, 25, 22])

    def test_result_control_limit(self):
        """Should limit array results."""
        adapter = JsonAdapter(f'{self.users_json}/users', 'limit=2')
        result = adapter.get_structure()

        users = result['value']
        self.assertEqual(len(users), 2)
        # Should have truncation warning
        self.assertIn('warnings', result)
        self.assertEqual(result['total_matches'], 5)
        self.assertEqual(result['displayed_results'], 2)

    def test_result_control_offset(self):
        """Should skip first N results."""
        adapter = JsonAdapter(f'{self.users_json}/users', 'offset=2')
        result = adapter.get_structure()

        users = result['value']
        self.assertEqual(len(users), 3)  # Should get last 3 users

    def test_result_control_combined(self):
        """Should combine sort, limit, and offset."""
        adapter = JsonAdapter(f'{self.users_json}/users', 'sort=-age&limit=2&offset=1')
        result = adapter.get_structure()

        users = result['value']
        self.assertEqual(len(users), 2)
        # After sorting descending by age: 35, 30, 28, 25, 22
        # Offset 1: 30, 28, 25, 22
        # Limit 2: 30, 28
        ages = [u['age'] for u in users]
        self.assertEqual(ages, [30, 28])

    def test_filter_and_result_control(self):
        """Should combine filtering and result control."""
        adapter = JsonAdapter(f'{self.users_json}/users', 'age>25&sort=-age&limit=2')
        result = adapter.get_structure()

        users = result['value']
        self.assertEqual(len(users), 2)
        # Filter: age > 25 → Alice (30), Charlie (35), David (28)
        # Sort descending: Charlie (35), Alice (30), David (28)
        # Limit 2: Charlie (35), Alice (30)
        names = [u['name'] for u in users]
        self.assertEqual(names, ['Charlie', 'Alice'])

    def test_filter_price_range(self):
        """Should filter products by price range."""
        adapter = JsonAdapter(f'{self.products_json}/products', 'price=10..25')
        result = adapter.get_structure()

        products = result['value']
        # Widget (15.99), Thingamabob (12.25), Gadget (25.50 is > 25, excluded)
        self.assertEqual(len(products), 2)
        self.assertTrue(all(10 <= p['price'] <= 25 for p in products))

    def test_filter_missing_field(self):
        """Should handle missing field gracefully."""
        adapter = JsonAdapter(f'{self.users_json}/users', 'nonexistent>100')
        result = adapter.get_structure()

        users = result['value']
        self.assertEqual(len(users), 0)  # No users have this field

    def test_sort_missing_field(self):
        """Should handle sorting by missing field."""
        # Add a user without score field
        test_json = Path(self.temp_dir) / 'test_missing.json'
        test_json.write_text(json.dumps({
            'users': [
                {'name': 'Alice', 'score': 85},
                {'name': 'Bob'},  # Missing score
                {'name': 'Charlie', 'score': 90}
            ]
        }))

        adapter = JsonAdapter(f'{test_json}/users', 'sort=score')
        result = adapter.get_structure()

        users = result['value']
        # Users with score should come first (sorted), then those without
        self.assertEqual(len(users), 3)

    def test_zero_limit(self):
        """Should support limit=0 (return empty array)."""
        adapter = JsonAdapter(f'{self.users_json}/users', 'limit=0')
        result = adapter.get_structure()

        users = result['value']
        self.assertEqual(len(users), 0)

    def test_offset_greater_than_total(self):
        """Should handle offset greater than array length."""
        adapter = JsonAdapter(f'{self.users_json}/users', 'offset=100')
        result = adapter.get_structure()

        users = result['value']
        self.assertEqual(len(users), 0)


if __name__ == '__main__':
    unittest.main()
