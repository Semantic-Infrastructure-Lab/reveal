"""Recall-gate controls: tiny real git corpora, each independent oracle, and the comparison."""
import ast
import importlib.util
import json
import re
import subprocess
import shutil
import sys
from pathlib import Path

import pytest

from reveal.adapters.depends import DependsAdapter

pytestmark = pytest.mark.component
SCRIPTS = Path(__file__).resolve().parent.parent / 'scripts'


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


oracles = _load('recall_oracles')  # the gate imports it by name, as when run from scripts/
gate = _load('recall_gate')
needs_gcc = pytest.mark.skipif(sys.platform == 'win32' or not shutil.which('gcc'),
                               reason='optional GCC oracle requires a qualified POSIX compiler host')


def _repo(root: Path, files: dict, recall: dict) -> tuple[Path, dict]:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding='utf-8')
    subprocess.run(['git', 'init', '-q', str(root)], check=True, timeout=30)
    subprocess.run(['git', '-C', str(root), 'add', '.'], check=True, timeout=30)
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                    'commit', '-qm', 'fixture'], check=True, timeout=30)
    sha = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], check=True, timeout=30,
                         capture_output=True, text=True, encoding='utf-8').stdout.strip()
    return root.resolve(), {'sha': sha, 'recall': recall}


def _build(root: Path, entry: dict):
    config = entry['recall']
    oracle = oracles.ORACLES[config['oracle']]
    importers = oracles.tracked_files(root, config['importer_dirs'], oracle.suffixes)
    return oracle.build(oracles.Scope(root, (root / config.get('scan_root', '.')).resolve(), importers, config))


@pytest.fixture
def corpus(tmp_path):
    return _repo(tmp_path, {
        'src/target.h': 'int probe(void);\n',
        'src/clean.c': '#include "target.h"\nint probe(void) { return 1; }\n',
        'src/partial.c': '#include "target.h"\nint broken( {{{\n',
    }, {'oracle': 'gcc-c', 'importer_dirs': ['src'], 'include_dirs': ['src']})


PYTHON = {
    'pyproject.toml': '[project]\nname = "pkg"\n',
    'pkg/__init__.py': 'VALUE = 1\n',
    'pkg/a.py': 'from . import b, VALUE\nfrom .sub.c import thing\n',
    'pkg/b.py': ('import pkg.a\nfrom typing import TYPE_CHECKING\n'
                 'if TYPE_CHECKING:\n    from pkg import sub\n'),
    'pkg/sub/__init__.py': '',
    'pkg/sub/c.py': 'thing = 1\n',
}


@pytest.fixture
def python_corpus(tmp_path):
    return _repo(tmp_path, PYTHON, {'oracle': 'python-ast', 'importer_dirs': ['.']})


@needs_gcc
def test_independent_oracle_sees_partial_source_and_measurement(corpus):
    root, entry = corpus
    oracle, coverage = _build(root, entry)
    assert oracle == {'src/target.h': ['src/clean.c', 'src/partial.c']}
    assert coverage['files'] == 3 and coverage['directives'] == 2
    measured = gate.measure(entry, root)
    assert measured['hit_edges'] == 2 and measured['recall'] == measured['precision'] == 1
    assert measured['partial_files'] == 1 and measured['oracle'] == 'gcc-c'


@needs_gcc
def test_cpp_oracle_uses_the_cpp_population_and_language(tmp_path):
    root, entry = _repo(tmp_path, {
        'code/target.hpp': 'struct Probe {};\n',
        'code/use.cpp': '#include "target.hpp"\nProbe p;\n',
        'code/skip.c': '#include "target.hpp"\n',  # a C file is outside the C++ population
    }, {'oracle': 'gcc-cpp', 'importer_dirs': ['code'], 'include_dirs': ['code']})
    assert _build(root, entry)[0] == {'code/target.hpp': ['code/use.cpp']}
    measured = gate.measure(entry, root)
    assert measured['recall'] == measured['precision'] == 1


def test_python_oracle_resolves_like_the_interpreter_and_skips_type_checking(python_corpus):
    root, entry = python_corpus
    edges, coverage = _build(root, entry)
    assert edges == {
        'pkg/__init__.py': ['pkg/a.py'],   # VALUE is a symbol of the package
        'pkg/a.py': ['pkg/b.py'],
        'pkg/b.py': ['pkg/a.py'],          # from . import b: sibling submodule
        'pkg/sub/c.py': ['pkg/a.py'],      # multi-segment relative import
    }
    assert coverage['type_checking_skipped'] == 1 and coverage['files'] == 5
    measured = gate.measure(entry, root)
    assert measured['recall'] == measured['precision'] == 1 and measured['oracle_edges'] == 4


def test_python_file_the_oracle_cannot_parse_is_a_failure_not_a_smaller_truth(tmp_path):
    root, entry = _repo(tmp_path, {**PYTHON, 'pkg/bad.py': 'def broken(:\n'},
                        {'oracle': 'python-ast', 'importer_dirs': ['.']})
    with pytest.raises(RuntimeError, match='could not parse 1 file'):
        _build(root, entry)


RUST = {
    'Cargo.toml': '[package]\nname = "fixture"\nversion = "0.1.0"\n',
    'src/main.rs': 'mod a;\nmod d;\nuse crate::{a::{b, c}, d::Thing};\nfn main() {}\n',
    'src/a.rs': 'pub mod b;\npub mod c;\n',
    'src/a/b.rs': 'use super::c::Item;\n',
    'src/a/c.rs': 'pub struct Item;\n',
    'src/d.rs': 'pub struct Thing;\n',
}


def test_rust_oracle_expands_nested_groups_and_super_paths(tmp_path):
    root, entry = _repo(tmp_path, RUST, {'oracle': 'rust-use', 'importer_dirs': ['.']})
    assert _build(root, entry)[0] == {
        'src/a/b.rs': ['src/main.rs'],
        'src/a/c.rs': ['src/a/b.rs', 'src/main.rs'],
        'src/d.rs': ['src/main.rs'],
    }
    assert oracles.rust_use_paths('crate::x::{self, y::{z, w as v}}') == ['crate::x', 'crate::x::y::z', 'crate::x::y::w']
    measured = gate.measure(entry, root)
    assert measured['recall'] == measured['precision'] == 1


def test_rust_aliased_use_list_item_is_an_edge(tmp_path):
    root, entry = _repo(tmp_path, {**RUST, 'src/main.rs': 'mod a;\nmod d;\nuse crate::{d::Thing as T};\nfn main() {}\n'},
                        {'oracle': 'rust-use', 'importer_dirs': ['.']})
    assert _build(root, entry)[0]['src/d.rs'] == ['src/main.rs']
    assert gate.measure(entry, root)['recall'] == 1


JAVA = {
    'lib/pom.xml': '<project/>\n',
    'lib/src/com/ex/A.java': ('package com.ex;\nimport com.ex.util.B;\nimport static com.ex.util.C.helper;\n'
                              'import com.ex.util.C.Inner;\npublic class A {}\n'),
    'lib/src/com/ex/E.java': 'package com.ex;\nimport com.ex.util.C.Inner.Deep;\npublic class E {}\n',
    'lib/src/com/ex/util/B.java': 'package com.ex.util;\nimport com.ex.A;\npublic class B {}\n',
    'lib/src/com/ex/util/C.java': ('package com.ex.util;\npublic class C {\n  public static void helper() {}\n'
                                   '  public static class Inner { public static class Deep {} }\n}\n'),
}


def test_java_oracle_handles_static_nested_and_wildcard_imports(tmp_path):
    root, entry = _repo(tmp_path, {**JAVA, 'mirror/src/com/ex/A.java': 'package com.ex;\npublic class A {}\n'},
                        {'oracle': 'java-jls', 'scan_root': 'lib', 'importer_dirs': ['lib/src']})
    assert _build(root, entry)[0] == {
        'lib/src/com/ex/A.java': ['lib/src/com/ex/util/B.java'],
        'lib/src/com/ex/util/B.java': ['lib/src/com/ex/A.java'],
        'lib/src/com/ex/util/C.java': ['lib/src/com/ex/A.java', 'lib/src/com/ex/E.java'],  # E: two nesting levels
    }
    measured = gate.measure(entry, root)  # the mirror outside scan_root is invisible to both sides
    assert measured['recall'] == measured['precision'] == 1


def _java_wildcard(tmp_path):
    return _repo(tmp_path, {**JAVA, 'lib/src/com/ex/util/B.java': 'package com.ex.util;\nimport com.ex.*;\npublic class B {}\n',
                            'lib/src/com/ex/D.java': 'package com.ex;\npublic class D {}\n'},
                 {'oracle': 'java-jls', 'scan_root': 'lib', 'importer_dirs': ['lib/src']})


def test_java_oracle_fans_a_wildcard_out_to_the_whole_package(tmp_path):
    edges = _build(*_java_wildcard(tmp_path))[0]
    assert edges['lib/src/com/ex/A.java'] == edges['lib/src/com/ex/D.java'] == ['lib/src/com/ex/util/B.java']


@pytest.mark.xfail(strict=True, reason='reveal gap found by this gate: Java import a.b.*; resolves to no file '
                   '(resolve_namespace_targets rejects wildcards), while Kotlin wildcards fan out')
def test_java_wildcard_import_is_an_edge_to_each_package_file(tmp_path):
    root, entry = _java_wildcard(tmp_path)
    assert gate.measure(entry, root)['recall'] == 1


def test_java_duplicate_types_in_scope_are_ambiguous_not_guessed(tmp_path):
    root, entry = _repo(tmp_path, {**JAVA, 'lib/src2/com/ex/A.java': 'package com.ex;\npublic class A {}\n'},
                        {'oracle': 'java-jls', 'scan_root': 'lib', 'importer_dirs': ['lib/src']})
    with pytest.raises(RuntimeError, match='duplicate type'):
        _build(root, entry)


def test_a_reveal_side_loss_is_measured_and_fails_the_gate(python_corpus, monkeypatch):
    # Negative control: the comparison is not vacuous. Drop every edge reveal resolves from
    # pkg/b.py and the gate must see the miss; drop all of them and it must refuse a zero.
    root, entry = python_corpus
    baseline = gate.measure(entry, root)
    real = DependsAdapter._resolve_statement_edges

    def lossy(self, stmt, file_path, *args, **kwargs):
        return None if file_path.name == 'b.py' else real(self, stmt, file_path, *args, **kwargs)

    monkeypatch.setattr(DependsAdapter, '_resolve_statement_edges', lossy)
    measured = gate.measure(entry, root)
    assert measured['recall'] == 0.75
    assert measured['differences'] == [{'target': 'pkg/a.py', 'missed': ['pkg/b.py'], 'extra': []}]
    assert gate.regressions({'py': measured}, {'py': baseline}) == ['py: recall dropped 100.000000% -> 75.000000%']
    monkeypatch.setattr(DependsAdapter, '_resolve_statement_edges', lambda *args, **kwargs: None)
    with pytest.raises(RuntimeError, match='zero oracle edges'):
        gate.measure(entry, root)


def test_the_gate_scores_what_depends_renders_not_the_private_graph(python_corpus, monkeypatch):
    # BACK-2062: the gate once read adapter._graph.reverse_deps, so it stayed green while the
    # rendered answer lost a dependent. Drop pkg/b.py from the rendered summary only; the graph keeps it.
    root, entry = python_corpus
    real = DependsAdapter._format_directory_summary

    def render_without_b(self, directory, top_n, fmt):
        result = real(self, directory, top_n, fmt)
        for module in result['modules']:
            module['dependents'] = [d for d in module['dependents'] if d != 'pkg/b.py']
            module['dependent_count'] = len(module['dependents'])
        return result

    monkeypatch.setattr(DependsAdapter, '_format_directory_summary', render_without_b)
    measured = gate.measure(entry, root)
    assert measured['recall'] == 0.75
    assert measured['differences'] == [{'target': 'pkg/a.py', 'missed': ['pkg/b.py'], 'extra': []}]


def test_a_truncated_rendered_summary_is_a_failure_not_a_smaller_answer(python_corpus, monkeypatch):
    # The rendered module list may be cut (?top=N); the gate must see total_modules > len(modules) and refuse.
    root, entry = python_corpus
    real = DependsAdapter._format_directory_summary

    def cut(self, directory, top_n, fmt):
        result = real(self, directory, top_n, fmt)
        result['modules'] = result['modules'][:1]  # total_modules still says what the full answer held
        return result

    monkeypatch.setattr(DependsAdapter, '_format_directory_summary', cut)
    with pytest.raises(RuntimeError, match='truncated'):
        gate.measure(entry, root)


def test_the_per_file_form_scores_the_rendered_package_view_and_refuses_a_cut(python_corpus, monkeypatch):
    # Go's answer is the per-file form of depends://, so that helper is gated the same way.
    root, entry = python_corpus
    scan = root.resolve()
    assert gate.rendered_dependents(scan, scan / 'pkg/a.py')['importers'] == {scan / 'pkg/b.py'}
    real = DependsAdapter._format_file_dependents

    def cut(self, target, top_n=None):
        result = real(self, target, top_n=top_n)
        result['dependents'] = []  # count still says what the full answer held
        return result

    monkeypatch.setattr(DependsAdapter, '_format_file_dependents', cut)
    with pytest.raises(RuntimeError, match='truncated'):
        gate.rendered_dependents(scan, scan / 'pkg/a.py')


def test_the_gate_scores_one_stated_rule_and_refuses_another(python_corpus, monkeypatch):
    # BACK-2062: the oracles' truth is every edge, function-level included, tests included,
    # TYPE_CHECKING excluded. The gate records the rule depends:// printed and refuses an answer
    # computed under any other rule, instead of scoring it against the wrong truth.
    root, entry = python_corpus
    measured = gate.measure(entry, root)
    assert measured['edge_rule']['lazy'] == 'include' and measured['edge_rule']['tests'] == 'included'
    real = DependsAdapter._edge_rule

    def load_time_only(self):
        return {**real(self), 'lazy': 'exclude'}

    monkeypatch.setattr(DependsAdapter, '_edge_rule', load_time_only)
    with pytest.raises(RuntimeError, match="rule lazy='exclude'"):
        gate.measure(entry, root)


def test_the_report_names_each_combination_it_declines(tmp_path, monkeypatch):
    # Every other parameter combination is listed with its reason, never left as 'runs, unmeasured'.
    monkeypatch.setattr(gate, '_selected', lambda manifest, wanted, signal='imports': ([], []))
    output = tmp_path / 'report.json'
    gate.main(['--corpus-root', str(tmp_path), '--output', str(output), '--baseline', str(tmp_path / 'none')])
    report = json.loads(output.read_text(encoding='utf-8'))
    declined = {row['combination']: row['reason'] for row in report['declined']}
    assert set(declined) == {'lazy=exclude', 'lazy=only', 'tests=exclude'}
    assert all(declined.values())
    assert report['scored'] == {'lazy': 'include', 'tests': 'included', 'type_checking': 'excluded'}


def test_unknown_oracle_and_escaping_scan_root_fail(python_corpus):
    root, entry = python_corpus
    with pytest.raises(RuntimeError, match="Unknown recall oracle 'nope'"):
        gate.measure({**entry, 'recall': {**entry['recall'], 'oracle': 'nope'}}, root)
    with pytest.raises(RuntimeError, match='scan_root'):
        gate.measure({**entry, 'recall': {**entry['recall'], 'scan_root': '..'}}, root)


@needs_gcc
def test_population_and_metric_regressions_bite(corpus):
    root, entry = corpus
    baseline = gate.measure(entry, root)
    assert not gate.regressions({'c': baseline}, {'c': baseline})
    for field, value in [('recall', 0), ('precision', 0), ('targets', 0), ('sha', 'wrong'), ('oracle', 'gcc-cpp')]:
        assert gate.regressions({'c': {**baseline, field: value}}, {'c': baseline})
    assert gate.regressions({}, {'c': baseline})
    assert gate.regressions({'c': baseline}, {}) == ['c: baseline missing; review required']
    assert gate.regressions({}, {}) == ['Baseline is empty; measurement unavailable']
    assert gate.regressions({'c': baseline, 'other': baseline}, {'c': baseline})


def test_missing_pin_empty_oracle_and_zero_hits_fail(corpus, monkeypatch):
    root, entry = corpus
    with pytest.raises(RuntimeError, match='pin mismatch'):
        gate.measure({**entry, 'sha': 'wrong'}, root)
    fake = oracles.Oracle(oracles.C_SUFFIXES, lambda scope: ({}, {'files': 0}))
    monkeypatch.setitem(gate.ORACLES, 'gcc-c', fake)
    with pytest.raises(RuntimeError, match='zero rows'):
        gate.measure(entry, root)
    fake = oracles.Oracle(oracles.C_SUFFIXES, lambda scope: ({'src/target.h': ['src/nonexistent.c']},
                                                             {'files': 3, 'directives': 1}))
    monkeypatch.setitem(gate.ORACLES, 'gcc-c', fake)
    with pytest.raises(RuntimeError, match='zero oracle edges'):
        gate.measure(entry, root)


def test_gcc_unavailable_is_not_an_empty_oracle(corpus, monkeypatch):
    root, entry = corpus
    monkeypatch.setattr(oracles.shutil, 'which', lambda name: None)
    with pytest.raises(RuntimeError, match='prerequisite unavailable'):
        _build(root, entry)


def test_unqualified_windows_probe_is_not_an_empty_oracle(corpus, monkeypatch):
    root, entry = corpus
    monkeypatch.setattr(oracles.sys, 'platform', 'win32')
    with pytest.raises(RuntimeError, match='Windows probe not qualified'):
        _build(root, entry)


def test_missing_baseline_leaves_a_failure_report(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, 'measure', lambda *args: {'recall': 1, 'precision': 1, 'hit_edges': 1,
                                                        'oracle_edges': 1})
    output = tmp_path / 'report.json'
    assert gate.main(['--corpus-root', str(tmp_path), '--output', str(output),
                      '--baseline', str(tmp_path / 'missing')]) == 1
    report = json.loads(output.read_text(encoding='utf-8'))
    assert report['failures'] and report['measured_at']


def test_a_partial_run_compares_only_its_corpora_and_rejects_unknown_ids(tmp_path, monkeypatch):
    manifest = tmp_path / 'manifest.yaml'
    manifest.write_text('corpora:\n'
                        '  - {id: one, language: c, recall: {oracle: gcc-c}}\n'
                        '  - {id: two, language: c, recall: {oracle: gcc-c}}\n'
                        '  - {language: go}\n', encoding='utf-8')
    row = {'oracle': 'gcc-c', 'sha': 's', 'targets': 1, 'oracle_edges': 1, 'hit_edges': 1, 'coverage': {},
           'recall': 1, 'precision': 1}
    baseline = tmp_path / 'baseline.json'
    baseline.write_text(json.dumps({'one': row, 'two': row}), encoding='utf-8')
    monkeypatch.setattr(gate, 'MANIFEST', manifest)
    measured = []
    monkeypatch.setattr(gate, 'measure', lambda entry, root: measured.append(entry['id']) or row)
    args = ['--corpus-root', str(tmp_path), '--output', str(tmp_path / 'r.json'), '--baseline', str(baseline)]
    assert gate.main([*args, '--corpus', 'two']) == 0 and measured == ['two']
    assert gate.main([*args, '--corpus', 'go']) == 1
    assert 'go: no recall entry' in json.loads((tmp_path / 'r.json').read_text(encoding='utf-8'))['failures'][0]
    measured.clear()
    assert gate.main(args) == 0 and measured == ['one', 'two']
    assert gate.main([*args, '--corpus', 'one', '--write-baseline']) == 0
    assert set(json.loads(baseline.read_text(encoding='utf-8'))) == {'one', 'two'}  # merged, not replaced


@pytest.mark.skipif(sys.platform == 'win32',
                    reason='the GCC oracle refuses before probing on Windows (BACK-1674)')
def test_slow_probe_gets_the_larger_budget_and_a_timeout_is_a_disclosed_failure(corpus, monkeypatch):
    # BACK-1678: a cold macOS runner blew the old 15 s budget on a one-line probe. The budget is now
    # a named 60 s constant, and a probe that still times out is a named measurement failure, not a
    # raw TimeoutExpired and never an empty/"unresolved" oracle row.
    root, entry = corpus
    seen = []

    def hang(cmd, **kwargs):
        seen.append(kwargs.get('timeout'))
        raise subprocess.TimeoutExpired(cmd, kwargs.get('timeout'))

    monkeypatch.setattr(oracles.shutil, 'which', lambda name: '/usr/bin/gcc')
    real_run = subprocess.run
    monkeypatch.setattr(oracles.subprocess, 'run', lambda cmd, **kw: hang(cmd, **kw) if cmd[0] == 'gcc'
                        else real_run(cmd, **kw))
    with pytest.raises(RuntimeError, match=r'timed out after 60s.*target\.h'):
        _build(root, entry)
    assert seen == [oracles.ORACLE_PROBE_TIMEOUT] and oracles.ORACLE_PROBE_TIMEOUT >= 60


@needs_gcc
def test_a_fast_probe_is_unaffected_by_the_timeout_handling(corpus):
    root, entry = corpus
    oracle, _ = _build(root, entry)
    assert oracle == {'src/target.h': ['src/clean.c', 'src/partial.c']}


def _ts_config(**extra):
    return {'oracle': 'typescript-compiler', 'importer_dirs': ['src'],
            'exclude_importer_suffixes': ['.d.ts', '.d.mts', '.d.cts'],
            'typescript_version': '5.9.3', 'node_version': '22.14.0', 'tsconfig': 'tsconfig.json', **extra}


@pytest.fixture
def compiler_oracle():
    import os
    if not shutil.which('node'):
        pytest.skip('optional Node/TypeScript compiler oracle not installed')
    module = os.environ.get('REVEAL_TS_ORACLE_MODULE', str(SCRIPTS / 'oracles/node_modules/typescript'))
    probe = subprocess.run(['node', '-e', 'console.log(require(process.argv[1]).version)', module],
                           capture_output=True, text=True, encoding='utf-8', timeout=120)
    if probe.returncode:
        pytest.skip('optional TypeScript oracle dependency not installed')
    assert probe.stdout.strip() == '5.9.3'
    return module


@pytest.fixture
def typescript_corpus(tmp_path, compiler_oracle):
    return _repo(tmp_path, {
        'package.json': '{"name":"oracle-fixture","private":true}',
        'tsconfig.json': '{"compilerOptions":{"baseUrl":".","paths":{"@lib/*":["src/lib/*"]},"allowJs":true,"module":"esnext","moduleResolution":"bundler","jsx":"react-jsx"}}',
        'src/lib/value.ts': 'export const value = 1;\n',
        'src/lib/index.ts': 'export { value } from "./value";\n',
        'src/use.tsx': 'import { value } from "@lib/value";\nexport const View = () => <div>{value}</div>;\n',
        'src/use.js': 'export { value } from "./lib";\n',
        'src/dynamic.ts': 'const mod = import("./lib/value");\n',
        'src/types.ts': 'export type T = typeof import("@lib/value");\n',
        'src/decl.d.ts': 'import { value } from "./lib/value";\n',
    }, _ts_config())


def test_compiler_oracle_resolves_aliases_barrels_dynamic_and_js(typescript_corpus):
    root, entry = typescript_corpus
    edges, coverage = _build(root, entry)
    assert edges == {'src/lib/index.ts': ['src/use.js'],
                     'src/lib/value.ts': ['src/dynamic.ts', 'src/lib/index.ts', 'src/types.ts', 'src/use.tsx']}
    assert coverage['files'] == 6 and coverage['declaration_files_skipped'] == 1
    assert coverage['typescript_version'] == '5.9.3' and coverage['population_digest']
    measured = gate.measure(entry, root)
    assert measured['recall'] == measured['precision'] == 1


def test_compiler_oracle_lost_edge_fails_the_existing_gate(typescript_corpus, monkeypatch):
    root, entry = typescript_corpus
    baseline = gate.measure(entry, root)
    real = DependsAdapter._resolve_statement_edges
    def lossy(self, stmt, file_path, *args, **kwargs):
        return None if file_path.name == 'use.tsx' else real(self, stmt, file_path, *args, **kwargs)
    monkeypatch.setattr(DependsAdapter, '_resolve_statement_edges', lossy)
    current = gate.measure(entry, root)
    assert current['recall'] == .8
    assert gate.regressions({'ts': current}, {'ts': baseline}) == ['ts: recall dropped 100.000000% -> 80.000000%']


def test_compiler_oracle_wrong_toolchain_and_zero_population_fail(typescript_corpus):
    root, entry = typescript_corpus
    with pytest.raises(RuntimeError, match='toolchain mismatch'):
        _build(root, {'recall': {**entry['recall'], 'typescript_version': '0.0.0'}})
    with pytest.raises(RuntimeError, match='zero rows'):
        gate.measure({**entry, 'recall': {**entry['recall'], 'importer_dirs': ['absent']}}, root)


def test_compiler_oracle_missing_node_is_a_failure(python_corpus, monkeypatch):
    root, _ = python_corpus
    monkeypatch.setattr(oracles.shutil, 'which', lambda name: None)
    with pytest.raises(RuntimeError, match='prerequisite unavailable'):
        oracles.build_typescript_oracle(oracles.Scope(root, root, [], _ts_config()))


def _pinned_go_available():
    if not shutil.which('go'):
        return False
    try:
        result = subprocess.run(['go', 'version'], capture_output=True, text=True,
                                encoding='utf-8', check=True, timeout=30)
        return result.stdout.split()[2] == 'go1.21.5'
    except (OSError, subprocess.SubprocessError, IndexError):
        return False


needs_go = pytest.mark.skipif(not _pinned_go_available(),
                             reason='optional Go 1.21.5 oracle toolchain unavailable')


@pytest.fixture
def go_corpus(tmp_path):
    return _repo(tmp_path, {
        'go.mod': 'module example.org/project\n\ngo 1.20\n',
        'target/target.go': 'package target\nfunc Run() {}\n',
        'use/use.go': 'package use\nimport alias "example.org/project/target"\nfunc Run() { alias.Run() }\n',
        'use/strings.go': 'package use\n// import "example.org/project/target"\nvar Text = `import "example.org/project/target"`\n',
    }, {'oracle': 'go-toolchain', 'importer_dirs': ['.'], 'go_version': 'go1.21.5'})


@needs_go
def test_go_native_parser_and_public_package_projection(go_corpus):
    root, entry = go_corpus
    edges, coverage = _build(root, entry)
    assert edges == {'target/target.go': ['use/use.go']}
    assert coverage['files'] == 3 and coverage['resolved_statements'] == 1
    measured = gate.measure(entry, root)
    assert measured['recall'] == measured['precision'] == 1


@needs_go
def test_go_lost_edge_fails_the_existing_gate(go_corpus, monkeypatch):
    root, entry = go_corpus
    before = gate.measure(entry, root)
    original = DependsAdapter._format_file_dependents
    def drop(self, target, **kwargs):
        answer = original(self, target, **kwargs)
        answer['dependents'] = []
        return answer
    monkeypatch.setattr(DependsAdapter, '_format_file_dependents', drop)
    with pytest.raises(RuntimeError, match='zero oracle edges'):
        gate.measure(entry, root)
    assert gate.regressions({'go': {**before, 'recall': 0.5}}, {'go': before})


@needs_go
def test_go_wrong_toolchain_is_unavailable(go_corpus):
    root, entry = go_corpus
    entry['recall']['go_version'] = 'go0.0.0'
    with pytest.raises(RuntimeError, match='requires go0.0.0'):
        _build(root, entry)


def test_python_call_oracle_handles_aliases_nested_scopes_and_negative_text(tmp_path):
    root, entry = _repo(tmp_path, {
        'pkg/a.py': 'from elsewhere import target as alias\ndef outer():\n alias()\n def inner():\n  helper()\n return inner\nclass API:\n def method(self):\n  self.target()\nTEXT = "target()"\n# target()\n',
    }, {})
    scope = oracles.Scope(root, root, [root / 'pkg/a.py'], {})
    edges, coverage = oracles.build_python_calls_oracle(scope)
    assert edges == {'target': ['pkg/a.py::method', 'pkg/a.py::outer'], 'helper': ['pkg/a.py::inner']}
    assert coverage['functions'] == 3


def test_python_call_loss_and_bad_population_fail(tmp_path, monkeypatch):
    root, entry = _repo(tmp_path, {
        'pkg/a.py': 'def caller():\n target()\n helper()\n',
        'pkg/b.py': 'def target(): pass\ndef helper(): pass\n',
    }, {})
    entry['call_recall'] = {'scan_root': 'pkg', 'importer_dirs': ['pkg']}
    before = gate.measure_calls(entry, root)
    assert before['recall'] == before['precision'] == 1
    from reveal.adapters.calls import adapter
    original = adapter.find_callers
    monkeypatch.setattr(adapter, 'find_callers', lambda path, target, **kw: (
        {**original(path, target, **kw), 'levels': [], 'total_callers': 0} if target == 'target'
        else original(path, target, **kw)))
    after = gate.measure_calls(entry, root)
    assert after['recall'] == 0.5 and gate.regressions({'calls': after}, {'calls': before})
    (root / 'pkg/a.py').write_text('def broken(:\n', encoding='utf-8')
    with pytest.raises(SyntaxError):
        gate.measure_calls(entry, root)


def _call_corpus(tmp_path):
    root, entry = _repo(tmp_path, {
        'pkg/a.py': 'def caller():\n target()\n helper()\n',
        'pkg/b.py': 'def target(): pass\ndef helper(): pass\ndef other():\n target()\n',
    }, {})
    entry['call_recall'] = {'scan_root': 'pkg', 'importer_dirs': ['pkg']}
    return root, entry


def test_the_calls_gate_scores_what_calls_renders_not_the_index(tmp_path, monkeypatch):
    # BACK-2062: measure_calls read find_callers directly, so a caller lost between the index and the
    # rendered calls:// answer stayed green. Drop pkg/b.py::other from the adapter's answer only.
    root, entry = _call_corpus(tmp_path)
    assert gate.measure_calls(entry, root)['recall'] == 1
    from reveal.adapters.calls.adapter import CallsAdapter
    real = CallsAdapter._callers

    def without_other(self, name, query_format):
        result = real(self, name, query_format)
        for level in result['levels']:
            level['callers'] = [row for row in level['callers'] if row['caller'] != 'other']
        result['total_callers'] = sum(len(level['callers']) for level in result['levels'])
        return result

    monkeypatch.setattr(CallsAdapter, '_callers', without_other)
    measured = gate.measure_calls(entry, root)
    assert measured['differences'] == [{'target': 'target', 'missed': ['pkg/b.py::other'], 'extra': []}]
    assert measured['recall'] == 2 / 3


def test_a_cut_calls_answer_is_a_failure_not_a_smaller_answer(tmp_path, monkeypatch):
    root, entry = _call_corpus(tmp_path)
    from reveal.adapters.calls.adapter import CallsAdapter
    real = CallsAdapter._callers

    def cut(self, name, query_format):
        result = real(self, name, query_format)
        for level in result['levels']:
            level['callers'] = level['callers'][:1]  # total_callers still says what the full answer held
        return result

    monkeypatch.setattr(CallsAdapter, '_callers', cut)
    with pytest.raises(RuntimeError, match='truncated'):
        gate.measure_calls(entry, root)


def test_swapped_extra_and_improvement_require_reviewed_baseline():
    baseline = {'oracle': 'fixture', 'sha': 'pin', 'targets': 1, 'oracle_edges': 2,
                'coverage': {}, 'extra_edges': 1, 'recall': 1, 'precision': 2 / 3,
                'differences': [{'target': 'target.py', 'missed': [], 'extra': ['a.py']}]}
    swapped = {**baseline, 'differences': [{'target': 'target.py', 'extra': ['b.py']}]}
    assert 'extra-edge population changed' in gate.regressions({'x': swapped}, {'x': baseline})[0]
    improved = {**baseline, 'extra_edges': 0, 'precision': 1, 'differences': []}
    assert gate.regressions({'x': improved}, {'x': baseline})
    assert not gate.regressions({'x': improved}, {'x': improved})
    assert gate.regressions({'x': baseline}, {'x': improved})


# --- Oracle independence (BACK-1840 F9): the oracles must not depend on the resolver they measure. ---

REVEAL_NAMES = {'reveal', 'reveal-cli', 'reveal_cli'}  # the package, its PyPI name, and its module spelling
_QUOTED = r'''(['"`])([^'"`\n]+)\1'''
_COMMENTS = re.compile(r'/\*.*?\*/|(?:^|(?<=\s))//[^\n]*', re.S)
_JS_IMPORTS = [re.compile(r'\brequire\s*\(\s*' + _QUOTED), re.compile(r'\bimport\s*\(\s*' + _QUOTED),
               re.compile(r'\bimport\s+(?:[^\'"`;()]*?\bfrom\s+)?' + _QUOTED)]
_GO_IMPORT_BLOCK = re.compile(r'^\s*import\s*\((.*?)^\s*\)', re.S | re.M)
_GO_IMPORT_LINE = re.compile(r'^\s*import\s+(?:[\w.]+\s+)?"([^"\n]+)"', re.M)
_GO_IMPORT_SPEC = re.compile(r'^\s*(?:[\w.]+\s+)?"([^"\n]+)"', re.M)
_SHELL_JS = re.compile(r'''\b(?:spawn|spawnSync|execFile|execFileSync|fork)\s*\(\s*(['"`])reveal\1'''
                       r'''|\bexec(?:Sync)?\s*\(\s*['"`]reveal\b|['"`]-m['"`]\s*,\s*['"`]reveal['"`]''')
_SHELL_GO = re.compile(r'\bexec\.Command(?:Context)?\(\s*(?:\w+\s*,\s*)?"reveal"|"-m"\s*,\s*"reveal"')
_PY_PROCESS_CALLS = {'run', 'Popen', 'call', 'check_call', 'check_output', 'system', 'popen', 'spawnlp', 'spawnvp',
                     'execlp', 'execvp', 'import_module', '__import__'}


def _mentions_reveal_command(node: ast.AST) -> bool:
    """A string under a process/import call that is or starts with a reveal invocation, or a '-m', 'reveal' pair."""
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            words = child.value.split()
            if words and words[0] in REVEAL_NAMES:
                return True
        if isinstance(child, (ast.List, ast.Tuple)):
            values = [e.value for e in child.elts if isinstance(e, ast.Constant)]
            if any(a == '-m' and b in REVEAL_NAMES for a, b in zip(values, values[1:])):
                return True
    return False


def oracle_imports(source: str, language: str) -> list[str]:
    """Names the oracle source imports, in the forms the predicate recognises."""
    names: list[str] = []
    if language == 'python':
        tree = ast.parse(source)
        names += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
        names += [node.module or '' for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    elif language == 'js':
        code = _COMMENTS.sub(' ', source)
        names += [m.group(2) for pattern in _JS_IMPORTS for m in pattern.finditer(code)]
    elif language == 'go':
        code = _COMMENTS.sub(' ', source)
        for block in _GO_IMPORT_BLOCK.findall(code):
            names += _GO_IMPORT_SPEC.findall(block)
        names += _GO_IMPORT_LINE.findall(code)
    return names


def _names_reveal(name: str) -> bool:
    """Any path or dotted segment spelled like Reveal; `revealjs` is a different package."""
    return any(part.lower() in REVEAL_NAMES for part in re.split(r'[/.]', name))


def shells_out_to_reveal(source: str, language: str) -> bool:
    if language == 'python':
        return any(isinstance(node, ast.Call) and _mentions_reveal_command(node)
                   and getattr(node.func, 'attr', getattr(node.func, 'id', '')) in _PY_PROCESS_CALLS
                   for node in ast.walk(ast.parse(source)))
    pattern = _SHELL_JS if language == 'js' else _SHELL_GO
    return bool(pattern.search(_COMMENTS.sub(' ', source)))


def depends_on_reveal(source: str, language: str) -> bool:
    """True when the oracle imports Reveal (any spelling) or runs it as a subprocess."""
    return (any(_names_reveal(name) for name in oracle_imports(source, language))
            or shells_out_to_reveal(source, language))


ORACLE_PLANTS = [
    # (id, language, source, must_catch)
    ('js-require', 'js', "const r = require('reveal');", True),
    ('js-require-relative', 'js', "const r = require('../reveal/x');", True),
    ('js-require-template', 'js', "const r = require(`reveal`);", True),
    ('js-require-pypi-name', 'js', "require('reveal-cli');", True),
    ('js-dynamic-import', 'js', "import('reveal');", True),
    ('js-spawnsync-python-m', 'js', "require('child_process').spawnSync('python', ['-m', 'reveal']);", True),
    ('js-spawn-reveal', 'js', "const { spawn } = require('child_process');\nspawn('reveal', ['depends://x']);", True),
    ('js-execfile-reveal', 'js', "execFile('reveal', ['x'], cb);", True),
    ('go-grouped', 'go', 'import (\n\t"os"\n\t"example.org/reveal"\n)\n', True),
    ('go-grouped-alias', 'go', 'import (\n\t"os"\n\tr "example.org/reveal/core"\n)\n', True),
    ('go-single-line', 'go', 'import "example.org/reveal"\nimport (\n\t"os"\n)\n', True),
    ('go-single-line-alias', 'go', 'import r "example.org/reveal"\n', True),
    ('go-exec-command', 'go', 'import (\n\t"os/exec"\n)\nfunc f() { exec.Command("reveal", "depends://x").Run() }\n', True),
    ('go-exec-python-m', 'go', 'func f() { exec.Command("python", "-m", "reveal").Run() }\n', True),
    ('py-import', 'python', 'import reveal.adapters\n', True),
    ('py-from-import', 'python', 'from reveal.adapters import depends\n', True),
    ('py-subprocess-run', 'python', "import subprocess\nsubprocess.run(['reveal', 'depends://x'])\n", True),
    ('py-subprocess-python-m', 'python', "import subprocess, sys\nsubprocess.run([sys.executable, '-m', 'reveal', 'x'])\n", True),
    ('py-subprocess-shell-string', 'python', "import subprocess\nsubprocess.check_output('reveal depends://x', shell=True)\n", True),
    # Negative controls: none of these depends on Reveal.
    ('js-comment-mentions-reveal', 'js', "// reveal is the resolver we measure; never require('reveal') here\nconst fs = require('fs');", False),
    ('js-unrelated-revealjs', 'js', "const r = require('revealjs');", False),
    ('js-string-mentions-reveal', 'js', "const fs = require('fs');\nconsole.log('reveal says hi');", False),
    ('go-comment-mentions-reveal', 'go', 'import (\n\t"os"\n)\n// reveal is the resolver we measure\n', False),
    ('go-unrelated-revealjs', 'go', 'import "example.org/revealjs"\n', False),
    ('go-exec-other-command', 'go', 'func f() { exec.Command("go", "list").Run() }\n', False),
    ('py-comment-mentions-reveal', 'python', "import os\n# reveal is the resolver we measure\n", False),
    ('py-unrelated-revealjs', 'python', 'import revealjs\n', False),
    ('py-subprocess-other', 'python', "import subprocess\nsubprocess.run(['go', 'list'])\n", False),
]


@pytest.mark.parametrize('language,source,must_catch',
                         [pytest.param(lang, src, catch, id=name) for name, lang, src, catch in ORACLE_PLANTS])
def test_oracle_independence_predicate_on_planted_snippets(language, source, must_catch):
    assert depends_on_reveal(source, language) is must_catch


@pytest.mark.parametrize('language,path', [
    ('python', 'recall_oracles.py'), ('js', 'ts_import_oracle.cjs'), ('go', 'oracles/go_import_oracle.go'),
])
def test_oracles_never_depend_on_reveal(language, path):
    # The oracle must stay independent of the resolver it measures, or a shared bug scores 100%.
    source = (SCRIPTS / path).read_text(encoding='utf-8')
    # Positive control per file: a file whose imports all go unrecognised must fail, not borrow another's.
    assert oracle_imports(source, language), f'{path}: the predicate recognised no import'
    assert not depends_on_reveal(source, language)


# --- partial_files is gated (BACK-1840 F10): more partially parsed files is a regression, fewer is not. ---

def _committed_baseline() -> dict:
    return json.loads((Path(__file__).resolve().parent / 'corpus' / 'recall_baseline.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('key,raised', [('c', 310), ('go-client_golang', 5)])
def test_more_partial_files_than_baseline_is_a_regression(key, raised):
    baseline = _committed_baseline()
    assert baseline[key]['partial_files'] < raised  # perturbation really is an increase
    current = json.loads(json.dumps(baseline))
    assert gate.regressions(current, baseline) == []  # unperturbed control: the committed baseline passes
    current[key]['partial_files'] = raised
    failures = gate.regressions(current, baseline)
    assert any(f.startswith(f'{key}: partial_files') for f in failures), failures


@pytest.mark.parametrize('key,lowered', [('c', 0), ('c-curl', 217)])
def test_fewer_partial_files_than_baseline_is_not_a_regression(key, lowered):
    baseline = _committed_baseline()
    assert lowered < baseline[key]['partial_files']
    current = json.loads(json.dumps(baseline))
    current[key]['partial_files'] = lowered
    assert gate.regressions(current, baseline) == []


def test_missing_partial_files_is_disclosed_not_failed_or_crashed():
    baseline = _committed_baseline()
    old_baseline = json.loads(json.dumps(baseline))
    del old_baseline['c']['partial_files']  # a baseline written before the field existed
    current = json.loads(json.dumps(baseline))
    notes: list[str] = []
    assert gate.regressions(current, old_baseline, notes) == []
    assert notes == ['c: partial_files not compared (baseline has no partial_files)']
    lost = json.loads(json.dumps(baseline))
    del lost['c-curl']['partial_files']
    notes = []
    assert gate.regressions(lost, baseline, notes) == []
    assert notes == ['c-curl: partial_files not compared (measurement has no partial_files)']
    # Calls measurements never carry the field: nothing to compare, nothing to disclose.
    notes = []
    calls = {'calls': {k: v for k, v in baseline['c'].items() if k != 'partial_files'}}
    assert gate.regressions(calls, calls, notes) == [] and notes == []
