"""Tests for reveal.utils.path_utils module."""

import pytest
from pathlib import Path
from reveal.utils.path_utils import (
    find_file_in_parents,
    search_parents,
    find_project_root,
    get_relative_to_root
)


class TestFindFileInParents:
    """Tests for find_file_in_parents function."""

    def test_find_file_in_same_directory(self, tmp_path):
        """Should find file in the same directory."""
        # Create test file
        test_file = tmp_path / "config.yaml"
        test_file.touch()

        # Search from the directory
        result = find_file_in_parents(tmp_path, "config.yaml")

        assert result == test_file
        assert result.exists()

    def test_find_file_in_parent_directory(self, tmp_path):
        """Should find file in parent directory."""
        # Create test file in parent
        config_file = tmp_path / "config.yaml"
        config_file.touch()

        # Create subdirectory
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        # Search from subdirectory
        result = find_file_in_parents(subdir, "config.yaml")

        assert result == config_file

    def test_find_file_starting_from_file_path(self, tmp_path):
        """Should handle starting from a file path (not directory)."""
        # Create config in root
        config = tmp_path / "config.yaml"
        config.touch()

        # Create subdirectory with a file
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        some_file = subdir / "module.py"
        some_file.touch()

        # Search starting from the file (should search from its parent)
        result = find_file_in_parents(some_file, "config.yaml")

        assert result == config

    def test_find_file_in_nested_structure(self, tmp_path):
        """Should find file multiple levels up."""
        # Create config at root
        config = tmp_path / "pyproject.toml"
        config.touch()

        # Create nested structure
        deep_dir = tmp_path / "src" / "module" / "submodule"
        deep_dir.mkdir(parents=True)

        # Search from deep directory
        result = find_file_in_parents(deep_dir, "pyproject.toml")

        assert result == config

    def test_file_not_found_returns_none(self, tmp_path):
        """Should return None if file not found."""
        result = find_file_in_parents(tmp_path, "nonexistent.txt")
        assert result is None

    def test_respects_max_depth(self, tmp_path):
        """Should stop searching after max_depth levels."""
        # Create config at root
        config = tmp_path / "config.yaml"
        config.touch()

        # Create deep structure (3 levels)
        deep_dir = tmp_path / "a" / "b" / "c"
        deep_dir.mkdir(parents=True)

        # Search with max_depth=2 (should not reach root)
        result = find_file_in_parents(deep_dir, "config.yaml", max_depth=2)

        assert result is None

    def test_finds_closest_file_when_multiple_exist(self, tmp_path):
        """Should return the closest file when multiple exist."""
        # Create config at root
        root_config = tmp_path / "config.yaml"
        root_config.touch()

        # Create subdirectory with its own config
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        sub_config = subdir / "config.yaml"
        sub_config.touch()

        # Search from subdirectory - should find closest
        result = find_file_in_parents(subdir, "config.yaml")

        assert result == sub_config


class TestSearchParents:
    """Tests for search_parents function."""

    def test_search_with_custom_condition(self, tmp_path):
        """Should find parent matching custom condition."""
        # Create structure
        docs = tmp_path / "docs"
        docs.mkdir()
        guides = docs / "guides"
        guides.mkdir()

        # Search for parent named 'docs'
        result = search_parents(guides, lambda p: p.name == "docs")

        assert result == docs

    def test_search_starting_from_file(self, tmp_path):
        """Should handle starting from file path."""
        # Create structure
        src = tmp_path / "src"
        src.mkdir()
        module = src / "module.py"
        module.touch()

        # Search for 'src' starting from file
        result = search_parents(module, lambda p: p.name == "src")

        assert result == src

    def test_condition_checking_file_existence(self, tmp_path):
        """Should work with condition that checks file existence."""
        # Create project structure
        project = tmp_path / "project"
        project.mkdir()
        pyproject = project / "pyproject.toml"
        pyproject.touch()

        src = project / "src"
        src.mkdir()

        # Search for parent containing pyproject.toml
        result = search_parents(
            src,
            lambda p: (p / "pyproject.toml").exists()
        )

        assert result == project

    def test_no_match_returns_none(self, tmp_path):
        """Should return None if no parent matches condition."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        result = search_parents(
            subdir,
            lambda p: p.name == "nonexistent"
        )

        assert result is None

    def test_respects_max_depth(self, tmp_path):
        """Should stop after max_depth levels."""
        # Create deep structure
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)

        # Search for root with limited depth
        result = search_parents(
            deep,
            lambda p: p.name == tmp_path.name,
            max_depth=2
        )

        assert result is None

    def test_stops_at_filesystem_root(self, tmp_path):
        """Should stop at filesystem root."""
        # Search for something that doesn't exist
        # Should eventually stop at filesystem root, not infinite loop
        result = search_parents(
            tmp_path,
            lambda p: p.name == "will_never_match_anything_ever_xyz",
            max_depth=100  # Large but not infinite
        )

        assert result is None


class TestFindProjectRoot:
    """Tests for find_project_root function."""

    def test_find_root_with_pyproject_toml(self, tmp_path):
        """Should find root containing pyproject.toml."""
        # Create project structure
        pyproject = tmp_path / "pyproject.toml"
        pyproject.touch()

        src = tmp_path / "src"
        src.mkdir()

        result = find_project_root(src)

        assert result == tmp_path

    def test_find_root_with_git(self, tmp_path):
        """Should find root containing .git."""
        # Create .git directory
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        src = tmp_path / "src"
        src.mkdir()

        result = find_project_root(src)

        assert result == tmp_path

    def test_find_root_with_setup_py(self, tmp_path):
        """Should find root containing setup.py."""
        setup = tmp_path / "setup.py"
        setup.touch()

        src = tmp_path / "src"
        src.mkdir()

        result = find_project_root(src)

        assert result == tmp_path

    def test_custom_markers(self, tmp_path):
        """Should work with custom marker list."""
        # Create custom marker
        makefile = tmp_path / "Makefile"
        makefile.touch()

        src = tmp_path / "src"
        src.mkdir()

        result = find_project_root(src, markers=["Makefile"])

        assert result == tmp_path

    def test_no_markers_found_returns_none(self, tmp_path):
        """Should return None if no markers found."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        result = find_project_root(subdir)

        assert result is None

    def test_finds_closest_root_with_multiple_markers(self, tmp_path):
        """Should find closest root when multiple exist."""
        # Outer project
        outer_git = tmp_path / ".git"
        outer_git.mkdir()

        # Inner project
        inner = tmp_path / "nested_project"
        inner.mkdir()
        inner_pyproject = inner / "pyproject.toml"
        inner_pyproject.touch()

        src = inner / "src"
        src.mkdir()

        result = find_project_root(src)

        # Should find inner project, not outer
        assert result == inner

    def test_checks_all_default_markers(self, tmp_path):
        """Should check multiple marker types."""
        # Test with different marker types
        markers = [
            "Cargo.toml",  # Rust
            "package.json",  # Node
            "go.mod",  # Go
            "setup.cfg",  # Python
        ]

        for marker in markers:
            test_dir = tmp_path / marker.replace(".", "_")
            test_dir.mkdir()
            marker_file = test_dir / marker
            marker_file.touch()

            subdir = test_dir / "src"
            subdir.mkdir()

            result = find_project_root(subdir)
            assert result == test_dir, f"Failed to find root with {marker}"


class TestGetRelativeToRoot:
    """Tests for get_relative_to_root function."""

    def test_returns_relative_path_from_root(self, tmp_path):
        """Should return path relative to project root."""
        # Create project structure
        pyproject = tmp_path / "pyproject.toml"
        pyproject.touch()

        src = tmp_path / "src"
        src.mkdir()
        module = src / "module.py"
        module.touch()

        result = get_relative_to_root(module)

        assert result == Path("src/module.py")

    def test_handles_absolute_paths(self, tmp_path):
        """Should resolve absolute paths."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.touch()

        src = tmp_path / "src"
        src.mkdir()

        # Use absolute path
        result = get_relative_to_root(src.resolve())

        assert result == Path("src")

    def test_returns_original_path_if_no_root_found(self, tmp_path):
        """Should return original path if no root markers found."""
        # No marker files
        subdir = tmp_path / "orphan"
        subdir.mkdir()

        result = get_relative_to_root(subdir)

        # Should return the resolved absolute path
        assert result == subdir.resolve()

    def test_custom_root_markers(self, tmp_path):
        """Should work with custom root markers."""
        makefile = tmp_path / "Makefile"
        makefile.touch()

        src = tmp_path / "src"
        src.mkdir()

        result = get_relative_to_root(src, root_markers=["Makefile"])

        assert result == Path("src")

    def test_handles_path_outside_root(self, tmp_path):
        """Should handle path that's not actually in the root."""
        # Create two separate directories
        project1 = tmp_path / "project1"
        project1.mkdir()
        (project1 / "pyproject.toml").touch()

        project2 = tmp_path / "project2"
        project2.mkdir()

        # Try to get relative path for project2 from project1's perspective
        # This should return the original path since it's not relative to root
        result = get_relative_to_root(project2)

        assert result == project2.resolve()

    def test_handles_relative_paths(self, tmp_path, monkeypatch):
        """Should resolve relative paths before processing."""
        # Create project in tmp_path
        pyproject = tmp_path / "pyproject.toml"
        pyproject.touch()

        src = tmp_path / "src"
        src.mkdir()

        # Change to tmp_path directory
        monkeypatch.chdir(tmp_path)

        # Use relative path
        result = get_relative_to_root(Path("src"))

        assert result == Path("src")

    def test_path_at_root(self, tmp_path):
        """Should handle path that is the root itself."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.touch()

        result = get_relative_to_root(tmp_path)

        assert result == Path(".")
