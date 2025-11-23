"""
Tests for file type detection.

Tests the file type detection logic based on file extensions.
"""

import unittest
from pathlib import Path
from reveal.detectors import detect_file_type, FILE_TYPE_MAP


class TestFileTypeDetection(unittest.TestCase):
    """Test file type detection based on extensions."""

    def test_detect_yaml_file(self):
        """Should detect YAML files."""
        self.assertEqual(detect_file_type(Path("config.yaml")), "yaml")
        self.assertEqual(detect_file_type(Path("config.yml")), "yaml")
        self.assertEqual(detect_file_type(Path("/path/to/file.yaml")), "yaml")

    def test_detect_json_file(self):
        """Should detect JSON files."""
        self.assertEqual(detect_file_type(Path("data.json")), "json")
        self.assertEqual(detect_file_type(Path("/path/to/config.json")), "json")

    def test_detect_python_file(self):
        """Should detect Python files."""
        self.assertEqual(detect_file_type(Path("script.py")), "python")
        self.assertEqual(detect_file_type(Path("module.py")), "python")

    def test_detect_jupyter_notebook(self):
        """Should detect Jupyter notebook files."""
        self.assertEqual(detect_file_type(Path("analysis.ipynb")), "jupyter")

    def test_detect_toml_file(self):
        """Should detect TOML files."""
        self.assertEqual(detect_file_type(Path("pyproject.toml")), "toml")
        self.assertEqual(detect_file_type(Path("Cargo.toml")), "toml")

    def test_detect_markdown_file(self):
        """Should detect Markdown files."""
        self.assertEqual(detect_file_type(Path("README.md")), "markdown")
        self.assertEqual(detect_file_type(Path("doc.markdown")), "markdown")

    def test_detect_unknown_extension(self):
        """Should return 'text' for unknown extensions."""
        self.assertEqual(detect_file_type(Path("file.xyz")), "text")
        self.assertEqual(detect_file_type(Path("document.doc")), "text")
        self.assertEqual(detect_file_type(Path("image.png")), "text")

    def test_detect_no_extension(self):
        """Should return 'text' for files without extension."""
        self.assertEqual(detect_file_type(Path("Makefile")), "text")
        self.assertEqual(detect_file_type(Path("README")), "text")
        self.assertEqual(detect_file_type(Path("LICENSE")), "text")

    def test_case_insensitive_detection(self):
        """Should handle extensions case-insensitively."""
        self.assertEqual(detect_file_type(Path("file.YAML")), "yaml")
        self.assertEqual(detect_file_type(Path("file.Json")), "json")
        self.assertEqual(detect_file_type(Path("file.PY")), "python")
        self.assertEqual(detect_file_type(Path("file.MD")), "markdown")

    def test_file_type_map_completeness(self):
        """FILE_TYPE_MAP should contain expected extensions."""
        self.assertIn('.yaml', FILE_TYPE_MAP)
        self.assertIn('.yml', FILE_TYPE_MAP)
        self.assertIn('.json', FILE_TYPE_MAP)
        self.assertIn('.py', FILE_TYPE_MAP)
        self.assertIn('.md', FILE_TYPE_MAP)
        self.assertIn('.toml', FILE_TYPE_MAP)
        self.assertIn('.ipynb', FILE_TYPE_MAP)

    def test_all_mapped_types_are_strings(self):
        """All file type values should be strings."""
        for file_type in FILE_TYPE_MAP.values():
            self.assertIsInstance(file_type, str)
            self.assertGreater(len(file_type), 0)

    def test_all_extensions_start_with_dot(self):
        """All extension keys should start with a dot."""
        for ext in FILE_TYPE_MAP.keys():
            self.assertTrue(ext.startswith('.'))

    def test_complex_file_paths(self):
        """Should handle complex file paths correctly."""
        self.assertEqual(
            detect_file_type(Path("/home/user/projects/myapp/config.yaml")),
            "yaml"
        )
        self.assertEqual(
            detect_file_type(Path("../../data/analysis.ipynb")),
            "jupyter"
        )
        self.assertEqual(
            detect_file_type(Path("./scripts/process.py")),
            "python"
        )

    def test_multiple_dots_in_filename(self):
        """Should handle filenames with multiple dots."""
        self.assertEqual(detect_file_type(Path("config.prod.yaml")), "yaml")
        self.assertEqual(detect_file_type(Path("test.data.json")), "json")
        self.assertEqual(detect_file_type(Path("my.script.py")), "python")

    def test_hidden_files(self):
        """Should handle hidden files (starting with dot)."""
        self.assertEqual(detect_file_type(Path(".config.yaml")), "yaml")
        self.assertEqual(detect_file_type(Path(".gitignore")), "text")


if __name__ == '__main__':
    unittest.main()
