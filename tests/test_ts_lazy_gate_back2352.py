"""Independent compiler scope labels qualify existing rendered lazy-mode scoring.

The baseline has an all-edges compiler oracle; missing lazy callbacks/rows are a
measurement feature gap, not evidence that the current runtime answer is wrong.
"""
import hashlib
import json
from dataclasses import replace

import pytest

from reveal.analyzers.imports.types import ImportGraph
from reveal.analyzers.imports.views import ImportView
from test_recall_gate import compiler_oracle, gate, oracles, _repo, _ts_config

pytestmark = pytest.mark.component
CONFIG = ('{"compilerOptions":{"allowJs":true,"module":"esnext",'
          '"moduleResolution":"bundler","strict":true}}')
SOURCES = {
    'package.json': '{"name":"independent-lazy-fixture","private":true}',
    'tsconfig.json': CONFIG,
    'src/target.ts': 'export const value = 1;\n',
    'src/module.ts': 'import { value } from "./target";\nexport { value };\n',
    'src/dynamic.ts': 'export const promise = import("./target");\n',
    'src/local.ts': 'export function load() { return import("./target"); }\n',
    'src/require.ts': 'export function load() { return require("./target"); }\n',
    'src/mixed.ts': 'import { value } from "./target";\nexport function load() { return require("./target"); }\n',
    'src/method.ts': 'export class Loader { load() { return import("./target"); } }\n',
    'src/arrow.ts': 'export const load = () => require("./target");\n',
    'src/iife.ts': '(function () { require("./target"); })();\n',
    'src/class_field.ts': 'export class Loader { value = require("./target"); }\n',
    'src/decl.d.ts': 'import { value } from "./target";\n',
}
LOCAL = ['src/arrow.ts', 'src/iife.ts', 'src/local.ts', 'src/method.ts', 'src/require.ts']
MODULE = ['src/class_field.ts', 'src/dynamic.ts', 'src/mixed.ts', 'src/module.ts']
ALL = {'src/target.ts': sorted(LOCAL + MODULE)}


def digest(value):
    return hashlib.sha256(json.dumps(value, separators=(',', ':')).encode('utf-8')).hexdigest()


@pytest.fixture
def corpus(tmp_path, compiler_oracle):
    return _repo(tmp_path, SOURCES, _ts_config(scan_file_cap=1000))


def scope_of(root, entry):
    oracle = oracles.ORACLES['typescript-compiler']
    return oracles.Scope(root, root, oracles.tracked_files(root, ['src'], oracle.suffixes), entry['recall'])


def require_lazy_rows(measured):
    assert 'lazy' in measured, 'Feature gap: compiler population is not yet scored under lazy=exclude/only'
    return measured['lazy']


def test_compiler_all_edges_and_toolchain_config_population_identity_stay_exact(corpus):
    root, entry = corpus
    edges, coverage = oracles.ORACLES['typescript-compiler'].build(scope_of(root, entry))
    assert edges == ALL
    assert coverage == {
        'files': 10, 'directives': 10, 'unresolved_directives': 0, 'excluded_targets': 0,
        'declaration_files_skipped': 1,
        'population_digest': digest(sorted(path for path in SOURCES if path.endswith('.ts') and not path.endswith('.d.ts'))),
        'config_digest': digest([['tsconfig.json', CONFIG]]),
        'compiler_options_digest': digest({}), 'typescript_version': '5.9.3',
        'node_version': '22.14.0', 'scan_file_cap': 1000,
    }
    measured = gate.measure(entry, root)
    assert measured['oracle_edges'] == measured['hit_edges'] == 9
    assert measured['recall'] == measured['precision'] == 1
    assert measured['edge_rule']['lazy'] == 'include'
    assert measured['edge_rule']['tests'] == 'included'
    assert measured['edge_rule']['type_checking'] == 'excluded'


def test_independent_compiler_partitions_function_ancestry_not_runtime_timing(corpus):
    root, entry = corpus
    oracle = oracles.ORACLES['typescript-compiler']
    assert oracle.lazy_only is not None, 'Feature gap: compiler oracle has no function-scope callback'
    assert oracle.lazy_only(scope_of(root, entry)) == {'src/target.ts': LOCAL}
    # IIFE is syntactically local despite immediate invocation. A class field and
    # module-body import() have no function ancestor; this is not execution timing.


def test_compiler_populations_are_scored_under_exact_rendered_lazy_rules(corpus):
    root, entry = corpus
    measured = gate.measure(entry, root)
    modes = require_lazy_rows(measured)
    assert modes['exclude']['oracle_edges'] == modes['exclude']['hit_edges'] == 4
    assert modes['only']['oracle_edges'] == modes['only']['hit_edges'] == 5
    for mode, row in modes.items():
        assert row['recall'] == row['precision'] == 1 and row['extra_edges'] == 0
        assert row['differences'] == [] and row['edge_rule']['lazy'] == mode
        assert row['edge_rule']['tests'] == 'included' and row['edge_rule']['type_checking'] == 'excluded'
    without = {key: value for key, value in measured.items() if key != 'lazy'}
    assert gate.regressions({'ts': measured}, {'ts': without}) == [
        'ts: lazy=exclude baseline missing; review required', 'ts: lazy=only baseline missing; review required']


def test_mixed_edge_scope_mutation_fails_modes_while_all_edges_remain_green(corpus, monkeypatch):
    root, entry = corpus
    baseline = gate.measure(entry, root)
    require_lazy_rows(baseline)
    original = ImportGraph.is_lazy_edge
    monkeypatch.setattr(ImportGraph, 'is_lazy_edge',
                        lambda self, source, target: source.name == 'mixed.ts' or original(self, source, target))
    measured = gate.measure(entry, root)
    assert measured['oracle_edges'] == measured['hit_edges'] == 9
    assert measured['recall'] == measured['precision'] == 1
    assert measured['lazy']['only']['differences'] == [
        {'target': 'src/target.ts', 'missed': [], 'extra': ['src/mixed.ts']}]
    assert measured['lazy']['exclude']['differences'] == [
        {'target': 'src/target.ts', 'missed': ['src/mixed.ts'], 'extra': []}]
    failures = gate.regressions({'ts': measured}, {'ts': baseline})
    assert any('lazy=exclude recall dropped' in failure for failure in failures)
    assert any('lazy=only extra-edge population changed' in failure for failure in failures)


def test_omitted_local_view_edge_fails_only_mode_without_changing_default(corpus, monkeypatch):
    root, entry = corpus
    baseline = gate.measure(entry, root)
    require_lazy_rows(baseline)
    original = ImportView._edges
    def omitted(self, default):
        view = original(self, default)
        if self.lazy != 'only':
            return view
        source = root / 'src/local.ts'
        return replace(view, reverse_deps={target: importers - {source}
                                          for target, importers in view.reverse_deps.items()},
                       dependencies={file: targets for file, targets in view.dependencies.items() if file != source})
    monkeypatch.setattr(ImportView, '_edges', omitted)
    measured = gate.measure(entry, root)
    assert measured['recall'] == measured['precision'] == 1
    assert measured['lazy']['exclude'] == baseline['lazy']['exclude']
    assert measured['lazy']['only']['differences'] == [
        {'target': 'src/target.ts', 'missed': ['src/local.ts'], 'extra': []}]
    assert any('lazy=only recall dropped' in failure
               for failure in gate.regressions({'ts': measured}, {'ts': baseline}))


def test_compiler_dependency_and_toolchain_failures_do_not_become_empty_scope(corpus, monkeypatch):
    root, entry = corpus
    oracle = oracles.ORACLES['typescript-compiler']
    scope = scope_of(root, entry)
    for field in ('typescript_version', 'node_version'):
        with pytest.raises(RuntimeError, match='toolchain mismatch'):
            oracle.build(scope._replace(config={**scope.config, field: '0.0.0'}))
    monkeypatch.setenv('REVEAL_TS_ORACLE_MODULE', str(root / 'absent-typescript'))
    with pytest.raises(RuntimeError, match='compiler oracle failed'):
        oracle.build(scope)
