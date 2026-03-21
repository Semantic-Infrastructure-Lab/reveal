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


    def test_init_py_imports_not_flagged_as_unused(self):
        """Imports in __init__.py should never be flagged — they are re-exports."""
        imports = [
            ImportStatement(
                file_path=Path('mypackage/__init__.py'),
                line_number=1,
                module_name='mypackage.adapter',
                imported_names=['MyAdapter'],
                is_relative=False,
                import_type='from_import',
                source_line='from mypackage.adapter import MyAdapter',
            ),
            ImportStatement(
                file_path=Path('mypackage/__init__.py'),
                line_number=2,
                module_name='mypackage.renderer',
                imported_names=['MyRenderer'],
                is_relative=False,
                import_type='from_import',
                source_line='from mypackage.renderer import MyRenderer',
            ),
        ]

        graph = ImportGraph.from_imports(imports)
        # Neither name appears in symbols_by_file (simulates "not used internally")
        symbols_by_file: dict = {Path('mypackage/__init__.py'): set()}

        unused = graph.find_unused_imports(symbols_by_file)

        # Both imports are in __init__.py — they are re-exports, should not be flagged
        assert len(unused) == 0, (
            "__init__.py imports are re-exports and must never be flagged as unused"
        )


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

        adapter = ImportsAdapter(str(tmp_path))
        result = adapter.get_structure()

        assert 'type' in result
        assert 'files' in result or 'error' not in result

    def test_query_params_flag_style(self, tmp_path):
        """Test flag-style query params (?circular vs ?circular=true)."""
        # Create test files with circular dependency
        (tmp_path / "a.py").write_text("from . import b\n")
        (tmp_path / "b.py").write_text("from . import a\n")

        # Test flag-style param (?circular)
        result_flag = ImportsAdapter(str(tmp_path), 'circular').get_structure()
        assert result_flag.get('type') == 'circular_dependencies'
        assert 'cycles' in result_flag

        # Test key-value param (?circular=true)
        result_kv = ImportsAdapter(str(tmp_path), 'circular=true').get_structure()
        assert result_kv.get('type') == 'circular_dependencies'
        assert 'cycles' in result_kv

        # Both should produce same results
        assert result_flag.get('count') == result_kv.get('count')

    def test_path_not_found(self):
        """Test error handling for non-existent paths."""
        adapter = ImportsAdapter('/nonexistent/path')
        result = adapter.get_structure()

        assert 'error' in result
        assert 'Path not found' in result['error']

    def test_unused_query_param(self, tmp_path):
        """Test ?unused query parameter."""
        # Create file with unused imports
        (tmp_path / "test.py").write_text("import os\nimport sys\n\nprint('hello')\n")

        result = ImportsAdapter(str(tmp_path), 'unused').get_structure()
        assert result['type'] == 'unused_imports'
        assert isinstance(result.get('unused'), list)

    def test_violations_query_param(self, tmp_path):
        """Test ?violations query parameter returns not-configured when no .reveal.yaml."""
        (tmp_path / "test.py").write_text("import os\n\nprint('hello')\n")

        result = ImportsAdapter(str(tmp_path), 'violations').get_structure()
        assert result['type'] == 'layer_violations'
        assert 'violations' in result
        # No config → count=0 and note explains configuration
        assert result['count'] == 0
        assert 'note' in result
        assert 'reveal.yaml' in result['note'].lower() or '.reveal.yaml' in result['note']

    def test_violations_detects_layer_violation(self, tmp_path):
        """Layer violation is reported when import crosses a deny boundary."""
        (tmp_path / "api").mkdir()
        (tmp_path / "db").mkdir()
        (tmp_path / "api" / "__init__.py").write_text("")
        (tmp_path / "db" / "__init__.py").write_text("")
        # api/routes.py imports from db/ — violates the deny rule
        (tmp_path / "api" / "routes.py").write_text("from db.session import Session\n")
        (tmp_path / "db" / "session.py").write_text("class Session: pass\n")
        (tmp_path / ".reveal.yaml").write_text(
            "architecture:\n"
            "  layers:\n"
            "    - name: presentation\n"
            "      paths: [api/]\n"
            "      allow_imports: []\n"
            "      deny_imports: [db/]\n"
        )

        result = ImportsAdapter(str(tmp_path), 'violations').get_structure()
        assert result['type'] == 'layer_violations'
        assert result['count'] == 1
        v = result['violations'][0]
        assert 'api/routes.py' in v['from_file']
        assert v['layer'] == 'presentation'

    def test_violations_no_violation_when_import_allowed(self, tmp_path):
        """No violation reported when import is within allowed_imports."""
        (tmp_path / "api").mkdir()
        (tmp_path / "models").mkdir()
        (tmp_path / "api" / "__init__.py").write_text("")
        (tmp_path / "models" / "__init__.py").write_text("")
        (tmp_path / "api" / "views.py").write_text("from models.user import User\n")
        (tmp_path / "models" / "user.py").write_text("class User: pass\n")
        (tmp_path / ".reveal.yaml").write_text(
            "architecture:\n"
            "  layers:\n"
            "    - name: presentation\n"
            "      paths: [api/]\n"
            "      allow_imports: [models/]\n"
            "      deny_imports: []\n"
        )

        result = ImportsAdapter(str(tmp_path), 'violations').get_structure()
        assert result['count'] == 0, f"Expected 0 violations, got: {result['violations']}"

    def test_get_element(self, tmp_path):
        """Test get_element method for specific file."""
        # Create test file
        (tmp_path / "test.py").write_text("import os\nimport sys\n")

        adapter = ImportsAdapter(str(tmp_path))
        adapter.get_structure()

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

        adapter = ImportsAdapter(str(tmp_path), 'circular')
        result = adapter.get_structure()

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

        adapter = ImportsAdapter(str(tmp_path))
        adapter.get_structure()

        # Get the internal graph
        graph = adapter._graph
        logging_file = tmp_path / "logging.py"

        # The dependency graph should NOT have logging.py depending on itself
        assert logging_file not in graph.dependencies.get(logging_file, set()), (
            "Self-dependency should not be added to the import graph"
        )


class TestResolverPureRelativeImports:
    """Regression tests for _resolve_relative with pure package-relative imports.

    Bug: `from . import X` (empty module_name) resolved to __init__.py instead of
    X.py, creating false-positive cycle edges __init__.py → adapter.py → __init__.py.
    Fixed in session wicked-grid-0321.
    """

    def test_from_dot_import_resolves_to_submodule(self, tmp_path):
        """from . import refs should resolve to refs.py, not __init__.py."""
        from reveal.analyzers.imports.resolver import resolve_python_import

        # Simulate: adapters/git/__init__.py and adapters/git/refs.py both exist.
        (tmp_path / "__init__.py").write_text("from .adapter import GitAdapter\n")
        (tmp_path / "refs.py").write_text("def list_branches(): pass\n")
        (tmp_path / "adapter.py").write_text("from . import refs\n")

        stmt = ImportStatement(
            file_path=tmp_path / "adapter.py",
            line_number=1,
            module_name="",
            imported_names=["refs"],
            is_relative=True,
            import_type="from_import",
            level=1,
            source_line="from . import refs",
        )
        resolved = resolve_python_import(stmt, base_path=tmp_path)

        assert resolved == tmp_path / "refs.py", (
            "from . import refs should resolve to refs.py, not __init__.py"
        )

    def test_from_dot_import_aliased_resolves_to_submodule(self, tmp_path):
        """from . import query as q should resolve to query.py (strip alias)."""
        from reveal.analyzers.imports.resolver import resolve_python_import

        (tmp_path / "__init__.py").write_text("")
        (tmp_path / "query.py").write_text("def run(): pass\n")

        stmt = ImportStatement(
            file_path=tmp_path / "adapter.py",
            line_number=1,
            module_name="",
            imported_names=["query as query_module"],  # tree-sitter gives full text
            is_relative=True,
            import_type="from_import",
            level=1,
            source_line="from . import query as query_module",
        )
        resolved = resolve_python_import(stmt, base_path=tmp_path)

        assert resolved == tmp_path / "query.py", (
            "Aliased 'from . import X as Y' should resolve to X.py, not __init__.py"
        )

    def test_from_dot_import_class_falls_back_to_init(self, tmp_path):
        """from . import MyClass (no sibling module) should fall back to __init__.py."""
        from reveal.analyzers.imports.resolver import resolve_python_import

        (tmp_path / "__init__.py").write_text("class MyClass: pass\n")
        # No MyClass.py exists — MyClass is defined in __init__.py

        stmt = ImportStatement(
            file_path=tmp_path / "consumer.py",
            line_number=1,
            module_name="",
            imported_names=["MyClass"],
            is_relative=True,
            import_type="from_import",
            level=1,
            source_line="from . import MyClass",
        )
        resolved = resolve_python_import(stmt, base_path=tmp_path)

        assert resolved == tmp_path / "__init__.py", (
            "When imported name is not a sibling module, fall back to __init__.py"
        )

    def test_init_re_export_pattern_no_false_cycle(self, tmp_path):
        """__init__.py re-exporting from adapter.py should not create a cycle.

        Structure: __init__.py imports GitAdapter from adapter.py,
        adapter.py imports refs, commits (sibling modules).
        This is the real pattern that triggered false-positive cycles.
        """
        # Create the __init__.py → adapter.py → refs.py structure
        (tmp_path / "__init__.py").write_text("from .adapter import GitAdapter\n")
        (tmp_path / "adapter.py").write_text(
            "from . import refs\nfrom . import commits\nclass GitAdapter: pass\n"
        )
        (tmp_path / "refs.py").write_text("def list_branches(): pass\n")
        (tmp_path / "commits.py").write_text("def get_history(): pass\n")

        adapter = ImportsAdapter(str(tmp_path), 'circular')
        result = adapter.get_structure()

        assert result['type'] == 'circular_dependencies'
        assert result['count'] == 0, (
            "__init__.py re-export pattern should not be flagged as circular. "
            "Got cycles: " + str(result.get('cycles', []))
        )

    def test_multi_dot_relative_import_level_extracted(self, tmp_path):
        """Multi-dot relative imports (from .. import X, from ... import Y) must
        report the correct level — not 0. Level=0 on a relative import causes
        the resolver to misidentify the target, producing false circular deps.

        Regression for BACK-101: tree-sitter-python wraps dots in import_prefix
        node; old code only checked direct '.' children of relative_import.
        """
        code = (
            "from . import a\n"        # level 1
            "from .. import b\n"       # level 2
            "from ... import c\n"      # level 3
            "from ..pkg import d\n"    # level 2, named module
            "from ...pkg.sub import e\n"  # level 3, dotted module
        )
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        imports = extract_python_imports(test_file)
        levels = {imp.module_name or imp.imported_names[0]: imp.level for imp in imports}

        assert levels['a'] == 1
        assert levels['b'] == 2
        assert levels['c'] == 3
        assert levels['pkg'] == 2
        assert levels.get('pkg.sub', levels.get('e')) == 3  # module or fallback

    def test_multi_dot_relative_import_no_false_cycle(self, tmp_path):
        """Inline multi-dot relative imports inside functions must not create
        false circular dependency edges. This is the exact pattern from
        reveal/cli/handlers/introspection.py that triggered BACK-101.
        """
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")

        handlers = pkg / "handlers"
        handlers.mkdir()
        (handlers / "__init__.py").write_text("")

        # introspection.py uses inline 'from .. import X' (level=2)
        # which should resolve UP to pkg/, not to handlers/__init__.py
        (handlers / "introspection.py").write_text(
            "def handle():\n"
            "    from .. import utils\n"
        )
        (pkg / "utils.py").write_text("def helper(): pass\n")

        adapter = ImportsAdapter(str(handlers), 'circular')
        result = adapter.get_structure()

        assert result['count'] == 0, (
            "Multi-dot inline relative import should not produce a false cycle. "
            "Got cycles: " + str(result.get('cycles', []))
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

        adapter = ImportsAdapter(str(tmp_path))
        result = adapter.get_structure()

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

        adapter = ImportsAdapter(str(tmp_path))
        result = adapter.get_structure()

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

        adapter = ImportsAdapter(str(tmp_path), 'unused')
        result = adapter.get_structure()

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        ImportsRenderer.render_structure(result, format='text')

        sys.stdout = old_stdout
        output = captured_output.getvalue()

        # Should contain unused imports info
        assert 'unused' in output.lower() or 'import' in output.lower()
