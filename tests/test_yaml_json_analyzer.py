"""
Tests for YAML/JSON analyzer.

Tests analysis with:
- YAML structure extraction
- JSON structure extraction
- Combined analyzer behavior
- UTF-8 handling
"""

import unittest
import tempfile
import os
from pathlib import Path
from reveal.analyzers.yaml_json import YamlAnalyzer, JsonAnalyzer


class TestYamlAnalyzer(unittest.TestCase):
    """Test YAML analyzer."""

    def test_extract_yaml_structure(self):
        """Should extract YAML top-level keys."""
        code = '''# YAML configuration
name: MyApp
version: 1.0.0

database:
  host: localhost
  port: 5432
  credentials:
    username: admin
    password: secret

services:
  - name: web
    port: 8080
  - name: api
    port: 3000

features:
  authentication: true
  caching: false
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = YamlAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should extract top-level keys
            self.assertIsNotNone(structure)
            self.assertIn('keys', structure)

            keys = structure['keys']
            key_names = [k['name'] for k in keys]
            self.assertIn('name', key_names)
            self.assertIn('version', key_names)
            self.assertIn('database', key_names)
            self.assertIn('services', key_names)
            self.assertIn('features', key_names)

        finally:
            os.unlink(temp_path)

    def test_extract_yaml_with_anchors(self):
        """Should handle YAML anchors and aliases."""
        code = '''# YAML with anchors
defaults: &defaults
  timeout: 30
  retries: 3

development:
  <<: *defaults
  host: localhost

production:
  <<: *defaults
  host: prod.example.com
  timeout: 60
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = YamlAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should be able to parse YAML with anchors (extract top-level keys)
            self.assertIsNotNone(structure)
            self.assertIn('keys', structure)

        finally:
            os.unlink(temp_path)


class TestJsonAnalyzer(unittest.TestCase):
    """Test JSON analyzer."""

    def test_extract_json_structure(self):
        """Should extract JSON top-level keys."""
        code = '''{
  "name": "MyApp",
  "version": "1.0.0",
  "database": {
    "host": "localhost",
    "port": 5432,
    "credentials": {
      "username": "admin",
      "password": "secret"
    }
  },
  "services": [
    {
      "name": "web",
      "port": 8080
    },
    {
      "name": "api",
      "port": 3000
    }
  ],
  "features": {
    "authentication": true,
    "caching": false
  }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = JsonAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should extract JSON top-level keys
            self.assertIsNotNone(structure)
            self.assertIn('keys', structure)

            keys = structure['keys']
            key_names = [k['name'] for k in keys]
            self.assertIn('name', key_names)
            self.assertIn('version', key_names)
            self.assertIn('database', key_names)
            self.assertIn('services', key_names)
            self.assertIn('features', key_names)

        finally:
            os.unlink(temp_path)

    def test_json_with_nested_arrays(self):
        """Should handle deeply nested JSON."""
        code = '''{
  "users": [
    {
      "id": 1,
      "name": "Alice",
      "roles": ["admin", "user"],
      "metadata": {
        "created": "2024-01-01",
        "tags": ["active", "verified"]
      }
    },
    {
      "id": 2,
      "name": "Bob",
      "roles": ["user"],
      "metadata": {
        "created": "2024-01-02",
        "tags": ["active"]
      }
    }
  ]
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = JsonAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should parse nested JSON (extract top-level keys)
            self.assertIsNotNone(structure)
            self.assertIn('keys', structure)

        finally:
            os.unlink(temp_path)

    def test_utf8_json(self):
        """Should handle UTF-8 characters in JSON."""
        code = '''{
  "greeting": "Hello 👋 World 🌍",
  "user": {
    "name": "田中太郎",
    "emoji": "🚀"
  },
  "messages": [
    "Welcome! 🎉",
    "Goodbye! 👋"
  ]
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = JsonAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should handle UTF-8 correctly
            self.assertIsNotNone(structure)
            self.assertIn('keys', structure)

        finally:
            os.unlink(temp_path)


class TestYamlAnalyzerUTF8(unittest.TestCase):
    """Test YAML analyzer UTF-8 handling."""

    def test_yaml_with_complex_types(self):
        """Should handle complex YAML types."""
        code = '''# Complex YAML types
string_value: "hello"
number_value: 42
float_value: 3.14
boolean_true: true
boolean_false: false
null_value: null

date: 2024-01-01
datetime: 2024-01-01T12:00:00Z

multiline_string: |
  This is a
  multiline string
  with preserved newlines

folded_string: >
  This is a folded
  string that will be
  joined into one line

list:
  - item1
  - item2
  - item3

nested:
  - name: first
    values: [1, 2, 3]
  - name: second
    values: [4, 5, 6]
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = YamlAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should parse complex YAML (extract top-level keys)
            self.assertIsNotNone(structure)
            self.assertIn('keys', structure)

        finally:
            os.unlink(temp_path)

    def test_utf8_yaml(self):
        """Should handle UTF-8 characters in YAML."""
        code = '''# ✨ YAML file with emoji ✨

greeting: "Hello 👋 World 🌍"

# 日本語コメント
user:
  name: "田中太郎"
  emoji: "🚀"

messages:
  - "Welcome! 🎉"
  - "Goodbye! 👋"
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = YamlAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should handle UTF-8 correctly
            self.assertIsNotNone(structure)
            self.assertIn('keys', structure)

        finally:
            os.unlink(temp_path)


class TestCombinedAnalyzerBehavior(unittest.TestCase):
    """Test that YAML and JSON analyzers work together."""

    def test_combined_analyzer_behavior(self):
        """Should work as separate YAML/JSON analyzers."""
        yaml_code = '''name: test
value: 123
'''
        json_code = '{"name": "test", "value": 123}'

        # Test YAML
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write(yaml_code)
            f.flush()
            yaml_path = f.name

        # Test JSON
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            f.write(json_code)
            f.flush()
            json_path = f.name

        try:
            # Both should work
            yaml_analyzer = YamlAnalyzer(yaml_path)
            yaml_structure = yaml_analyzer.get_structure()
            self.assertIsNotNone(yaml_structure)
            self.assertIn('keys', yaml_structure)

            json_analyzer = JsonAnalyzer(json_path)
            json_structure = json_analyzer.get_structure()
            self.assertIsNotNone(json_structure)
            self.assertIn('keys', json_structure)

        finally:
            os.unlink(yaml_path)
            os.unlink(json_path)


class TestYamlExtraction(unittest.TestCase):
    """Test YAML element extraction."""

    def test_extract_yaml_key(self):
        """Should extract specific YAML key with content."""
        code = '''name: MyApp
version: 1.0.0
database:
  host: localhost
  port: 5432
services:
  - web
  - api
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = YamlAnalyzer(temp_path)

            # Extract 'database' key
            result = analyzer.extract_element('key', 'database')
            self.assertIsNotNone(result)
            self.assertEqual(result['name'], 'database')
            self.assertEqual(result['line_start'], 3)
            self.assertIn('host: localhost', result['source'])
            self.assertIn('port: 5432', result['source'])

        finally:
            os.unlink(temp_path)

    def test_extract_yaml_simple_key(self):
        """Should extract simple YAML key."""
        code = '''name: MyApp
version: 1.0.0
description: A simple app
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = YamlAnalyzer(temp_path)

            # Extract 'version' key
            result = analyzer.extract_element('key', 'version')
            self.assertIsNotNone(result)
            self.assertEqual(result['name'], 'version')
            self.assertEqual(result['line_start'], 2)
            self.assertEqual(result['line_end'], 2)
            self.assertIn('1.0.0', result['source'])

        finally:
            os.unlink(temp_path)

    def test_extract_yaml_nonexistent_key(self):
        """Should return None for nonexistent key."""
        code = '''name: MyApp
version: 1.0.0
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = YamlAnalyzer(temp_path)
            result = analyzer.extract_element('key', 'nonexistent')
            # Should fall back to grep-based search which returns None if not found
            self.assertIsNone(result)

        finally:
            os.unlink(temp_path)


class TestJsonExtraction(unittest.TestCase):
    """Test JSON element extraction."""

    def test_extract_json_key(self):
        """Should extract specific JSON key with content."""
        code = '''{
  "name": "MyApp",
  "version": "1.0.0",
  "database": {
    "host": "localhost",
    "port": 5432
  },
  "services": ["web", "api"]
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = JsonAnalyzer(temp_path)

            # Extract 'database' key
            result = analyzer.extract_element('key', 'database')
            self.assertIsNotNone(result)
            self.assertEqual(result['name'], 'database')
            self.assertEqual(result['line_start'], 4)
            self.assertIn('host', result['source'])
            self.assertIn('localhost', result['source'])

        finally:
            os.unlink(temp_path)

    def test_extract_json_simple_key(self):
        """Should extract simple JSON key."""
        code = '''{
  "name": "MyApp",
  "version": "1.0.0",
  "description": "A simple app"
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = JsonAnalyzer(temp_path)

            # Extract 'version' key
            result = analyzer.extract_element('key', 'version')
            self.assertIsNotNone(result)
            self.assertEqual(result['name'], 'version')
            self.assertEqual(result['line_start'], 3)
            self.assertIn('1.0.0', result['source'])

        finally:
            os.unlink(temp_path)

    def test_extract_json_nonexistent_key(self):
        """Should return None for nonexistent key."""
        code = '{"name": "MyApp", "version": "1.0.0"}'
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = JsonAnalyzer(temp_path)
            result = analyzer.extract_element('key', 'nonexistent')
            # Should fall back to grep-based search which returns None if not found
            self.assertIsNone(result)

        finally:
            os.unlink(temp_path)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases for YAML/JSON analyzers."""

    def test_empty_yaml(self):
        """Should handle empty YAML file."""
        code = ''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = YamlAnalyzer(temp_path)
            structure = analyzer.get_structure()
            # Empty file returns empty dict or dict with empty keys
            self.assertIsNotNone(structure)

        finally:
            os.unlink(temp_path)

    def test_empty_json(self):
        """Should handle empty JSON object."""
        code = '{}'
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = JsonAnalyzer(temp_path)
            structure = analyzer.get_structure()
            # Empty object returns empty dict or dict with empty keys
            self.assertIsNotNone(structure)

        finally:
            os.unlink(temp_path)

    def test_json_array_at_root(self):
        """Should handle JSON array at root level."""
        code = '[{"name": "item1"}, {"name": "item2"}]'
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = JsonAnalyzer(temp_path)
            structure = analyzer.get_structure()
            # Array at root has no keys
            self.assertIsNotNone(structure)
            # Should return empty dict since there are no top-level keys
            self.assertEqual(structure, {})

        finally:
            os.unlink(temp_path)

    def test_yaml_with_comments_only(self):
        """Should handle YAML with only comments."""
        code = '''# This is a comment
# Another comment
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = YamlAnalyzer(temp_path)
            structure = analyzer.get_structure()
            # Comments only returns empty structure
            self.assertIsNotNone(structure)

        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()
