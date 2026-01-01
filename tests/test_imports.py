"""Tests for imports:// adapter and import analysis."""

import pytest
from pathlib import Path
from reveal.analyzers.imports import ImportStatement, ImportGraph
from reveal.analyzers.imports.python import extract_python_imports, extract_python_symbols
from reveal.adapters.imports import ImportsAdapter


class TestImportStatement:
    """Test ImportStatement dataclass."""

    def test_create_basic_import(self):
        """Test creating a basic import statement."""
        stmt = ImportStatement(
            file_path=Path('test.py'),
            line_number=1,
            module_name='os',
            imported_names=[],
            is_relative=False,
            import_type='import'
        )

        assert stmt.file_path == Path('test.py')
        assert stmt.line_number == 1
        assert stmt.module_name == 'os'
        assert stmt.imported_names == []
        assert not stmt.is_relative
        assert stmt.import_type == 'import'

    def test_create_from_import(self):
        """Test creating a from-import statement."""
        stmt = ImportStatement(
            file_path=Path('test.py'),
            line_number=2,
            module_name='sys',
            imported_names=['path', 'argv'],
            is_relative=False,
            import_type='from_import'
        )

        assert stmt.module_name == 'sys'
        assert stmt.imported_names == ['path', 'argv']
        assert stmt.import_type == 'from_import'


class TestImportGraph:
    """Test ImportGraph data structure and algorithms."""

    def test_create_empty_graph(self):
        """Test creating an empty import graph."""
        graph = ImportGraph()

        assert graph.get_import_count() == 0
        assert graph.get_file_count() == 0
        assert graph.find_cycles() == []

    def test_from_imports(self):
        """Test building graph from import statements."""
        imports = [
            ImportStatement(
                file_path=Path('a.py'),
                line_number=1,
                module_name='os',
                imported_names=[],
                is_relative=False,
                import_type='import'
            ),
            ImportStatement(
                file_path=Path('a.py'),
                line_number=2,
                module_name='sys',
                imported_names=['path'],
                is_relative=False,
                import_type='from_import'
            ),
        ]

        graph = ImportGraph.from_imports(imports)

        assert graph.get_import_count() == 2
        assert graph.get_file_count() == 1
        assert Path('a.py') in graph.files
        assert len(graph.files[Path('a.py')]) == 2

    def test_add_dependency(self):
        """Test adding dependency edges."""
        graph = ImportGraph()
        file_a = Path('a.py')
        file_b = Path('b.py')

        graph.add_dependency(file_a, file_b)

        assert file_b in graph.dependencies[file_a]
        assert file_a in graph.reverse_deps[file_b]

    def test_find_cycles_simple(self):
        """Test detecting simple circular dependency."""
        graph = ImportGraph()
        a = Path('a.py')
        b = Path('b.py')

        # Create cycle: a -> b -> a
        graph.files[a] = []
        graph.files[b] = []
        graph.add_dependency(a, b)
        graph.add_dependency(b, a)

        cycles = graph.find_cycles()

        assert len(cycles) > 0
        # Should find the cycle (order may vary)

    def test_find_unused_imports(self):
        """Test detecting unused imports."""
        imports = [
            ImportStatement(
                file_path=Path('test.py'),
                line_number=1,
                module_name='os',
                imported_names=[],
                is_relative=False,
                import_type='import'
            ),
            ImportStatement(
                file_path=Path('test.py'),
                line_number=2,
                module_name='sys',
                imported_names=[],
                is_relative=False,
                import_type='import'
            ),
        ]

        graph = ImportGraph.from_imports(imports)

        # Only 'os' is used
        symbols_by_file = {
            Path('test.py'): {'os', 'something_else'}
        }

        unused = graph.find_unused_imports(symbols_by_file)

        # sys should be marked as unused
        assert len(unused) == 1
        assert unused[0].module_name == 'sys'


class TestPythonImportExtraction:
    """Test Python import extraction."""

    def test_extract_basic_import(self, tmp_path):
        """Test extracting basic import statement."""
        code = "import os\nimport sys\n"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        imports = extract_python_imports(test_file)

        assert len(imports) == 2
        assert imports[0].module_name == 'os'
        assert imports[1].module_name == 'sys'
        assert all(stmt.import_type == 'import' for stmt in imports)

    def test_extract_from_import(self, tmp_path):
        """Test extracting from-import statement."""
        code = "from os import path, environ\n"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        imports = extract_python_imports(test_file)

        assert len(imports) == 1
        assert imports[0].module_name == 'os'
        assert imports[0].imported_names == ['path', 'environ']
        assert imports[0].import_type == 'from_import'

    def test_extract_star_import(self, tmp_path):
        """Test extracting star import."""
        code = "from os import *\n"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        imports = extract_python_imports(test_file)

        assert len(imports) == 1
        assert imports[0].import_type == 'star_import'
        assert imports[0].imported_names == ['*']

    def test_extract_aliased_import(self, tmp_path):
        """Test extracting aliased import."""
        code = "import numpy as np\n"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        imports = extract_python_imports(test_file)

        assert len(imports) == 1
        assert imports[0].module_name == 'numpy'
        assert imports[0].alias == 'np'

    def test_extract_symbols(self, tmp_path):
        """Test extracting symbol usage."""
        code = """
import os
import sys

def main():
    path = os.path.join('a', 'b')
    print(os.environ)
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        symbols = extract_python_symbols(test_file)

        assert 'os' in symbols
        assert 'print' in symbols
        # 'sys' imported but not used, so won't be in used symbols


class TestImportsAdapter:
    """Test ImportsAdapter."""

    def test_adapter_registration(self):
        """Test that adapter is properly registered."""
        from reveal.adapters.base import get_adapter_class

        adapter_class = get_adapter_class('imports')
        assert adapter_class is ImportsAdapter

    def test_get_help(self):
        """Test adapter help documentation."""
        help_data = ImportsAdapter.get_help()

        assert help_data['name'] == 'imports'
        assert 'description' in help_data
        assert 'examples' in help_data
        assert len(help_data['examples']) > 0

    def test_get_metadata(self):
        """Test adapter metadata."""
        adapter = ImportsAdapter()
        metadata = adapter.get_metadata()

        assert 'status' in metadata

    def test_analyze_directory(self, tmp_path):
        """Test analyzing a directory with Python files."""
        # Create test files
        (tmp_path / "a.py").write_text("import os\nimport sys\n")
        (tmp_path / "b.py").write_text("from pathlib import Path\n")

        adapter = ImportsAdapter()
        result = adapter.get_structure(f"imports://{tmp_path}")

        assert 'type' in result
        assert 'files' in result or 'error' not in result
