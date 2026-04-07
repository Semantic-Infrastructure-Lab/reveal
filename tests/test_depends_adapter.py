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
        assert r['contract_version'] == '1.0'

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


if __name__ == '__main__':
    unittest.main()
