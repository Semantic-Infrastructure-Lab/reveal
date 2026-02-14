"""Tests for reveal/utils/path_utils.py - path utilities."""

import pytest
from pathlib import Path
from reveal.utils.path_utils import (
    find_file_in_parents,
    search_parents,
    find_project_root,
    get_relative_to_root
)


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
