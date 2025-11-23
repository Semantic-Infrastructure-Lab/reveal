"""
Tests for Jupyter Notebook analyzer.

Ensures that Jupyter analyzer correctly parses .ipynb files
and provides progressive disclosure of notebook structure.
"""

import json
import unittest
from reveal.analyzers.jupyter_analyzer import JupyterAnalyzer


class TestJupyterAnalyzer(unittest.TestCase):
    """Test Jupyter notebook analyzer."""

    def test_basic_notebook_structure(self):
        """Jupyter analyzer should parse basic notebook structure."""
        notebook = {
            "cells": [
                {
                    "cell_type": "code",
                    "execution_count": 1,
                    "metadata": {},
                    "source": ["print('hello')"],
                    "outputs": []
                },
                {
                    "cell_type": "markdown",
                    "metadata": {},
                    "source": ["# Heading"]
                }
            ],
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3",
                    "language": "python",
                    "name": "python3"
                },
                "language_info": {
                    "name": "python"
                }
            },
            "nbformat": 4,
            "nbformat_minor": 2
        }

        lines = json.dumps(notebook, indent=2).split('\n')
        analyzer = JupyterAnalyzer(lines)
        structure = analyzer.analyze_structure()

        # Check basic metadata
        self.assertEqual(structure['total_cells'], 2)
        self.assertEqual(structure['kernel'], 'Python 3')
        self.assertEqual(structure['language'], 'python')
        self.assertEqual(structure['nbformat'], 4)

        # Check cell counts
        self.assertEqual(structure['cell_counts']['code'], 1)
        self.assertEqual(structure['cell_counts']['markdown'], 1)

    def test_cell_summaries_with_line_numbers(self):
        """Jupyter analyzer should provide cell summaries with line numbers."""
        notebook = {
            "cells": [
                {
                    "cell_type": "code",
                    "execution_count": 1,
                    "source": ["import numpy as np", "import pandas as pd"],
                    "outputs": [{"output_type": "stream"}]
                }
            ],
            "metadata": {
                "kernelspec": {"name": "python3"}
            },
            "nbformat": 4
        }

        lines = json.dumps(notebook, indent=2).split('\n')
        analyzer = JupyterAnalyzer(lines)
        structure = analyzer.analyze_structure()

        cells = structure['cells']
        self.assertEqual(len(cells), 1)

        cell = cells[0]
        self.assertEqual(cell['index'], 0)
        self.assertEqual(cell['type'], 'code')
        self.assertEqual(cell['execution_count'], 1)
        self.assertEqual(cell['outputs_count'], 1)
        self.assertEqual(cell['source_lines'], 2)
        self.assertIn('import numpy', cell['first_line'])

    def test_multiple_cell_types(self):
        """Jupyter analyzer should handle notebooks with multiple cell types."""
        notebook = {
            "cells": [
                {"cell_type": "markdown", "source": ["# Title"]},
                {"cell_type": "code", "source": ["x = 1"], "execution_count": 1, "outputs": []},
                {"cell_type": "markdown", "source": ["Some text"]},
                {"cell_type": "code", "source": ["y = 2"], "execution_count": 2, "outputs": []},
                {"cell_type": "raw", "source": ["raw content"]}
            ],
            "metadata": {"kernelspec": {"name": "python3"}},
            "nbformat": 4
        }

        lines = json.dumps(notebook, indent=2).split('\n')
        analyzer = JupyterAnalyzer(lines)
        structure = analyzer.analyze_structure()

        self.assertEqual(structure['total_cells'], 5)
        self.assertEqual(structure['cell_counts']['markdown'], 2)
        self.assertEqual(structure['cell_counts']['code'], 2)
        self.assertEqual(structure['cell_counts']['raw'], 1)

    def test_code_cells_with_outputs(self):
        """Jupyter analyzer should track outputs for code cells."""
        notebook = {
            "cells": [
                {
                    "cell_type": "code",
                    "execution_count": 1,
                    "source": ["1 + 1"],
                    "outputs": [
                        {"output_type": "execute_result", "data": {"text/plain": ["2"]}},
                        {"output_type": "stream", "name": "stdout", "text": ["output"]}
                    ]
                }
            ],
            "metadata": {"kernelspec": {"name": "python3"}},
            "nbformat": 4
        }

        lines = json.dumps(notebook, indent=2).split('\n')
        analyzer = JupyterAnalyzer(lines)
        structure = analyzer.analyze_structure()

        cell = structure['cells'][0]
        self.assertEqual(cell['outputs_count'], 2)

    def test_cells_without_execution_count(self):
        """Jupyter analyzer should handle cells that haven't been executed."""
        notebook = {
            "cells": [
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "source": ["# Not executed yet"],
                    "outputs": []
                }
            ],
            "metadata": {"kernelspec": {"name": "python3"}},
            "nbformat": 4
        }

        lines = json.dumps(notebook, indent=2).split('\n')
        analyzer = JupyterAnalyzer(lines)
        structure = analyzer.analyze_structure()

        cell = structure['cells'][0]
        self.assertIsNone(cell['execution_count'])

    def test_multiline_cells(self):
        """Jupyter analyzer should handle multiline cell content."""
        notebook = {
            "cells": [
                {
                    "cell_type": "code",
                    "execution_count": 1,
                    "source": [
                        "def hello():\n",
                        "    print('hello')\n",
                        "    return True\n"
                    ],
                    "outputs": []
                }
            ],
            "metadata": {"kernelspec": {"name": "python3"}},
            "nbformat": 4
        }

        lines = json.dumps(notebook, indent=2).split('\n')
        analyzer = JupyterAnalyzer(lines)
        structure = analyzer.analyze_structure()

        cell = structure['cells'][0]
        self.assertEqual(cell['source_lines'], 3)
        self.assertIn('def hello', cell['first_line'])

    def test_empty_notebook(self):
        """Jupyter analyzer should handle empty notebooks."""
        notebook = {
            "cells": [],
            "metadata": {"kernelspec": {"name": "python3"}},
            "nbformat": 4
        }

        lines = json.dumps(notebook, indent=2).split('\n')
        analyzer = JupyterAnalyzer(lines)
        structure = analyzer.analyze_structure()

        self.assertEqual(structure['total_cells'], 0)
        self.assertEqual(structure['cells'], [])
        self.assertEqual(structure['cell_counts'], {})

    def test_preview_generation(self):
        """Jupyter analyzer should generate meaningful previews."""
        notebook = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": ["# Data Analysis\n", "This is a test notebook."]
                },
                {
                    "cell_type": "code",
                    "execution_count": 1,
                    "source": ["import pandas as pd\n", "df = pd.read_csv('data.csv')"],
                    "outputs": []
                }
            ],
            "metadata": {
                "kernelspec": {"display_name": "Python 3", "name": "python3"},
                "language_info": {"name": "python"}
            },
            "nbformat": 4
        }

        lines = json.dumps(notebook, indent=2).split('\n')
        analyzer = JupyterAnalyzer(lines)
        preview = analyzer.generate_preview()

        # Should have preview content
        self.assertGreater(len(preview), 0)

        # Check that preview includes kernel info
        preview_text = '\n'.join(line for _, line in preview)
        self.assertIn('Python 3', preview_text)

        # Check that cell content is shown
        self.assertIn('Data Analysis', preview_text)
        self.assertIn('import pandas', preview_text)

    def test_preview_limits_cells(self):
        """Jupyter analyzer preview should limit number of cells shown."""
        # Create notebook with 15 cells
        cells = [
            {"cell_type": "code", "source": [f"x = {i}"], "execution_count": i, "outputs": []}
            for i in range(15)
        ]
        notebook = {
            "cells": cells,
            "metadata": {"kernelspec": {"name": "python3"}},
            "nbformat": 4
        }

        lines = json.dumps(notebook, indent=2).split('\n')
        analyzer = JupyterAnalyzer(lines)
        preview = analyzer.generate_preview()

        preview_text = '\n'.join(line for _, line in preview)
        # Should show message about more cells
        self.assertIn('more cells', preview_text)

    def test_preview_limits_cell_lines(self):
        """Jupyter analyzer preview should limit lines shown per cell."""
        long_source = [f"line_{i}\n" for i in range(20)]
        notebook = {
            "cells": [
                {
                    "cell_type": "code",
                    "execution_count": 1,
                    "source": long_source,
                    "outputs": []
                }
            ],
            "metadata": {"kernelspec": {"name": "python3"}},
            "nbformat": 4
        }

        lines = json.dumps(notebook, indent=2).split('\n')
        analyzer = JupyterAnalyzer(lines)
        preview = analyzer.generate_preview()

        preview_text = '\n'.join(line for _, line in preview)
        # Should show message about more lines
        self.assertIn('more lines', preview_text)

    def test_format_structure_output(self):
        """Jupyter analyzer should format structure output nicely."""
        notebook = {
            "cells": [
                {
                    "cell_type": "code",
                    "execution_count": 1,
                    "source": ["print('test')"],
                    "outputs": [{"output_type": "stream"}]
                }
            ],
            "metadata": {
                "kernelspec": {"display_name": "Python 3", "name": "python3"},
                "language_info": {"name": "python"}
            },
            "nbformat": 4
        }

        lines = json.dumps(notebook, indent=2).split('\n')
        analyzer = JupyterAnalyzer(lines, file_path="test.ipynb")
        structure = analyzer.analyze_structure()
        formatted = analyzer.format_structure(structure)

        # Should return list of formatted strings
        self.assertIsInstance(formatted, list)
        self.assertGreater(len(formatted), 0)

        formatted_text = '\n'.join(formatted)
        # Should include key information
        self.assertIn('Python 3', formatted_text)
        self.assertIn('python', formatted_text)
        self.assertIn('code', formatted_text)

    def test_malformed_json_error_handling(self):
        """Jupyter analyzer should handle malformed JSON gracefully."""
        lines = ['{', '"cells": [']  # Invalid JSON

        analyzer = JupyterAnalyzer(lines)
        structure = analyzer.analyze_structure()

        # Should have parse error
        self.assertIsNotNone(structure.get('error'))
        self.assertEqual(structure['total_cells'], 0)

        # Preview should still work (fallback to raw lines)
        preview = analyzer.generate_preview()
        self.assertGreater(len(preview), 0)

    def test_missing_metadata(self):
        """Jupyter analyzer should handle missing metadata gracefully."""
        notebook = {
            "cells": [
                {"cell_type": "code", "source": ["x = 1"], "execution_count": 1, "outputs": []}
            ],
            "metadata": {},  # Empty metadata
            "nbformat": 4
        }

        lines = json.dumps(notebook, indent=2).split('\n')
        analyzer = JupyterAnalyzer(lines)
        structure = analyzer.analyze_structure()

        # Should use 'unknown' for missing info
        self.assertEqual(structure['kernel'], 'unknown')
        self.assertEqual(structure['language'], 'unknown')

    def test_with_file_path(self):
        """Jupyter analyzer should use file_path for composable output."""
        notebook = {
            "cells": [
                {"cell_type": "code", "source": ["x = 1"], "execution_count": 1, "outputs": []}
            ],
            "metadata": {"kernelspec": {"name": "python3"}},
            "nbformat": 4
        }

        lines = json.dumps(notebook, indent=2).split('\n')
        analyzer = JupyterAnalyzer(lines, file_path='analysis.ipynb')

        # Verify file_path is stored
        self.assertEqual(analyzer.file_path, 'analysis.ipynb')

        # format_location should use file path
        loc = analyzer.format_location(5)
        self.assertEqual(loc, 'analysis.ipynb:5')

    def test_string_source_instead_of_list(self):
        """Jupyter analyzer should handle source as string (old format)."""
        notebook = {
            "cells": [
                {
                    "cell_type": "code",
                    "execution_count": 1,
                    "source": "print('hello')",  # String instead of list
                    "outputs": []
                }
            ],
            "metadata": {"kernelspec": {"name": "python3"}},
            "nbformat": 4
        }

        lines = json.dumps(notebook, indent=2).split('\n')
        analyzer = JupyterAnalyzer(lines)
        structure = analyzer.analyze_structure()

        cell = structure['cells'][0]
        self.assertIn('print', cell['first_line'])


class TestJupyterComposability(unittest.TestCase):
    """Test that Jupyter line numbers make output composable."""

    def test_format_location_helper(self):
        """Jupyter analyzer should use format_location helper."""
        notebook = {
            "cells": [],
            "metadata": {},
            "nbformat": 4
        }

        lines = json.dumps(notebook, indent=2).split('\n')

        analyzer = JupyterAnalyzer(lines, file_path='notebook.ipynb')
        loc = analyzer.format_location(10)
        self.assertEqual(loc, 'notebook.ipynb:10')

        # Without file_path, should use L0000 format
        analyzer_no_path = JupyterAnalyzer(lines)
        loc = analyzer_no_path.format_location(10)
        self.assertEqual(loc, 'L0010')


if __name__ == '__main__':
    unittest.main()
