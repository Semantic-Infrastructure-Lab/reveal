"""scripts/graph_invariants.py (BACK-1096): oracle-free graph invariants, checked on a small committed
fixture through the public request path, each with a red control.

Every invariant compares two views of one graph. Each one is shown green on the real answers for
tests/fixtures/graph_invariants_back1096/proj (a Python package with a multi-target import, a lazy
import and a TYPE_CHECKING import), then red on a deliberately broken graph: an answer with one edge
dropped or one count doubled, and for the import and call engines an engine patched to lose one
reverse edge, which the public views must expose.
"""
import copy
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

from conftest import _run_reveal_in

SCRIPTS = Path(__file__).resolve().parent.parent / 'scripts'
FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'graph_invariants_back1096'


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load('imports_fold_snapshot')  # the runner imports it by name, as when run from scripts/
_load('recall_oracles')  # the package_wildcards invariant blanks literals with its jvm_strip_noise
inv = _load('graph_invariants')


@pytest.fixture
def root(tmp_path):
    shutil.copytree(FIXTURE, tmp_path / 'corpora')
    return tmp_path / 'corpora'


def _answer(root, uri, expect=(0,)):
    result = _run_reveal_in(root, uri, '--format', 'json')
    assert result.returncode in expect, (uri, result.stdout, result.stderr)
    return json.loads(result.stdout)


def _imports(root):
    return {view: _answer(root, f'imports://proj?{query}root=proj')
            for view, query in (('importers', 'importers&'), ('fan_in', 'rank=fan-in&'), ('default', ''))}


def _rank(root):
    return _answer(root, 'calls://proj?rank=callers&top=0&builtins=true&test-framework=true')


def _callees(root, rank, count=50):
    return {caller: _answer(root, f'calls://proj?callees={caller[0]}:{caller[1]}&builtins=true')
            for caller in inv.sample_callers(rank, count)}


def _entry(answer, module):
    return next(e for e in answer['entries'] if e['file'] == module)


# ── fan_in_total ──────────────────────────────────────────────────────────────

def test_fan_in_total_holds_on_the_fixture(root):
    views = _imports(root)
    row = inv.check_fan_in_total(views['fan_in'], views['importers'])
    assert row['status'] == 'green', row
    # Positive control: the fixture has six edges, and every sum names them.
    assert set(row['sums'].values()) == {6}


def test_fan_in_total_red_when_an_importer_row_is_dropped(root):
    views = _imports(root)
    _entry(views['importers'], 'pkg/a.py')['importers'].pop()
    row = inv.check_fan_in_total(views['fan_in'], views['importers'])
    assert row['status'] == 'red'
    assert {'sums_differ'} <= {key for example in row['examples'] for key in example}


def test_fan_in_total_red_when_one_fan_in_is_double_counted(root):
    views = _imports(root)
    _entry(views['fan_in'], 'pkg/b.py')['fan_in'] *= 2
    row = inv.check_fan_in_total(views['fan_in'], views['importers'])
    assert row['status'] == 'red'
    assert any(example.get('module') == 'pkg/b.py' for example in row['examples'])


# ── importers_resolved ────────────────────────────────────────────────────────

def test_importers_resolved_holds_and_counts_edges_beyond_the_first_target(root):
    views = _imports(root)
    row = inv.check_importers_resolved(views['importers'], views['default'], views['fan_in'])
    assert row['status'] == 'green', row
    assert row['population'] == 6
    # `from pkg import a, b` resolves to pkg/__init__.py first: a.py and b.py are edges the
    # default view's single `resolved` does not show; so is the lazy `from pkg import c`.
    assert row['resolved_edges'] == 3 and row['edges_beyond_first_target'] == 3


def test_importers_resolved_red_when_a_resolved_import_is_not_an_importer(root):
    views = _imports(root)
    _entry(views['importers'], 'pkg/a.py')['importers'].remove('pkg/b.py')
    row = inv.check_importers_resolved(views['importers'], views['default'], views['fan_in'])
    assert row['status'] == 'red'
    assert {'resolved_not_an_importer': ['pkg/b.py', 'pkg/a.py']} in row['examples']


def test_importers_resolved_red_when_an_importer_list_overstates_out_degree(root):
    views = _imports(root)
    _entry(views['importers'], 'pkg/b.py')['importers'].append('pkg/a.py')
    row = inv.check_importers_resolved(views['importers'], views['default'], views['fan_in'])
    assert row['status'] == 'red'
    assert {'file': 'pkg/a.py', 'importer_list_out_degree': 1, 'rank_fan_out': 0} in row['examples']


@pytest.fixture(params=['css', 'json'])
def outside_project(tmp_path, request):
    """One retained outside fact beside one genuine counted edge (BACK-2340)."""
    proj = tmp_path / 'proj'
    (proj / 'src').mkdir(parents=True)
    (proj / 'package.json').write_text('{"name": "p"}\n', encoding='utf-8')
    if request.param == 'css':
        (proj / 'assets').mkdir()
        (proj / 'assets' / 'x.css').write_text('a {}\n', encoding='utf-8')
        outside = "import '../assets/x.css';\n"
    else:
        outside = "import pkg from '../package.json';\n"
    (proj / 'src' / 'a.ts').write_text(outside + "import { b } from './b';\n", encoding='utf-8')
    (proj / 'src' / 'b.ts').write_text('export const b = 1;\n', encoding='utf-8')
    return proj


@pytest.mark.parametrize('scan', ['proj/src', 'proj'])
def test_pinned_runner_distinguishes_all_facts_from_counted_edges(outside_project, scan):
    root = outside_project.parent
    rows = inv.run_imports(InProcessRequests({}, root, 60), scan, root / scan,
                           ('importers_resolved',), 3)
    row, = rows
    assert row['status'] == 'green', row
    assert row['resolved_statements'] == row['resolved_edges'] == 2
    outside = int(scan == 'proj/src')
    assert row['counted_resolved_edges'] == row['population'] == 2 - outside
    assert row['outside_root_resolved_edges'] == outside


def _outside_views(proj, form='uri', scope='root'):
    path = 'proj/src'
    views = {}
    for view, query, flags in [('default', '', []), ('importers', 'importers&', ['--importers']),
                               ('fan_in', 'rank=fan-in&', ['--rank', 'fan-in'])]:
        control = f'root={path}' if scope == 'root' else 'scope=path'
        argv = ([f'imports://{path}?{query}{control}'] if form == 'uri' else
                ['imports', path, *flags, f'--{scope}', path if scope == 'root' else 'path'])
        result = _run_reveal_in(proj.parent, *argv, '--format', 'json')
        assert result.returncode == 0, (argv, result.stderr)
        views[view] = json.loads(result.stdout)
    return views


@pytest.mark.parametrize('form', ['uri', 'command'])
@pytest.mark.parametrize('scope', ['root', 'scope'])
def test_scoped_public_answers_keep_outside_facts_and_detect_inside_loss(outside_project, form, scope):
    views = _outside_views(outside_project, form, scope)
    facts, statements = inv.resolved_edges(views['default'])
    assert statements == len(facts) == 2
    assert ('a.ts', 'b.ts') in facts
    assert any(target.startswith('../') for _, target in facts)
    row = inv.check_importers_resolved(views['importers'], views['default'], views['fan_in'],
                                      scan_dir=outside_project / 'src')
    assert row['status'] == 'green', row
    _entry(views['importers'], 'b.ts')['importers'].remove('a.ts')
    row = inv.check_importers_resolved(views['importers'], views['default'], views['fan_in'],
                                      scan_dir=outside_project / 'src')
    assert row['status'] == 'red'
    assert {'resolved_not_an_importer': ['a.ts', 'b.ts']} in row['examples']
    assert any('importer_list_out_degree' in e for e in row['examples'])


@pytest.mark.parametrize('field,value', [('outside_root_edges', None), ('outside_root_edges', 0),
                                        ('outside_root_edges', -1), ('outside_root_edges', True),
                                        ('outside_root_edges', 2), ('root', '..'),
                                        ('root_source', 'inferred'), ('tests_param', 'exclude'),
                                        ('lazy', 'exclude')])
def test_scoped_checker_rejects_missing_or_wrong_disclosure(outside_project, field, value):
    views = _outside_views(outside_project)
    if value is None:
        views['importers']['edge_rule'].pop(field)
    else:
        views['importers']['edge_rule'][field] = value
    row = inv.check_importers_resolved(views['importers'], views['default'], views['fan_in'],
                                      scan_dir=outside_project / 'src')
    assert row['status'] == 'red', row
    assert any('counted_scope' in e or 'outside_root_disclosure' in e for e in row['examples'])


def test_scoped_checker_keeps_multi_target_disclosure_as_a_lower_bound(outside_project):
    views = _outside_views(outside_project)
    for answer in views.values():
        answer['edge_rule']['outside_root_edges'] = 2
    row = inv.check_importers_resolved(views['importers'], views['default'], views['fan_in'],
                                      scan_dir=outside_project / 'src')
    assert row['status'] == 'green', row
    assert row['outside_root_resolved_edges'] == 1
    # Even mutually consistent counted answers must not gain an outside edge.
    target = next(t for _, t in inv.resolved_edges(views['default'])[0] if t.startswith('../'))
    views['importers']['entries'].append({'file': target, 'importers': ['a.ts'], 'fan_in': 1})
    _entry(views['fan_in'], 'a.ts')['fan_out'] = 2
    row = inv.check_importers_resolved(views['importers'], views['default'], views['fan_in'],
                                      scan_dir=outside_project / 'src')
    assert row['status'] == 'red'
    assert {'outside_root_importer_edge': ['a.ts', target]} in row['examples']


def test_scoped_checker_normalizes_lexically_without_following_target_symlinks(tmp_path):
    scan = tmp_path / 'src'
    scan.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    try:
        (scan / 'link').symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('directory symlinks are unavailable')
    rule = {'root': '.', 'root_source': 'root_param', 'scope_param': 'root', 'outside_root_edges': 0,
            'tests_param': 'include', 'lazy': 'include'}
    # The product containment rule is lexical on canonical graph paths, not a second
    # filesystem resolution of displayed target names. Both facts must remain required.
    default = {'files': {'a.ts': [{'resolved': 'link/b.ts'}, {'resolved': '../src/c.ts'}]}, 'edge_rule': rule}
    reverse = {'entries': [], 'edge_rule': rule}
    rank = {'entries': [{'file': 'a.ts', 'fan_out': 2}], 'edge_rule': rule}
    row = inv.check_importers_resolved(reverse, default, rank, scan_dir=scan)
    assert row['counted_resolved_edges'] == 2
    assert row['outside_root_resolved_edges'] == 0
    assert {'resolved_not_an_importer': ['a.ts', 'link/b.ts']} in row['examples']
    assert {'resolved_not_an_importer': ['a.ts', '../src/c.ts']} in row['examples']


def test_type_checking_import_is_no_edge_in_either_view(root):
    """Negative control: the TYPE_CHECKING `from pkg import c` (b.py line 7) shows unresolved and
    adds no edge, so the two views agree without it."""
    views = _imports(root)
    line7 = [s for s in views['default']['files']['pkg/b.py'] if s['line'] == 7]
    assert line7 and line7[0]['resolved'] is None


# ── importer_citations ────────────────────────────────────────────────────────

def _per_target(root, views):
    targets = inv.citation_targets(views['importers'], views['default'], 3)
    return {t: _answer(root, f'imports://proj?importers={t}&root=proj') for t in targets}


def test_importer_citations_hold_on_the_fixture(root):
    views = _imports(root)
    per_target = _per_target(root, views)
    # The targets with edges the default view does not show come first.
    assert sorted(per_target) == ['pkg/a.py', 'pkg/b.py', 'pkg/c.py']
    row = inv.check_importer_citations(views['importers'], views['default'], per_target, root / 'proj')
    assert row['status'] == 'green', row
    assert row['population'] == 4


def test_importer_citations_red_when_a_row_cites_a_line_with_no_import(root):
    views = _imports(root)
    per_target = _per_target(root, views)
    per_target['pkg/a.py']['importers'][0]['line'] = 11
    row = inv.check_importer_citations(views['importers'], views['default'], per_target, root / 'proj')
    assert row['status'] == 'red'
    assert row['examples'][0]['uncited_row']['line'] == 11


def test_importer_citations_red_when_the_per_file_answer_loses_an_importer(root):
    views = _imports(root)
    per_target = _per_target(root, views)
    per_target['pkg/a.py']['importers'].pop()
    row = inv.check_importer_citations(views['importers'], views['default'], per_target, root / 'proj')
    assert row['status'] == 'red'
    assert {'target': 'pkg/a.py', 'per_file': 1, 'directory_view': 2} in row['examples']


def test_a_convention_row_is_cited_by_the_line_that_names_the_constant(tmp_path):
    """A convention edge (Ruby Zeitwerk) comes from a constant reference, not an import statement:
    the cited line must name the constant; a line that does not is a violation."""
    (tmp_path / 'app.rb').write_text('class App\n  Widget.new\nend\n', encoding='utf-8')
    importers = {'entries': [{'file': 'widget.rb', 'fan_in': 1, 'importers': ['app.rb']}]}
    default_view = {'files': {}}
    good = {'widget.rb': {'importers': [{'file': 'app.rb', 'line': 2, 'module': 'Widget', 'via': ['convention']}]}}
    row = inv.check_importer_citations(importers, default_view, good, tmp_path)
    assert row['status'] == 'green' and row['convention_rows'] == 1
    bad = copy.deepcopy(good)
    bad['widget.rb']['importers'][0]['line'] = 1
    assert inv.check_importer_citations(importers, default_view, bad, tmp_path)['status'] == 'red'


class InProcessRequests(inv.Requests):
    """The runner's request layer answered in-process (no `python -m reveal` spawn per request)."""

    def get(self, argv):
        result = _run_reveal_in(self.cwd, *argv)
        row = {'argv': argv, 'status': 'ok', 'exit_code': result.returncode, 'stderr': result.stderr}
        try:
            row['json'] = json.loads(result.stdout)
        except ValueError:
            row['status'] = 'no_json'
        self.log.append({'argv': argv, 'exit_code': result.returncode, 'partial': None})
        return row


def test_a_package_directory_module_is_cited_through_one_of_its_files(tmp_path):
    """Go answers per package: the directory view names the package directory (`lib`), and
    ?importers=lib on a directory is the summary of everything under it, not that module's
    importers. The runner asks for one file of the package, which the graph maps to the package."""
    proj = tmp_path / 'gomod'
    (proj / 'lib').mkdir(parents=True)
    (proj / 'go.mod').write_text('module example.com/m\n\ngo 1.21\n', encoding='utf-8')
    (proj / 'lib' / 'lib.go').write_text('package lib\n\nfunc Hello() string { return "hi" }\n', encoding='utf-8')
    (proj / 'main.go').write_text('package main\n\nimport "example.com/m/lib"\n\nfunc main() { lib.Hello() }\n',
                                  encoding='utf-8')
    rows = inv.run_imports(InProcessRequests({}, tmp_path, 60), 'gomod', proj, ('importer_citations',), 3)
    assert [(r['invariant'], r['status'], r['population']) for r in rows] == [('importer_citations', 'green', 1)], rows


def test_a_package_is_cited_through_a_file_that_does_not_import_it(tmp_path):
    """A Go external test file (`package lib_test`) imports its own package; named as the package's
    proxy, ?importers= leaves it out (a file is not its own importer), so it cannot stand for the
    package: the runner picks a file of the package that is not among its importers."""
    proj = tmp_path / 'gomod'
    (proj / 'lib').mkdir(parents=True)
    (proj / 'go.mod').write_text('module example.com/m\n\ngo 1.21\n', encoding='utf-8')
    (proj / 'lib' / 'lib.go').write_text('package lib\n\nfunc Hello() string { return "hi" }\n', encoding='utf-8')
    (proj / 'lib' / 'a_test.go').write_text('package lib_test\n\nimport "example.com/m/lib"\n\n'
                                            'func use() { lib.Hello() }\n', encoding='utf-8')
    (proj / 'main.go').write_text('package main\n\nimport "example.com/m/lib"\n\nfunc main() { lib.Hello() }\n',
                                  encoding='utf-8')
    rows = inv.run_imports(InProcessRequests({}, tmp_path, 60), 'gomod', proj, ('importer_citations',), 3)
    assert [(r['invariant'], r['status'], r['population']) for r in rows] == [('importer_citations', 'green', 2)], rows


def test_a_file_name_with_a_plus_is_named_as_spelled(tmp_path):
    """imports ?importers= reads its value raw (uri_codec 'raw'), so `Data+PKCE.swift` must go in as
    written: percent-encoded (`Data%2BPKCE.swift`) it matches no file and exits 2."""
    proj = tmp_path / 'jsproj'
    proj.mkdir()
    (proj / 'package.json').write_text('{"name": "p"}\n', encoding='utf-8')
    (proj / 'a+b.js').write_text('export const x = 1;\n', encoding='utf-8')
    (proj / 'main.js').write_text("import { x } from './a+b.js';\nconsole.log(x);\n", encoding='utf-8')
    rows = inv.run_imports(InProcessRequests({}, tmp_path, 60), 'jsproj', proj, ('importer_citations',), 3)
    assert [(r['invariant'], r['status'], r['population']) for r in rows] == [('importer_citations', 'green', 1)], rows


# ── engine-level red control (imports) ────────────────────────────────────────

def test_an_engine_that_loses_one_reverse_edge_turns_both_import_invariants_red(root, monkeypatch):
    """The graph keeps forward and reverse adjacency separately; an engine that adds b.py -> a.py
    to the forward side only must be caught through the public views alone."""
    from reveal.analyzers.imports.types import ImportGraph
    original = ImportGraph.add_dependency

    def forward_only(self, from_file, to_file, scope=None, via=None):
        original(self, from_file, to_file, scope, via)
        if from_file.name == 'b.py' and to_file.name == 'a.py':
            self.reverse_deps[to_file].discard(from_file)

    monkeypatch.setattr(ImportGraph, 'add_dependency', forward_only)
    views = _imports(root)
    assert inv.check_fan_in_total(views['fan_in'], views['importers'])['status'] == 'red'
    row = inv.check_importers_resolved(views['importers'], views['default'], views['fan_in'])
    assert row['status'] == 'red'
    assert {'resolved_not_an_importer': ['pkg/b.py', 'pkg/a.py']} in row['examples']


# ── package_wildcards (BACK-2507) ─────────────────────────────────────────────

JVM_TREE = {
    'src/a/Base.scala': 'package cats\npackage effect\n\nclass Base\n',
    'src/a/Obj.scala': 'package catseffect\n\npackage examples {\n  object Shutdown\n}\n',
    # statements inside a comment or a string are no statement; the real wildcard sits on line 6
    'src/b/Use.scala': ('package app\n\n// import cats.effect._\nobject Use {\n  val s = "import cats.effect._"\n'
                        '  import cats.effect._\n  import catseffect.examples._\n  import scala.util._\n}\n'),
    'src/b/Use2.scala': 'package app\n\nimport cats.effect._\nobject Use2\n',
    'src/k/Decl.kt': 'package kt.decl\n\nclass Decl\n',
    'src/k/Use.kt': 'package kt.use\n\nimport kt.decl.*\nimport kotlin.collections.*\n\nclass Use\n',
    'src/j/Decl.java': 'package jv.decl;\n\npublic class Decl {}\n',
    'src/j/Use.java': 'package jv.use;\n\nimport jv.decl.*;\nimport static jv.decl.Decl.*;\nimport java.util.*;\n\npublic class Use {}\n',
}


@pytest.fixture
def jvm_default(tmp_path):
    scan = tmp_path / 'jvm'
    for name, text in JVM_TREE.items():
        (scan / name).parent.mkdir(parents=True, exist_ok=True)
        (scan / name).write_text(text, encoding='utf-8')
    return scan, _answer(tmp_path, 'imports://jvm?root=jvm', expect=(0, 3))


def test_declared_packages_nest_chained_clauses_and_package_objects():
    assert inv.declared_packages('package a.b\npackage c\nclass X\n') == {'a.b', 'a.b.c'}
    assert inv.declared_packages('package a\npackage object b\n') == {'a', 'a.b'}
    assert inv.declared_packages('class NoPackage\n') == set()


def test_package_wildcards_hold_on_the_real_answer_and_ignore_literals_and_comments(jvm_default):
    scan, view = jvm_default
    packages = inv.scan_declared_packages(scan)
    assert {'cats.effect', 'catseffect.examples', 'kt.decl', 'jv.decl'} <= packages
    row = inv.check_package_wildcards(view, packages)
    # Use.scala:6 and Use2.scala:3 (cats.effect._), Use.scala:7 (catseffect.examples._), Use.kt, Use.java;
    # scala.util._, kotlin.collections.* and java.util.* name no scanned package, and the Java static
    # wildcard `jv.decl.Decl.*` names a class (still unresolved in Reveal), so the disclosure leaves it out
    assert (row['status'], row['population'], row['packages'], row['importer_files']) == ('green', 5, 4, 4), row
    assert view['edge_rule']['package_wildcards']['packages'] == {
        'cats.effect': 2, 'catseffect.examples': 1, 'kt.decl': 1, 'jv.decl': 1}


@pytest.mark.parametrize('damage', ['dropped', 'overstated', 'wrong_package'])
def test_package_wildcards_red_when_the_disclosure_disagrees_with_the_listing(jvm_default, damage):
    scan, view = jvm_default
    view = copy.deepcopy(view)
    rule = view['edge_rule']['package_wildcards']
    if damage == 'dropped':
        del view['edge_rule']['package_wildcards']  # what an engine without BACK-2506 answers
    elif damage == 'overstated':
        rule['statements'] += 1
    else:
        rule['packages']['cats.effect'] -= 1
        rule['packages']['other.pkg'] = 1
    row = inv.check_package_wildcards(view, inv.scan_declared_packages(scan))
    assert row['status'] == 'red', row


@pytest.fixture
def cargo_workspace(tmp_path):
    """BACK-2549's workspace: crates named bare as path dependencies, inherited, renamed and own-library."""
    from test_rust_package_model_back2549 import write_workspace
    return write_workspace(tmp_path / 'ws')


def test_local_units_resolved_holds_on_the_real_answer(cargo_workspace):
    view = _answer(cargo_workspace.parent, 'imports://ws?root=ws')
    row = inv.check_local_units_resolved(view, inv.scan_crate_scopes(cargo_workspace), cargo_workspace)
    # matcher x3 (workspace-inherited twice, own library once), search (renamed), inner (inherited)
    assert (row['status'], row['population'], row['packages']) == ('green', 5, 4)


def test_local_units_resolved_red_when_a_local_crate_name_has_no_target(cargo_workspace):
    view = _answer(cargo_workspace.parent, 'imports://ws?root=ws')
    damaged = copy.deepcopy(view)
    for stmt in damaged['files']['crates/search/src/lib.rs']:
        stmt['resolved'] = None
    row = inv.check_local_units_resolved(damaged, inv.scan_crate_scopes(cargo_workspace), cargo_workspace)
    assert (row['status'], row['violations']) == ('red', 2)
    assert {e['module'] for e in row['examples']} == {'matcher::Matcher', 'inner::Deep'}


def test_local_units_resolved_reads_each_packages_own_dependencies(cargo_workspace):
    """A crate the package does not depend on is a local binding of that name, not the crate: out of scope."""
    scopes = inv.scan_crate_scopes(cargo_workspace)
    root = cargo_workspace.resolve()
    assert scopes[root / 'crates/matcher'] == {'matcher'}
    assert scopes[root] == {'app', 'matcher', 'search'}   # keys as code spells them (renamed); serde is not in-tree
    assert scopes[root / 'crates/search'] == {'grep_search', 'matcher', 'inner'}


@pytest.fixture
def go_workspace(tmp_path):
    """BACK-2557's tree: staged modules linked by go.work and local replaces, a nested and a decoy module."""
    from test_go_package_model_back2557 import write_workspace
    return write_workspace(tmp_path / 'ws')


def test_local_units_resolved_holds_on_the_real_go_answer(go_workspace):
    view = _answer(go_workspace.parent, 'imports://ws?root=ws')
    row = inv.check_local_units_resolved(view, inv.scan_crate_scopes(go_workspace), go_workspace,
                                         inv.scan_go_module_scopes(go_workspace))
    # main.go x4 (go.work api and client, own pkg/util, replaced vendored/lib), rest.go, auth.go, sample.go;
    # conv.go's apimachinery is no module api can name, tools' example.com/app is the published module
    assert (row['status'], row['population'], row['packages']) == ('green', 7, 8), row


@pytest.mark.parametrize('damage', ['unresolved', 'decoy'])
def test_local_units_resolved_red_when_a_go_module_import_misses_or_lands_elsewhere(go_workspace, damage):
    view = copy.deepcopy(_answer(go_workspace.parent, 'imports://ws?root=ws'))
    for stmt in view['files']['pkg/app/main.go']:
        if stmt['module'] == 'example.com/app/vendored/lib':
            # an engine without go.work/replace (or the longest-path rule) answers one of these
            stmt['resolved'] = None if damage == 'unresolved' else 'vendored/lib'
    row = inv.check_local_units_resolved(view, {}, go_workspace, inv.scan_go_module_scopes(go_workspace))
    assert (row['status'], row['violations']) == ('red', 1), row
    assert row['examples'][0]['expected'] == 'third_party/vendored/lib'


def test_go_module_scopes_read_go_work_and_local_replaces_from_the_corpus(go_workspace):
    scopes = inv.scan_go_module_scopes(go_workspace)
    root, staging = go_workspace.resolve(), go_workspace.resolve() / 'staging/src/example.com'
    workspace = {'example.com/app', 'example.com/api', 'example.com/client', 'example.com/sampler', 'example.com/plugins'}
    assert set(scopes[root]) == workspace | {'example.com/app/vendored'}
    assert scopes[root]['example.com/app/vendored'] == root / 'third_party/vendored'
    assert set(scopes[staging / 'client']) == workspace   # example.com/remote => a module: not a directory
    assert set(scopes[staging / 'apimachinery']) == {'example.com/apimachinery'}
    # scanning below the go.work still reads it (Kubernetes' staging/src/k8s.io row)
    below = inv.scan_go_module_scopes(go_workspace / 'staging/src')
    assert set(below[staging / 'sampler']) == {'example.com/api', 'example.com/client', 'example.com/sampler',
                                               'example.com/plugins'}


def test_package_wildcards_empty_when_no_wildcard_names_a_scanned_package(tmp_path):
    scan = tmp_path / 'p'
    scan.mkdir()
    (scan / 'A.java').write_text('package a;\nimport java.util.*;\npublic class A {}\n', encoding='utf-8')
    view = _answer(tmp_path, 'imports://p?root=p', expect=(0, 3))
    assert inv.check_package_wildcards(view, inv.scan_declared_packages(scan))['status'] == 'empty'


# ── calls_inverse and callers_view ────────────────────────────────────────────

def test_calls_inverse_holds_on_the_fixture(root):
    rank = _rank(root)
    callees = _callees(root, rank)
    assert set(callees) == {('proj/pkg/a.py', 'run'), ('proj/pkg/b.py', 'go'), ('proj/pkg/b.py', 'later'),
                            ('proj/pkg/c.py', 'both')}
    row = inv.check_calls_inverse(rank, callees)
    assert row['status'] == 'green', row
    assert row['population'] > 0 and row['dedup_shadowed'] == 0


def test_calls_inverse_red_when_a_callee_list_drops_a_call(root):
    rank = _rank(root)
    callees = _callees(root, rank)
    match = callees[('proj/pkg/c.py', 'both')]['matches'][0]
    match['calls'].remove('b.go')
    row = inv.check_calls_inverse(rank, callees)
    assert row['status'] == 'red'
    assert {'caller': ['proj/pkg/c.py', 'both'], 'indexed_not_in_callees': ['b.go', 'b.go']} in row['examples']


def test_calls_inverse_red_when_a_callee_list_has_a_call_nothing_indexes(root):
    rank = _rank(root)
    callees = _callees(root, rank)
    callees[('proj/pkg/a.py', 'run')]['matches'][0]['calls'].append('phantom')
    row = inv.check_calls_inverse(rank, callees)
    assert row['status'] == 'red'
    assert {'caller': ['proj/pkg/a.py', 'run'], 'callee_not_indexed': 'phantom'} in row['examples']


def test_calls_inverse_counts_a_call_the_ranking_deduplicated_away_but_does_not_fail_it():
    """Negative control: the ranking keeps one record per (file, caller) under each key, so `helper`
    called as both `self.helper` and `helper` shows only the first under key `helper`."""
    rank = {'entries': [{'name': 'helper', 'caller_count': 1,
                         'callers': [{'file': 'm.py', 'caller': 'run', 'call_expr': 'self.helper'}]},
                        {'name': 'self.helper', 'caller_count': 1,
                         'callers': [{'file': 'm.py', 'caller': 'run', 'call_expr': 'self.helper'}]}]}
    callees = {('m.py', 'run'): {'matches': [{'file': 'm.py', 'function': 'run', 'calls': ['self.helper', 'helper']}]}}
    row = inv.check_calls_inverse(rank, callees)
    assert row['status'] == 'green' and row['dedup_shadowed'] == 1
    callees[('m.py', 'run')]['matches'][0]['calls'].append('other')
    assert inv.check_calls_inverse(rank, callees)['status'] == 'red'


def test_callers_view_holds_and_goes_red_on_a_dropped_caller(root):
    rank = _rank(root)
    callers = {name: _answer(root, f'calls://proj?callers={name}') for name in inv.sample_names(rank, 4)}
    assert 'helper' in callers  # the most-called plain name is always sampled
    assert inv.check_callers_view(rank, callers)['status'] == 'green'
    callers['helper']['levels'][0]['callers'].pop()
    row = inv.check_callers_view(rank, callers)
    assert row['status'] == 'red' and row['examples'][0]['name'] == 'helper'


def test_an_index_that_loses_one_call_turns_calls_inverse_red(root, monkeypatch):
    """Engine-level red control: the callers index drops c.py both's `b.go`; the forward callee
    list still has it, so the inverse must fail on exactly that call."""
    import reveal.adapters.calls.index as calls_index
    original = calls_index._index_callee

    def lossy(index, callee, record, alias_map, class_aliases=None):
        if callee == 'b.go' and record.get('caller') == 'both':
            return
        original(index, callee, record, alias_map, class_aliases)

    monkeypatch.setattr(calls_index, '_index_callee', lossy)
    rank = _rank(root)
    row = inv.check_calls_inverse(rank, _callees(root, rank))
    assert row['status'] == 'red'
    assert {'caller': ['proj/pkg/c.py', 'both'], 'callee_not_indexed': 'b.go'} in row['examples']


# ── call_targets (BACK-2569) ──────────────────────────────────────────────────

class _InProcess:
    """run_call_targets' request side, in process: one --stdin batch per call, as Requests.batch."""

    def __init__(self, root):
        self.root = root

    def batch(self, lines):
        result = _run_reveal_in(self.root, '--stdin', '--format', 'json', stdin='\n'.join(lines) + '\n')
        answers = inv.json_stream(result.stdout)
        return answers, None if answers else f'no answers: {result.stderr}'


def _call_targets(root, scan='proj', count=50):
    rank = _answer(root, f'calls://{scan}?rank=callers&top=0&builtins=true&test-framework=true')
    return inv.run_call_targets(_InProcess(root), scan, inv.sample_callers(rank, count))


EXTERNAL_TREE = {
    'ext/c.py': 'import json\nfrom os.path import join\n\n\ndef loads(s):\n    return json.loads(join(s, "x"))\n',
    'ext/d.py': 'def join(a, b):\n    return a\n',
    'ext/e.py': 'from d import join\n\n\ndef run(s):\n    return join(s, "y")\n',
}


def _tree(tmp_path, files):
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text, encoding='utf-8')
    return tmp_path


def test_call_targets_holds_on_the_fixture(root):
    row = _call_targets(root)
    assert row['status'] == 'green', row
    # Positive control: b.py's `helper()` is bound to pkg/a.py, which defines it. (`a.run()` is not
    # checked: `from pkg import a` reads as pkg/__init__.py, the statement's first target, BACK-2574.)
    assert row['edges_checked']['bound_file'] >= 1 and row['edges_checked']['target_defines'] >= 3
    assert row['walks'] == row['walks_requested'] == 4


def test_call_targets_checks_external_and_in_tree_bindings(tmp_path):
    root = _tree(tmp_path, EXTERNAL_TREE)
    row = _call_targets(root, 'ext')
    assert row['status'] == 'green', row
    # json.loads and join (os.path) in c.py are external; join in e.py is bound to d.py.
    assert row['edges_checked'] == {'bound_file': 1, 'external_binding': 2, 'target_defines': 1}


def test_a_resolver_that_ignores_external_bindings_turns_call_targets_red(tmp_path, monkeypatch):
    """Engine-level red control: the BACK-2553 defect (json.loads read as recursion, os.path's join
    read as d.py's) restored by switching the binding check off."""
    from reveal.adapters.calls.resolve import CallResolver
    monkeypatch.setattr(CallResolver, '_reachable', lambda self, call, caller_file, candidates: candidates)
    row = _call_targets(_tree(tmp_path, EXTERNAL_TREE), 'ext')
    assert row['status'] == 'red'
    assert {(v['rule'], v['call'], v['got']) for v in row['examples']} == {
        ('external_binding', 'json.loads', 'ext/c.py:5'), ('external_binding', 'join', 'ext/d.py:1')}


def test_a_call_that_misses_its_bound_file_turns_call_targets_red(tmp_path, monkeypatch):
    """Engine-level red control: the resolver ignores what an in-tree import names, so e.py's `join`,
    bound to d.py, is resolved to another file's same-named function."""
    from reveal.adapters.calls.resolve import CallResolver
    root = _tree(tmp_path, {**EXTERNAL_TREE, 'ext/f.py': 'def join(a, b):\n    return b\n'})
    assert _call_targets(root, 'ext')['status'] == 'green'
    monkeypatch.setattr(CallResolver, '_disambiguate',
                        lambda self, call, tail, caller_file, candidates: candidates[-1])
    row = _call_targets(root, 'ext')
    assert [(v['rule'], v['call'], v['got'], v['bound_to']) for v in row['examples']] == [
        ('bound_file', 'join', 'ext/f.py:1', 'ext/d.py')]


def test_call_targets_red_when_a_target_does_not_define_the_name():
    walks = [{'levels': [{'level': 1, 'callees': [
        {'caller_file': 'p/a.py', 'caller_line': 1, 'call_expr': 'helper', 'callee': 'helper',
         'resolved': True, 'callee_file': 'p/b.py', 'callee_line': 7}]}]}]
    outlines = {'p/a.py': {}, 'p/b.py': {'helper': {3}}}
    row = inv.check_call_targets(walks, {'files': {}}, outlines, 'p')
    assert row['status'] == 'red' and row['examples'][0]['rule'] == 'target_defines'
    outlines['p/b.py']['helper'] = {7}
    assert inv.check_call_targets(walks, {'files': {}}, outlines, 'p')['status'] == 'green'


@pytest.mark.parametrize('stmt, bound', [
    ({'type': 'from_import', 'names': ['join', 'split as sp'], 'file': 'a.py'}, [('join', 'join'), ('sp', 'split')]),
    ({'type': 'import', 'module': 'os.path', 'names': [], 'alias': 'osp', 'file': 'a.py'}, [('osp', None)]),
    ({'type': 'import', 'module': 'os.path', 'names': [], 'file': 'a.py'}, [('os', None)]),
    ({'type': 'namespace_import', 'module': 'fs', 'names': ['*'], 'alias': 'fs', 'file': 'a.ts'}, [('fs', None)]),
    ({'type': 'default_import', 'module': 'typescript', 'names': ['ts'], 'file': 'a.ts'}, [('ts', None)]),
    ({'type': 'import', 'module': 'java.util.List', 'names': [], 'file': 'A.java'}, []),  # a guessed name
    ({'type': 'include', 'module': 'array', 'names': [], 'file': 'a.cpp'}, []),
])
def test_statement_bindings_reads_only_the_languages_own_binding_rule(stmt, bound):
    assert inv.statement_bindings(stmt) == bound


# ── no_match ──────────────────────────────────────────────────────────────────

SPECS = [{'noun': 'imports', 'name': 'importers', 'names': 'file', 'flags': ['--importers']},
         {'noun': 'calls', 'name': 'callers', 'names': 'symbol', 'flags': ['--callers']}]


def _no_match_results(root, specs=SPECS):
    return [(label, spelling, value, {'exit_code': r.returncode, 'stderr': r.stderr})
            for label, spelling, value, argv in inv.no_match_requests('proj', specs)
            for r in [_run_reveal_in(root, *argv)]]


def test_no_match_holds_for_every_declared_spelling(root):
    results = _no_match_results(root)
    assert [(r[0], r[1]) for r in results] == [('imports:importers', 'uri'), ('imports:importers', 'cli'),
                                               ('calls:callers', 'uri'), ('calls:callers', 'cli')]
    row = inv.check_no_match(results)
    assert row['status'] == 'green', row


def test_no_match_red_on_a_clean_zero_an_unnamed_target_or_a_usage_error(root):
    results = _no_match_results(root)
    label, spelling, value, row = results[0]
    clean_zero = [(label, spelling, value, dict(row, exit_code=0))]
    unnamed = [(label, spelling, value, dict(row, stderr='Error: nothing matched'))]
    usage = [(label, spelling, value, dict(row, stderr=f'error: unrecognized arguments: --x {value}'))]
    for broken in (clean_zero, unnamed, usage):
        assert inv.check_no_match(broken)['status'] == 'red', broken


def test_the_declared_specs_are_read_from_the_checkout_under_test(root):
    env = inv.request_env(SCRIPTS.parent, disk_cache=False)
    specs = inv.declared_target_specs(env, root)
    assert {(s['noun'], s['name']) for s in specs} >= {('imports', 'importers'), ('calls', 'callers'),
                                                       ('calls', 'callees')}
    assert all(s['flags'] for s in specs)


# ── rows and the driver ───────────────────────────────────────────────────────

def test_a_zero_population_is_empty_not_green():
    assert inv.make_row('x', 0, [])['status'] == 'empty'
    assert inv.make_row('x', 3, [])['status'] == 'green'
    assert inv.make_row('x', 0, [{'v': 1}])['status'] == 'red'


def test_the_runner_end_to_end_on_the_fixture(root, tmp_path):
    """The real driver through `python -m reveal` processes: one corpus, every invariant green,
    the JSON report written, exit 0."""
    out = tmp_path / 'report.json'
    rc = inv.main(['--corpus-root', str(root), '--corpus', 'proj', '--output', str(out),
                   '--only', 'fan_in_total', '--only', 'importers_resolved', '--only', 'no_match',
                   '--timeout', '120'])
    report = json.loads(out.read_text(encoding='utf-8'))
    rows = {row['invariant']: row for row in report['corpora']['proj']['rows']}
    assert rc == 0, rows
    assert {name: row['status'] for name, row in rows.items()} == {
        'fan_in_total': 'green', 'importers_resolved': 'green', 'no_match': 'green'}
    assert rows['fan_in_total']['population'] == 6
    assert rows['no_match']['population'] == 2 * len(report['target_specs'])
