"""Tests for CSV analyzer."""

import unittest
import tempfile
import os
from reveal.analyzers.csv_analyzer import CsvAnalyzer


class TestCsvAnalyzer(unittest.TestCase):
    """Test CSV/TSV file analysis."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def create_csv_file(self, content: str, name: str = "test.csv") -> str:
        """Helper: Create CSV file with given content."""
        path = os.path.join(self.temp_dir, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_basic_csv_structure(self):
        """Test basic CSV file structure extraction."""
        content = """name,age,city
Alice,30,NYC
Bob,25,LA
Charlie,35,Chicago"""

        path = self.create_csv_file(content)
        analyzer = CsvAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertEqual(structure['column_count'], 3)
        self.assertEqual(structure['row_count'], 3)
        self.assertIn('name', structure['columns'])
        self.assertIn('age', structure['columns'])
        self.assertIn('city', structure['columns'])

    def test_type_inference_integer(self):
        """Test integer type inference."""
        content = """id,count
1,100
2,200
3,300"""

        path = self.create_csv_file(content)
        analyzer = CsvAnalyzer(path)
        structure = analyzer.get_structure()

        schema = {col['name']: col['type'] for col in structure['schema']}
        self.assertEqual(schema['id'], 'integer')
        self.assertEqual(schema['count'], 'integer')

    def test_type_inference_float(self):
        """Test float type inference."""
        content = """price,rating
19.99,4.5
29.99,4.8
39.99,4.2"""

        path = self.create_csv_file(content)
        analyzer = CsvAnalyzer(path)
        structure = analyzer.get_structure()

        schema = {col['name']: col['type'] for col in structure['schema']}
        self.assertEqual(schema['price'], 'float')
        self.assertEqual(schema['rating'], 'float')

    def test_type_inference_string(self):
        """Test string type inference."""
        content = """name,description
Product A,Best seller
Product B,New arrival
Product C,Limited edition"""

        path = self.create_csv_file(content)
        analyzer = CsvAnalyzer(path)
        structure = analyzer.get_structure()

        schema = {col['name']: col['type'] for col in structure['schema']}
        self.assertEqual(schema['name'], 'string')
        self.assertEqual(schema['description'], 'string')

    def test_type_inference_boolean(self):
        """Test boolean type inference."""
        content = """active,verified
true,yes
false,no
true,yes"""

        path = self.create_csv_file(content)
        analyzer = CsvAnalyzer(path)
        structure = analyzer.get_structure()

        schema = {col['name']: col['type'] for col in structure['schema']}
        self.assertEqual(schema['active'], 'boolean')
        self.assertEqual(schema['verified'], 'boolean')

    def test_missing_values(self):
        """Test missing value detection."""
        content = """name,age,city
Alice,30,NYC
Bob,,LA
Charlie,35,"""

        path = self.create_csv_file(content)
        analyzer = CsvAnalyzer(path)
        structure = analyzer.get_structure()

        # Find age column schema
        age_schema = next(col for col in structure['schema'] if col['name'] == 'age')
        self.assertEqual(age_schema['missing'], 1)
        self.assertAlmostEqual(age_schema['missing_pct'], 33.3, places=1)

        # Find city column schema
        city_schema = next(col for col in structure['schema'] if col['name'] == 'city')
        self.assertEqual(city_schema['missing'], 1)

    def test_tsv_delimiter(self):
        """Test TSV file with tab delimiter."""
        content = """name\tage\tcity
Alice\t30\tNYC
Bob\t25\tLA"""

        path = self.create_csv_file(content, "test.tsv")
        analyzer = CsvAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertEqual(structure['delimiter'], 'tab')
        self.assertEqual(structure['column_count'], 3)
        self.assertEqual(structure['row_count'], 2)

    def test_head_parameter(self):
        """Test head parameter to limit rows."""
        content = """id,name
1,Alice
2,Bob
3,Charlie
4,David
5,Eve"""

        path = self.create_csv_file(content)
        analyzer = CsvAnalyzer(path)
        structure = analyzer.get_structure(head=2)

        self.assertEqual(len(structure['sample_rows']), 2)
        self.assertEqual(structure['sample_rows'][0]['name'], 'Alice')
        self.assertEqual(structure['sample_rows'][1]['name'], 'Bob')

    def test_tail_parameter(self):
        """Test tail parameter to show last rows."""
        content = """id,name
1,Alice
2,Bob
3,Charlie
4,David
5,Eve"""

        path = self.create_csv_file(content)
        analyzer = CsvAnalyzer(path)
        structure = analyzer.get_structure(tail=2)

        self.assertEqual(len(structure['sample_rows']), 2)
        self.assertEqual(structure['sample_rows'][0]['name'], 'David')
        self.assertEqual(structure['sample_rows'][1]['name'], 'Eve')

    def test_range_parameter(self):
        """Test range parameter to show specific rows."""
        content = """id,name
1,Alice
2,Bob
3,Charlie
4,David
5,Eve"""

        path = self.create_csv_file(content)
        analyzer = CsvAnalyzer(path)
        structure = analyzer.get_structure(range=(2, 4))

        self.assertEqual(len(structure['sample_rows']), 3)
        self.assertEqual(structure['sample_rows'][0]['name'], 'Bob')
        self.assertEqual(structure['sample_rows'][2]['name'], 'David')

    def test_empty_csv(self):
        """Test empty CSV file (header only)."""
        content = """name,age,city"""

        path = self.create_csv_file(content)
        analyzer = CsvAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertEqual(structure['row_count'], 0)
        self.assertIn('message', structure)

    def test_malformed_csv(self):
        """Test malformed CSV handling."""
        content = """"""  # Completely empty

        path = self.create_csv_file(content)
        analyzer = CsvAnalyzer(path)
        structure = analyzer.get_structure()

        self.assertIn('message', structure)
        self.assertEqual(structure['row_count'], 0)

    def test_get_element_by_row(self):
        """Test getting specific row by number."""
        content = """name,age,city
Alice,30,NYC
Bob,25,LA
Charlie,35,Chicago"""

        path = self.create_csv_file(content)
        analyzer = CsvAnalyzer(path)

        # Get row 2
        row = analyzer.get_element('2')
        self.assertIsNotNone(row)
        self.assertEqual(row['row_number'], 2)
        self.assertEqual(row['data']['name'], 'Bob')
        self.assertEqual(row['data']['age'], '25')

    def test_get_element_invalid_row(self):
        """Test getting non-existent row."""
        content = """name,age
Alice,30
Bob,25"""

        path = self.create_csv_file(content)
        analyzer = CsvAnalyzer(path)

        # Row 999 doesn't exist
        row = analyzer.get_element('999')
        self.assertIsNone(row)

    def test_get_element_invalid_format(self):
        """Test getting element with invalid row number format."""
        content = """name,age
Alice,30"""

        path = self.create_csv_file(content)
        analyzer = CsvAnalyzer(path)

        row = analyzer.get_element('not_a_number')
        self.assertIsNone(row)

    def test_sample_values(self):
        """Test that sample values are provided in schema."""
        content = """fruit,color
apple,red
banana,yellow
cherry,red
grape,purple"""

        path = self.create_csv_file(content)
        analyzer = CsvAnalyzer(path)
        structure = analyzer.get_structure()

        color_schema = next(col for col in structure['schema'] if col['name'] == 'color')
        self.assertIn('sample_values', color_schema)
        self.assertGreater(len(color_schema['sample_values']), 0)


if __name__ == '__main__':
    unittest.main()
