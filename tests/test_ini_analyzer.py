"""Tests for INI analyzer."""

import unittest
import tempfile
import os
from reveal.analyzers.ini_analyzer import IniAnalyzer


class TestIniAnalyzer(unittest.TestCase):
    """Test INI/Properties file analysis."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def create_ini_file(self, content: str, name: str = "test.ini") -> str:
        """Helper: Create INI file with given content."""
        path = os.path.join(self.temp_dir, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_basic_ini_structure(self):
        """Test basic INI file structure extraction."""
        content = """[database]
host = localhost
port = 5432
name = mydb

[logging]
level = INFO
file = app.log"""

        path = self.create_ini_file(content)
        analyzer = IniAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertEqual(structure['section_count'], 2)
        self.assertEqual(structure['total_keys'], 5)

        sections = {s['name']: s for s in structure['sections']}
        self.assertIn('database', sections)
        self.assertIn('logging', sections)
        self.assertEqual(sections['database']['key_count'], 3)
        self.assertEqual(sections['logging']['key_count'], 2)

    def test_type_inference_integer(self):
        """Test integer type inference."""
        content = """[server]
port = 8080
workers = 4"""

        path = self.create_ini_file(content)
        analyzer = IniAnalyzer(path)
        structure = analyzer.get_structure()

        keys = {k['name']: k for k in structure['sections'][0]['keys']}
        self.assertEqual(keys['port']['type'], 'integer')
        self.assertEqual(keys['workers']['type'], 'integer')

    def test_type_inference_float(self):
        """Test float type inference."""
        content = """[performance]
timeout = 30.5
threshold = 0.95"""

        path = self.create_ini_file(content)
        analyzer = IniAnalyzer(path)
        structure = analyzer.get_structure()

        keys = {k['name']: k for k in structure['sections'][0]['keys']}
        self.assertEqual(keys['timeout']['type'], 'float')
        self.assertEqual(keys['threshold']['type'], 'float')

    def test_type_inference_boolean(self):
        """Test boolean type inference."""
        content = """[features]
debug = true
cache = yes
ssl = on
verbose = false"""

        path = self.create_ini_file(content)
        analyzer = IniAnalyzer(path)
        structure = analyzer.get_structure()

        keys = {k['name']: k for k in structure['sections'][0]['keys']}
        self.assertEqual(keys['debug']['type'], 'boolean')
        self.assertEqual(keys['cache']['type'], 'boolean')
        self.assertEqual(keys['ssl']['type'], 'boolean')
        self.assertEqual(keys['verbose']['type'], 'boolean')

    def test_type_inference_list(self):
        """Test list type inference (comma-separated values)."""
        content = """[app]
allowed_hosts = localhost,example.com,test.com
modules = auth,api,admin"""

        path = self.create_ini_file(content)
        analyzer = IniAnalyzer(path)
        structure = analyzer.get_structure()

        keys = {k['name']: k for k in structure['sections'][0]['keys']}
        self.assertEqual(keys['allowed_hosts']['type'], 'list')
        self.assertEqual(keys['modules']['type'], 'list')

    def test_type_inference_string(self):
        """Test string type inference."""
        content = """[app]
name = My Application
description = A great app
version = v1.0.0"""

        path = self.create_ini_file(content)
        analyzer = IniAnalyzer(path)
        structure = analyzer.get_structure()

        keys = {k['name']: k for k in structure['sections'][0]['keys']}
        self.assertEqual(keys['name']['type'], 'string')
        self.assertEqual(keys['description']['type'], 'string')
        self.assertEqual(keys['version']['type'], 'string')

    def test_default_section(self):
        """Test DEFAULT section handling."""
        content = """[DEFAULT]
timezone = UTC
locale = en_US

[app]
name = MyApp"""

        path = self.create_ini_file(content)
        analyzer = IniAnalyzer(path)
        structure = analyzer.get_structure()

        sections = {s['name']: s for s in structure['sections']}
        self.assertIn('DEFAULT', sections)
        self.assertEqual(sections['DEFAULT']['key_count'], 2)

    def test_head_parameter(self):
        """Test head parameter to limit sections."""
        content = """[section1]
key1 = value1

[section2]
key2 = value2

[section3]
key3 = value3"""

        path = self.create_ini_file(content)
        analyzer = IniAnalyzer(path)
        structure = analyzer.get_structure(head=2)

        self.assertEqual(len(structure['sections']), 2)
        self.assertEqual(structure['sections'][0]['name'], 'section1')
        self.assertEqual(structure['sections'][1]['name'], 'section2')

    def test_tail_parameter(self):
        """Test tail parameter to show last sections."""
        content = """[section1]
key1 = value1

[section2]
key2 = value2

[section3]
key3 = value3"""

        path = self.create_ini_file(content)
        analyzer = IniAnalyzer(path)
        structure = analyzer.get_structure(tail=2)

        self.assertEqual(len(structure['sections']), 2)
        self.assertEqual(structure['sections'][0]['name'], 'section2')
        self.assertEqual(structure['sections'][1]['name'], 'section3')

    def test_range_parameter(self):
        """Test range parameter to show specific sections."""
        content = """[section1]
key1 = value1

[section2]
key2 = value2

[section3]
key3 = value3

[section4]
key4 = value4"""

        path = self.create_ini_file(content)
        analyzer = IniAnalyzer(path)
        structure = analyzer.get_structure(range=(2, 3))

        self.assertEqual(len(structure['sections']), 2)
        self.assertEqual(structure['sections'][0]['name'], 'section2')
        self.assertEqual(structure['sections'][1]['name'], 'section3')

    def test_properties_format(self):
        """Test Java-style properties file (no sections)."""
        content = """# Application properties
app.name = MyApp
app.version = 1.0
server.port = 8080
debug = true"""

        path = self.create_ini_file(content, "test.properties")
        analyzer = IniAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertEqual(structure['section_count'], 0)
        self.assertEqual(structure['total_keys'], 4)
        self.assertEqual(structure['sections'][0]['name'], '(no section)')

    def test_empty_ini_file(self):
        """Test empty INI file handling."""
        content = """# Just comments"""

        path = self.create_ini_file(content)
        analyzer = IniAnalyzer(path)
        structure = analyzer.get_structure()

        # Empty INI (just comments) is valid - returns empty sections
        self.assertEqual(structure['section_count'], 0)
        self.assertEqual(structure['total_keys'], 0)
        self.assertEqual(structure['sections'], [])

    def test_get_element_section(self):
        """Test getting entire section."""
        content = """[database]
host = localhost
port = 5432
name = mydb"""

        path = self.create_ini_file(content)
        analyzer = IniAnalyzer(path)
        element = analyzer.get_element('database')

        self.assertIsNotNone(element)
        self.assertEqual(element['name'], 'database')
        self.assertEqual(element['key_count'], 3)

        keys = {k['name']: k for k in element['keys']}
        self.assertEqual(keys['host']['value'], 'localhost')
        self.assertEqual(keys['port']['value'], '5432')

    def test_get_element_specific_key(self):
        """Test getting specific key value using section.key format."""
        content = """[database]
host = localhost
port = 5432"""

        path = self.create_ini_file(content)
        analyzer = IniAnalyzer(path)
        element = analyzer.get_element('database.host')

        self.assertIsNotNone(element)
        self.assertEqual(element['section'], 'database')
        self.assertEqual(element['key'], 'host')
        self.assertEqual(element['value'], 'localhost')

    def test_get_element_nonexistent_section(self):
        """Test getting non-existent section."""
        content = """[database]
host = localhost"""

        path = self.create_ini_file(content)
        analyzer = IniAnalyzer(path)
        element = analyzer.get_element('nonexistent')

        self.assertIsNone(element)

    def test_get_element_nonexistent_key(self):
        """Test getting non-existent key."""
        content = """[database]
host = localhost"""

        path = self.create_ini_file(content)
        analyzer = IniAnalyzer(path)
        element = analyzer.get_element('database.nonexistent')

        self.assertIsNone(element)

    def test_comments_ignored(self):
        """Test that comments are properly ignored."""
        content = """# This is a comment
; This is also a comment
[app]
# Comment in section
name = MyApp  # Inline comment
; Another comment
version = 1.0"""

        path = self.create_ini_file(content)
        analyzer = IniAnalyzer(path)
        structure = analyzer.get_structure()

        # Should only count actual keys, not comments
        self.assertEqual(structure['total_keys'], 2)

    def test_multiline_values(self):
        """Test handling of multiline values."""
        content = """[app]
description = This is a long
    description that spans
    multiple lines"""

        path = self.create_ini_file(content)
        analyzer = IniAnalyzer(path)
        structure = analyzer.get_structure()

        keys = {k['name']: k for k in structure['sections'][0]['keys']}
        # configparser automatically handles multiline values
        self.assertIn('description', keys)


if __name__ == '__main__':
    unittest.main()
