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
import os
from pathlib import Path

import pytest

from reveal.analyzers.imports import service as import_service

from reveal.analyzers.imports import build_cache

from reveal.analyzers.imports import extraction as import_extraction

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
    real = import_extraction.extract_one_file

    def counting(fp_str, *args):
        calls.append(fp_str)
        return real(fp_str, *args)

    monkeypatch.setattr(import_extraction, 'extract_one_file', counting)
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
    real = import_extraction.extract_one_file

    def counting(fp_str, *args):
        calls.append(fp_str)
        return real(fp_str, *args)

    monkeypatch.setattr(import_extraction, 'extract_one_file', counting)
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
    """Every service build: the explicit root and optional request focus."""
    seen = []
    real = import_service.analyze

    def spy(scope, *args, **kwargs):
        built = real(scope, *args, **kwargs)
        seen.append((scope.root, scope.focus))
        return built

    monkeypatch.setattr(import_service, 'analyze', spy)
    return seen


def _all_path_scoped(seen, path):
    assert seen, 'the caller built no import graph'
    assert all(root == path.resolve() and focus is None for root, focus in seen), seen


@pytest.mark.parametrize('query', ['', 'top=0'])
def test_architecture_alias_passes_scope_path_once(fx, builds, query):
    from reveal.adapters.architecture import ArchitectureAdapter
    result = ArchitectureAdapter(str(fx / 'pkg'), query).get_structure()
    _all_path_scoped(builds, fx / 'pkg')
    assert len(builds) == 1
    assert result['type'] == 'overview' and result['map_status'] == 'complete'


def test_overview_imports_analysis_passes_scope_path(fx, builds):
    from reveal.adapters.overview import OverviewAdapter, _run_imports_analysis
    _run_imports_analysis(OverviewAdapter(str(fx / 'pkg')), fx / 'pkg', 5, scope_usable=True)
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
    from conftest import _run_reveal_direct
    monkeypatch.chdir(fx)
    out = _run_reveal_direct('imports://pkg/core.py?importers', '--format', 'json')
    data = json.loads(out.stdout)
    assert data['type'] == 'module_importers' and data['count'] == 5
    assert {Path(r['file']).parts[-1] for r in data['importers']} == {'a.py', 'b.py', 'd.py', 'run.py', 'test_core.py'}
    assert not any(Path(r['file']).is_absolute() for r in data['importers'])


def test_importers_text_lists_each_importer_with_stage_and_scope(fx, capsys):
    from reveal.adapters.imports import ImportsRenderer
    ImportsRenderer.render_structure(_structure(fx / 'pkg' / 'core.py', 'importers'))
    text = capsys.readouterr().out
    assert 'Importers of core.py: 5' in text
    assert 'b.py:2  pkg.core  [direct, local]' in text
    assert 'Resolved at the scan root ..' in text
    ImportsRenderer.render_structure(_structure(fx / 'pkg', 'importers'))
    text = capsys.readouterr().out
    assert 'Modules with importers: 6' in text and 'core.py  (5)' in text
    assert 'Import Analysis' not in text


# ── D6 exit codes (imports is a declared command) ─────────────────────────────────────────────

def test_imports_exits_2_for_usage_and_3_for_partial_analysis(fx, monkeypatch):
    from conftest import _run_reveal_direct
    monkeypatch.chdir(fx)
    assert _run_reveal_direct('imports://pkg?rank=fan-in').returncode == 0
    assert _run_reveal_direct('imports://missing_dir').returncode == 2  # was 1
    assert _run_reveal_direct('imports://pkg?rank=nope').returncode == 2  # was 1
    assert _run_reveal_direct('imports://pkg?rank=fan-in&max_files=2').returncode == 3  # capped walk; was 0
    (fx / 'pkg' / 'broken.py').write_text('def f(\n    x = ( ( (\n', encoding='utf-8')
    assert _run_reveal_direct('imports://pkg?rank=fan-in').returncode == 3  # parsed with errors; was 0


def test_reveal_imports_subcommand_answers_like_the_uri(fx, monkeypatch):
    from conftest import _run_reveal_direct
    monkeypatch.chdir(fx)
    typed = _run_reveal_direct('imports', 'pkg/core.py', '--importers', '--tests', 'exclude', '--format', 'json')
    uri = _run_reveal_direct('imports://pkg/core.py?importers&tests=exclude', '--format', 'json')
    assert typed.returncode == uri.returncode == 0
    strip = lambda out: {k: v for k, v in json.loads(out).items() if k not in ('meta', 'provenance')}
    assert strip(typed.stdout) == strip(uri.stdout)
    assert json.loads(typed.stdout)['count'] == 4


# ── what the host-request memo may keep ────────────────────────────────────────────────────────

@pytest.fixture
def extraction_calls(monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    calls = []
    real = import_extraction.extract_one_file

    def counting(fp_str, *args):
        calls.append(Path(fp_str).name)
        return real(fp_str, *args)

    monkeypatch.setattr(import_extraction, 'extract_one_file', counting)
    return calls


def test_the_memo_never_keeps_a_build_that_lost_a_file(fx, monkeypatch, extraction_calls):
    """chmod moves no stat the tree stamp reads: a build with an unreadable file is returned,
    never kept (BACK-2083), or the next request serves the loss after the file is readable."""
    from reveal import base as reveal_base
    denied = {(fx / 'pkg' / 'a.py').resolve()}
    real = reveal_base.FileAnalyzer._read_file

    def read(self):
        if Path(self.path).resolve() in denied:
            raise PermissionError(13, 'Permission denied', str(self.path))
        return real(self)

    monkeypatch.setattr(reveal_base.FileAnalyzer, '_read_file', read)  # noqa: V036 reviewed: serial
    with request_cache.host_request():
        lost = _structure(fx / 'pkg' / 'core.py', 'importers')
    assert lost['metadata']['files_failed_count'] == 1
    denied.clear()
    with request_cache.host_request():
        healthy = _structure(fx / 'pkg' / 'core.py', 'importers')
    assert healthy['metadata']['files_failed_count'] == 0
    assert 'a.py' in {row['file'] for row in healthy['importers']}


def test_a_gitignore_off_build_lives_for_its_request_only(fx, extraction_calls):
    """The tree stamp walks with the default gitignore switch, so it cannot see an edit to an
    ignored file: a build made with the switch off is dropped at the next request (BACK-2118)."""
    from reveal.utils.gitignore import gitignore_scope
    with request_cache.host_request(), gitignore_scope(False):
        _structure(fx / 'pkg', 'rank=fan-in')
        built = len(extraction_calls)
        _structure(fx / 'pkg', 'rank=fan-in')
    within = len(extraction_calls)
    assert built and within == built  # reused inside its own request
    with request_cache.host_request(), gitignore_scope(False):
        _structure(fx / 'pkg', 'rank=fan-in')
    assert len(extraction_calls) > within


def test_an_edit_evicts_the_old_build_from_the_memo(fx, extraction_calls):
    """The key already carries every file's stat, so a stale build is never served; the tree stamp
    (register_validated_cache) is what drops it, so a root holds one build per live variant."""
    root = str(fx.resolve())
    with request_cache.host_request():
        _structure(fx / 'pkg', 'rank=fan-in')
    assert len(build_cache._GRAPH_MEMO[root]) == 1
    (fx / 'pkg' / 'core.py').write_text('CONST = 3\n\n\ndef helper():\n    return 2\n', encoding='utf-8')
    os.utime(fx / 'pkg' / 'core.py', ns=(1, 1))
    with request_cache.host_request():
        _structure(fx / 'pkg', 'rank=fan-in')
    assert len(build_cache._GRAPH_MEMO[root]) == 1


def test_a_php_include_through_a_define_constant_is_tagged_constant(tmp_path):
    _write(tmp_path, {
        'composer.json': '{}\n',
        'config.php': "<?php\ndefine('BASE', __DIR__ . '/');\n",
        'lib/x.php': '<?php\nfunction x() {}\n',
        'main.php': "<?php\nrequire_once BASE . 'lib/x.php';\n",
        'other.php': "<?php\nrequire_once __DIR__ . '/lib/x.php';\n",
    })
    rows = {r['file']: r for r in _structure(tmp_path / 'lib' / 'x.php', 'importers')['importers']}
    assert rows['../main.php']['via'] == ['constant']
    assert rows['../other.php']['via'] == ['direct']


def _cycle_pairs(root: Path, count: int = 8) -> None:
    """More cycle groups than the summary lists (5), so --verbose changes the answer."""
    _write(root, {f'm{n}{side}.py': f'import m{n}{"b" if side == "a" else "a"}\n'
                  for n in range(count) for side in 'ab'})


def test_the_verbose_flag_expands_reveal_imports_as_the_uri_does(tmp_path):
    """`reveal imports PATH --verbose` is `imports://PATH?verbose`: it bound no parameter, so the
    answer stayed a summary while the flag ledger said it had no effect."""
    from conftest import _run_reveal_direct as run
    _cycle_pairs(tmp_path)
    plain = run('imports', tmp_path, '--circular')
    flag = run('imports', tmp_path, '--circular', '--verbose')
    uri = run(f'imports://{tmp_path.as_posix()}?circular&verbose')
    assert flag.stdout == uri.stdout != plain.stdout
    assert 'has no effect' not in flag.stderr
    assert 'has no effect' not in plain.stderr


def test_an_unset_verbose_is_not_supplied_to_reveal_imports(tmp_path):
    """A boolean carried by its global flag is supplied only when set (`?verbose` is presence)."""
    from conftest import _run_reveal_direct as run
    _cycle_pairs(tmp_path)
    assert run('imports', tmp_path, '--circular').stdout == run(f'imports://{tmp_path.as_posix()}?circular').stdout
