"""Tests for M105 rule: CLI handler not wired to main.py."""

import pytest
import tempfile
from pathlib import Path
from reveal.rules.maintainability.M105 import M105


class TestM105Init:
    """Tests for M105 rule initialization."""

    def test_rule_attributes(self):
        """Test rule has correct attributes."""
        rule = M105()
        assert rule.code == "M105"
        assert rule.message == "CLI handler function not wired to main.py"
        assert rule.severity.name == "HIGH"
        assert 'reveal/cli/handlers_*.py' in rule.file_patterns


class TestM105Detection:
    """Tests for M105 detection logic."""

    def test_detect_handler_not_imported(self):
        """Test detection of handler function not imported in main.py."""
        content = '''"""Handler functions."""

def handle_stats_overview():
    """Show stats overview."""
    pass

def handle_stats_detail(name: str):
    """Show stats detail."""
    pass
'''
        rule = M105()
        # Note: In real usage, this would check main.py
        # For unit tests, we're testing the pattern matching
        handlers = rule.HANDLER_PATTERN.findall(content)
        assert 'handle_stats_overview' in handlers
        assert 'handle_stats_detail' in handlers

    def test_ignore_non_handler_functions(self):
        """Test that non-handler functions are ignored."""
        content = '''"""Utility functions."""

def process_data():
    """Process data."""
    pass

def validate_input():
    """Validate input."""
    pass

def handle_special_case():
    """This IS a handler."""
    pass
'''
        rule = M105()
        handlers = rule.HANDLER_PATTERN.findall(content)
        # Only handle_special_case should match
        assert 'handle_special_case' in handlers
        assert 'process_data' not in handlers
        assert 'validate_input' not in handlers

    def test_find_handler_line(self):
        """Test finding line number of handler."""
        content = '''"""Handlers."""

def helper():
    pass

def handle_command():
    """Command handler."""
    pass
'''
        rule = M105()
        line = rule._find_handler_line('handle_command', content)
        assert line == 6  # 1-indexed, line 6 (triple-quote string starts at line 1)

    def test_is_imported_multiline(self):
        """Test detection of multiline imports."""
        main_content = '''from .cli import (
    handle_file,
    handle_scaffold_adapter,
    handle_scaffold_analyzer,
)
'''
        rule = M105()
        assert rule._is_imported('handle_scaffold_adapter', main_content)
        assert rule._is_imported('handle_file', main_content)
        assert not rule._is_imported('handle_missing', main_content)

    def test_is_imported_single_line(self):
        """Test detection of single-line imports."""
        main_content = '''from .cli import handle_file, handle_scaffold_adapter'''
        rule = M105()
        assert rule._is_imported('handle_scaffold_adapter', main_content)
        assert rule._is_imported('handle_file', main_content)

    def test_is_called(self):
        """Test detection of handler calls."""
        main_content = '''
def main():
    if condition:
        handle_scaffold_adapter(name, uri)

    result = handle_file(path)
'''
        rule = M105()
        assert rule._is_called('handle_scaffold_adapter', main_content)
        assert rule._is_called('handle_file', main_content)
        assert not rule._is_called('handle_missing', main_content)

    def test_no_detections_for_non_handler_files(self):
        """Test that non-handler files are skipped."""
        content = '''"""Regular module."""

def handle_data():
    pass
'''
        rule = M105()
        detections = rule.check(
            file_path='reveal/utils.py',
            structure=None,
            content=content
        )
        assert len(detections) == 0

    def test_no_detections_when_handlers_properly_wired(self):
        """Test no detections when everything is properly wired."""
        # This is more of an integration test
        # In practice, M105 checks actual main.py
        rule = M105()
        # Testing with actual reveal/cli/handlers_scaffold.py should pass
        # because it's properly wired


class TestM105Integration:
    """Integration tests for M105 with actual reveal files."""

    def test_actual_handlers_scaffold_file(self):
        """Test M105 against actual handlers_scaffold.py."""
        handlers_path = Path('reveal/cli/handlers_scaffold.py')
        if not handlers_path.exists():
            pytest.skip("handlers_scaffold.py not found")

        content = handlers_path.read_text()
        rule = M105()

        # Check that we find handlers
        handlers = rule.HANDLER_PATTERN.findall(content)
        assert len(handlers) > 0
        assert 'handle_scaffold_adapter' in handlers

    def test_scaffold_command_imports_scaffold_handlers(self):
        """Test that scaffold.py imports and calls scaffold handlers."""
        scaffold_path = Path('reveal/cli/commands/scaffold.py')
        if not scaffold_path.exists():
            pytest.skip("scaffold.py not found")

        content = scaffold_path.read_text(encoding='utf-8')
        rule = M105()

        # All three handlers must be present in the file (imported and called)
        for handler in ('handle_scaffold_adapter', 'handle_scaffold_analyzer', 'handle_scaffold_rule'):
            assert handler in content, f"{handler} not found in scaffold.py"
            assert rule._is_called(handler, content), f"{handler} not called in scaffold.py"


class TestM105EdgeCases:
    """Test edge cases for M105."""

    def test_handler_with_type_hints(self):
        """Test detection of handlers with type hints."""
        content = '''
def handle_command(arg: str, flag: bool = False) -> None:
    """Handler with type hints."""
    pass
'''
        rule = M105()
        handlers = rule.HANDLER_PATTERN.findall(content)
        assert 'handle_command' in handlers

    def test_handler_with_decorators(self):
        """Test detection of handlers with decorators."""
        content = '''
@decorator
def handle_command():
    """Decorated handler."""
    pass
'''
        rule = M105()
        handlers = rule.HANDLER_PATTERN.findall(content)
        assert 'handle_command' in handlers

    def test_handler_with_multiline_args(self):
        """Test detection of handlers with multiline arguments."""
        content = '''
def handle_command(
    arg1: str,
    arg2: int,
    flag: bool = False
) -> None:
    """Handler with multiline args."""
    pass
'''
        rule = M105()
        handlers = rule.HANDLER_PATTERN.findall(content)
        assert 'handle_command' in handlers


class TestM105CheckIntegration:
    """Integration tests that exercise the full check() path (lines 68-108)."""

    def _make_handlers_file(self, tmpdir: Path, content: str) -> Path:
        """Create reveal/cli/handlers_test.py in tmpdir."""
        handlers_dir = tmpdir / 'reveal' / 'cli'
        handlers_dir.mkdir(parents=True)
        handlers_file = handlers_dir / 'handlers_test.py'
        handlers_file.write_text(content)
        return handlers_file

    def _make_main_py(self, tmpdir: Path, content: str) -> Path:
        reveal_dir = tmpdir / 'reveal'
        reveal_dir.mkdir(parents=True, exist_ok=True)
        main_file = reveal_dir / 'main.py'
        main_file.write_text(content)
        return main_file

    def test_handler_not_imported_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            handler_content = 'def handle_test():\n    pass\n'
            handlers_file = self._make_handlers_file(tmpdir, handler_content)
            self._make_main_py(tmpdir, '# empty main\n')
            rule = M105()
            detections = rule.check(str(handlers_file), None, handler_content)
            assert len(detections) == 1
            assert 'not imported' in detections[0].message
            assert 'handle_test' in detections[0].message

    def test_handler_imported_not_called_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            handler_content = 'def handle_test():\n    pass\n'
            handlers_file = self._make_handlers_file(tmpdir, handler_content)
            self._make_main_py(tmpdir, 'from .cli import handle_test\n')
            rule = M105()
            detections = rule.check(str(handlers_file), None, handler_content)
            assert len(detections) == 1
            assert 'imported but never called' in detections[0].message

    def test_handler_properly_wired_no_detection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            handler_content = 'def handle_test():\n    pass\n'
            handlers_file = self._make_handlers_file(tmpdir, handler_content)
            main_content = 'from .cli import handle_test\nhandle_test()\n'
            self._make_main_py(tmpdir, main_content)
            rule = M105()
            detections = rule.check(str(handlers_file), None, handler_content)
            assert len(detections) == 0

    def test_no_handlers_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            handler_content = '# no handlers here\ndef helper(): pass\n'
            handlers_file = self._make_handlers_file(tmpdir, handler_content)
            self._make_main_py(tmpdir, '# main\n')
            rule = M105()
            detections = rule.check(str(handlers_file), None, handler_content)
            assert len(detections) == 0

    def test_main_py_missing_skips_check(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            handler_content = 'def handle_test():\n    pass\n'
            handlers_file = self._make_handlers_file(tmpdir, handler_content)
            # Don't create main.py
            rule = M105()
            detections = rule.check(str(handlers_file), None, handler_content)
            assert len(detections) == 0

    def test_file_path_without_reveal_dir(self):
        # _find_main_py returns None when 'reveal' not in path parts
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            handlers_dir = tmpdir / 'myapp' / 'cli'
            handlers_dir.mkdir(parents=True)
            handlers_file = handlers_dir / 'handlers_test.py'
            handler_content = 'def handle_test():\n    pass\n'
            handlers_file.write_text(handler_content)
            rule = M105()
            detections = rule.check(str(handlers_file), None, handler_content)
            assert len(detections) == 0


class TestM105IsImportedExtended:
    """Cover remaining _is_imported branches."""

    def test_direct_import_statement(self):
        # Line 121: `import handle_foo` form
        main_content = 'import handle_foo\nimport something_else\n'
        rule = M105()
        assert rule._is_imported('handle_foo', main_content)

    def test_direct_import_not_found(self):
        main_content = 'import handle_bar\n'
        rule = M105()
        assert not rule._is_imported('handle_missing', main_content)


class TestM105FindHandlerLineDefault:
    """Cover the return 1 default in _find_handler_line (line 188)."""

    def test_handler_not_in_content_returns_line_1(self):
        rule = M105()
        line = rule._find_handler_line('handle_missing', 'def handle_other():\n    pass\n')
        assert line == 1

    def test_handler_at_start_returns_line_1(self):
        rule = M105()
        line = rule._find_handler_line('handle_cmd', 'def handle_cmd(): pass\n')
        assert line == 1
