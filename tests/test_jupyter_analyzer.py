"""Tests for Jupyter notebook analyzer."""

import unittest
import tempfile
import os
import json
from reveal.analyzers.jupyter_analyzer import JupyterAnalyzer


class TestJupyterAnalyzer(unittest.TestCase):
    """Test Jupyter notebook analyzer."""

    def create_temp_notebook(self, notebook_data: dict) -> str:
        """Helper: Create temp notebook file."""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, "test.ipynb")
        with open(path, 'w') as f:
            json.dump(notebook_data, f)
        return path

    def teardown_file(self, path: str):
        """Helper: Clean up temp file."""
        os.unlink(path)
        os.rmdir(os.path.dirname(path))

    def test_basic_notebook_structure(self):
        """Test extraction of basic notebook structure."""
        notebook = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": ["# Hello World\n", "This is a test notebook."]
                },
                {
                    "cell_type": "code",
                    "source": ["print('hello')"],
                    "execution_count": 1,
                    "outputs": []
                }
            ],
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3",
                    "name": "python3"
                },
                "language_info": {
                    "name": "python"
                }
            }
        }
        path = self.create_temp_notebook(notebook)
        try:
            analyzer = JupyterAnalyzer(path)
            structure = analyzer.get_structure()

            self.assertIn('cells', structure)
            cells = structure['cells']
            self.assertEqual(len(cells), 2)

            # First cell is markdown
            self.assertEqual(cells[0]['type'], 'markdown')
            self.assertIn('Hello World', cells[0]['name'])

            # Second cell is code
            self.assertEqual(cells[1]['type'], 'code')

        finally:
            self.teardown_file(path)

    def test_code_cell_with_execution_count(self):
        """Test code cell execution count extraction."""
        notebook = {
            "cells": [
                {
                    "cell_type": "code",
                    "source": ["x = 1 + 1"],
                    "execution_count": 5,
                    "outputs": [{"output_type": "execute_result"}]
                }
            ],
            "metadata": {}
        }
        path = self.create_temp_notebook(notebook)
        try:
            analyzer = JupyterAnalyzer(path)
            structure = analyzer.get_structure()

            cells = structure['cells']
            self.assertEqual(len(cells), 1)
            self.assertEqual(cells[0]['execution_count'], 5)
            self.assertEqual(cells[0]['outputs_count'], 1)

        finally:
            self.teardown_file(path)

    def test_unexecuted_code_cell(self):
        """Test code cell that hasn't been executed."""
        notebook = {
            "cells": [
                {
                    "cell_type": "code",
                    "source": ["# Not yet run"],
                    "execution_count": None,
                    "outputs": []
                }
            ],
            "metadata": {}
        }
        path = self.create_temp_notebook(notebook)
        try:
            analyzer = JupyterAnalyzer(path)
            structure = analyzer.get_structure()

            cells = structure['cells']
            self.assertEqual(len(cells), 1)
            self.assertIsNone(cells[0]['execution_count'])
            self.assertIn('not executed', cells[0]['name'])

        finally:
            self.teardown_file(path)

    def test_empty_notebook(self):
        """Test with empty notebook."""
        notebook = {
            "cells": [],
            "metadata": {}
        }
        path = self.create_temp_notebook(notebook)
        try:
            analyzer = JupyterAnalyzer(path)
            structure = analyzer.get_structure()

            # Should return empty or minimal structure
            self.assertEqual(structure.get('cells', []), [])

        finally:
            self.teardown_file(path)

    def test_invalid_json(self):
        """Test with malformed JSON."""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, "bad.ipynb")
        with open(path, 'w') as f:
            f.write("{ this is not valid json")

        try:
            analyzer = JupyterAnalyzer(path)
            # Should have parse error
            self.assertIsNotNone(analyzer.parse_error)

            structure = analyzer.get_structure()
            self.assertIn('error', structure)

        finally:
            os.unlink(path)
            os.rmdir(temp_dir)

    def test_source_as_string(self):
        """Test handling source as string instead of list."""
        notebook = {
            "cells": [
                {
                    "cell_type": "code",
                    "source": "single_line_source",
                    "execution_count": 1,
                    "outputs": []
                }
            ],
            "metadata": {}
        }
        path = self.create_temp_notebook(notebook)
        try:
            analyzer = JupyterAnalyzer(path)
            structure = analyzer.get_structure()

            cells = structure['cells']
            self.assertEqual(len(cells), 1)
            self.assertIn('single_line_source', cells[0]['name'])

        finally:
            self.teardown_file(path)

    def test_long_cell_content_truncation(self):
        """Test that long cell content is truncated in preview."""
        long_content = "x = " + "a" * 100  # More than 50 chars
        notebook = {
            "cells": [
                {
                    "cell_type": "code",
                    "source": [long_content],
                    "execution_count": 1,
                    "outputs": []
                }
            ],
            "metadata": {}
        }
        path = self.create_temp_notebook(notebook)
        try:
            analyzer = JupyterAnalyzer(path)
            structure = analyzer.get_structure()

            cells = structure['cells']
            # Name should be truncated with ...
            self.assertIn('...', cells[0]['name'])

        finally:
            self.teardown_file(path)

    def test_multiple_cell_types(self):
        """Test notebook with multiple cell types."""
        notebook = {
            "cells": [
                {"cell_type": "markdown", "source": ["# Title"]},
                {"cell_type": "code", "source": ["x = 1"], "execution_count": 1, "outputs": []},
                {"cell_type": "markdown", "source": ["## Section"]},
                {"cell_type": "code", "source": ["y = 2"], "execution_count": 2, "outputs": []},
                {"cell_type": "raw", "source": ["Raw text"]}
            ],
            "metadata": {}
        }
        path = self.create_temp_notebook(notebook)
        try:
            analyzer = JupyterAnalyzer(path)
            structure = analyzer.get_structure()

            cells = structure['cells']
            self.assertEqual(len(cells), 5)

            # Check types are preserved
            self.assertEqual(cells[0]['type'], 'markdown')
            self.assertEqual(cells[1]['type'], 'code')
            self.assertEqual(cells[4]['type'], 'raw')

        finally:
            self.teardown_file(path)

    def test_kernel_metadata(self):
        """Test kernel and language info extraction."""
        notebook = {
            "cells": [],
            "metadata": {
                "kernelspec": {
                    "display_name": "Julia 1.8",
                    "name": "julia-1.8"
                },
                "language_info": {
                    "name": "julia",
                    "version": "1.8.0"
                }
            }
        }
        path = self.create_temp_notebook(notebook)
        try:
            analyzer = JupyterAnalyzer(path)
            # Check metadata was parsed
            self.assertEqual(analyzer.metadata.get('kernelspec', {}).get('display_name'), 'Julia 1.8')

        finally:
            self.teardown_file(path)

    def test_generate_preview(self):
        """Test preview generation."""
        notebook = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": ["# Title\n", "Description"]
                },
                {
                    "cell_type": "code",
                    "source": ["print('hello')"],
                    "execution_count": 1,
                    "outputs": [{"output_type": "stream"}]
                }
            ],
            "metadata": {
                "kernelspec": {"display_name": "Python 3"},
                "language_info": {"name": "python"}
            }
        }
        path = self.create_temp_notebook(notebook)
        try:
            analyzer = JupyterAnalyzer(path)
            preview = analyzer.generate_preview()

            # Should have content
            self.assertGreater(len(preview), 0)

            # Preview should include cell content
            preview_text = '\n'.join(line for _, line in preview)
            self.assertIn('MARKDOWN', preview_text.upper())
            self.assertIn('CODE', preview_text.upper())

        finally:
            self.teardown_file(path)

    def test_preview_with_invalid_json(self):
        """Test preview falls back to raw JSON on parse error."""
        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, "bad.ipynb")
        with open(path, 'w') as f:
            f.write('{"invalid": true\n')

        try:
            analyzer = JupyterAnalyzer(path)
            preview = analyzer.generate_preview()

            # Should show raw content
            self.assertGreater(len(preview), 0)

        finally:
            os.unlink(path)
            os.rmdir(temp_dir)

    def test_cell_outputs_with_data(self):
        """Test code cell with multiple outputs."""
        notebook = {
            "cells": [
                {
                    "cell_type": "code",
                    "source": ["import matplotlib.pyplot as plt\n", "plt.plot([1,2,3])"],
                    "execution_count": 1,
                    "outputs": [
                        {"output_type": "execute_result"},
                        {"output_type": "display_data"}
                    ]
                }
            ],
            "metadata": {}
        }
        path = self.create_temp_notebook(notebook)
        try:
            analyzer = JupyterAnalyzer(path)
            structure = analyzer.get_structure()

            cells = structure['cells']
            self.assertEqual(cells[0]['outputs_count'], 2)

        finally:
            self.teardown_file(path)

    def test_find_cell_line(self):
        """Test cell line number detection."""
        notebook = {
            "cells": [
                {"cell_type": "markdown", "source": ["# First"]},
                {"cell_type": "code", "source": ["x = 1"], "execution_count": 1, "outputs": []}
            ],
            "metadata": {}
        }
        path = self.create_temp_notebook(notebook)
        try:
            analyzer = JupyterAnalyzer(path)

            # Should find line numbers for cells (both are valid line numbers >= 1)
            line1 = analyzer._find_cell_line(0)
            line2 = analyzer._find_cell_line(1)

            # Both should be valid line numbers
            self.assertGreaterEqual(line1, 1)
            self.assertGreaterEqual(line2, 1)

        finally:
            self.teardown_file(path)


if __name__ == '__main__':
    unittest.main()
