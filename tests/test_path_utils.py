"""Tests for reveal/utils/path_utils.py - path utilities."""

import tempfile
import pytest
from pathlib import Path, PureWindowsPath
from reveal.utils.path_utils import (
    find_file_in_parents,
    search_parents,
    search_parents_within_ceiling,
    find_project_root,
    resolve_project_root,
    reveal_yaml_is_root,
    get_relative_to_root,
    detect_non_python_language,
    to_posix,
    to_relative_display,
    is_unsafe_scan_root,
    is_skippable_dir,
    is_test_dir,
    is_test_filename,
    is_vendor_dir,
    is_minified_filename,
    classify_path_provenance,
)

# BACK-1149: exercises internal functions/modules directly, not CLI/MCP/network surface
pytestmark = pytest.mark.component


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


class TestResolveProjectRoot:
    """BACK-612: the unified tiered resolver shared by depends://, config,
    and the I002/D005 rules. Tiers, first wins: -1 root_override → 0
    .reveal.yaml root:true → 1 package marker → 2 VCS → 3 __init__ chain."""

    def test_root_override_beats_everything(self, tmp_path):
        (tmp_path / '.reveal.yaml').write_text('root: true\n')
        (tmp_path / '.git').mkdir()
        comp = tmp_path / 'a' / 'b'
        comp.mkdir(parents=True)
        target = comp / 'x.c'
        target.write_text('int x;\n')

        assert resolve_project_root(target, root_override=comp) == comp

    def test_reveal_root_beats_ancestor_vcs(self, tmp_path):
        (tmp_path / '.git').mkdir()
        comp = tmp_path / 'vendor' / 'thing'
        (comp / 'src').mkdir(parents=True)
        (comp / '.reveal.yaml').write_text('root: true\n')
        target = comp / 'src' / 'x.c'
        target.write_text('int x;\n')

        assert resolve_project_root(target) == comp

    def test_package_marker_beats_ancestor_vcs(self, tmp_path):
        (tmp_path / '.git').mkdir()
        pkg = tmp_path / 'component'
        (pkg / 'src').mkdir(parents=True)
        (pkg / 'pyproject.toml').write_text('[project]\nname="c"\n')
        target = pkg / 'src' / 'm.py'
        target.write_text('x = 1\n')

        assert resolve_project_root(target) == pkg

    def test_package_marker_disabled_falls_through_to_vcs(self, tmp_path):
        (tmp_path / '.git').mkdir()
        pkg = tmp_path / 'component'
        (pkg / 'src').mkdir(parents=True)
        (pkg / 'pyproject.toml').write_text('[project]\nname="c"\n')
        target = pkg / 'src' / 'm.py'
        target.write_text('x = 1\n')

        # config-style call (no package tier) climbs past the marker to the VCS root.
        assert resolve_project_root(
            target, use_package_markers=False
        ) == tmp_path

    def test_vcs_root_when_no_package_marker(self, tmp_path):
        (tmp_path / '.git').mkdir()
        target = tmp_path / 'src' / 'm.py'
        (tmp_path / 'src').mkdir()
        target.write_text('x = 1\n')

        assert resolve_project_root(target) == tmp_path

    def test_init_package_dir_is_not_promoted_to_root(self, tmp_path):
        """The __init__.py guard: a marker-bearing dir that is also a Python
        package is skipped so the climb finds the real root above it."""
        (tmp_path / '.git').mkdir()
        pkg = tmp_path / 'homeassistant'
        pkg.mkdir()
        (pkg / '__init__.py').write_text('')
        (pkg / 'setup.py').write_text('# source module, not a root marker\n')
        target = pkg / 'core.py'
        target.write_text('x = 1\n')

        # setup.py sits in a package dir → skipped; real root is the VCS root.
        assert resolve_project_root(target) == tmp_path

    def test_init_guard_and_chain_compose_when_no_higher_root(self, tmp_path):
        """Guard (tier 1) + contiguous __init__ chain (tier 3) compose: when a
        marker-bearing package dir has NO real root above it, the guard skips
        it but the chain recovers the same dir — no over-climb into nowhere."""
        # No .git, no ancestor marker anywhere before the ceiling.
        pkg = tmp_path / 'proj' / 'app'
        pkg.mkdir(parents=True)
        (pkg / '__init__.py').write_text('')
        (pkg / 'pyproject.toml').write_text('[project]\nname="app"\n')
        target = pkg / 'm.py'
        target.write_text('x = 1\n')

        assert resolve_project_root(target, python_init_chain=True) == pkg

    def test_chain_climbs_to_contiguous_top(self, tmp_path):
        pkg = tmp_path / 'pkg'
        (pkg / 'sub').mkdir(parents=True)
        (pkg / '__init__.py').write_text('')
        (pkg / 'sub' / '__init__.py').write_text('')
        target = pkg / 'sub' / 'm.py'
        target.write_text('x = 1\n')

        assert resolve_project_root(
            target,
            honor_reveal_root=False,
            use_package_markers=False,
            use_vcs=False,
            python_init_chain=True,
        ) == pkg

    def test_js_workspace_lerna_json_beats_nearest_package_json(self, tmp_path):
        """BACK-698: a lerna.json ancestor is the true root for a package
        nested inside a monorepo — not the package's own package.json."""
        workspace = tmp_path / 'nest'
        workspace.mkdir()
        (workspace / 'lerna.json').write_text('{}\n')
        pkg = workspace / 'packages' / 'common'
        (pkg / 'src').mkdir(parents=True)
        (pkg / 'package.json').write_text('{"name": "@nestjs/common"}\n')
        target = pkg / 'src' / 'index.ts'
        target.write_text('export {};\n')

        assert resolve_project_root(target) == workspace

    def test_js_workspace_pnpm_yaml_beats_nearest_package_json(self, tmp_path):
        workspace = tmp_path / 'monorepo'
        workspace.mkdir()
        (workspace / 'pnpm-workspace.yaml').write_text("packages:\n  - 'packages/*'\n")
        pkg = workspace / 'packages' / 'utils'
        pkg.mkdir(parents=True)
        (pkg / 'package.json').write_text('{"name": "utils"}\n')
        target = pkg / 'index.ts'
        target.write_text('export {};\n')

        assert resolve_project_root(target) == workspace

    def test_js_workspace_package_json_workspaces_field_beats_nearest(self, tmp_path):
        """npm/yarn workspaces: the root package.json declares a "workspaces"
        array rather than using a separate lerna/pnpm marker file."""
        workspace = tmp_path / 'monorepo'
        workspace.mkdir()
        (workspace / 'package.json').write_text('{"name": "root", "workspaces": ["packages/*"]}\n')
        pkg = workspace / 'packages' / 'utils'
        pkg.mkdir(parents=True)
        (pkg / 'package.json').write_text('{"name": "utils"}\n')
        target = pkg / 'index.ts'
        target.write_text('export {};\n')

        assert resolve_project_root(target) == workspace

    def test_single_package_js_repo_not_promoted_past_own_root(self, tmp_path):
        """No ancestor declares workspace membership → the nearest package.json
        stays the root, exactly as before BACK-698 (no regression for the
        common single-package case)."""
        (tmp_path / '.git').mkdir()
        pkg = tmp_path / 'app'
        (pkg / 'src').mkdir(parents=True)
        (pkg / 'package.json').write_text('{"name": "app"}\n')
        target = pkg / 'src' / 'index.ts'
        target.write_text('export {};\n')

        assert resolve_project_root(target) == pkg

    def test_unrelated_ancestor_package_json_does_not_count_as_workspace(self, tmp_path):
        """An ancestor package.json with no "workspaces" field is just another
        ordinary package — must NOT be promoted to root (would silently widen
        the scan to an unrelated sibling tree)."""
        (tmp_path / 'package.json').write_text('{"name": "unrelated-ancestor"}\n')
        pkg = tmp_path / 'nested' / 'app'
        (pkg / 'src').mkdir(parents=True)
        (pkg / 'package.json').write_text('{"name": "app"}\n')
        target = pkg / 'src' / 'index.ts'
        target.write_text('export {};\n')

        assert resolve_project_root(target) == pkg

    def test_js_workspace_marker_ignored_for_non_js_package_root(self, tmp_path):
        """The workspace climb is gated on the matched tier-1 root itself
        having a package.json — a Python project sitting under an ancestor
        pnpm-workspace.yaml (e.g. a mixed-language monorepo) must not be
        redirected to that unrelated workspace root."""
        workspace = tmp_path / 'monorepo'
        workspace.mkdir()
        (workspace / 'pnpm-workspace.yaml').write_text("packages:\n  - 'packages/*'\n")
        pkg = workspace / 'services' / 'api'
        (pkg / 'src').mkdir(parents=True)
        (pkg / 'pyproject.toml').write_text('[project]\nname="api"\n')
        target = pkg / 'src' / 'm.py'
        target.write_text('x = 1\n')

        assert resolve_project_root(target) == pkg

    def test_returns_none_when_nothing_matches(self, tmp_path):
        target = tmp_path / 'loose' / 'm.py'
        (tmp_path / 'loose').mkdir()
        target.write_text('x = 1\n')

        assert resolve_project_root(
            target, honor_reveal_root=False, use_package_markers=False, use_vcs=False
        ) is None

    def test_reveal_yaml_without_root_true_does_not_pin(self, tmp_path):
        (tmp_path / '.git').mkdir()
        comp = tmp_path / 'vendor' / 'thing'
        (comp / 'src').mkdir(parents=True)
        (comp / '.reveal.yaml').write_text('exclude:\n  - "*.tmp"\n')
        target = comp / 'src' / 'x.c'
        target.write_text('int x;\n')

        assert resolve_project_root(target) == tmp_path

    def test_reveal_yaml_is_root_helper(self, tmp_path):
        yes = tmp_path / 'a.yaml'
        yes.write_text('root: true\n')
        no = tmp_path / 'b.yaml'
        no.write_text('root: false\n')
        other = tmp_path / 'c.yaml'
        other.write_text('exclude: ["x"]\n')

        assert reveal_yaml_is_root(yes) is True
        assert reveal_yaml_is_root(no) is False
        assert reveal_yaml_is_root(other) is False
        assert reveal_yaml_is_root(tmp_path / 'missing.yaml') is False


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


class TestToRelativeDisplay:
    """to_relative_display() (BACK-1194) — the shared helper replacing
    overview.py/deps.py/imports.py/architecture.py's duplicated
    relative_to()-then-except-ValueError idiom.

    The bug: Path.relative_to() is lexical, not filesystem-aware. When a
    CLI target is given as a relative path (e.g. `.` from inside the
    project dir) while the file being displayed arrives already absolute
    (typical of a separate file-walk subsystem), relative_to() raises and
    the caller's fallback returns the raw absolute path -- leaking the
    analyst's local filesystem layout/username into a DD deliverable.
    """

    def test_relative_base_absolute_file_still_relativizes(self, tmp_path, monkeypatch):
        """The exact repro shape: base_path relative (unresolved), file
        already absolute -- this is what silently leaked before the fix."""
        (tmp_path / "sub").mkdir()
        abs_file = str((tmp_path / "sub" / "mod.py").resolve())
        monkeypatch.chdir(tmp_path)
        assert to_relative_display(abs_file, Path(".")) == "sub/mod.py"

    def test_both_already_absolute_still_works(self, tmp_path):
        (tmp_path / "sub").mkdir()
        abs_file = tmp_path / "sub" / "mod.py"
        assert to_relative_display(str(abs_file), tmp_path) == "sub/mod.py"

    def test_genuinely_outside_base_falls_back_to_original(self, tmp_path):
        outside = tmp_path.parent / "elsewhere.py"
        assert to_relative_display(str(outside), tmp_path) == to_posix(str(outside))

    def test_no_base_path_returns_original(self):
        assert to_relative_display("/abs/file.py", None) == "/abs/file.py"

    def test_windows_style_result_normalized_to_posix(self, tmp_path, monkeypatch):
        (tmp_path / "sub").mkdir()
        abs_file = str((tmp_path / "sub" / "mod.py").resolve())
        monkeypatch.chdir(tmp_path)
        assert "\\" not in to_relative_display(abs_file, Path("."))


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


class TestIsTestDir:
    """BACK-1199: canonical test-directory vocabulary, shared by
    surface.py, hotspots.py, and rules/maintainability/M102.py — previously
    each redefined this independently, and M102's copy didn't know about
    spec/specs/__tests__ (RSpec/Jest conventions), so on any non-Python
    test suite M102 could report test files as orphaned source."""

    def test_canonical_names_recognized(self):
        for name in ('test', 'tests', 'spec', 'specs', '__tests__'):
            assert is_test_dir(name) is True, name

    def test_exact_match_only_not_prefix(self):
        # A real package directory named e.g. `testpkg` must NOT match —
        # this is exact-set membership, not a `startswith('test')` prefix
        # check (that broader match is surface.py's own opt-in layer).
        for name in ('testpkg', 'testing', 'contests', 'attestation'):
            assert is_test_dir(name) is False, name


class TestIsTestFilename:
    """BACK-1199: canonical test_/_test filename vocabulary."""

    def test_generic_prefix_and_suffix_match(self):
        assert is_test_filename('test_foo') is True
        assert is_test_filename('foo_test') is True

    def test_bare_canonical_name_matches(self):
        # A top-level `tests.py`/`spec.py` is itself a test file.
        assert is_test_filename('tests') is True
        assert is_test_filename('spec') is True

    def test_unrelated_name_does_not_match(self):
        assert is_test_filename('main') is False
        assert is_test_filename('testpkg') is False


class TestIsVendorDir:
    """BACK-1195: canonical vendored/third-party directory vocabulary."""

    def test_canonical_names_recognized(self):
        for name in ('vendor', 'third_party', 'thirdparty', 'node_modules', 'bower_components'):
            assert is_vendor_dir(name) is True, name

    def test_unrelated_name_does_not_match(self):
        for name in ('vendors', 'src', 'lib'):
            assert is_vendor_dir(name) is False, name


class TestIsMinifiedFilename:
    """BACK-1195: minified/bundled build-artifact filename suffixes."""

    def test_recognized_suffixes(self):
        for name in ('app.min.js', 'app.min.css', 'app-min.js', 'app-min.css', 'app.bundle.js'):
            assert is_minified_filename(name) is True, name

    def test_unrelated_filename_does_not_match(self):
        for name in ('app.js', 'minimal.py', 'admin.js'):
            assert is_minified_filename(name) is False, name


class TestClassifyPathProvenance:
    """BACK-1195: 'test'/'vendor'/'minified'/None classification, cheap
    path-only signals, no file content read. Priority order matters when a
    file matches more than one signal."""

    def test_first_party_file_is_none(self):
        assert classify_path_provenance(('src',), 'app.py') is None

    def test_top_level_vendor_dir(self):
        assert classify_path_provenance(('vendor',), 'thing.rb') == 'vendor'

    def test_nested_vendor_dir(self):
        assert classify_path_provenance(('app', 'assets', 'vendor'), 'lib.js') == 'vendor'

    def test_spec_dir_is_test(self):
        assert classify_path_provenance(('spec',), 'thing_spec.rb') == 'test'

    def test_minified_filename(self):
        assert classify_path_provenance((), 'app.min.js') == 'minified'

    def test_test_takes_priority_over_vendor(self):
        # A vendored dependency's own bundled test suite: test-ness is the
        # more actionable DD signal (BACK-1199's motivating case).
        assert classify_path_provenance(('vendor', 'spec'), 'thing_spec.rb') == 'test'
