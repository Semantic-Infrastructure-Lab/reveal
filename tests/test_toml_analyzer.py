"""Tests for TOML analyzer."""

import unittest
import tempfile
import os
from pathlib import Path
import pytest

from reveal.analyzers.toml import TomlAnalyzer

# BACK-1149: component-layer test -- single analyzer in isolation, no subprocess/CLI/MCP
pytestmark = pytest.mark.component


class TestTomlAnalyzer(unittest.TestCase):
    """Test TOML file analyzer."""

    def create_temp_toml(self, content: str) -> str:
        """Helper: Create temp TOML file."""
        fd, path = tempfile.mkstemp(suffix='.toml')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(content)
            return path
        except (OSError, IOError) as e:
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
Homepage = "https://github.com/Semantic-Infrastructure-Lab/reveal"

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


def test_ast_query_reports_toml_section_lines(tmp_path):
    """BACK-1416: ast:// read only 'line', so every TOML section (keyed
    'line_start') came back at line 0 while the outline said 1 and 4."""
    from reveal.adapters.ast import AstAdapter
    f = tmp_path / 'c.toml'
    f.write_text('[server]\nport = 1\n\n[db]\nhost = "x"\n', encoding='utf-8')
    results = AstAdapter(str(f), '').get_structure()['results']
    assert [(r['name'], r['line']) for r in results] == [('server', 1), ('db', 4)]


if __name__ == '__main__':
    unittest.main()


_SECTIONS = '[widget]\nname = "x"\nv = 1\n\n# about helper\n[helper]\nk = 1\n\n[[arr]]\nz = 2\n'


def _sections(tmp_path, text=_SECTIONS):
    f = tmp_path / 'd.toml'
    f.write_text(text, encoding='utf-8')
    return f, {s['name']: s for s in TomlAnalyzer(str(f)).get_structure()['sections']}


def test_sections_carry_a_line_end_that_stops_at_the_last_key(tmp_path):
    """BACK-1416: sections had no line_end, so ast:// said '[0 lines]'; and the end must not
    run into the blank/comment lines in front of the next table, or past the end of the file."""
    _, sections = _sections(tmp_path)
    assert {n: (s['line_start'], s['line_end']) for n, s in sections.items()} == {
        'widget': (1, 3), 'helper': (6, 7), 'arr': (9, 10)}


def test_ast_query_reports_the_section_length(tmp_path):
    from reveal.adapters.ast import AstAdapter
    f, _ = _sections(tmp_path)
    results = AstAdapter(str(f), '').get_structure()['results']
    assert [(r['name'], r['line'], r['line_count']) for r in results] == [
        ('widget', 1, 3), ('helper', 6, 2), ('arr', 9, 2)]


def test_outline_and_element_extraction_agree_on_where_a_section_ends(tmp_path):
    f, sections = _sections(tmp_path)
    analyzer = TomlAnalyzer(str(f))
    for name, section in sections.items():
        element = analyzer.extract_element('section', name)
        assert (element['line_start'], element['line_end']) == (
            section['line_start'], section['line_end']), name


def test_a_section_without_a_trailing_newline_ends_on_its_last_key(tmp_path):
    _, sections = _sections(tmp_path, '[a]\nk = 1')
    assert sections['a']['line_end'] == 2
