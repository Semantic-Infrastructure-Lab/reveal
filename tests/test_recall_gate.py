"""Recall-gate controls use a tiny real git corpus and independent GCC oracle."""
import importlib.util
import subprocess
import shutil
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.component
SCRIPT = Path(__file__).resolve().parent.parent / 'scripts/recall_gate.py'
spec = importlib.util.spec_from_file_location('recall_gate', SCRIPT)
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)


@pytest.fixture
def corpus(tmp_path):
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src/target.h').write_text('int probe(void);\n', encoding='utf-8')
    (tmp_path / 'src/clean.c').write_text('#include "target.h"\nint probe(void) { return 1; }\n', encoding='utf-8')
    (tmp_path / 'src/partial.c').write_text('#include "target.h"\nint broken( {{{\n', encoding='utf-8')
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                    'commit', '-qm', 'fixture'], check=True)
    sha = subprocess.run(['git', '-C', str(tmp_path), 'rev-parse', 'HEAD'], check=True,
                         capture_output=True, text=True, encoding='utf-8').stdout.strip()
    return tmp_path, {'sha': sha, 'recall': {'importer_dirs': ['src'], 'include_dirs': ['src']}}


@pytest.mark.skipif(sys.platform == 'win32' or not shutil.which('gcc'),
                    reason='optional GCC oracle requires a qualified POSIX compiler host')
def test_independent_oracle_sees_partial_source_and_measurement(corpus):
    root, entry = corpus
    oracle, coverage = gate.build_c_oracle(root, entry['recall'])
    assert oracle == {'src/target.h': ['src/clean.c', 'src/partial.c']}
    assert coverage['files'] == 3 and coverage['directives'] == 2
    measured = gate.measure(entry, root)
    assert measured['hit_edges'] == 2 and measured['recall'] == measured['precision'] == 1
    assert measured['partial_files'] == 1


@pytest.mark.skipif(sys.platform == 'win32' or not shutil.which('gcc'),
                    reason='optional GCC oracle requires a qualified POSIX compiler host')
def test_population_and_metric_regressions_bite(corpus):
    root, entry = corpus
    baseline = gate.measure(entry, root)
    assert not gate.regressions({'c': baseline}, {'c': baseline})
    for field, value in [('recall', 0), ('precision', 0), ('targets', 0), ('sha', 'wrong')]:
        assert gate.regressions({'c': {**baseline, field: value}}, {'c': baseline})
    assert gate.regressions({}, {'c': baseline})
    assert gate.regressions({'c': baseline}, {})
    assert gate.regressions({'c': baseline, 'other': baseline}, {'c': baseline})


def test_missing_pin_empty_oracle_and_zero_hits_fail(corpus, monkeypatch):
    root, entry = corpus
    with pytest.raises(RuntimeError, match='pin mismatch'):
        gate.measure({**entry, 'sha': 'wrong'}, root)
    monkeypatch.setattr(gate, 'build_c_oracle', lambda *args: ({}, {'files': 0}))
    with pytest.raises(RuntimeError, match='zero rows'):
        gate.measure(entry, root)
    monkeypatch.setattr(gate, 'build_c_oracle', lambda *args: ({'src/target.h': ['src/nonexistent.c']},
                                                             {'files': 3, 'directives': 1}))
    with pytest.raises(RuntimeError, match='zero oracle edges'):
        gate.measure(entry, root)


def test_gcc_unavailable_is_not_an_empty_oracle(corpus, monkeypatch):
    root, entry = corpus
    monkeypatch.setattr(gate.shutil, 'which', lambda name: None)
    with pytest.raises(RuntimeError, match='prerequisite unavailable'):
        gate.build_c_oracle(root, entry['recall'])


def test_unqualified_windows_probe_is_not_an_empty_oracle(corpus, monkeypatch):
    root, entry = corpus
    monkeypatch.setattr(gate.sys, 'platform', 'win32')
    with pytest.raises(RuntimeError, match='Windows probe not qualified'):
        gate.build_c_oracle(root, entry['recall'])


def test_missing_baseline_leaves_a_failure_report(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, 'measure', lambda *args: {'recall': 1, 'precision': 1})
    output = tmp_path / 'report.json'
    assert gate.main(['--corpus-root', str(tmp_path), '--output', str(output),
                      '--baseline', str(tmp_path / 'missing')]) == 1
    import json
    report = json.loads(output.read_text(encoding='utf-8'))
    assert report['failures'] and report['measured_at']


@pytest.mark.skipif(sys.platform == 'win32',
                    reason='build_c_oracle refuses before probing on Windows (BACK-1674)')
def test_slow_probe_gets_the_larger_budget_and_a_timeout_is_a_disclosed_failure(corpus, monkeypatch):
    # BACK-1678: a cold macOS runner blew the old 15 s budget on a one-line probe. The budget is now
    # a named 60 s constant, and a probe that still times out is a named measurement failure, not a
    # raw TimeoutExpired and never an empty/"unresolved" oracle row.
    root, entry = corpus
    seen = []

    def hang(cmd, **kwargs):
        seen.append(kwargs.get('timeout'))
        raise subprocess.TimeoutExpired(cmd, kwargs.get('timeout'))

    monkeypatch.setattr(gate.shutil, 'which', lambda name: '/usr/bin/gcc')
    real_run = subprocess.run
    monkeypatch.setattr(gate.subprocess, 'run', lambda cmd, **kw: hang(cmd, **kw) if cmd[0] == 'gcc'
                        else real_run(cmd, **kw))
    with pytest.raises(RuntimeError, match=r'timed out after 60s.*target\.h'):
        gate.build_c_oracle(root, entry['recall'])
    assert seen == [gate.ORACLE_PROBE_TIMEOUT] and gate.ORACLE_PROBE_TIMEOUT >= 60


@pytest.mark.skipif(sys.platform == 'win32' or not shutil.which('gcc'),
                    reason='optional GCC oracle requires a qualified POSIX compiler host')
def test_a_fast_probe_is_unaffected_by_the_timeout_handling(corpus):
    root, entry = corpus
    oracle, _ = gate.build_c_oracle(root, entry['recall'])
    assert oracle == {'src/target.h': ['src/clean.c', 'src/partial.c']}
