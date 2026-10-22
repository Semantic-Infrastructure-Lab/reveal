"""imports:// on the one resolution owner (BACK-1054 item 2, slice S2 of folding depends://,
deps:// and calls?modules into imports://).

imports:// resolved at the requested path, so a package's absolute imports (``from pkg import
core`` under ``imports://proj/pkg``) never resolved: fan-in 0 for every file and "No circular
dependencies found!" while I002, which climbs to the project root, reported the cycle. It now
resolves at the project root depends:// climbs to (``&scope=root``, the default) through
depends://'s cascade, answers ``?importers`` (the depends:// file and directory answers),
counts ``&tests`` and ``&lazy`` at presentation, discloses its one file cap (``&max_files``), and
keeps a validated graph across host requests. The commands that read imports at the requested
path (architecture, overview, pack, the architecture diff) pass ``&scope=path`` and keep their
numbers.
"""
import json
from pathlib import Path

import pytest

from reveal.adapters import imports as imports_adapter
from reveal.adapters.imports import ImportsAdapter
from reveal.utils import request_cache

pytestmark = [pytest.mark.component]


def _write(root: Path, files: dict) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')


# The design report's fixture (lane C, fx/): a package with module-level, function-level and
# TYPE_CHECKING-only importers of core, importers outside the package (tests/, scripts/), a lazy
# cycle (cyc1 <-> cyc2) and a load-time cycle (cyc3 <-> cyc4).
FX = {
    'pyproject.toml': '[project]\nname = "fx"\nversion = "0"\n',
    'pkg/__init__.py': '',
    'pkg/core.py': 'CONST = 2\n\n\ndef helper():\n    return 1\n',
    'pkg/a.py': 'from pkg import core\n\n\ndef use():\n    return core.helper()\n',
    'pkg/b.py': 'def f():\n    from pkg.core import helper\n    return helper()\n',
    'pkg/c.py': ('from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from pkg.core import CONST\n\n\n'
                 'def g(x: "CONST"):\n    return x\n'),
    'pkg/d.py': 'import os\nfrom pkg.core import CONST\n\nX = CONST\n',
    'pkg/cyc1.py': 'import pkg.cyc2\n\n\ndef one():\n    return pkg.cyc2.two()\n',
    'pkg/cyc2.py': 'def two():\n    import pkg.cyc1\n    return pkg.cyc1\n',
    'pkg/cyc3.py': 'from pkg import cyc4\n\n\ndef three():\n    return cyc4.four()\n',
    'pkg/cyc4.py': 'from pkg import cyc3\n\n\ndef four():\n    return cyc3\n',
    'tests/test_core.py': 'from pkg.core import helper\n\n\ndef test_helper():\n    assert helper() == 1\n',
    'scripts/run.py': 'import pkg.core\n\npkg.core.helper()\n',
}


@pytest.fixture
def fx(tmp_path):
    _write(tmp_path, FX)
    return tmp_path


def _structure(path: Path, query: str = '') -> dict:
    return ImportsAdapter(str(path), query).get_structure()


def _fan_in(result: dict) -> dict:
    return {Path(e['file']).name: e['fan_in'] for e in result['entries']}


# ── red-first controls (design table, slice S2) ────────────────────────────────────────────────

def test_circular_under_a_package_finds_the_load_time_cycle(fx):
    result = _structure(fx / 'pkg', 'circular')
    assert result['count'] == 1  # was 0: absolute pkg.* imports did not resolve at root = pkg
    assert [sorted(Path(f).name for f in group) for group in result['cycles']] == [['cyc3.py', 'cyc4.py']]


def test_fan_in_under_a_package_counts_every_importer_under_the_root(fx):
    fan_in = _fan_in(_structure(fx / 'pkg', 'rank=fan-in'))
    assert fan_in['core.py'] == 5  # a, b (function-level), d, scripts/run.py, tests/test_core.py; was 0
    # Rows are the requested path's files only: the importers outside it are counted, not listed.
    assert set(fan_in) == {Path(f).name for f in FX if f.startswith('pkg/')}


def test_importers_of_a_file_lists_each_import_line_scope_and_stage(fx):
    result = _structure(fx / 'pkg' / 'core.py', 'importers')
    assert result['type'] == 'module_importers'  # was 'imports': ?importers was an unknown parameter
    rows = {row['file']: row for row in result['importers']}
    assert set(rows) == {'a.py', 'b.py', 'd.py', '../scripts/run.py', '../tests/test_core.py'}
    assert result['count'] == 5
    assert rows['b.py']['scope'] == ['local'] and rows['a.py']['scope'] == ['module']
    assert rows['d.py']['line'] == 2 and rows['d.py']['module'] == 'pkg.core'
    assert {row['via'][0] for row in rows.values()} == {'direct'}


@pytest.mark.disk_cache
def test_warm_per_file_importers_extracts_nothing(fx, tmp_path_factory, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path_factory.mktemp('cache')))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')
    calls = []
    real = imports_adapter._extract_one_file

    def counting(fp_str, *args):
        calls.append(fp_str)
        return real(fp_str, *args)

    monkeypatch.setattr(imports_adapter, '_extract_one_file', counting)
    cold = _structure(fx / 'pkg' / 'core.py', 'importers')
    assert calls, 'positive control: the cold request extracts'
    calls.clear()
    warm = _structure(fx / 'pkg' / 'core.py', 'importers')
    assert warm['type'] == 'module_importers'
    assert calls == []
    assert warm['importers'] == cold['importers']


def test_a_host_request_reuses_the_graph_with_the_disk_cache_off(fx, monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    calls = []
    real = imports_adapter._extract_one_file

    def counting(fp_str, *args):
        calls.append(fp_str)
        return real(fp_str, *args)

    monkeypatch.setattr(imports_adapter, '_extract_one_file', counting)
    # Outside a request nothing would revalidate an entry: every call builds (negative control).
    _structure(fx / 'pkg' / 'core.py', 'importers')
    outside = len(calls)
    _structure(fx / 'pkg' / 'core.py', 'importers')
    assert outside and len(calls) == 2 * outside
    calls.clear()
    with request_cache.host_request():
        first = _structure(fx / 'pkg' / 'core.py', 'importers')
    built = len(calls)
    with request_cache.host_request():
        # Another view of the same root, under other &tests/&lazy: one graph, no new variant.
        again = _structure(fx / 'pkg' / 'core.py', 'importers')
        _structure(fx / 'pkg', 'rank=fan-in&tests=exclude&lazy=exclude')
    assert built and len(calls) == built
    assert again['importers'] == first['importers']
    # An edit moves the tree stamp: the next request rebuilds and sees it.
    (fx / 'pkg' / 'e.py').write_text('from pkg.core import helper\n', encoding='utf-8')
    with request_cache.host_request():
        edited = _structure(fx / 'pkg' / 'core.py', 'importers')
    assert len(calls) > built
    assert 'e.py' in {row['file'] for row in edited['importers']}


# ── the directory answer is depends://'s, as sets ──────────────────────────────────────────────

def test_directory_importers_equal_the_depends_directory_summary_as_sets(fx):
    from reveal.adapters.depends import DependsAdapter
    mine = _structure(fx, 'importers')
    depends = DependsAdapter(str(fx)).get_structure()
    assert mine['type'] == 'importer_summary'
    assert {e['file']: set(e['importers']) for e in mine['entries']} == \
        {m['module']: set(m['dependents']) for m in depends['modules']}
    assert all(e['fan_in'] == len(e['importers']) for e in mine['entries'])


def test_importers_named_relative_to_the_requested_directory(fx):
    named = _structure(fx / 'pkg', 'importers=core.py')
    direct = _structure(fx / 'pkg' / 'core.py', 'importers')
    assert named['type'] == 'module_importers'
    assert {r['file'] for r in named['importers']} == {'a.py', 'b.py', 'd.py', '../scripts/run.py',
                                                        '../tests/test_core.py'}
    assert named['count'] == direct['count'] == 5


# ── tests and lazy are presentation ────────────────────────────────────────────────────────────

def test_tests_exclude_drops_importers_under_a_test_path(fx):
    result = _structure(fx / 'pkg', 'rank=fan-in&tests=exclude')
    assert _fan_in(result)['core.py'] == 4
    assert result['edge_rule']['tests'] == 'importers_not_counted'
    assert result['edge_rule']['tests_param'] == 'exclude'
    included = _structure(fx / 'pkg', 'rank=fan-in')
    assert included['edge_rule']['tests'] == 'included'


def test_lazy_exclude_drops_the_function_level_importer(fx):
    rows = _structure(fx / 'pkg' / 'core.py', 'importers&lazy=exclude')['importers']
    assert {r['file'] for r in rows} == {'a.py', 'd.py', '../scripts/run.py', '../tests/test_core.py'}


def test_every_answer_states_root_source_scope_tests_and_lazy(fx):
    for query in ('rank=fan-in', 'circular', 'importers', 'entrypoints', 'components', ''):
        rule = _structure(fx / 'pkg', query)['edge_rule']
        assert (rule['root'], rule['root_source'], rule['scope'], rule['scope_param']) == \
            ('..', 'package_marker', 'scan_root', 'root'), query
        assert rule['tests_param'] == 'include' and rule['lazy'] in ('include', 'exclude'), query
        assert 'Resolved at the scan root ..' in rule['text'], query
        assert rule['ungated_languages'] == [], query


# ── scope=path is the old answer ───────────────────────────────────────────────────────────────

def test_scope_path_resolves_at_the_requested_path(fx):
    result = _structure(fx / 'pkg', 'rank=fan-in&scope=path')
    assert _fan_in(result)['core.py'] == 0  # absolute pkg.* imports do not resolve at root = pkg
    assert result['edge_rule']['scope'] == 'scanned_path'
    assert (result['edge_rule']['root'], result['edge_rule']['root_source']) == ('.', 'path')
    assert _structure(fx / 'pkg', 'circular&scope=path')['count'] == 0


def test_root_param_pins_the_root_and_a_refused_one_says_why(fx, tmp_path_factory):
    pinned = _structure(fx / 'pkg', f'rank=fan-in&root={fx / "pkg"}')
    assert pinned['edge_rule']['root_source'] == 'root_param'
    assert _fan_in(pinned)['core.py'] == 0
    elsewhere = tmp_path_factory.mktemp('elsewhere')
    refused = _structure(fx / 'pkg', f'rank=fan-in&root={elsewhere}')
    assert _fan_in(refused)['core.py'] == 5
    assert any(w.get('type') == 'root_rejected' and 'does not contain the target' in w['message']
               for w in refused['meta']['warnings'])
    ignored = _structure(fx / 'pkg', f'rank=fan-in&scope=path&root={fx}')
    assert any(w.get('type') == 'root_rejected' and 'scope=path' in w['message']
               for w in ignored['meta']['warnings'])


def test_max_files_is_one_disclosed_budget(fx):
    capped = _structure(fx / 'pkg', 'rank=fan-in&max_files=3')
    budget = capped['metadata']['scan_budget']
    assert budget['limit'] == 3 and budget['capped'] is True
    assert any(w.get('type') == 'scan_capped' for w in capped['meta']['warnings'])
    whole = _structure(fx / 'pkg', 'rank=fan-in')['metadata']['scan_budget']
    assert whole['limit'] == 20000 and whole['capped'] is False


@pytest.mark.parametrize('query', ['scope=both', 'tests=maybe', 'max_files=0', 'max_files=x', 'scope'])
def test_malformed_request_parameters_are_rejected(fx, query):
    with pytest.raises(ValueError):
        ImportsAdapter(str(fx / 'pkg'), query)


# ── the cascade's stages, through imports:// ───────────────────────────────────────────────────

def test_swift_module_edges_count_as_importers_but_never_close_a_cycle(tmp_path):
    _write(tmp_path, {
        'Package.swift': '// swift-tools-version:5.5\nimport PackageDescription\n',
        'Sources/Alpha/A.swift': 'import Beta\n\nstruct A {}\n',
        'Sources/Beta/B.swift': 'import Alpha\n\nstruct B {}\n',
    })
    (tmp_path / '.git').mkdir()
    fan_in = _structure(tmp_path, 'rank=fan-in')
    assert _fan_in(fan_in) == {'A.swift': 1, 'B.swift': 1, 'Package.swift': 0}
    assert fan_in['edge_rule']['via'] == {'module': 2}
    assert fan_in['edge_rule']['ungated_languages'] == ['swift']
    assert 'Not gated' in fan_in['edge_rule']['text']
    circular = _structure(tmp_path, 'circular')
    assert circular['count'] == 0
    assert 'module and convention edges never close a cycle' in circular['edge_rule']['text']


def test_gated_languages_are_the_recall_gate_populations():
    import yaml
    from reveal.analyzers.imports.resolution import IMPORT_RECALL_GATED
    manifest = Path(__file__).parent / 'corpus' / 'manifest.yaml'
    entries = yaml.safe_load(manifest.read_text(encoding='utf-8'))['corpora']
    assert IMPORT_RECALL_GATED == {e['language'] for e in entries if 'recall' in e}


# ── the callers that read imports at the requested path keep their numbers ────────────────────

@pytest.fixture
def builds(monkeypatch):
    """Every ImportsAdapter graph build: (requested path, scan root, root source)."""
    seen = []
    real = ImportsAdapter._build_graph

    def spy(self, target_path, *args, **kwargs):
        real(self, target_path, *args, **kwargs)
        seen.append((Path(target_path).resolve(), self._scan.root, self._scan.source))

    monkeypatch.setattr(ImportsAdapter, '_build_graph', spy)
    return seen


def _all_path_scoped(seen, path):
    assert seen, 'the caller built no import graph'
    assert all(root == path.resolve() and source == 'path' for _requested, root, source in seen), seen


def test_architecture_imports_analysis_passes_scope_path(fx, builds):
    from reveal.adapters.architecture import ArchitectureAdapter, _run_imports_analysis
    data = _run_imports_analysis(ArchitectureAdapter(str(fx / 'pkg')), fx / 'pkg')
    _all_path_scoped(builds, fx / 'pkg')
    assert data


def test_architecture_combined_analysis_passes_scope_path(fx, builds):
    from reveal.adapters.architecture import ArchitectureAdapter, _run_combined_analysis
    _run_combined_analysis(ArchitectureAdapter(str(fx / 'pkg')), fx / 'pkg', 10)
    _all_path_scoped(builds, fx / 'pkg')


def test_overview_imports_analysis_passes_scope_path(fx, builds):
    from reveal.adapters.overview import OverviewAdapter, _run_imports_analysis
    _run_imports_analysis(OverviewAdapter(str(fx / 'pkg')), fx / 'pkg')
    _all_path_scoped(builds, fx / 'pkg')


def test_pack_import_graph_passes_scope_path(fx, builds):
    from reveal.adapters.pack import _build_pack_import_graph
    graph, _scanned = _build_pack_import_graph(fx / 'pkg')
    _all_path_scoped(builds, fx / 'pkg')
    assert graph is not None
    assert not any(p.name == 'core.py' for p in graph.reverse_deps)  # the path-scoped answer


def test_architecture_diff_snapshot_passes_scope_path(fx, builds):
    from reveal.diff.architecture_diff import _snapshot
    _snapshot(fx / 'pkg', 10)
    _all_path_scoped(builds, fx / 'pkg')


# ── the URI path ───────────────────────────────────────────────────────────────────────────────

def test_importers_through_the_cli_json(fx, monkeypatch):
    from tests.conftest import _run_reveal_direct
    monkeypatch.chdir(fx)
    out = _run_reveal_direct('imports://pkg/core.py?importers', '--format', 'json')
    data = json.loads(out.stdout)
    assert data['type'] == 'module_importers' and data['count'] == 5
    assert {Path(r['file']).parts[-1] for r in data['importers']} == {'a.py', 'b.py', 'd.py', 'run.py', 'test_core.py'}
    assert not any(Path(r['file']).is_absolute() for r in data['importers'])
