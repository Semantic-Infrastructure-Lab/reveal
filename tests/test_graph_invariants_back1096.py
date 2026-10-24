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
