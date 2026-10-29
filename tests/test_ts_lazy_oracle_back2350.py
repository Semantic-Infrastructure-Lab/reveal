"""Compiler-oracle scope features; a missing callback previously left modes unscored."""
import hashlib
import json

import pytest

from test_recall_gate import _repo, _ts_config, compiler_oracle, gate, oracles
from reveal.analyzers.imports.types import ImportGraph

CONFIG = ('{"compilerOptions":{"allowJs":true,"module":"esnext",'
          '"moduleResolution":"bundler","jsx":"react-jsx"}}')
TARGET = 'export const value = 1; export interface Thing { value: number; }\n'
BASIC = {
    'package.json': '{"name":"scope-fixture","private":true}',
    'tsconfig.json': CONFIG,
    'src/target.ts': TARGET,
    'src/module.ts': 'import { value } from "./target"; export const top = value;\n',
    'src/dynamic.ts': 'export const top = import("./target");\n',
    'src/local.ts': 'export function load() { return import("./target"); }\n',
    'src/mixed.ts': 'import { value } from "./target"; export function load() { return import("./target"); }\n',
    'src/arrow.tsx': 'export const load = () => import("./target");\n',
    'src/method.ts': 'export class Loader { load() { return require("./target"); } }\n',
}
RICH = {
    **BASIC,
    'src/require.js': 'exports.load = function () { return require("./target"); };\n',
    'src/fields.ts': ('class Fields {\n field = require("./target");\n'
                      ' static field = import("./target");\n static { require("./target"); }\n}\n'),
    'src/nested.ts': 'export function outer() { class Nested { static field = require("./target"); } }\n',
    'src/accessors.ts': ('class Access { constructor() { require("./target"); }\n'
                         ' get value() { return import("./target"); }\n'
                         ' set value(x) { require("./target"); } }\n'),
    'src/barrel.ts': 'export { value } from "./target";\n',
    'src/equals.ts': 'import target = require("./target");\n',
    'src/type_only.ts': 'import type { Thing } from "./target"; export type Alias = Thing;\n',
    'src/type_import.ts': 'export type Alias = import("./target").Thing;\n',
    'src/ambient.ts': 'declare function ambient(): import("./target").Thing;\n',
    'src/signature.ts': 'interface Contract { method(): import("./target").Thing; }\n',
    'src/function_type.ts': 'export type Factory = () => import("./target").Thing;\n',
    'src/local_type.ts': 'export function local() { type Alias = import("./target").Thing; }\n',
    'src/namespace.ts': 'namespace N { export const value = require("./target"); }\n',
    'src/decl.d.ts': 'import { value } from "./target";\n',
}
LAZY = ['src/accessors.ts', 'src/ambient.ts', 'src/arrow.tsx', 'src/local.ts', 'src/local_type.ts',
        'src/method.ts', 'src/nested.ts', 'src/require.js']


def scope(root, entry):
    oracle = oracles.ORACLES['typescript-compiler']
    return oracles.Scope(root, root, oracles.tracked_files(root, ['src'], oracle.suffixes), entry['recall'])


@pytest.fixture
def tiny(tmp_path, compiler_oracle):
    return _repo(tmp_path, BASIC, _ts_config())


@pytest.fixture
def rich(tmp_path, compiler_oracle):
    return _repo(tmp_path, RICH, _ts_config())


def digest(value):
    return hashlib.sha256(json.dumps(value, separators=(',', ':')).encode('utf-8')).hexdigest()


def test_existing_union_population_and_config_digests(rich):
    root, entry = rich
    edges, coverage = oracles.ORACLES['typescript-compiler'].build(scope(root, entry))
    expected = sorted(name for name in RICH if name.startswith('src/')
                      and name not in ('src/target.ts', 'src/decl.d.ts'))
    assert edges == {'src/target.ts': expected}
    population = sorted(name for name in RICH if name.startswith('src/') and name != 'src/decl.d.ts')
    assert coverage['files'] == len(population) and coverage['declaration_files_skipped'] == 1
    assert coverage['population_digest'] == digest(population)
    assert coverage['config_digest'] == digest([['tsconfig.json', CONFIG]])
    assert coverage['compiler_options_digest'] == digest({})


def test_compiler_scope_callback_covers_function_values_methods_classes_and_types(rich):
    root, entry = rich
    oracle = oracles.ORACLES['typescript-compiler']
    # Feature qualification: the prior callback was None, not an incorrectly labelled edge.
    assert callable(oracle.lazy_only)
    assert oracle.lazy_only(scope(root, entry)) == {'src/target.ts': LAZY}


def test_mixed_pair_any_module_contributor_keeps_pair_out_of_lazy_only(tiny):
    root, entry = tiny
    oracle = oracles.ORACLES['typescript-compiler']
    assert callable(oracle.lazy_only)
    assert oracle.lazy_only(scope(root, entry)) == {
        'src/target.ts': ['src/arrow.tsx', 'src/local.ts', 'src/method.ts']}
    assert oracle.build(scope(root, entry))[0]['src/target.ts'] == [
        'src/arrow.tsx', 'src/dynamic.ts', 'src/local.ts', 'src/method.ts', 'src/mixed.ts', 'src/module.ts']


def test_actual_gate_scores_previously_unscored_compiler_modes(tiny):
    root, entry = tiny
    measured = gate.measure(entry, root)
    assert measured['recall'] == measured['precision'] == 1
    assert set(measured['lazy']) == {'exclude', 'only'}
    assert measured['lazy']['exclude']['oracle_edges'] == measured['lazy']['only']['oracle_edges'] == 3
    assert all(row['recall'] == row['precision'] == 1 for row in measured['lazy'].values())


def test_wrong_scope_mutation_fails_modes_while_default_union_stays_green(tiny, monkeypatch):
    root, entry = tiny
    baseline = gate.measure(entry, root)
    assert 'lazy' in baseline
    real = ImportGraph.is_lazy_edge
    monkeypatch.setattr(ImportGraph, 'is_lazy_edge', lambda self, src, dst:
                        real(self, src, dst) or src.name == 'mixed.ts')
    measured = gate.measure(entry, root)
    assert measured['oracle_edges'] == baseline['oracle_edges']
    assert measured['recall'] == measured['precision'] == 1
    assert measured['lazy']['only']['differences'] == [
        {'target': 'src/target.ts', 'missed': [], 'extra': ['src/mixed.ts']}]
    assert measured['lazy']['exclude']['differences'] == [
        {'target': 'src/target.ts', 'missed': ['src/mixed.ts'], 'extra': []}]
    failures = gate.regressions({'ts': measured}, {'ts': baseline})
    assert any('lazy=exclude recall dropped' in failure for failure in failures)
    assert any('lazy=only extra-edge population changed' in failure for failure in failures)


def test_new_modes_require_explicit_baseline_review(tiny):
    root, entry = tiny
    measured = gate.measure(entry, root)
    assert 'lazy' in measured
    old = {key: value for key, value in measured.items() if key != 'lazy'}
    assert gate.regressions({'ts': measured}, {'ts': old}) == [
        'ts: lazy=exclude baseline missing; review required', 'ts: lazy=only baseline missing; review required']


def test_callback_preserves_source_error_instead_of_empty_scope(tiny):
    root, entry = tiny
    (root / 'src/local.ts').write_text('export function broken( {\n', encoding='utf-8')
    oracle = oracles.ORACLES['typescript-compiler']
    with pytest.raises(RuntimeError, match='cannot parse'):
        oracle.build(scope(root, entry))
    assert callable(oracle.lazy_only)
    with pytest.raises(RuntimeError, match='cannot parse'):
        oracle.lazy_only(scope(root, entry))
