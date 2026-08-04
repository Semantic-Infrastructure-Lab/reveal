"""Tests targeting uncovered lines in reveal/adapters/diff/resolution.py."""

import pytest
from pathlib import Path
from unittest import mock

from reveal.adapters.diff.resolution import (
    resolve_uri,
    resolve_directory,
    instantiate_adapter,
    find_element,
    find_analyzable_files,
    extract_metadata,
)


class TestFindElement:
    """Test find_element — covers lines 254–260 (class method search)."""

    def test_finds_function(self):
        structure = {'functions': [{'name': 'my_func'}], 'classes': []}
        result = find_element(structure, 'my_func')
        assert result == {'name': 'my_func'}

    def test_finds_class(self):
        structure = {'functions': [], 'classes': [{'name': 'MyClass', 'methods': []}]}
        result = find_element(structure, 'MyClass')
        assert result == {'name': 'MyClass', 'methods': []}

    def test_finds_class_method(self):
        """Covers lines 258–260 — searching class methods."""
        structure = {
            'functions': [],
            'classes': [
                {
                    'name': 'MyClass',
                    'methods': [{'name': 'my_method'}, {'name': 'other'}],
                }
            ],
        }
        result = find_element(structure, 'my_method')
        assert result == {'name': 'my_method'}

    def test_returns_none_when_not_found(self):
        structure = {
            'functions': [{'name': 'foo'}],
            'classes': [{'name': 'Bar', 'methods': [{'name': 'baz'}]}],
        }
        assert find_element(structure, 'missing') is None

    def test_handles_nested_structure_key(self):
        """Handles structure wrapped under 'structure' key."""
        inner = {'functions': [{'name': 'inner_func'}], 'classes': []}
        structure = {'structure': inner}
        result = find_element(structure, 'inner_func')
        assert result == {'name': 'inner_func'}

    def test_multiple_classes_finds_correct_method(self):
        """Searches across multiple classes."""
        structure = {
            'functions': [],
            'classes': [
                {'name': 'ClassA', 'methods': [{'name': 'alpha'}]},
                {'name': 'ClassB', 'methods': [{'name': 'beta'}]},
            ],
        }
        assert find_element(structure, 'beta') == {'name': 'beta'}


class TestResolveUri:
    """Test resolve_uri — covers git URI branches and unsupported scheme."""

    def test_git_at_format_calls_resolve_git_adapter(self):
        """Line 41 — git:// with @ routes to resolve_git_adapter."""
        with mock.patch('reveal.adapters.diff.resolution.resolve_git_adapter') as mock_ga:
            mock_ga.return_value = {'type': 'file'}
            result = resolve_uri('git://reveal/main.py@HEAD~1')
            mock_ga.assert_called_once_with('reveal/main.py@HEAD~1')
            assert result == {'type': 'file'}

    def test_git_colon_slash_format_raises_value_error(self):
        """Lines 45–46 — git://REF:path raises ValueError with hint."""
        with pytest.raises(ValueError, match="Git URI format error"):
            resolve_uri('git://HEAD~1:path/to/file.py')

    def test_unsupported_scheme_raises_value_error(self):
        """Line 79 — unregistered scheme raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported URI scheme: notreal://"):
            resolve_uri('notreal://something')

    def test_plain_path_adds_file_scheme(self, tmp_path):
        """Plain path without :// is treated as file://."""
        py_file = tmp_path / 'sample.py'
        py_file.write_text('x = 1\n')
        result = resolve_uri(str(py_file))
        assert result is not None

    def test_git_bare_resource_calls_resolve_git_adapter(self):
        """Line 59 — git:// with no @ and no / calls resolve_git_adapter."""
        with mock.patch('reveal.adapters.diff.resolution.resolve_git_adapter') as mock_ga:
            mock_ga.return_value = {'type': 'repo'}
            result = resolve_uri('git://main')
            mock_ga.assert_called_once_with('main')

    def test_valid_non_file_adapter_scheme(self):
        """Lines 82–83 — non-git/non-file scheme uses registered adapter."""
        mock_adapter = mock.Mock()
        mock_adapter.get_structure.return_value = {'type': 'env'}
        mock_class = mock.Mock(return_value=mock_adapter)

        with mock.patch('reveal.adapters.diff.resolution.get_adapter_class', return_value=mock_class):
            with mock.patch('reveal.adapters.diff.resolution.instantiate_adapter', return_value=mock_adapter):
                result = resolve_uri('env://')
                assert result == {'type': 'env'}


class TestResolveDirectory:
    """Test resolve_directory — covers error path and imports aggregation."""

    def test_non_directory_raises_value_error(self):
        """Line 99 — non-existent path raises ValueError."""
        with pytest.raises(ValueError, match="Not a directory"):
            resolve_directory('/nonexistent/path/to/dir')

    def test_aggregates_imports(self, tmp_path):
        """Lines 124–125 — imports are collected from files."""
        py_file = tmp_path / 'sample.py'
        py_file.write_text('import os\nimport sys\n')
        result = resolve_directory(str(tmp_path))
        assert result['type'] == 'directory'
        assert result['file_count'] >= 1
        assert isinstance(result['imports'], list)

    def test_result_has_expected_keys(self, tmp_path):
        """Result dict has all required keys."""
        (tmp_path / 'mod.py').write_text('x = 1\n')
        result = resolve_directory(str(tmp_path))
        assert {'type', 'path', 'file_count', 'functions', 'classes', 'imports'} <= set(result.keys())


class TestFindAnalyzableFiles:
    """find_analyzable_files' ignore-dir filtering — BACK-552 parity.

    Regression coverage for BACK-913: this walk used to hardcode its own
    ignore-dir literal instead of routing through is_skippable_dir(), so a
    real source directory bare-named 'venv'/'dist'/'build' was silently
    excluded (the exact bug BACK-552 fixed for the general path-walking
    code, which never propagated here).
    """

    def test_ambiguous_dir_with_source_is_not_skipped(self, tmp_path):
        real_pkg = tmp_path / 'venv'
        real_pkg.mkdir()
        (real_pkg / 'main.py').write_text('x = 1\n')

        found = {p.name for p in find_analyzable_files(tmp_path)}
        assert 'main.py' in found

    def test_ambiguous_dir_without_source_is_skipped(self, tmp_path):
        fake_venv = tmp_path / 'venv'
        fake_venv.mkdir()
        (fake_venv / 'pyvenv.cfg').write_text('home = /usr\n')
        nested = fake_venv / 'lib' / 'site-packages'
        nested.mkdir(parents=True)
        (nested / 'pkg.py').write_text('y = 2\n')

        found = {p.name for p in find_analyzable_files(tmp_path)}
        assert 'pkg.py' not in found

    def test_unconditional_dir_always_skipped(self, tmp_path):
        cache = tmp_path / '__pycache__'
        cache.mkdir()
        (cache / 'mod.cpython-310.pyc').write_bytes(b'')
        (tmp_path / 'real.py').write_text('z = 3\n')

        found = {p.name for p in find_analyzable_files(tmp_path)}
        assert found == {'real.py'}


class TestInstantiateAdapter:
    """Test instantiate_adapter — covers file scheme and signature branches."""

    def test_file_scheme_no_analyzer_raises(self):
        """Line 162 — file scheme with unrecognizable extension raises ValueError."""
        with pytest.raises(ValueError, match="No analyzer found"):
            instantiate_adapter(object, 'file', 'nonexistent_file.unknownxyz')

    def test_no_param_adapter_called_without_args(self):
        """Lines 175–176 — adapter with no params is instantiated without args."""
        class NoArgAdapter:
            def get_structure(self):
                return {}

        result = instantiate_adapter(NoArgAdapter, 'env', 'resource')
        assert isinstance(result, NoArgAdapter)

    def test_with_param_adapter_called_with_resource(self):
        """Lines 178–179 — adapter with params receives resource string."""
        class ArgAdapter:
            def __init__(self, resource):
                self.resource = resource
            def get_structure(self):
                return {}

        result = instantiate_adapter(ArgAdapter, 'custom', 'my-resource')
        assert result.resource == 'my-resource'

    def test_exception_fallback_tries_without_args(self):
        """Lines 183–186 — when signature inspection fails, fallback to no-args."""
        class StubAdapter:
            """Adapter that succeeds without args even though signature is tricky."""
            def get_structure(self):
                return {}

        with mock.patch('inspect.signature', side_effect=TypeError("can't inspect")):
            result = instantiate_adapter(StubAdapter, 'stub', 'resource')
            assert isinstance(result, StubAdapter)


class TestExtractMetadata:
    """Test extract_metadata (simple utility, but ensures import coverage)."""

    def test_basic_metadata(self):
        structure = {'type': 'python'}
        meta = extract_metadata(structure, 'file://app.py')
        assert meta['uri'] == 'file://app.py'
        assert meta['type'] == 'python'

    def test_unknown_type_fallback(self):
        meta = extract_metadata({}, 'env://')
        assert meta['type'] == 'unknown'
