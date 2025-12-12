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


if __name__ == '__main__':
    unittest.main()
