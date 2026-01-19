"""Tests for XML analyzer."""

import unittest
import tempfile
import os
from reveal.analyzers.xml_analyzer import XmlAnalyzer


class TestXmlAnalyzer(unittest.TestCase):
    """Test XML file analysis."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def create_xml_file(self, content: str, name: str = "test.xml") -> str:
        """Helper: Create XML file with given content."""
        path = os.path.join(self.temp_dir, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_basic_xml_structure(self):
        """Test basic XML file structure extraction."""
        content = """<?xml version="1.0"?>
<root>
    <child1>Value 1</child1>
    <child2>Value 2</child2>
    <child3>Value 3</child3>
</root>"""

        path = self.create_xml_file(content)
        analyzer = XmlAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertEqual(structure['root']['tag'], 'root')
        self.assertEqual(structure['statistics']['child_count'], 3)
        self.assertEqual(len(structure['children']), 3)
        self.assertEqual(structure['children'][0]['tag'], 'child1')
        self.assertEqual(structure['children'][0]['text'], 'Value 1')

    def test_element_with_attributes(self):
        """Test XML element with attributes."""
        content = """<?xml version="1.0"?>
<config>
    <server host="localhost" port="8080" ssl="true">
        <name>Production</name>
    </server>
</config>"""

        path = self.create_xml_file(content)
        analyzer = XmlAnalyzer(path)
        structure = analyzer.get_structure()

        server = structure['children'][0]
        self.assertEqual(server['tag'], 'server')
        self.assertEqual(server['attributes']['host'], 'localhost')
        self.assertEqual(server['attributes']['port'], '8080')
        self.assertEqual(server['attributes']['ssl'], 'true')
        self.assertEqual(len(server['children']), 1)

    def test_element_count_and_depth(self):
        """Test element counting and depth calculation."""
        content = """<?xml version="1.0"?>
<root>
    <level1>
        <level2>
            <level3>Deep value</level3>
        </level2>
    </level1>
    <sibling>Value</sibling>
</root>"""

        path = self.create_xml_file(content)
        analyzer = XmlAnalyzer(path)
        structure = analyzer.get_structure()

        # Root + 2 children + 1 grandchild + 1 great-grandchild = 5 total
        self.assertEqual(structure['statistics']['total_elements'], 5)
        # Root (0) -> level1 (1) -> level2 (2) -> level3 (3) = depth 3
        self.assertEqual(structure['statistics']['max_depth'], 3)

    def test_namespace_detection(self):
        """Test XML namespace detection."""
        content = """<?xml version="1.0"?>
<root xmlns="http://example.com/schema">
    <child1>Value 1</child1>
    <child2 xmlns="http://example.com/other">Value 2</child2>
</root>"""

        path = self.create_xml_file(content)
        analyzer = XmlAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertEqual(structure['statistics']['namespace_count'], 2)
        self.assertEqual(len(structure['namespaces']), 2)

        # Check namespace URIs are present
        ns_uris = [ns['uri'] for ns in structure['namespaces']]
        self.assertIn('http://example.com/schema', ns_uris)
        self.assertIn('http://example.com/other', ns_uris)

    def test_type_inference_integer(self):
        """Test integer type inference for text content."""
        content = """<?xml version="1.0"?>
<config>
    <port>8080</port>
    <timeout>30</timeout>
</config>"""

        path = self.create_xml_file(content)
        analyzer = XmlAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertEqual(structure['children'][0]['text_type'], 'integer')
        self.assertEqual(structure['children'][1]['text_type'], 'integer')

    def test_type_inference_float(self):
        """Test float type inference for text content."""
        content = """<?xml version="1.0"?>
<config>
    <version>1.5</version>
    <ratio>3.14159</ratio>
</config>"""

        path = self.create_xml_file(content)
        analyzer = XmlAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertEqual(structure['children'][0]['text_type'], 'float')
        self.assertEqual(structure['children'][1]['text_type'], 'float')

    def test_type_inference_boolean(self):
        """Test boolean type inference for text content."""
        content = """<?xml version="1.0"?>
<config>
    <enabled>true</enabled>
    <debug>false</debug>
    <verbose>yes</verbose>
</config>"""

        path = self.create_xml_file(content)
        analyzer = XmlAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertEqual(structure['children'][0]['text_type'], 'boolean')
        self.assertEqual(structure['children'][1]['text_type'], 'boolean')
        self.assertEqual(structure['children'][2]['text_type'], 'boolean')

    def test_type_inference_string(self):
        """Test string type inference for text content."""
        content = """<?xml version="1.0"?>
<config>
    <name>Production</name>
    <description>Main server</description>
</config>"""

        path = self.create_xml_file(content)
        analyzer = XmlAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertEqual(structure['children'][0]['text_type'], 'string')
        self.assertEqual(structure['children'][1]['text_type'], 'string')

    def test_head_filtering(self):
        """Test head parameter for filtering top-level children."""
        content = """<?xml version="1.0"?>
<root>
    <item1/>
    <item2/>
    <item3/>
    <item4/>
    <item5/>
</root>"""

        path = self.create_xml_file(content)
        analyzer = XmlAnalyzer(path)
        structure = analyzer.get_structure(head=3)

        self.assertEqual(len(structure['children']), 3)
        self.assertEqual(structure['children'][0]['tag'], 'item1')
        self.assertEqual(structure['children'][2]['tag'], 'item3')
        self.assertEqual(structure['filtered']['showing'], 3)
        self.assertEqual(structure['filtered']['total'], 5)

    def test_tail_filtering(self):
        """Test tail parameter for filtering top-level children."""
        content = """<?xml version="1.0"?>
<root>
    <item1/>
    <item2/>
    <item3/>
    <item4/>
    <item5/>
</root>"""

        path = self.create_xml_file(content)
        analyzer = XmlAnalyzer(path)
        structure = analyzer.get_structure(tail=2)

        self.assertEqual(len(structure['children']), 2)
        self.assertEqual(structure['children'][0]['tag'], 'item4')
        self.assertEqual(structure['children'][1]['tag'], 'item5')

    def test_range_filtering(self):
        """Test range parameter for filtering top-level children."""
        content = """<?xml version="1.0"?>
<root>
    <item1/>
    <item2/>
    <item3/>
    <item4/>
    <item5/>
</root>"""

        path = self.create_xml_file(content)
        analyzer = XmlAnalyzer(path)
        structure = analyzer.get_structure(range=(2, 4))

        self.assertEqual(len(structure['children']), 3)
        self.assertEqual(structure['children'][0]['tag'], 'item2')
        self.assertEqual(structure['children'][2]['tag'], 'item4')

    def test_element_extraction_by_name(self):
        """Test element extraction by tag name."""
        content = """<?xml version="1.0"?>
<root>
    <config>
        <server>Server 1</server>
    </config>
    <data>
        <server>Server 2</server>
    </data>
</root>"""

        path = self.create_xml_file(content)
        analyzer = XmlAnalyzer(path)
        element = analyzer.get_element('server')

        self.assertIsNotNone(element)
        self.assertEqual(element['tag'], 'server')
        self.assertEqual(element['match_count'], 2)
        self.assertEqual(len(element['matches']), 2)
        self.assertEqual(element['matches'][0]['text'], 'Server 1')
        self.assertEqual(element['matches'][1]['text'], 'Server 2')

    def test_element_extraction_not_found(self):
        """Test element extraction when tag doesn't exist."""
        content = """<?xml version="1.0"?>
<root>
    <child>Value</child>
</root>"""

        path = self.create_xml_file(content)
        analyzer = XmlAnalyzer(path)
        element = analyzer.get_element('nonexistent')

        self.assertIsNone(element)

    def test_element_extraction_with_path(self):
        """Test element extraction includes path information."""
        content = """<?xml version="1.0"?>
<root>
    <level1>
        <target>Found</target>
    </level1>
</root>"""

        path = self.create_xml_file(content)
        analyzer = XmlAnalyzer(path)
        element = analyzer.get_element('target')

        self.assertIsNotNone(element)
        self.assertEqual(element['matches'][0]['path'], 'root/level1/target')

    def test_empty_element(self):
        """Test handling of empty XML elements."""
        content = """<?xml version="1.0"?>
<root>
    <empty/>
    <whitespace>   </whitespace>
</root>"""

        path = self.create_xml_file(content)
        analyzer = XmlAnalyzer(path)
        structure = analyzer.get_structure()

        # Empty element should not have text field
        self.assertNotIn('text', structure['children'][0])
        # Whitespace-only should be treated as empty
        self.assertNotIn('text', structure['children'][1])

    def test_malformed_xml(self):
        """Test handling of malformed XML."""
        content = """<?xml version="1.0"?>
<root>
    <unclosed>
</root>"""

        path = self.create_xml_file(content)
        analyzer = XmlAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertIn('error', structure)
        self.assertIn('message', structure)

    def test_maven_pom_example(self):
        """Test real-world Maven pom.xml structure."""
        content = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>my-app</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>junit</groupId>
            <artifactId>junit</artifactId>
            <version>4.12</version>
        </dependency>
    </dependencies>
</project>"""

        path = self.create_xml_file(content, 'pom.xml')
        analyzer = XmlAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertEqual(structure['root']['tag'], 'project')
        self.assertIn('namespace', structure['root'])
        self.assertEqual(structure['statistics']['child_count'], 5)

        # Find dependencies element
        deps = analyzer.get_element('dependency')
        self.assertIsNotNone(deps)
        self.assertEqual(deps['match_count'], 1)

    def test_android_manifest_example(self):
        """Test real-world Android manifest structure."""
        content = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.example.app">
    <application
        android:label="My App"
        android:icon="@drawable/icon">
        <activity android:name=".MainActivity">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
            </intent-filter>
        </activity>
    </application>
</manifest>"""

        path = self.create_xml_file(content, 'AndroidManifest.xml')
        analyzer = XmlAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertEqual(structure['root']['tag'], 'manifest')
        self.assertIn('package', structure['root']['attributes'])

        # Check application element
        app = structure['children'][0]
        self.assertEqual(app['tag'], 'application')
        # ElementTree stores namespaced attributes with full URI
        self.assertTrue(any('label' in key for key in app['attributes'].keys()))

    def test_default_filtering_large_document(self):
        """Test that large documents (>10 children) are filtered by default."""
        # Create XML with 15 children
        children = '\n'.join([f'    <item{i}/>' for i in range(1, 16)])
        content = f"""<?xml version="1.0"?>
<root>
{children}
</root>"""

        path = self.create_xml_file(content)
        analyzer = XmlAnalyzer(path)
        structure = analyzer.get_structure()

        # Should show only first 10 by default
        self.assertEqual(len(structure['children']), 10)
        self.assertEqual(structure['filtered']['showing'], 10)
        self.assertEqual(structure['filtered']['total'], 15)

    def test_no_namespace(self):
        """Test XML document without namespaces."""
        content = """<?xml version="1.0"?>
<root>
    <child>Value</child>
</root>"""

        path = self.create_xml_file(content)
        analyzer = XmlAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertEqual(structure['statistics']['namespace_count'], 0)
        self.assertNotIn('namespaces', structure)
        self.assertIsNone(structure['root']['namespace'])


if __name__ == '__main__':
    unittest.main()
