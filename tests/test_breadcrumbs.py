"""Tests for reveal/utils/breadcrumbs.py - Navigation hint system."""

import pytest
from io import StringIO
from unittest.mock import Mock, patch
import sys

from reveal.utils.breadcrumbs import (
    get_element_placeholder,
    get_file_type_from_analyzer,
    print_breadcrumbs,
    _show_breadcrumb_hint_once,
    _show_hint_once,
)
# Bound at import time, before the autouse _isolated_hint_store fixture below
# ever runs — these names keep pointing at the real disk-backed
# implementations even after the fixture monkeypatches the module
# attributes of the same names, so TestSeenHintsPersistence can exercise
# the actual read/write logic.
from reveal.utils.breadcrumbs import _load_seen_hints as _real_load_seen_hints
from reveal.utils.breadcrumbs import _save_seen_hints as _real_save_seen_hints


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
        """Markdown files use <section> placeholder (aligns with --section flag)."""
        assert get_element_placeholder('markdown') == '<section>'

    def test_dockerfile_placeholder(self):
        """Dockerfile uses <instruction> placeholder."""
        assert get_element_placeholder('dockerfile') == '<instruction>'

    def test_nginx_placeholder(self):
        """Nginx config uses <directive> placeholder."""
        assert get_element_placeholder('nginx') == '<directive>'

    def test_html_placeholder(self):
        """HTML files use <element> placeholder."""
        assert get_element_placeholder('html') == '<element>'

    def test_jupyter_placeholder(self):
        """Jupyter notebooks use <cell> placeholder."""
        assert get_element_placeholder('jupyter') == '<cell>'

    def test_sql_placeholder(self):
        """SQL files use <function> placeholder."""
        assert get_element_placeholder('sql') == '<function>'

    def test_elixir_placeholder(self):
        """Elixir files use <function> placeholder."""
        assert get_element_placeholder('elixir') == '<function>'

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
        """HTMLAnalyzer maps to 'html'."""
        mock = Mock()
        mock.__class__.__name__ = 'HTMLAnalyzer'
        assert get_file_type_from_analyzer(mock) == 'html'

    def test_hcl_analyzer(self):
        """HCLAnalyzer maps to 'terraform'."""
        mock = Mock()
        mock.__class__.__name__ = 'HCLAnalyzer'
        assert get_file_type_from_analyzer(mock) == 'terraform'

    def test_graphql_analyzer(self):
        """GraphQLAnalyzer maps to 'graphql'."""
        mock = Mock()
        mock.__class__.__name__ = 'GraphQLAnalyzer'
        assert get_file_type_from_analyzer(mock) == 'graphql'

    def test_sql_analyzer(self):
        """SQLAnalyzer maps to 'sql'."""
        mock = Mock()
        mock.__class__.__name__ = 'SQLAnalyzer'
        assert get_file_type_from_analyzer(mock) == 'sql'

    def test_tsx_analyzer(self):
        """TSXAnalyzer maps to 'typescript' (shares TS structure/hints)."""
        mock = Mock()
        mock.__class__.__name__ = 'TSXAnalyzer'
        assert get_file_type_from_analyzer(mock) == 'typescript'

    def test_elixir_analyzer(self):
        """ElixirAnalyzer maps to 'elixir'."""
        mock = Mock()
        mock.__class__.__name__ = 'ElixirAnalyzer'
        assert get_file_type_from_analyzer(mock) == 'elixir'

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


@pytest.fixture(autouse=True)
def _isolated_hint_store(monkeypatch):
    """Give every test its own in-memory `_show_hint_once` store.

    Without this, tests hit the real ~/.local/share/reveal/seen_hints.json
    (never mocked) and leak state between tests running in the same
    pytest-xdist worker — a hint shown by one test would come back
    suppressed in the next. Fresh set() per test means every test sees
    each hint_id for "the first time", matching what a single-call test
    expects; tests that specifically want to exercise the once-only
    suppression call capture_breadcrumbs twice within the same test, where
    this store persists across both calls.
    """
    store = set()
    monkeypatch.setattr('reveal.utils.breadcrumbs._load_seen_hints', lambda: set(store))
    monkeypatch.setattr('reveal.utils.breadcrumbs._save_seen_hints', lambda seen: store.update(seen))
    yield store


# ==============================================================================
# _show_breadcrumb_hint_once Tests
# ==============================================================================

class TestShowBreadcrumbHintOnce:
    """Tests for the once-per-install orientation nudge."""

    def test_first_call_points_to_agent_help(self):
        """First call in an install points new agents to --agent-help."""
        mock_hint_file = Mock()
        mock_hint_file.exists.return_value = False

        with patch('reveal.config.get_data_path', return_value=mock_hint_file):
            old_stderr = sys.stderr
            sys.stderr = StringIO()
            try:
                _show_breadcrumb_hint_once()
                output = sys.stderr.getvalue()
            finally:
                sys.stderr = old_stderr

        assert '--agent-help' in output
        assert '--disable-breadcrumbs' in output
        mock_hint_file.touch.assert_called_once()

    def test_subsequent_call_is_silent(self):
        """Once the hint file exists, nothing is printed."""
        mock_hint_file = Mock()
        mock_hint_file.exists.return_value = True

        with patch('reveal.config.get_data_path', return_value=mock_hint_file):
            old_stderr = sys.stderr
            sys.stderr = StringIO()
            try:
                _show_breadcrumb_hint_once()
                output = sys.stderr.getvalue()
            finally:
                sys.stderr = old_stderr

        assert output == ''
        mock_hint_file.touch.assert_not_called()


# ==============================================================================
# _show_hint_once Tests — the generalized, keyed version of the mechanism
# above (BACK-926 companion / BREADCRUMB_HINT_THROTTLING_2026-08-02.md)
# ==============================================================================

class TestShowHintOnce:
    """Tests for the generalized keyed show-once mechanism.

    Uses the autouse _isolated_hint_store fixture (in-memory), not real
    disk — that's covered separately by TestSeenHintsPersistence.
    """

    def test_first_call_prints_and_returns_true(self):
        output = StringIO()
        old_stdout = sys.stdout
        sys.stdout = output
        try:
            shown = _show_hint_once('demo_hint', ['line one', 'line two'])
        finally:
            sys.stdout = old_stdout

        assert shown is True
        assert output.getvalue() == 'line one\nline two\n'

    def test_second_call_same_id_is_silent_and_returns_false(self):
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            _show_hint_once('demo_hint', ['line one'])
            sys.stdout = StringIO()
            shown = _show_hint_once('demo_hint', ['line one'])
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        assert shown is False
        assert output == ''

    def test_different_hint_ids_are_independent(self):
        old_stdout = sys.stdout
        try:
            sys.stdout = StringIO()
            _show_hint_once('hint_a', ['a'])
            sys.stdout = StringIO()
            shown_b = _show_hint_once('hint_b', ['b'])
            output_b = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        assert shown_b is True
        assert output_b == 'b\n'


# ==============================================================================
# _load_seen_hints / _save_seen_hints Tests — the real disk-backed store
# (bypasses the autouse in-memory fixture; see the import comment at the
# top of this file for how)
# ==============================================================================

class TestSeenHintsPersistence:
    """Round-trip tests for the JSON set file backing _show_hint_once."""

    def test_load_missing_file_returns_empty_set(self, monkeypatch):
        mock_file = Mock()
        mock_file.exists.return_value = False
        monkeypatch.setattr('reveal.config.get_data_path', lambda name: mock_file)

        assert _real_load_seen_hints() == set()

    def test_save_then_load_round_trips(self, monkeypatch, tmp_path):
        real_file = tmp_path / 'seen_hints.json'
        monkeypatch.setattr('reveal.config.get_data_path', lambda name: real_file)

        _real_save_seen_hints({'alpha', 'beta'})

        assert _real_load_seen_hints() == {'alpha', 'beta'}

    def test_load_corrupt_file_returns_empty_set(self, monkeypatch, tmp_path):
        real_file = tmp_path / 'seen_hints.json'
        real_file.write_text('not valid json', encoding='utf-8')
        monkeypatch.setattr('reveal.config.get_data_path', lambda name: real_file)

        assert _real_load_seen_hints() == set()

    def test_save_uses_seen_hints_json_filename(self, monkeypatch, tmp_path):
        """Confirms the data-path key, so it's visibly distinct from the
        legacy seen_breadcrumb_hint marker file the two mechanisms coexist
        with."""
        captured = {}

        def fake_get_data_path(name):
            captured['name'] = name
            return tmp_path / name

        monkeypatch.setattr('reveal.config.get_data_path', fake_get_data_path)
        _real_save_seen_hints({'x'})

        assert captured['name'] == 'seen_hints.json'


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

    def test_metadata_second_call_is_silent(self):
        """Metadata's boilerplate hint is shown once per install, not every call."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        capture_breadcrumbs('metadata', 'test.py', config=mock_config)
        second = capture_breadcrumbs('metadata', 'other.py', config=mock_config)

        assert second.strip() == ''


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
        """Markdown structure suggests --section, --links, and --code."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('structure', 'README.md', 'markdown', config=mock_config)
        assert '--section' in output
        assert '--links' in output
        assert '--code' in output

    def test_structure_markdown_frames_outline_as_not_content(self):
        """Markdown structure states the outline≠content mental model, not just mechanics."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('structure', 'README.md', 'markdown', config=mock_config)
        assert 'Outline only' in output
        assert 'headings show where, not what' in output

    def test_structure_python_does_not_frame_outline_as_not_content(self):
        """Code files don't get the doc-oriented outline≠content framing."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('structure', 'test.py', 'python', config=mock_config)
        assert 'Outline only' not in output

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

    def test_structure_graphql_shows_outline(self):
        """GraphQL structure suggests --outline (Type hierarchy)."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('structure', 'schema.graphql', 'graphql', config=mock_config)
        assert '--outline' in output
        assert '# Type hierarchy' in output

    def test_structure_second_call_same_type_is_silent(self):
        """The '<function> # Extract by name' line and the --check/--outline
        pair are both boilerplate — shown once per install, not per file."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        capture_breadcrumbs('structure', 'first.py', 'python', config=mock_config)
        second = capture_breadcrumbs('structure', 'second.py', 'python', config=mock_config)

        assert second.strip() == ''

    def test_structure_second_call_different_type_still_shown(self):
        """A boilerplate hint_id is per file_type — seeing Python's doesn't
        suppress YAML's, since it's a different lesson."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        capture_breadcrumbs('structure', 'first.py', 'python', config=mock_config)
        second = capture_breadcrumbs('structure', 'config.yaml', 'yaml', config=mock_config)

        assert '--check' in second
        assert '# Validate syntax' in second


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

    def test_large_file_ast_queries_second_call_is_silent(self):
        """The 3-line AST-query suggestion is identical for every large file
        of a matching type — shown once, not per file."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True
        structure = {'functions': [{'name': f'func_{i}'} for i in range(25)]}

        capture_breadcrumbs('structure', 'first.py', 'python', config=mock_config, structure=structure)
        second = capture_breadcrumbs('structure', 'second.py', 'python', config=mock_config, structure=structure)

        assert second.strip() == ''


# ==============================================================================
# print_breadcrumbs Tests - Hierarchical and Ordinal Extraction
# ==============================================================================

class TestPrintBreadcrumbsHierarchical:
    """Tests for hierarchical and ordinal extraction breadcrumbs."""

    def test_classes_suggest_hierarchical_extraction(self):
        """Files with classes suggest Class.method extraction syntax."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        structure = {
            'classes': [{'name': 'MyClass'}, {'name': 'OtherClass'}],
            'functions': [{'name': 'helper'}],
        }

        output = capture_breadcrumbs(
            'structure', 'test.py', 'python',
            config=mock_config, structure=structure
        )
        assert "MyClass.method" in output
        assert "# Hierarchical extraction" in output

    def test_no_classes_no_hierarchical_hint(self):
        """Files without classes don't show hierarchical hint."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        structure = {
            'functions': [{'name': 'foo'}, {'name': 'bar'}],
        }

        output = capture_breadcrumbs(
            'structure', 'test.py', 'python',
            config=mock_config, structure=structure
        )
        assert ".method" not in output

    def test_markdown_headings_suggest_section_extraction(self):
        """Markdown files with headings suggest --section '<first heading>' (doc equivalent of Class.method)."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        structure = {
            'headings': [{'name': 'Introduction'}, {'name': 'Usage'}],
        }

        output = capture_breadcrumbs(
            'structure', 'guide.md', 'markdown',
            config=mock_config, structure=structure
        )
        assert "--section 'Introduction'" in output
        assert "# Extract this section" in output

    def test_markdown_no_headings_no_section_extraction_hint(self):
        """Markdown files without headings don't show the specific section hint."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        structure = {
            'headings': [],
        }

        output = capture_breadcrumbs(
            'structure', 'guide.md', 'markdown',
            config=mock_config, structure=structure
        )
        assert "# Extract this section" not in output

    def test_section_extraction_hint_not_shown_for_code(self):
        """Doc section suggester doesn't apply to code files, even with a 'headings' key."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        structure = {
            'headings': [{'name': 'Introduction'}],
            'functions': [{'name': 'foo'}],
        }

        output = capture_breadcrumbs(
            'structure', 'test.py', 'python',
            config=mock_config, structure=structure
        )
        assert "# Extract this section" not in output

    def test_many_elements_suggest_ordinal_extraction(self):
        """Files with >5 elements suggest ordinal (@N) extraction."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        structure = {
            'functions': [{'name': f'func_{i}'} for i in range(8)],
        }

        output = capture_breadcrumbs(
            'structure', 'test.py', 'python',
            config=mock_config, structure=structure
        )
        assert "@3" in output
        assert "# Extract 3rd element" in output

    def test_few_elements_no_ordinal_hint(self):
        """Files with <=5 elements don't show ordinal hint."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        structure = {
            'functions': [{'name': 'foo'}, {'name': 'bar'}],
        }

        output = capture_breadcrumbs(
            'structure', 'test.py', 'python',
            config=mock_config, structure=structure
        )
        assert "@3" not in output

    def test_ordinal_extraction_second_call_is_silent(self):
        """'@3 # Extract 3rd element' is boilerplate (always literally '3rd'
        regardless of actual count) — shown once, not per file."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True
        structure = {'functions': [{'name': f'func_{i}'} for i in range(8)]}

        capture_breadcrumbs('structure', 'first.py', 'python', config=mock_config, structure=structure)
        second = capture_breadcrumbs('structure', 'second.py', 'python', config=mock_config, structure=structure)

        assert "@3" not in second

    def test_hierarchical_extraction_stays_dynamic_across_calls(self):
        """Unlike the boilerplate lines, the real class name is genuinely
        file-specific — it must show every time, with the right file's data,
        even after other boilerplate in the same context has been throttled."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        capture_breadcrumbs(
            'structure', 'first.py', 'python', config=mock_config,
            structure={'classes': [{'name': 'FirstClass'}]},
        )
        second = capture_breadcrumbs(
            'structure', 'second.py', 'python', config=mock_config,
            structure={'classes': [{'name': 'SecondClass'}]},
        )

        assert 'SecondClass.method' in second
        assert 'FirstClass.method' not in second


# ==============================================================================
# print_breadcrumbs Tests - New File Types
# ==============================================================================

class TestPrintBreadcrumbsNewFileTypes:
    """Tests for new file type breadcrumbs (CSV, XML, INI, PowerShell, etc.)."""

    def test_csv_shows_head_hint(self):
        """CSV files suggest --head for row filtering."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('structure', 'data.csv', 'csv', config=mock_config)
        assert '--head 10' in output
        assert '<row>' in output

    def test_xml_shows_head_hint(self):
        """XML files suggest --head for element filtering."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('structure', 'config.xml', 'xml', config=mock_config)
        assert '--head 10' in output
        assert '<element>' in output

    def test_ini_shows_section_placeholder(self):
        """INI files use <section> placeholder."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('structure', 'config.ini', 'ini', config=mock_config)
        assert '<section>' in output
        assert '--check' in output

    def test_powershell_shows_code_hints(self):
        """PowerShell files show code-type hints."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('structure', 'deploy.ps1', 'powershell', config=mock_config)
        assert '<function>' in output
        assert '--check' in output
        assert '--outline' in output

    def test_terraform_shows_resource_placeholder(self):
        """Terraform files use <resource> placeholder."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('structure', 'main.tf', 'terraform', config=mock_config)
        assert '<resource>' in output
        assert '--check' in output


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

    def test_typed_graphql_shows_check(self):
        """BACK-923: typed GraphQL context used to get zero type-specific hint
        (the _API_TYPES branch existed only in the structure-context function,
        not the typed one). Now shares one table with structure context and
        gets --check (not --outline, which typed context IS already)."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs('typed', 'schema.graphql', 'graphql', config=mock_config)
        assert '--check' in output
        assert '# Check code quality' in output
        # The structure-context line ("Type hierarchy") would be a no-op here
        # since typed context already IS the outline/type-hierarchy view.
        assert 'Type hierarchy' not in output

    def test_typed_second_call_same_type_is_silent(self):
        """Both typed-context lines (extract-element + --check) are
        boilerplate per file_type — shown once, not per file."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        capture_breadcrumbs('typed', 'first.py', 'python', config=mock_config)
        second = capture_breadcrumbs('typed', 'second.py', 'python', config=mock_config)

        assert second.strip() == ''


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

    def test_element_back_hint_second_call_is_silent(self):
        """'-> Back: reveal {path} # See full structure' fires on every
        named/line/ordinal extraction — the highest-frequency boilerplate
        line in this module — so it's shown once, not per extraction."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        capture_breadcrumbs('element', 'test.py', 'python', config=mock_config, element_name='first_func')
        second = capture_breadcrumbs('element', 'test.py', 'python', config=mock_config, element_name='second_func')

        assert 'Back:' not in second
        # The extraction confirmation itself is a result, not a hint — never throttled.
        assert 'Extracted second_func' in second

    def test_element_nearby_hint_stays_dynamic_across_calls(self):
        """Unlike 'Back:', the 'Nearby' line's target line number is computed
        from this specific extraction — must show every time with fresh data."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        capture_breadcrumbs(
            'element', 'test.py', 'python', config=mock_config,
            element_name='first_func', line_count=10, line_start=5,
        )
        second = capture_breadcrumbs(
            'element', 'test.py', 'python', config=mock_config,
            element_name='second_func', line_count=20, line_start=100,
        )

        assert 'Nearby: reveal test.py :125' in second


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


# ==============================================================================
# print_breadcrumbs Tests - Quality Check Context
# ==============================================================================

class TestPrintBreadcrumbsQualityCheck:
    """Tests for quality-check context breadcrumbs."""

    def test_no_issues_suggests_exploration(self):
        """When no issues found, suggests exploration paths."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs(
            'quality-check', 'test.py', 'python',
            config=mock_config, detections=[]
        )
        assert 'reveal test.py' in output
        assert '# See structure' in output
        assert '--outline' in output

    def test_issues_found_suggests_stats(self):
        """When issues found, suggests stats adapter."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        mock_detection = Mock()
        mock_detection.rule_code = 'E501'
        mock_detection.context = None

        output = capture_breadcrumbs(
            'quality-check', 'test.py', 'python',
            config=mock_config, detections=[mock_detection]
        )
        assert 'stats://test.py' in output
        assert 'help://rules' in output

    def test_complexity_issues_suggest_function(self):
        """When complexity issues found, suggests viewing complex function."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        mock_detection = Mock()
        mock_detection.rule_code = 'C901'
        mock_detection.context = 'Function: complex_handler'

        output = capture_breadcrumbs(
            'quality-check', 'test.py', 'python',
            config=mock_config, detections=[mock_detection]
        )
        assert 'reveal test.py complex_handler' in output
        assert '# View complex function' in output

    def test_multiple_complexity_issues_suggest_first(self):
        """With multiple complexity issues, suggests first function."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        mock_d1 = Mock()
        mock_d1.rule_code = 'C901'
        mock_d1.context = 'Function: first_complex'

        mock_d2 = Mock()
        mock_d2.rule_code = 'C902'
        mock_d2.context = 'Function: second_long (150 lines)'

        output = capture_breadcrumbs(
            'quality-check', 'test.py', 'python',
            config=mock_config, detections=[mock_d1, mock_d2]
        )
        assert 'reveal test.py first_complex' in output

    def test_non_complexity_issues_suggest_structure(self):
        """Non-complexity issues suggest structure view."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        mock_detection = Mock()
        mock_detection.rule_code = 'B001'
        mock_detection.context = None

        output = capture_breadcrumbs(
            'quality-check', 'test.py', 'python',
            config=mock_config, detections=[mock_detection]
        )
        # Should suggest structure, not a specific function
        assert 'reveal test.py' in output
        assert '# See structure' in output

    def test_quality_check_trailer_second_call_is_silent_but_complex_function_stays_dynamic(self):
        """The stats://+help://rules trailer is identical every call —
        boilerplate, shown once. The named complex function is real,
        file-specific data from this call's own detections — never throttled."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        first_detection = Mock()
        first_detection.rule_code = 'C901'
        first_detection.context = 'Function: first_complex'
        capture_breadcrumbs(
            'quality-check', 'test.py', 'python',
            config=mock_config, detections=[first_detection],
        )

        second_detection = Mock()
        second_detection.rule_code = 'C901'
        second_detection.context = 'Function: second_complex'
        second = capture_breadcrumbs(
            'quality-check', 'test.py', 'python',
            config=mock_config, detections=[second_detection],
        )

        assert 'stats://' not in second
        assert 'help://rules' not in second
        assert 'reveal test.py second_complex' in second


# ==============================================================================
# print_breadcrumbs Tests - Directory Check Context (Phase 3)
# ==============================================================================

class TestPrintBreadcrumbsDirectoryCheck:
    """Tests for directory-check context breadcrumbs (pre-commit workflow)."""

    def test_issues_found_shows_precommit_workflow(self):
        """When issues found, shows pre-commit workflow with fix suggestion."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs(
            'directory-check', 'src/',
            config=mock_config,
            total_issues=5,
            files_with_issues=2,
            files_checked=10
        )
        assert 'Pre-Commit Workflow:' in output
        assert 'Fix the 5 issues' in output
        assert 'diff://git://HEAD/.:.' in output
        assert 'stats://src/' in output

    def test_no_issues_shows_clean_workflow(self):
        """When no issues, shows clean pre-commit workflow."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        output = capture_breadcrumbs(
            'directory-check', 'src/',
            config=mock_config,
            total_issues=0,
            files_with_issues=0,
            files_checked=15
        )
        assert 'Pre-Commit Workflow:' in output
        assert '✅ All 15 files clean' in output
        assert 'git commit' in output
        assert 'diff://git://HEAD/.:.' in output

    def test_directory_check_respects_config(self):
        """Directory check respects breadcrumbs config."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = False

        output = capture_breadcrumbs(
            'directory-check', 'src/',
            config=mock_config,
            total_issues=0,
            files_checked=10
        )
        assert output == ''

    def test_issues_workflow_second_call_is_silent(self):
        """The pre-commit workflow text is a fixed template (only the issue
        count/path vary) — the lesson is shown once, not on every --check."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        capture_breadcrumbs(
            'directory-check', 'src/', config=mock_config,
            total_issues=5, files_with_issues=2, files_checked=10,
        )
        second = capture_breadcrumbs(
            'directory-check', 'other/', config=mock_config,
            total_issues=9, files_with_issues=3, files_checked=20,
        )

        # print_breadcrumbs always emits its own leading blank line first.
        assert second.strip() == ''

    def test_clean_and_issues_workflows_are_independent_hints(self):
        """Seeing the 'issues found' workflow doesn't suppress the 'all
        clean' workflow — they're different lessons for different outcomes."""
        mock_config = Mock()
        mock_config.is_breadcrumbs_enabled.return_value = True

        capture_breadcrumbs(
            'directory-check', 'src/', config=mock_config,
            total_issues=5, files_with_issues=2, files_checked=10,
        )
        second = capture_breadcrumbs(
            'directory-check', 'other/', config=mock_config,
            total_issues=0, files_with_issues=0, files_checked=20,
        )

        assert '✅ All 20 files clean' in second

