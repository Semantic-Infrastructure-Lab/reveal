"""Tests for reveal/utils/path_utils.py - path utilities."""

import tempfile
import pytest
from pathlib import Path, PureWindowsPath
from reveal.utils.path_utils import (
    find_file_in_parents,
    search_parents,
    search_parents_within_ceiling,
    find_project_root,
    get_relative_to_root,
    detect_non_python_language,
    to_posix,
    is_unsafe_scan_root,
    is_skippable_dir,
)


class TestDetectNonPythonLanguage:
    """Test detect_non_python_language() — BACK-403 extension coverage."""

    def test_single_c_file(self, tmp_path):
        f = tmp_path / "util.c"
        f.write_text("")
        assert detect_non_python_language(f) == 'C'

    def test_single_header_file(self, tmp_path):
        f = tmp_path / "util.h"
        f.write_text("")
        assert detect_non_python_language(f) == 'C'

    def test_single_cpp_file(self, tmp_path):
        f = tmp_path / "widget.cpp"
        f.write_text("")
        assert detect_non_python_language(f) == 'C++'

    def test_dominant_language_in_directory(self, tmp_path):
        for name in ["a.c", "b.c", "c.c", "d.h"]:
            (tmp_path / name).write_text("")
        (tmp_path / "helper.rb").write_text("")
        assert detect_non_python_language(tmp_path) == 'C'

    def test_no_false_positive_from_minority_file(self, tmp_path):
        # Regression: a single .rb file should not win against a majority
        # of .c/.h files just because .c/.h were previously unmapped.
        for name in [f"f{i}.c" for i in range(5)] + ["g.h"]:
            (tmp_path / name).write_text("")
        (tmp_path / "helper.rb").write_text("")
        assert detect_non_python_language(tmp_path) == 'C'

    def test_unknown_extension_returns_empty(self, tmp_path):
        f = tmp_path / "readme.txt"
        f.write_text("")
        assert detect_non_python_language(f) == ''

    def test_python_file_returns_empty(self, tmp_path):
        f = tmp_path / "main.py"
        f.write_text("")
        assert detect_non_python_language(f) == ''


class TestFindFileInParents:
    """Test find_file_in_parents() for upward file search."""

    def test_find_file_in_parent_directory(self, tmp_path):
        """Find file in immediate parent."""
        # Create structure: tmp_path/config.yaml, tmp_path/src/file.py
        config = tmp_path / "config.yaml"
        config.write_text("config")

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        start_file = src_dir / "file.py"
        start_file.write_text("code")

        result = find_file_in_parents(start_file, "config.yaml")

        assert result == config

    def test_find_file_in_ancestor(self, tmp_path):
        """Find file in distant ancestor."""
        # Create: tmp_path/.git, tmp_path/a/b/c/file.py
        marker = tmp_path / ".git"
        marker.mkdir()

        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        start = deep / "file.py"
        start.write_text("code")

        result = find_file_in_parents(start, ".git")

        assert result == marker

    def test_file_not_found(self, tmp_path):
        """Return None when file not found."""
        start = tmp_path / "file.py"
        start.write_text("code")

        result = find_file_in_parents(start, "nonexistent.yaml")

        assert result is None

    def test_start_from_directory(self, tmp_path):
        """Support starting from directory path."""
        config = tmp_path / "config.yaml"
        config.write_text("config")

        src_dir = tmp_path / "src"
        src_dir.mkdir()

        result = find_file_in_parents(src_dir, "config.yaml")

        assert result == config

    def test_start_from_file(self, tmp_path):
        """Support starting from file path."""
        config = tmp_path / "config.yaml"
        config.write_text("config")

        file = tmp_path / "file.py"
        file.write_text("code")

        result = find_file_in_parents(file, "config.yaml")

        assert result == config

    def test_max_depth_limit(self, tmp_path):
        """Respect max_depth limit."""
        # Create deep structure
        deep = tmp_path
        for i in range(25):
            deep = deep / f"level{i}"
            deep.mkdir(exist_ok=True)

        # Put marker at top
        marker = tmp_path / "marker.txt"
        marker.write_text("marker")

        # Start from bottom with low max_depth
        result = find_file_in_parents(deep, "marker.txt", max_depth=5)

        # Should not find (too deep)
        assert result is None

    def test_max_depth_sufficient(self, tmp_path):
        """Find file within max_depth."""
        marker = tmp_path / "marker.txt"
        marker.write_text("marker")

        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)

        result = find_file_in_parents(deep, "marker.txt", max_depth=5)

        assert result == marker

    def test_file_in_current_directory(self, tmp_path):
        """Find file in starting directory itself."""
        config = tmp_path / "config.yaml"
        config.write_text("config")

        result = find_file_in_parents(tmp_path, "config.yaml")

        assert result == config

    def test_stops_at_filesystem_root(self, tmp_path):
        """Stop searching at filesystem root."""
        start = tmp_path / "file.py"
        start.write_text("code")

        # Should not find and not error at root
        result = find_file_in_parents(start, "definitely_not_exists.xyz")

        assert result is None


class TestSearchParents:
    """Test search_parents() for conditional parent search."""

    def test_find_parent_by_name(self, tmp_path):
        """Find parent directory by name."""
        docs = tmp_path / "docs"
        docs.mkdir()
        guides = docs / "guides"
        guides.mkdir()
        intro = guides / "intro.md"
        intro.write_text("content")

        result = search_parents(intro, lambda p: p.name == "docs")

        assert result == docs

    def test_find_parent_containing_file(self, tmp_path):
        """Find parent containing specific file."""
        config = tmp_path / "pyproject.toml"
        config.write_text("config")

        src = tmp_path / "src" / "module"
        src.mkdir(parents=True)
        file = src / "code.py"
        file.write_text("code")

        result = search_parents(
            file,
            lambda p: (p / "pyproject.toml").exists()
        )

        assert result == tmp_path

    def test_condition_not_met(self, tmp_path):
        """Return None when condition never met."""
        file = tmp_path / "file.py"
        file.write_text("code")

        result = search_parents(
            file,
            lambda p: p.name == "nonexistent_dir"
        )

        assert result is None

    def test_start_from_directory(self, tmp_path):
        """Start search from directory."""
        target = tmp_path / "target"
        target.mkdir()
        nested = target / "nested"
        nested.mkdir()

        result = search_parents(nested, lambda p: p.name == "target")

        assert result == target

    def test_max_depth_limit(self, tmp_path):
        """Respect max_depth parameter."""
        deep = tmp_path
        for i in range(10):
            deep = deep / f"level{i}"
            deep.mkdir()

        # Condition at top level
        result = search_parents(
            deep,
            lambda p: p.name == tmp_path.name,
            max_depth=5
        )

        # Should not reach tmp_path (too deep)
        assert result is None

    def test_immediate_match(self, tmp_path):
        """Match starting directory itself."""
        target = tmp_path / "target"
        target.mkdir()

        result = search_parents(target, lambda p: p.name == "target")

        assert result == target

    def test_complex_condition(self, tmp_path):
        """Use complex condition function."""
        # Find parent with multiple .py files
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("a")
        (src / "b.py").write_text("b")

        nested = src / "nested"
        nested.mkdir()
        (nested / "c.py").write_text("c")

        def has_multiple_py_files(p: Path) -> bool:
            return len(list(p.glob("*.py"))) >= 2

        result = search_parents(nested, has_multiple_py_files)

        assert result == src


class TestSearchParentsWithinCeiling:
    """BACK-525 layer 2: search_parents_within_ceiling never climbs past (or
    promotes) a hard ceiling — is_unsafe_scan_root or a mount-boundary
    crossing — even when the condition would otherwise match there."""

    def test_finds_match_below_ceiling(self, tmp_path):
        """Behaves like search_parents when the match is well within bounds."""
        target = tmp_path / "proj"
        target.mkdir()
        (target / "marker").write_text("x")
        nested = target / "src"
        nested.mkdir()

        result = search_parents_within_ceiling(nested, lambda p: (p / "marker").exists())

        assert result == target

    def test_stops_at_unsafe_root_without_matching(self, tmp_path, monkeypatch):
        """A condition that would match at an unsafe root (here: tmp_path
        itself, monkeypatched as unsafe) must never be honored there —
        the climb stops at the ceiling and returns None."""
        monkeypatch.setattr(
            "reveal.utils.path_utils.is_unsafe_scan_root",
            lambda p: str(p) == str(tmp_path),
        )
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)

        result = search_parents_within_ceiling(nested, lambda p: p == tmp_path)

        assert result is None

    def test_unsafe_root_never_returned_even_as_intermediate(self, tmp_path, monkeypatch):
        """The ceiling check applies at every level of the climb, not just
        the final candidate — a marker one level above the ceiling is still
        found, but nothing at or beyond the ceiling ever is."""
        monkeypatch.setattr(
            "reveal.utils.path_utils.is_unsafe_scan_root",
            lambda p: str(p) == str(tmp_path),
        )
        proj = tmp_path / "proj"
        (proj / "src").mkdir(parents=True)
        (proj / "marker").write_text("x")

        result = search_parents_within_ceiling(proj / "src", lambda p: (p / "marker").exists())

        assert result == proj

    def test_respects_max_depth(self, tmp_path):
        deep = tmp_path
        for i in range(10):
            deep = deep / f"level{i}"
            deep.mkdir()

        result = search_parents_within_ceiling(
            deep, lambda p: p.name == tmp_path.name, max_depth=5
        )

        assert result is None


class TestFindProjectRoot:
    """Test find_project_root() for project root detection."""

    def test_find_with_pyproject_toml(self, tmp_path):
        """Find root via pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text("config")

        src = tmp_path / "src" / "module"
        src.mkdir(parents=True)
        file = src / "code.py"
        file.write_text("code")

        result = find_project_root(file)

        assert result == tmp_path

    def test_find_with_git_directory(self, tmp_path):
        """Find root via .git directory."""
        (tmp_path / ".git").mkdir()

        src = tmp_path / "src"
        src.mkdir()
        file = src / "file.py"
        file.write_text("code")

        result = find_project_root(file)

        assert result == tmp_path

    def test_find_with_setup_py(self, tmp_path):
        """Find root via setup.py."""
        (tmp_path / "setup.py").write_text("setup")

        module = tmp_path / "module"
        module.mkdir()

        result = find_project_root(module)

        assert result == tmp_path

    def test_find_with_custom_markers(self, tmp_path):
        """Use custom marker list."""
        (tmp_path / "custom.config").write_text("config")

        src = tmp_path / "src"
        src.mkdir()

        result = find_project_root(src, markers=["custom.config"])

        assert result == tmp_path

    def test_no_project_root_found(self, tmp_path):
        """Return None when no markers found."""
        # No markers present
        file = tmp_path / "file.py"
        file.write_text("code")

        result = find_project_root(file)

        assert result is None

    def test_multiple_markers(self, tmp_path):
        """Find root with multiple markers present."""
        (tmp_path / "pyproject.toml").write_text("config")
        (tmp_path / ".git").mkdir()
        (tmp_path / "setup.py").write_text("setup")

        src = tmp_path / "src"
        src.mkdir()

        result = find_project_root(src)

        assert result == tmp_path

    def test_nested_projects(self, tmp_path):
        """Find nearest project root in nested projects."""
        # Outer project
        (tmp_path / "pyproject.toml").write_text("outer")

        # Inner project
        inner = tmp_path / "vendor" / "lib"
        inner.mkdir(parents=True)
        (inner / "pyproject.toml").write_text("inner")

        inner_src = inner / "src"
        inner_src.mkdir()

        result = find_project_root(inner_src)

        # Should find inner project root, not outer
        assert result == inner

    def test_cargo_toml_marker(self, tmp_path):
        """Recognize Cargo.toml (Rust) as marker."""
        (tmp_path / "Cargo.toml").write_text("rust")

        src = tmp_path / "src"
        src.mkdir()

        result = find_project_root(src)

        assert result == tmp_path

    def test_package_json_marker(self, tmp_path):
        """Recognize package.json (Node.js) as marker."""
        (tmp_path / "package.json").write_text("node")

        src = tmp_path / "src"
        src.mkdir()

        result = find_project_root(src)

        assert result == tmp_path


class TestGetRelativeToRoot:
    """Test get_relative_to_root() for relative path display."""

    def test_path_relative_to_project_root(self, tmp_path):
        """Convert absolute path to relative."""
        (tmp_path / "pyproject.toml").write_text("config")

        src = tmp_path / "src" / "module"
        src.mkdir(parents=True)
        file = src / "code.py"
        file.write_text("code")

        result = get_relative_to_root(file)

        assert result == Path("src/module/code.py")

    def test_path_already_relative(self, tmp_path):
        """Handle already relative paths."""
        (tmp_path / "pyproject.toml").write_text("config")

        # Change to tmp_path so relative path resolves
        import os
        original = os.getcwd()
        try:
            os.chdir(tmp_path)

            result = get_relative_to_root(Path("src/file.py"))

            # Should be relative to project root
            assert "src" in str(result)
        finally:
            os.chdir(original)

    def test_no_project_root_returns_original(self, tmp_path):
        """Return original path if no root found."""
        # No markers
        file = tmp_path / "file.py"
        file.write_text("code")

        result = get_relative_to_root(file)

        # Should return absolute path (no root found)
        assert result.is_absolute()
        assert result == file.resolve()

    def test_with_custom_markers(self, tmp_path):
        """Use custom root markers."""
        (tmp_path / "custom.marker").write_text("marker")

        src = tmp_path / "src"
        src.mkdir()
        file = src / "code.py"
        file.write_text("code")

        result = get_relative_to_root(file, root_markers=["custom.marker"])

        assert result == Path("src/code.py")

    def test_path_outside_root(self, tmp_path):
        """Handle paths outside project root."""
        project = tmp_path / "project"
        project.mkdir()
        (project / "pyproject.toml").write_text("config")

        outside = tmp_path / "outside"
        outside.mkdir()
        file = outside / "file.py"
        file.write_text("code")

        result = get_relative_to_root(file)

        # Can't make relative, returns original
        assert result.is_absolute()

    def test_file_at_root(self, tmp_path):
        """Handle file at project root."""
        (tmp_path / "pyproject.toml").write_text("config")
        file = tmp_path / "readme.md"
        file.write_text("readme")

        result = get_relative_to_root(file)

        assert result == Path("readme.md")

    def test_value_error_in_relative_to(self, tmp_path, monkeypatch):
        """Handle ValueError when relative_to() fails."""
        from unittest.mock import Mock
        (tmp_path / "pyproject.toml").write_text("config")

        file = tmp_path / "file.py"
        file.write_text("code")

        # Mock path.relative_to() to raise ValueError
        original_relative_to = Path.relative_to

        def mock_relative_to(self, other):
            if str(self).endswith("file.py"):
                raise ValueError("Not a subpath")
            return original_relative_to(self, other)

        monkeypatch.setattr(Path, "relative_to", mock_relative_to)

        result = get_relative_to_root(file)

        # Should return absolute path when relative_to fails
        assert result.is_absolute()
        assert result == file.resolve()


class TestToPosix:
    """to_posix() — portable path serialization (Windows path-separator safety)."""

    def test_posix_path_object_unchanged(self):
        assert to_posix(Path("a/b/c.py")) == "a/b/c.py"

    def test_windows_backslash_string_normalized(self):
        # Simulates str(rel) on Windows, which emits backslashes and broke
        # cross-OS comparisons (e.g. pack's 'relative' field vs 'tests/foo.py').
        assert to_posix("tests\\test_core.py") == "tests/test_core.py"

    def test_pure_windows_path_normalized(self):
        # A path built with Windows semantics serializes with forward slashes.
        assert to_posix(PureWindowsPath("tests", "sub", "file.py")) == "tests/sub/file.py"

    def test_already_posix_string_unchanged(self):
        assert to_posix("already/posix.py") == "already/posix.py"

    def test_absolute_windows_path_keeps_drive(self):
        assert to_posix("C:\\proj\\src\\a.py") == "C:/proj/src/a.py"

    def test_output_never_contains_backslash(self):
        # The core contract: output is portable regardless of input separator.
        assert "\\" not in to_posix("a\\b\\c\\d.py")


class TestIsUnsafeScanRoot:
    """is_unsafe_scan_root() — platform-aware system/temp/home root detection.

    Replaces three divergent hardcoded POSIX-only sets that silently no-opped
    on Windows (temp = C:\\...\\Temp, anchor = C:\\) and macOS (temp =
    /var/folders/..., /tmp -> /private/tmp). The simulation tests below run on
    Linux yet exercise the non-Linux behavior, so a regression is caught on the
    dev machine instead of only on the (slow, post-push) Windows CI matrix.
    """

    def test_filesystem_anchor_is_unsafe(self):
        assert is_unsafe_scan_root("/") is True

    def test_os_tempdir_is_unsafe(self):
        assert is_unsafe_scan_root(tempfile.gettempdir()) is True

    def test_home_is_unsafe(self):
        assert is_unsafe_scan_root(str(Path.home())) is True

    def test_none_is_not_unsafe(self):
        assert is_unsafe_scan_root(None) is False

    def test_real_project_dir_is_safe(self, tmp_path):
        proj = tmp_path / "myproject"
        proj.mkdir()
        assert is_unsafe_scan_root(str(proj)) is False

    def test_tempdir_is_derived_at_runtime_not_hardcoded(self, tmp_path, monkeypatch):
        # The macOS/Windows bug in one test: the OS temp dir is NOT '/tmp'
        # (macOS: /var/folders/...; Windows: C:\\...\\Temp). Recognizing it must
        # come from tempfile.gettempdir() at call time, never a hardcoded '/tmp'.
        # Point gettempdir at a non-/tmp location and confirm it's flagged
        # unsafe, while a child of it (a real project checkout) is not.
        fake_temp = tmp_path / "os_specific_temp"
        fake_temp.mkdir()
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(fake_temp))
        assert is_unsafe_scan_root(str(fake_temp)) is True
        assert is_unsafe_scan_root(str(fake_temp / "project")) is False

    def test_home_is_derived_at_runtime(self, tmp_path, monkeypatch):
        fake_home = tmp_path / "home_user"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
        assert is_unsafe_scan_root(str(fake_home)) is True
        assert is_unsafe_scan_root(str(fake_home / "code" / "proj")) is False


class TestIsSkippableDir:
    """BACK-552: env/venv/build/dist are ambiguous names — context-sensitive,
    not a bare-name membership check. A directory-walk pruning helper."""

    def test_unconditional_names_always_skip(self, tmp_path):
        assert is_skippable_dir(tmp_path, '.git') is True
        assert is_skippable_dir(tmp_path, 'node_modules') is True
        assert is_skippable_dir(tmp_path, '__pycache__') is True

    def test_unrelated_name_never_skips(self, tmp_path):
        assert is_skippable_dir(tmp_path, 'src') is False
        assert is_skippable_dir(tmp_path, 'lib') is False

    def test_ambiguous_name_with_source_files_not_skipped(self, tmp_path):
        for name in ('env', 'venv', 'build', 'dist'):
            d = tmp_path / name
            d.mkdir()
            (d / 'Real.java').write_text('class Real {}')
            assert is_skippable_dir(tmp_path, name) is False, name

    def test_ambiguous_name_with_no_source_files_skipped(self, tmp_path):
        for name in ('env', 'venv', 'build', 'dist'):
            d = tmp_path / name
            d.mkdir()
            (d / 'nested').mkdir()
            assert is_skippable_dir(tmp_path, name) is True, name

    def test_ambiguous_name_missing_dir_skipped(self, tmp_path):
        # Directory doesn't exist on disk (e.g. a stale walk entry) — fail safe.
        assert is_skippable_dir(tmp_path, 'venv') is True

    def test_ambiguous_name_with_only_data_files_skipped(self, tmp_path):
        # A real venv/build dir with non-source files (configs, binaries) at
        # its top level still has no *code* files there, so it's skipped.
        d = tmp_path / 'dist'
        d.mkdir()
        (d / 'package-1.0.whl').write_bytes(b'')
        (d / 'pyvenv.cfg').write_text('')
        assert is_skippable_dir(tmp_path, 'dist') is True
