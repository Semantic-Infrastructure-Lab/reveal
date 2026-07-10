"""Tests for depends:// adapter — inverse module dependency graph."""

import textwrap
import unittest
from pathlib import Path

import pytest


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_pkg(tmp_path):
    """
    pkg/
      utils.py        — no imports
      models.py       — imports utils
      api.py          — imports utils, models
      cli.py          — imports models
    """
    _write(tmp_path / 'pkg' / 'utils.py', """\
        def helper(): pass
    """)
    _write(tmp_path / 'pkg' / 'models.py', """\
        from .utils import helper
        class User: pass
    """)
    _write(tmp_path / 'pkg' / 'api.py', """\
        from .utils import helper
        from .models import User
        def handler(): pass
    """)
    _write(tmp_path / 'pkg' / 'cli.py', """\
        from .models import User
        def main(): pass
    """)
    # pyproject.toml so find_project_root stops here
    (tmp_path / 'pyproject.toml').write_text('[project]\nname = "test"\n')
    return tmp_path


@pytest.fixture
def star_pkg(tmp_path):
    """Package with a star import to test star_import type detection."""
    _write(tmp_path / 'pkg' / 'constants.py', 'X = 1\n')
    _write(tmp_path / 'pkg' / 'other.py', 'from .constants import *\n')
    (tmp_path / 'pyproject.toml').write_text('[project]\nname = "test"\n')
    return tmp_path


@pytest.fixture
def gradle_pkg(tmp_path):
    """
    Gradle-style Java tree, no .git/pyproject.toml anywhere — only a
    `settings.gradle.kts` at the true root — with the dependent in a sibling
    package directory (com/example/app) from the target (com/example/util).
    Regression fixture for BACK-498: find_project_root() didn't recognize
    Gradle/Maven/dotnet/SPM/Composer root markers, so depends:// fell back to
    scanning just the target file's own parent dir and missed this dependent
    entirely (while imports://?rank=fan-in, which scans the whole given
    directory, saw it fine).
    """
    (tmp_path / 'settings.gradle.kts').write_text('rootProject.name = "demo"\n')
    _write(tmp_path / 'src/main/java/com/example/util/Helper.java', """\
        package com.example.util;
        public class Helper {
            public static int add(int a, int b) { return a + b; }
        }
    """)
    _write(tmp_path / 'src/main/java/com/example/app/Main.java', """\
        package com.example.app;
        import com.example.util.Helper;
        public class Main {
            public static void main(String[] args) { Helper.add(1, 2); }
        }
    """)
    return tmp_path


# ---------------------------------------------------------------------------
# Unit: DependsAdapter with controlled fixture data
# ---------------------------------------------------------------------------

class TestDependsAdapterFileTarget:
    """Single-file target: depends://pkg/utils.py"""

    def test_type_is_module_dependents(self, simple_pkg):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'utils.py'))
        r = a.get_structure()
        assert r['type'] == 'module_dependents'

    def test_contract_version_present(self, simple_pkg):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'utils.py'))
        r = a.get_structure()
        assert r['contract_version'] == '1.1'

    def test_utils_has_two_importers(self, simple_pkg):
        """utils.py is imported by models.py and api.py — cli.py does not import it."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'utils.py'))
        r = a.get_structure()
        assert r['count'] == 2
        importer_names = {Path(d['file']).name for d in r['dependents']}
        assert 'models.py' in importer_names
        assert 'api.py' in importer_names
        assert 'cli.py' not in importer_names

    def test_models_has_two_importers(self, simple_pkg):
        """models.py is imported by api.py and cli.py."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'models.py'))
        r = a.get_structure()
        assert r['count'] == 2
        importer_names = {Path(d['file']).name for d in r['dependents']}
        assert 'api.py' in importer_names
        assert 'cli.py' in importer_names

    def test_cli_has_no_importers(self, simple_pkg):
        """cli.py is not imported by anyone."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'cli.py'))
        r = a.get_structure()
        assert r['count'] == 0
        assert r['dependents'] == []

    def test_dependent_record_has_required_fields(self, simple_pkg):
        """Each dependent record exposes file, line, names, type, is_relative."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'utils.py'))
        r = a.get_structure()
        for dep in r['dependents']:
            assert 'file' in dep
            assert 'line' in dep
            assert 'names' in dep
            assert 'type' in dep
            assert 'is_relative' in dep

    def test_imported_names_correct(self, simple_pkg):
        """models.py imports 'helper' from utils — names should include 'helper'."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'utils.py'))
        r = a.get_structure()
        models_dep = next(d for d in r['dependents'] if Path(d['file']).name == 'models.py')
        assert 'helper' in models_dep['names']

    def test_nonexistent_path_returns_error(self, tmp_path):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(tmp_path / 'does_not_exist.py'))
        r = a.get_structure()
        assert 'error' in r


class TestDependsAdapterDirectoryTarget:
    """Directory target: depends://pkg/ — reverse dependency summary."""

    def test_type_is_dependency_summary(self, simple_pkg):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg'))
        r = a.get_structure()
        assert r['type'] == 'dependency_summary'

    def test_utils_is_most_imported(self, simple_pkg):
        """utils.py has 2 importers, models.py has 2 — both should appear at top."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg'))
        r = a.get_structure()
        modules = r['modules']
        names = [Path(m['module']).name for m in modules]
        assert 'utils.py' in names
        assert 'models.py' in names

    def test_top_n_limits_results(self, simple_pkg):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg'), query='top=1')
        r = a.get_structure()
        assert len(r['modules']) == 1

    def test_sorted_by_dependent_count_descending(self, simple_pkg):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg'))
        r = a.get_structure()
        counts = [m['dependent_count'] for m in r['modules']]
        assert counts == sorted(counts, reverse=True)

    def test_modules_include_dependents_list(self, simple_pkg):
        """Each module entry lists the actual importer file paths."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg'))
        r = a.get_structure()
        utils_entry = next(
            m for m in r['modules'] if Path(m['module']).name == 'utils.py'
        )
        importer_names = {Path(p).name for p in utils_entry['dependents']}
        assert 'models.py' in importer_names
        assert 'api.py' in importer_names

    def test_leaf_modules_not_in_results(self, simple_pkg):
        """cli.py has no importers — should not appear in dependency_summary."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg'))
        r = a.get_structure()
        names = [Path(m['module']).name for m in r['modules']]
        assert 'cli.py' not in names


class TestDependsAdapterStarImport:
    """Star imports are captured (type=star_import)."""

    def test_star_import_captured(self, star_pkg):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(star_pkg / 'pkg' / 'constants.py'))
        r = a.get_structure()
        assert r['count'] == 1
        dep = r['dependents'][0]
        assert dep['type'] == 'star_import'


class TestDependsAdapterDotFormat:
    """?format=dot produces GraphViz output."""

    def test_dot_format_starts_with_digraph(self, simple_pkg):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg'), query='format=dot')
        r = a.get_structure()
        # _format flag is set
        assert r.get('_format') == 'dot'

    def test_dot_renderer_output(self, simple_pkg, capsys):
        from reveal.adapters.depends import DependsAdapter, DependsRenderer
        a = DependsAdapter(str(simple_pkg / 'pkg'), query='format=dot')
        r = a.get_structure()
        DependsRenderer.render_structure(r, format='text')
        captured = capsys.readouterr()
        assert 'digraph depends' in captured.out
        assert 'rankdir=LR' in captured.out


class TestDependsAdapterMetadata:
    """Metadata fields are populated."""

    def test_metadata_in_result(self, simple_pkg):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'utils.py'))
        r = a.get_structure()
        assert 'metadata' in r
        meta = r['metadata']
        assert 'total_files_scanned' in meta
        assert 'total_import_edges' in meta

    def test_total_import_edges_positive(self, simple_pkg):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'utils.py'))
        r = a.get_structure()
        assert r['metadata']['total_import_edges'] > 0


class TestDependsAdapterSchema:
    """Schema and help methods."""

    def test_get_schema_has_adapter_key(self):
        from reveal.adapters.depends import DependsAdapter
        schema = DependsAdapter.get_schema()
        assert schema['adapter'] == 'depends'
        assert 'uri_syntax' in schema
        assert 'query_params' in schema
        assert 'output_types' in schema

    def test_get_help_has_name(self):
        from reveal.adapters.depends import DependsAdapter
        help_data = DependsAdapter.get_help()
        assert help_data['name'] == 'depends'
        assert 'examples' in help_data

    def test_adapter_registered_as_depends_scheme(self):
        from reveal.adapters.base import get_adapter_class
        cls = get_adapter_class('depends')
        assert cls is not None
        from reveal.adapters.depends import DependsAdapter
        assert cls is DependsAdapter

    def test_renderer_registered(self):
        from reveal.adapters.base import get_renderer_class
        renderer = get_renderer_class('depends')
        assert renderer is not None


class TestDependsAdapterRenderer:
    """Renderer produces expected output."""

    def test_render_structure_file_target(self, simple_pkg, capsys):
        from reveal.adapters.depends import DependsAdapter, DependsRenderer
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'utils.py'))
        r = a.get_structure()
        DependsRenderer.render_structure(r, format='text')
        captured = capsys.readouterr()
        assert 'Dependents of:' in captured.out
        assert '2 file(s) import this module' in captured.out

    def test_render_structure_json(self, simple_pkg, capsys):
        from reveal.adapters.depends import DependsAdapter, DependsRenderer
        import json
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'utils.py'))
        r = a.get_structure()
        DependsRenderer.render_structure(r, format='json')
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed['type'] == 'module_dependents'

    def test_render_no_dependents_message(self, simple_pkg, capsys):
        from reveal.adapters.depends import DependsAdapter, DependsRenderer
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'cli.py'))
        r = a.get_structure()
        DependsRenderer.render_structure(r, format='text')
        captured = capsys.readouterr()
        assert 'No dependents found' in captured.out

    def test_render_summary_directory(self, simple_pkg, capsys):
        from reveal.adapters.depends import DependsAdapter, DependsRenderer
        a = DependsAdapter(str(simple_pkg / 'pkg'))
        r = a.get_structure()
        DependsRenderer.render_structure(r, format='text')
        captured = capsys.readouterr()
        assert 'Reverse Dependency Summary' in captured.out


class TestDependsAdapterCrossModuleRoot:
    """BACK-498: cross-package-directory dependents for Gradle/Maven/dotnet/
    SPM/Composer trees with no .git/pyproject.toml, only their own ecosystem's
    root marker."""

    def test_gradle_root_marker_finds_sibling_package_dependent(self, gradle_pkg):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(gradle_pkg / 'src/main/java/com/example/util/Helper.java'))
        r = a.get_structure()
        assert r['count'] == 1
        dependent_paths = [d['file'] for d in r['dependents']]
        assert any('Main.java' in p for p in dependent_paths)

    def test_no_root_marker_falls_back_to_src_ancestor(self, tmp_path):
        """No settings.gradle.kts either: widen to the nearest 'src' ancestor
        rather than the bare parent dir (still finds the sibling-package
        dependent one level up from a same-name-only fallback)."""
        from reveal.adapters.depends import DependsAdapter
        _write(tmp_path / 'src/main/java/com/example/util/Helper.java', """\
            package com.example.util;
            public class Helper {
                public static int add(int a, int b) { return a + b; }
            }
        """)
        _write(tmp_path / 'src/main/java/com/example/app/Main.java', """\
            package com.example.app;
            import com.example.util.Helper;
            public class Main {
                public static void main(String[] args) { Helper.add(1, 2); }
            }
        """)
        a = DependsAdapter(str(tmp_path / 'src/main/java/com/example/util/Helper.java'))
        r = a.get_structure()
        assert r['count'] == 1

    # BACK-515: every language depends:// builds an import graph for must have
    # its project-root marker recognized by `_has_project_marker`. A missing
    # marker is not cosmetic — search_parents climbs past the real root to some
    # ancestor `.git`, and _build_graph then scans every file under it (the
    # reported "hang" was a full monorepo scan, not an infinite loop). This
    # matrix guards the BACK-514 language set (Lua/Scala/Dart/Zig/GDScript);
    # add a row whenever depends:// gains another language.
    #
    # Each row: (marker filename or '*.ext' glob, module-file extension,
    # `require`/import line importing `bar`, `bar` module body).
    _ROOT_MARKER_CASES = [
        ('mylib-1.0.rockspec', 'lua', 'local bar = require("bar")', 'return {}'),
        ('build.sbt', 'scala', 'import bar.Thing', 'package bar\nclass Thing'),
        ('pubspec.yaml', 'dart', "import 'bar.dart';", 'class Bar {}'),
        ('build.zig', 'zig', 'const bar = @import("bar.zig");', 'pub const x = 1;'),
        ('project.godot', 'gd', 'const Bar = preload("bar.gd")', 'extends Node'),
    ]

    @pytest.mark.parametrize(
        'marker,ext,importer_body,module_body',
        _ROOT_MARKER_CASES,
        ids=[c[1] for c in _ROOT_MARKER_CASES],
    )
    def test_language_root_marker_stops_ancestor_climb(
        self, tmp_path, marker, ext, importer_body, module_body
    ):
        """A per-language root marker at the true project root must stop
        search_parents there, not climb past it to a decoy `.git` several
        levels up. Regression matrix for the BACK-515 hang across every
        depends://-supported language BACK-514 added."""
        from reveal.adapters.depends import _has_project_marker

        # Decoy marker several levels above the real project root.
        (tmp_path / '.git').mkdir()
        proj = tmp_path / 'vendor' / 'lib'
        proj.mkdir(parents=True)
        (proj / marker).write_text('# marker\n')
        _write(proj / f'src/foo.{ext}', importer_body + '\n')
        _write(proj / f'src/bar.{ext}', module_body + '\n')

        # The marker dir is recognized; the src dir below it is not.
        assert _has_project_marker(proj)
        assert not _has_project_marker(proj / 'src')

    def test_rockspec_resolves_lua_dependent(self, tmp_path):
        """End-to-end companion to the marker matrix: with a `*.rockspec`
        root, the Lua importer is actually resolved (not just that the scan
        is bounded)."""
        from reveal.adapters.depends import DependsAdapter

        (tmp_path / '.git').mkdir()
        (tmp_path / 'vendor' / 'lua-lib').mkdir(parents=True)
        (tmp_path / 'vendor' / 'lua-lib' / 'mylib-1.0.rockspec').write_text('package = "mylib"\n')
        _write(tmp_path / 'vendor/lua-lib/src/foo.lua', """\
            local bar = require("bar")
        """)
        _write(tmp_path / 'vendor/lua-lib/src/bar.lua', """\
            return {}
        """)
        a = DependsAdapter(str(tmp_path / 'vendor/lua-lib/src/bar.lua'))
        r = a.get_structure()
        assert r['count'] == 1
        assert 'foo.lua' in r['dependents'][0]['file']


class TestDependsAdapterScanRootResolution:
    """BACK-525 layers 1-3: tiered nearest-marker climb, hard ceiling, and
    the inferred-project fallback that replaces the flat marker-climb."""

    def test_package_marker_beats_nearer_vcs_root(self, tmp_path):
        """A package/build marker several levels up must be preferred over a
        *nearer* VCS root — package evidence is a project-unit signal, a bare
        `.git` is only a climb ceiling, and being nearer doesn't promote it
        (the core insight the flat nearest-match marker list couldn't
        express: it always picked whichever marker was nearest, regardless
        of kind)."""
        from reveal.adapters.depends import _resolve_project_root

        (tmp_path / 'pyproject.toml').write_text('[project]\nname = "monorepo"\n')
        nested = tmp_path / 'packages' / 'foo'
        (nested / '.git').mkdir(parents=True)
        target = nested / 'src' / 'target.py'
        _write(target, 'x = 1\n')

        assert _resolve_project_root(target) == tmp_path

    def test_no_marker_before_ceiling_returns_none(self, tmp_path):
        """No package or VCS marker anywhere between the target and the hard
        ceiling (here: tmp_path's own ancestry crosses the OS temp dir) —
        the climb must stop at the ceiling, not silently pick some unrelated
        ancestor up past it."""
        from reveal.adapters.depends import _resolve_project_root

        target = tmp_path / 'no_markers' / 'target.py'
        _write(target, 'x = 1\n')

        assert _resolve_project_root(target) is None

    def test_inferred_fallback_scopes_to_target_dir_and_warns(self, tmp_path):
        """When no marker is found before the ceiling, depends:// must scope
        to the target's own directory (never scan the ceiling) and disclose
        it via a warning + metadata flag, not silently degrade."""
        from reveal.adapters.depends import DependsAdapter

        pkg = tmp_path / 'no_markers' / 'pkg'
        _write(pkg / 'utils.py', 'def helper(): pass\n')
        _write(pkg / 'models.py', 'from .utils import helper\n')

        a = DependsAdapter(str(pkg / 'utils.py'))
        r = a.get_structure()

        assert r['count'] == 1
        assert r['metadata']['root_inferred'] is True
        assert 'warning' in r
        assert "couldn't determine this file's project boundary" in r['warning'].lower()

    def test_vcs_root_still_used_when_no_package_marker_exists(self, tmp_path):
        """No package marker anywhere, but a `.git` exists before the
        ceiling — tier 2 (VCS root) still applies; a real repo boundary is
        legitimate project evidence, not something layer 3 should override."""
        from reveal.adapters.depends import _resolve_project_root

        (tmp_path / '.git').mkdir()
        target = tmp_path / 'src' / 'target.py'
        _write(target, 'x = 1\n')

        assert _resolve_project_root(target) == tmp_path


class TestDependsAdapterLanguageScoping:
    """BACK-525 layer 4: a single-file target only parses files in its own
    extractor's extension family — a Python target must not pay to
    tree-sitter-parse sibling files in unrelated languages."""

    def test_other_language_files_excluded_from_scan_count(self, tmp_path):
        from reveal.adapters.depends import DependsAdapter

        (tmp_path / 'pyproject.toml').write_text('[project]\nname = "test"\n')
        _write(tmp_path / 'pkg/utils.py', 'def helper(): pass\n')
        _write(tmp_path / 'pkg/models.py', 'from .utils import helper\n')
        # Decoy: an unrelated Go file living right alongside the Python
        # package, *with an import statement* so it would register in
        # graph.files (get_file_count counts only files with imports) if
        # it were wrongly parsed. Pre-BACK-525, every supported language
        # under scan_root got tree-sitter-parsed looking for importers;
        # layer 4 should skip this entirely for a .py target.
        _write(tmp_path / 'pkg/other.go', 'package pkg\nimport "fmt"\n')

        a = DependsAdapter(str(tmp_path / 'pkg' / 'utils.py'))
        r = a.get_structure()

        assert r['count'] == 1
        # Only models.py has an import statement (utils.py has none); the
        # Go decoy — despite having its own import — must never register.
        assert r['metadata']['total_files_scanned'] == 1

    def test_c_target_still_scans_its_own_header_family(self, tmp_path):
        """C's family is {.c, .h} — narrowing to the target's own extension
        alone (not its extractor's full family) would wrongly drop header
        dependents/dependencies."""
        from reveal.adapters.depends import DependsAdapter

        (tmp_path / '.git').mkdir()
        _write(tmp_path / 'src/foo.h', 'void foo(void);\n')
        _write(tmp_path / 'src/foo.c', '#include "foo.h"\nvoid foo(void) {}\n')

        a = DependsAdapter(str(tmp_path / 'src' / 'foo.h'))
        r = a.get_structure()

        assert r['count'] == 1
        assert 'foo.c' in r['dependents'][0]['file']

    def test_directory_target_stays_unscoped_across_languages(self, tmp_path):
        """A directory target isn't tied to one extractor family — it must
        still see dependents across every supported language, unchanged
        from pre-BACK-525 behavior."""
        from reveal.adapters.depends import DependsAdapter

        (tmp_path / 'pyproject.toml').write_text('[project]\nname = "test"\n')
        _write(tmp_path / 'pkg/utils.py', 'def helper(): pass\n')
        _write(tmp_path / 'pkg/models.py', 'from .utils import helper\n')
        _write(tmp_path / 'pkg/other.go', 'package pkg\nimport "fmt"\n')

        a = DependsAdapter(str(tmp_path / 'pkg'))
        r = a.get_structure()

        assert r['type'] == 'dependency_summary'
        # models.py (Python import) and other.go (Go import) both register —
        # a directory target spans every supported language, unscoped.
        assert r['metadata']['total_files_scanned'] == 2


class TestDependsAdapterScanCap:
    """BACK-524: _build_graph must bound the walk instead of unbounded-scanning
    a huge marker-legit ancestor repo — warn-and-continue with partial results,
    not a silent hang. Caps _SCAN_FILE_CAP down via monkeypatch so the test
    corpus itself stays small; real default is 5,000."""

    @pytest.fixture
    def wide_pkg(self, tmp_path):
        """5 sibling modules, each imported by the next — bigger than a
        monkeypatched cap of 3, so the walk must stop mid-tree."""
        (tmp_path / 'pyproject.toml').write_text('[project]\nname = "test"\n')
        for i in range(5):
            imp = f'from .mod{i - 1} import x\n' if i > 0 else ''
            _write(tmp_path / 'pkg' / f'mod{i}.py', f"{imp}x = {i}\n")
        return tmp_path

    def test_cap_sets_scan_capped_flag(self, wide_pkg, monkeypatch):
        from reveal.adapters.depends import DependsAdapter
        monkeypatch.setattr(DependsAdapter, '_SCAN_FILE_CAP', 3)
        a = DependsAdapter(str(wide_pkg / 'pkg' / 'mod0.py'))
        r = a.get_structure()
        assert r['metadata']['scan_capped'] is True

    def test_cap_emits_warning_in_result(self, wide_pkg, monkeypatch):
        from reveal.adapters.depends import DependsAdapter
        monkeypatch.setattr(DependsAdapter, '_SCAN_FILE_CAP', 3)
        a = DependsAdapter(str(wide_pkg / 'pkg' / 'mod0.py'))
        r = a.get_structure()
        assert 'warning' in r
        assert 'capped at 3 files' in r['warning']

    def test_cap_warning_in_known_limits(self, wide_pkg, monkeypatch):
        from reveal.adapters.depends import DependsAdapter
        monkeypatch.setattr(DependsAdapter, '_SCAN_FILE_CAP', 3)
        a = DependsAdapter(str(wide_pkg / 'pkg' / 'mod0.py'))
        r = a.get_structure()
        assert any('BACK-524' in limit for limit in r['_meta']['known_limits'])

    def test_no_cap_hit_below_threshold(self, wide_pkg):
        """Default cap (5,000) is nowhere near this fixture's 5 files — no
        warning, no flag, unaffected by the BACK-524 guard."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(wide_pkg / 'pkg' / 'mod0.py'))
        r = a.get_structure()
        assert r['metadata']['scan_capped'] is False
        assert 'warning' not in r

    def test_render_structure_shows_warning(self, wide_pkg, monkeypatch, capsys):
        from reveal.adapters.depends import DependsAdapter, DependsRenderer
        monkeypatch.setattr(DependsAdapter, '_SCAN_FILE_CAP', 3)
        a = DependsAdapter(str(wide_pkg / 'pkg'))
        r = a.get_structure()
        DependsRenderer.render_structure(r, format='text')
        captured = capsys.readouterr()
        assert 'Scan capped at 3 files' in captured.out


if __name__ == '__main__':
    unittest.main()
