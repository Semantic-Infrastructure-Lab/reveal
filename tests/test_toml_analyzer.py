"""Tests for TOML analyzer."""

import unittest
import tempfile
import os
from pathlib import Path
from reveal.analyzers.toml import TomlAnalyzer


class TestTomlAnalyzer(unittest.TestCase):
    """Test TOML file analyzer."""

    def create_temp_toml(self, content: str) -> str:
        """Helper: Create temp TOML file."""
        fd, path = tempfile.mkstemp(suffix='.toml')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(content)
            return path
        except:
            os.close(fd)
            raise

    def test_simple_sections(self):
        """Test extraction of simple sections."""
        content = """
[build-system]
requires = ["setuptools"]

[project]
name = "test"
version = "1.0.0"

[tool.pytest]
testpaths = ["tests"]
"""
        path = self.create_temp_toml(content)
        try:
            analyzer = TomlAnalyzer(path)
            structure = analyzer.get_structure()

            self.assertIn('sections', structure)
            sections = structure['sections']
            self.assertEqual(len(sections), 3)

            section_names = [s['name'] for s in sections]
            self.assertEqual(section_names, ['build-system', 'project', 'tool.pytest'])

        finally:
            os.unlink(path)

    def test_top_level_keys(self):
        """Test extraction of top-level keys."""
        content = """
name = "my-project"
version = "1.0.0"
description = "A test project"

[section]
key = "value"
"""
        path = self.create_temp_toml(content)
        try:
            analyzer = TomlAnalyzer(path)
            structure = analyzer.get_structure()

            self.assertIn('keys', structure)
            keys = structure['keys']
            self.assertEqual(len(keys), 3)

            key_names = [k['name'] for k in keys]
            self.assertEqual(key_names, ['name', 'version', 'description'])

        finally:
            os.unlink(path)

    def test_array_sections(self):
        """Test extraction of array sections [[section]]."""
        content = """
[[tool.mypy.overrides]]
module = "test.*"
ignore_errors = true

[[tool.mypy.overrides]]
module = "docs.*"
ignore_errors = true
"""
        path = self.create_temp_toml(content)
        try:
            analyzer = TomlAnalyzer(path)
            structure = analyzer.get_structure()

            self.assertIn('sections', structure)
            sections = structure['sections']
            self.assertEqual(len(sections), 2)

            # Both should have the same name (array section)
            for section in sections:
                self.assertEqual(section['name'], 'tool.mypy.overrides')

        finally:
            os.unlink(path)

    def test_pyproject_toml_structure(self):
        """Test with real pyproject.toml structure."""
        content = """
[build-system]
requires = ["setuptools>=45", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "reveal-cli"
version = "0.7.0"
description = "Semantic code explorer"

[project.urls]
Homepage = "https://github.com/scottsen/reveal"

[tool.pytest.ini_options]
testpaths = ["tests"]
"""
        path = self.create_temp_toml(content)
        try:
            analyzer = TomlAnalyzer(path)
            structure = analyzer.get_structure()

            self.assertIn('sections', structure)
            sections = structure['sections']
            section_names = [s['name'] for s in sections]

            # Should find all nested sections
            self.assertIn('build-system', section_names)
            self.assertIn('project', section_names)
            self.assertIn('project.urls', section_names)
            self.assertIn('tool.pytest.ini_options', section_names)

        finally:
            os.unlink(path)

    def test_empty_file(self):
        """Test with empty TOML file."""
        content = ""
        path = self.create_temp_toml(content)
        try:
            analyzer = TomlAnalyzer(path)
            structure = analyzer.get_structure()

            # Should return empty structure
            self.assertEqual(structure, {})

        finally:
            os.unlink(path)

    def test_comments_ignored(self):
        """Test that comments are properly ignored."""
        content = """
# This is a comment
[section]
# Another comment
key = "value"  # Inline comment
"""
        path = self.create_temp_toml(content)
        try:
            analyzer = TomlAnalyzer(path)
            structure = analyzer.get_structure()

            self.assertIn('sections', structure)
            self.assertEqual(len(structure['sections']), 1)

        finally:
            os.unlink(path)

    def test_extract_section(self):
        """Test extraction of specific section."""
        content = """
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[project]
name = "test"
version = "1.0.0"
"""
        path = self.create_temp_toml(content)
        try:
            analyzer = TomlAnalyzer(path)
            result = analyzer.extract_element('section', 'project')

            self.assertIsNotNone(result)
            self.assertEqual(result['name'], 'project')
            self.assertIn('name = "test"', result['source'])
            self.assertIn('version = "1.0.0"', result['source'])

        finally:
            os.unlink(path)


if __name__ == '__main__':
    unittest.main()
