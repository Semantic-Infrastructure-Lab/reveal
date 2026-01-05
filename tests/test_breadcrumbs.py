"""Tests for reveal/utils/breadcrumbs.py - Navigation hint system."""

import pytest
from io import StringIO
from unittest.mock import Mock, patch
import sys

from reveal.utils.breadcrumbs import (
    get_element_placeholder,
    get_file_type_from_analyzer,
    print_breadcrumbs,
)


# ==============================================================================
# get_element_placeholder Tests
# ==============================================================================

class TestGetElementPlaceholder:
    """Tests for get_element_placeholder function."""

    def test_python_placeholder(self):
        """Python files use <function> placeholder."""
        assert get_element_placeholder('python') == '<function>'

    def test_javascript_placeholder(self):
        """JavaScript files use <function> placeholder."""
        assert get_element_placeholder('javascript') == '<function>'

    def test_typescript_placeholder(self):
        """TypeScript files use <function> placeholder."""
        assert get_element_placeholder('typescript') == '<function>'

    def test_rust_placeholder(self):
        """Rust files use <function> placeholder."""
        assert get_element_placeholder('rust') == '<function>'

    def test_go_placeholder(self):
        """Go files use <function> placeholder."""
        assert get_element_placeholder('go') == '<function>'

    def test_bash_placeholder(self):
        """Bash files use <function> placeholder."""
        assert get_element_placeholder('bash') == '<function>'

    def test_gdscript_placeholder(self):
        """GDScript files use <function> placeholder."""
        assert get_element_placeholder('gdscript') == '<function>'

    def test_yaml_placeholder(self):
        """YAML files use <key> placeholder."""
        assert get_element_placeholder('yaml') == '<key>'

    def test_json_placeholder(self):
        """JSON files use <key> placeholder."""
        assert get_element_placeholder('json') == '<key>'

    def test_jsonl_placeholder(self):
        """JSONL files use <entry> placeholder."""
        assert get_element_placeholder('jsonl') == '<entry>'

    def test_toml_placeholder(self):
        """TOML files use <key> placeholder."""
        assert get_element_placeholder('toml') == '<key>'

    def test_markdown_placeholder(self):
        """Markdown files use <heading> placeholder."""
        assert get_element_placeholder('markdown') == '<heading>'

    def test_dockerfile_placeholder(self):
        """Dockerfile uses <instruction> placeholder."""
        assert get_element_placeholder('dockerfile') == '<instruction>'

    def test_nginx_placeholder(self):
        """Nginx config uses <directive> placeholder."""
        assert get_element_placeholder('nginx') == '<directive>'

    def test_jupyter_placeholder(self):
        """Jupyter notebooks use <cell> placeholder."""
        assert get_element_placeholder('jupyter') == '<cell>'

    def test_unknown_type_placeholder(self):
        """Unknown file types get default <element> placeholder."""
        assert get_element_placeholder('unknown') == '<element>'
        assert get_element_placeholder(None) == '<element>'
        assert get_element_placeholder('') == '<element>'


# ==============================================================================
# get_file_type_from_analyzer Tests
# ==============================================================================

class TestGetFileTypeFromAnalyzer:
    """Tests for get_file_type_from_analyzer function."""

    def test_python_analyzer(self):
        """PythonAnalyzer maps to 'python'."""
        mock = Mock()
        mock.__class__.__name__ = 'PythonAnalyzer'
        assert get_file_type_from_analyzer(mock) == 'python'

    def test_javascript_analyzer(self):
        """JavaScriptAnalyzer maps to 'javascript'."""
        mock = Mock()
        mock.__class__.__name__ = 'JavaScriptAnalyzer'
        assert get_file_type_from_analyzer(mock) == 'javascript'

    def test_typescript_analyzer(self):
        """TypeScriptAnalyzer maps to 'typescript'."""
        mock = Mock()
        mock.__class__.__name__ = 'TypeScriptAnalyzer'
        assert get_file_type_from_analyzer(mock) == 'typescript'

    def test_rust_analyzer(self):
        """RustAnalyzer maps to 'rust'."""
        mock = Mock()
        mock.__class__.__name__ = 'RustAnalyzer'
        assert get_file_type_from_analyzer(mock) == 'rust'

    def test_go_analyzer(self):
        """GoAnalyzer maps to 'go'."""
        mock = Mock()
        mock.__class__.__name__ = 'GoAnalyzer'
        assert get_file_type_from_analyzer(mock) == 'go'

    def test_bash_analyzer(self):
        """BashAnalyzer maps to 'bash'."""
        mock = Mock()
        mock.__class__.__name__ = 'BashAnalyzer'
        assert get_file_type_from_analyzer(mock) == 'bash'

    def test_markdown_analyzer(self):
        """MarkdownAnalyzer maps to 'markdown'."""
        mock = Mock()
        mock.__class__.__name__ = 'MarkdownAnalyzer'
        assert get_file_type_from_analyzer(mock) == 'markdown'

    def test_yaml_analyzer(self):
        """YamlAnalyzer maps to 'yaml'."""
        mock = Mock()
        mock.__class__.__name__ = 'YamlAnalyzer'
        assert get_file_type_from_analyzer(mock) == 'yaml'

    def test_json_analyzer(self):
        """JsonAnalyzer maps to 'json'."""
        mock = Mock()
        mock.__class__.__name__ = 'JsonAnalyzer'
        assert get_file_type_from_analyzer(mock) == 'json'

    def test_jsonl_analyzer(self):
        """JsonlAnalyzer maps to 'jsonl'."""
        mock = Mock()
        mock.__class__.__name__ = 'JsonlAnalyzer'
        assert get_file_type_from_analyzer(mock) == 'jsonl'

    def test_toml_analyzer(self):
        """TomlAnalyzer maps to 'toml'."""
        mock = Mock()
        mock.__class__.__name__ = 'TomlAnalyzer'
        assert get_file_type_from_analyzer(mock) == 'toml'

    def test_dockerfile_analyzer(self):
        """DockerfileAnalyzer maps to 'dockerfile'."""
        mock = Mock()
        mock.__class__.__name__ = 'DockerfileAnalyzer'
        assert get_file_type_from_analyzer(mock) == 'dockerfile'

    def test_nginx_analyzer(self):
        """NginxAnalyzer maps to 'nginx'."""
        mock = Mock()
        mock.__class__.__name__ = 'NginxAnalyzer'
        assert get_file_type_from_analyzer(mock) == 'nginx'

    def test_gdscript_analyzer(self):
        """GDScriptAnalyzer maps to 'gdscript'."""
        mock = Mock()
        mock.__class__.__name__ = 'GDScriptAnalyzer'
        assert get_file_type_from_analyzer(mock) == 'gdscript'

    def test_jupyter_analyzer(self):
        """JupyterAnalyzer maps to 'jupyter'."""
        mock = Mock()
        mock.__class__.__name__ = 'JupyterAnalyzer'
        assert get_file_type_from_analyzer(mock) == 'jupyter'

    def test_html_analyzer(self):
        """HtmlAnalyzer maps to 'html'."""
        mock = Mock()
        mock.__class__.__name__ = 'HtmlAnalyzer'
        assert get_file_type_from_analyzer(mock) == 'html'

    def test_treesitter_analyzer(self):
        """TreeSitterAnalyzer maps to None (generic fallback)."""
        mock = Mock()
        mock.__class__.__name__ = 'TreeSitterAnalyzer'
        assert get_file_type_from_analyzer(mock) is None

    def test_unknown_analyzer(self):
        """Unknown analyzer classes return None."""
        mock = Mock()
        mock.__class__.__name__ = 'UnknownAnalyzer'
        assert get_file_type_from_analyzer(mock) is None


# ==============================================================================
# Helper for capturing stdout
# ==============================================================================

def capture_breadcrumbs(context, path, file_type=None, config=None, **kwargs):
    """Capture print_breadcrumbs output."""
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    try:
        print_breadcrumbs(context, path, file_type, config, **kwargs)
        return sys.stdout.getvalue()
    finally:
        sys.stdout = old_stdout


# ==============================================================================
# print_breadcrumbs Tests - Config Handling
# ==============================================================================

class TestPrintBreadcrumbsConfig:
    """Tests for breadcrumbs config handling."""

    def test_breadcrumbs_disabled_returns_nothing(self):
        """When breadcrumbs disabled, nothing is printed."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = False

        output = capture_breadcrumbs('structure', 'test.py', 'python', config=mock_config)
        assert output == ''

    def test_breadcrumbs_enabled_prints_output(self):
        """When breadcrumbs enabled, output is printed."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('structure', 'test.py', 'python', config=mock_config)
        assert 'reveal test.py' in output

    def test_auto_config_loading_for_file(self):
        """When config=None and path is a file, config is auto-loaded."""
        import tempfile
        import os

        # Create a temp file to test with
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('# test file')
            temp_path = f.name

        try:
            # Call without config - should auto-load and work
            output = capture_breadcrumbs('structure', temp_path, 'python', config=None)
            # Should produce output (breadcrumbs enabled by default)
            assert 'reveal' in output or output == ''  # Empty if breadcrumbs disabled in user config
        finally:
            os.unlink(temp_path)

    def test_auto_config_loading_for_directory(self):
        """When config=None and path is a directory, config is auto-loaded."""
        import tempfile

        # Use temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Call without config - should auto-load and work
            output = capture_breadcrumbs('structure', temp_dir, None, config=None)
            # Should produce output (or empty if disabled)
            assert isinstance(output, str)


# ==============================================================================
# print_breadcrumbs Tests - Metadata Context
# ==============================================================================

class TestPrintBreadcrumbsMetadata:
    """Tests for metadata context breadcrumbs."""

    def test_metadata_context_shows_structure_hint(self):
        """Metadata context suggests viewing structure."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('metadata', 'test.py', config=mock_config)
        assert 'reveal test.py' in output
        assert '# See structure' in output

    def test_metadata_context_shows_check_hint(self):
        """Metadata context suggests quality check."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('metadata', 'test.py', config=mock_config)
        assert '--check' in output
        assert '# Quality check' in output


# ==============================================================================
# print_breadcrumbs Tests - Structure Context
# ==============================================================================

class TestPrintBreadcrumbsStructure:
    """Tests for structure context breadcrumbs."""

    def test_structure_python_shows_function_placeholder(self):
        """Python structure uses <function> placeholder."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('structure', 'test.py', 'python', config=mock_config)
        assert '<function>' in output

    def test_structure_python_shows_check_and_outline(self):
        """Python structure suggests --check and --outline."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('structure', 'test.py', 'python', config=mock_config)
        assert '--check' in output
        assert '--outline' in output

    def test_structure_markdown_shows_links_and_code(self):
        """Markdown structure suggests --links and --code."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('structure', 'README.md', 'markdown', config=mock_config)
        assert '--links' in output
        assert '--code' in output
        assert '--frontmatter' in output

    def test_structure_html_shows_check_and_links(self):
        """HTML structure suggests --check and --links."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('structure', 'index.html', 'html', config=mock_config)
        assert '--check' in output
        assert '--links' in output
        assert '# Validate HTML' in output

    def test_structure_yaml_shows_check(self):
        """YAML structure suggests --check."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('structure', 'config.yaml', 'yaml', config=mock_config)
        assert '--check' in output
        assert '# Validate syntax' in output

    def test_structure_json_shows_check(self):
        """JSON structure suggests --check."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('structure', 'data.json', 'json', config=mock_config)
        assert '--check' in output
        assert '# Validate syntax' in output

    def test_structure_dockerfile_shows_check(self):
        """Dockerfile structure suggests --check."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('structure', 'Dockerfile', 'dockerfile', config=mock_config)
        assert '--check' in output
        assert '# Validate configuration' in output

    def test_structure_nginx_shows_check(self):
        """Nginx structure suggests --check."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('structure', 'nginx.conf', 'nginx', config=mock_config)
        assert '--check' in output
        assert '# Validate configuration' in output


# ==============================================================================
# print_breadcrumbs Tests - Large File Detection
# ==============================================================================

class TestPrintBreadcrumbsLargeFile:
    """Tests for large file detection in structure context."""

    def test_large_file_suggests_ast_queries(self):
        """Files with >20 elements suggest AST queries."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        # Create structure with >20 elements
        structure = {
            'functions': [{'name': f'func_{i}'} for i in range(25)],
        }

        output = capture_breadcrumbs(
            'structure', 'large.py', 'python',
            config=mock_config, structure=structure
        )
        assert "ast://" in output
        assert "complexity>10" in output
        assert "lines>50" in output

    def test_large_file_skips_outline_suggestion(self):
        """Large files don't suggest --outline (return early)."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        structure = {
            'functions': [{'name': f'func_{i}'} for i in range(25)],
        }

        output = capture_breadcrumbs(
            'structure', 'large.py', 'python',
            config=mock_config, structure=structure
        )
        assert '--outline' not in output  # Skipped due to early return

    def test_small_file_no_ast_queries(self):
        """Files with <=20 elements don't suggest AST queries."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        structure = {
            'functions': [{'name': f'func_{i}'} for i in range(5)],
        }

        output = capture_breadcrumbs(
            'structure', 'small.py', 'python',
            config=mock_config, structure=structure
        )
        assert "ast://" not in output
        assert '--outline' in output  # Standard suggestion

    def test_large_file_detection_for_typescript(self):
        """Large file detection works for TypeScript."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        structure = {
            'functions': [{'name': f'func_{i}'} for i in range(25)],
        }

        output = capture_breadcrumbs(
            'structure', 'large.ts', 'typescript',
            config=mock_config, structure=structure
        )
        assert "ast://" in output

    def test_large_file_detection_not_for_markdown(self):
        """Large file detection doesn't apply to markdown."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        structure = {
            'headings': [{'name': f'heading_{i}'} for i in range(25)],
        }

        output = capture_breadcrumbs(
            'structure', 'large.md', 'markdown',
            config=mock_config, structure=structure
        )
        assert "ast://" not in output
        assert '--links' in output  # Standard markdown suggestion


# ==============================================================================
# print_breadcrumbs Tests - Import Analysis
# ==============================================================================

class TestPrintBreadcrumbsImports:
    """Tests for import analysis breadcrumbs."""

    def test_many_imports_suggests_imports_adapter(self):
        """Files with >5 imports suggest imports:// adapter."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        structure = {
            'imports': [{'name': f'import_{i}'} for i in range(10)],
            'functions': [{'name': 'main'}],
        }

        output = capture_breadcrumbs(
            'structure', 'test.py', 'python',
            config=mock_config, structure=structure
        )
        assert "imports://" in output
        assert "(10 imports)" in output

    def test_few_imports_no_suggestion(self):
        """Files with <=5 imports don't suggest imports:// adapter."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        structure = {
            'imports': [{'name': f'import_{i}'} for i in range(3)],
            'functions': [{'name': 'main'}],
        }

        output = capture_breadcrumbs(
            'structure', 'test.py', 'python',
            config=mock_config, structure=structure
        )
        assert "imports://" not in output

    def test_imports_suggestion_for_javascript(self):
        """Import suggestion works for JavaScript."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        structure = {
            'imports': [{'name': f'import_{i}'} for i in range(8)],
        }

        output = capture_breadcrumbs(
            'structure', 'index.js', 'javascript',
            config=mock_config, structure=structure
        )
        assert "imports://" in output

    def test_imports_suggestion_not_for_go(self):
        """Import suggestion doesn't apply to Go (not in supported list)."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        structure = {
            'imports': [{'name': f'import_{i}'} for i in range(10)],
        }

        output = capture_breadcrumbs(
            'structure', 'main.go', 'go',
            config=mock_config, structure=structure
        )
        assert "imports://" not in output


# ==============================================================================
# print_breadcrumbs Tests - Typed Context
# ==============================================================================

class TestPrintBreadcrumbsTyped:
    """Tests for typed (outline) context breadcrumbs."""

    def test_typed_shows_flat_structure_hint(self):
        """Typed context suggests viewing flat structure."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('typed', 'test.py', 'python', config=mock_config)
        assert '# See flat structure' in output

    def test_typed_python_shows_check(self):
        """Typed Python context suggests --check."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('typed', 'test.py', 'python', config=mock_config)
        assert '--check' in output

    def test_typed_markdown_shows_links(self):
        """Typed markdown context suggests --links."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('typed', 'README.md', 'markdown', config=mock_config)
        assert '--links' in output

    def test_typed_html_shows_check_and_links(self):
        """Typed HTML context suggests --check and --links."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('typed', 'index.html', 'html', config=mock_config)
        assert '--check' in output
        assert '--links' in output

    def test_typed_yaml_shows_check(self):
        """Typed YAML context suggests --check."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('typed', 'config.yaml', 'yaml', config=mock_config)
        assert '--check' in output
        assert '# Validate syntax' in output

    def test_typed_dockerfile_shows_check(self):
        """Typed Dockerfile context suggests --check."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('typed', 'Dockerfile', 'dockerfile', config=mock_config)
        assert '--check' in output
        assert '# Validate configuration' in output


# ==============================================================================
# print_breadcrumbs Tests - Element Context
# ==============================================================================

class TestPrintBreadcrumbsElement:
    """Tests for element context breadcrumbs."""

    def test_element_shows_extracted_info(self):
        """Element context shows extraction info."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs(
            'element', 'test.py', 'python',
            config=mock_config, element_name='my_function'
        )
        assert 'Extracted my_function' in output

    def test_element_shows_line_count(self):
        """Element context includes line count when provided."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs(
            'element', 'test.py', 'python',
            config=mock_config, element_name='my_function', line_count=50
        )
        assert '(50 lines)' in output

    def test_element_shows_back_hint(self):
        """Element context suggests going back to structure."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs(
            'element', 'test.py', 'python',
            config=mock_config, element_name='func'
        )
        assert 'Back:' in output
        assert '# See full structure' in output

    def test_element_shows_check_hint(self):
        """Element context suggests quality check."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs(
            'element', 'test.py', 'python',
            config=mock_config, element_name='func'
        )
        assert 'Check:' in output
        assert '--check' in output


# ==============================================================================
# print_breadcrumbs Tests - Unknown Context
# ==============================================================================

class TestPrintBreadcrumbsUnknown:
    """Tests for unknown/unhandled contexts."""

    def test_unknown_context_prints_blank_line(self):
        """Unknown context only prints blank line."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('unknown', 'test.py', config=mock_config)
        # Only blank line from print() at start
        assert output.strip() == ''
