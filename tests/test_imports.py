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

    def test_query_params_flag_style(self, tmp_path):
        """Test flag-style query params (?circular vs ?circular=true)."""
        # Create test files with circular dependency
        (tmp_path / "a.py").write_text("from . import b\n")
        (tmp_path / "b.py").write_text("from . import a\n")

        adapter = ImportsAdapter()

        # Test flag-style param (?circular)
        result_flag = adapter.get_structure(f"imports://{tmp_path}?circular")
        assert result_flag.get('type') == 'circular_dependencies'
        assert 'cycles' in result_flag

        # Test key-value param (?circular=true)
        result_kv = adapter.get_structure(f"imports://{tmp_path}?circular=true")
        assert result_kv.get('type') == 'circular_dependencies'
        assert 'cycles' in result_kv

        # Both should produce same results
        assert result_flag.get('count') == result_kv.get('count')

    def test_path_not_found(self):
        """Test error handling for non-existent paths."""
        adapter = ImportsAdapter()
        result = adapter.get_structure("imports:///nonexistent/path")

        assert 'error' in result
        assert 'Path not found' in result['error']

    def test_unused_query_param(self, tmp_path):
        """Test ?unused query parameter."""
        adapter = ImportsAdapter()

        # Create file with unused imports
        (tmp_path / "test.py").write_text("import os\nimport sys\n\nprint('hello')\n")

        # Test unused detection
        result = adapter.get_structure(f"imports://{tmp_path}?unused")
        assert result['type'] == 'unused_imports'
        assert isinstance(result.get('unused'), list)

    def test_violations_query_param(self, tmp_path):
        """Test ?violations query parameter."""
        adapter = ImportsAdapter()

        # Create test file
        (tmp_path / "test.py").write_text("import os\n\nprint('hello')\n")

        # Test violations (placeholder - actual layer violations need config)
        result = adapter.get_structure(f"imports://{tmp_path}?violations")
        assert result['type'] == 'layer_violations'
        assert 'violations' in result

    def test_get_element(self, tmp_path):
        """Test get_element method for specific file."""
        adapter = ImportsAdapter()

        # Create test file
        (tmp_path / "test.py").write_text("import os\nimport sys\n")

        # First, analyze the directory
        adapter.get_structure(f"imports://{tmp_path}")

        # Then get specific element
        result = adapter.get_element("test.py")
        assert result is not None
        assert result['file'].endswith('test.py')
        assert result['count'] == 2
        assert len(result['imports']) == 2

        # Test non-existent element
        result_missing = adapter.get_element("nonexistent.py")
        assert result_missing is None

    def test_get_element_before_analysis(self):
        """Test get_element returns None before analysis."""
        adapter = ImportsAdapter()
        result = adapter.get_element("anything.py")
        assert result is None

    def test_get_metadata_before_analysis(self):
        """Test get_metadata before analysis."""
        adapter = ImportsAdapter()
        metadata = adapter.get_metadata()
        assert metadata['status'] == 'not_analyzed'


class TestStdlibShadowing:
    """Test handling of local files that shadow stdlib modules."""

    def test_logging_py_importing_stdlib_logging(self, tmp_path):
        """Test that logging.py importing stdlib logging doesn't create false circular.

        When a file like 'logging.py' does 'import logging' (intending stdlib),
        the resolver finds the local file first. This should NOT create a
        self-dependency (logging.py -> logging.py) that gets flagged as circular.

        Regression test for: https://github.com/scottsen/reveal/issues/XX
        """
        # Create a directory structure with a local logging.py
        (tmp_path / "logging.py").write_text("import logging\n\nlogger = logging.getLogger(__name__)\n")

        adapter = ImportsAdapter()
        result = adapter.get_structure(f"imports://{tmp_path}?circular")

        # Should find no cycles - the self-reference should be filtered out
        assert result['type'] == 'circular_dependencies'
        assert result['count'] == 0, (
            "Self-reference (logging.py -> logging.py) should not be flagged as circular. "
            "Local files importing their stdlib counterparts should be ignored."
        )

    def test_self_import_not_added_to_graph(self, tmp_path):
        """Test that resolved imports equal to source file are not added as dependencies."""
        # Create logging.py that imports logging (stdlib)
        (tmp_path / "logging.py").write_text("import logging\n")

        adapter = ImportsAdapter()
        adapter.get_structure(f"imports://{tmp_path}")

        # Get the internal graph
        graph = adapter._graph
        logging_file = tmp_path / "logging.py"

        # The dependency graph should NOT have logging.py depending on itself
        assert logging_file not in graph.dependencies.get(logging_file, set()), (
            "Self-dependency should not be added to the import graph"
        )


class TestImportsAdapterSchema:
    """Test schema generation for AI agent integration."""

    def test_get_schema(self):
        """Should return machine-readable schema."""
        schema = ImportsAdapter.get_schema()

        assert schema is not None
        assert schema['adapter'] == 'imports'
        assert 'description' in schema
        assert 'uri_syntax' in schema
        assert 'imports://' in schema['uri_syntax']

    def test_schema_query_params(self):
        """Schema should document query parameters."""
        schema = ImportsAdapter.get_schema()

        assert 'query_params' in schema
        query_params = schema['query_params']

        # Should have analysis params
        assert 'unused' in query_params
        assert 'circular' in query_params
        assert 'violations' in query_params

        # Each param should have type and description
        for param_name, param_info in query_params.items():
            assert 'type' in param_info
            assert 'description' in param_info

    def test_schema_output_types(self):
        """Schema should define output types."""
        schema = ImportsAdapter.get_schema()

        assert 'output_types' in schema
        assert len(schema['output_types']) >= 2

        # Should have import output types
        output_types = [ot['type'] for ot in schema['output_types']]
        assert 'import_summary' in output_types
        assert 'unused_imports' in output_types

    def test_schema_examples(self):
        """Schema should include usage examples."""
        schema = ImportsAdapter.get_schema()

        assert 'example_queries' in schema
        assert len(schema['example_queries']) >= 3

        # Examples should have required fields
        for example in schema['example_queries']:
            assert 'uri' in example
            assert 'description' in example

    def test_schema_batch_support(self):
        """Schema should indicate batch support status."""
        schema = ImportsAdapter.get_schema()

        assert 'supports_batch' in schema
        assert 'supports_advanced' in schema

    def test_schema_supported_languages(self):
        """Schema should list supported languages."""
        schema = ImportsAdapter.get_schema()

        assert 'supported_languages' in schema
        languages = schema['supported_languages']
        assert isinstance(languages, list)
        assert 'Python' in languages


class TestImportsRenderer:
    """Test renderer output formatting."""

    def test_renderer_imports_overview(self, tmp_path):
        """Renderer should format imports overview correctly."""
        from reveal.adapters.imports import ImportsRenderer
        from io import StringIO
        import sys

        # Create test files
        test_file = tmp_path / "test.py"
        test_file.write_text("import os\nimport sys\n")

        adapter = ImportsAdapter()
        result = adapter.get_structure(f"imports://{tmp_path}")

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        ImportsRenderer.render_structure(result, format='text')

        sys.stdout = old_stdout
        output = captured_output.getvalue()

        # Should contain key sections
        assert 'Import Analysis:' in output
        assert 'Files:' in output

    def test_renderer_json_format(self, tmp_path):
        """Renderer should support JSON output."""
        import json
        from reveal.adapters.imports import ImportsRenderer
        from io import StringIO
        import sys

        # Create test files
        test_file = tmp_path / "test.py"
        test_file.write_text("import os\n")

        adapter = ImportsAdapter()
        result = adapter.get_structure(f"imports://{tmp_path}")

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        ImportsRenderer.render_structure(result, format='json')

        sys.stdout = old_stdout
        output = captured_output.getvalue()

        # Should be valid JSON
        parsed = json.loads(output)
        assert 'type' in parsed

    def test_renderer_error_handling(self):
        """Renderer should handle errors gracefully."""
        from reveal.adapters.imports import ImportsRenderer
        from io import StringIO
        import sys

        # Capture stderr (render_error outputs to stderr)
        old_stderr = sys.stderr
        sys.stderr = captured_output = StringIO()

        error = FileNotFoundError("Import analysis failed")
        ImportsRenderer.render_error(error)

        sys.stderr = old_stderr
        output = captured_output.getvalue()

        assert 'Error' in output
        assert 'Import analysis failed' in output

    def test_renderer_unused_imports(self, tmp_path):
        """Renderer should format unused imports correctly."""
        from reveal.adapters.imports import ImportsRenderer
        from io import StringIO
        import sys

        # Create test file with unused import
        test_file = tmp_path / "test.py"
        test_file.write_text("import os  # unused\nprint('hello')\n")

        adapter = ImportsAdapter()
        result = adapter.get_structure(f"imports://{tmp_path}?unused")

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        ImportsRenderer.render_structure(result, format='text')

        sys.stdout = old_stdout
        output = captured_output.getvalue()

        # Should contain unused imports info
        assert 'unused' in output.lower() or 'import' in output.lower()
