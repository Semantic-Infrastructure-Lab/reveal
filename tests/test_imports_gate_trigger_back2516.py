"""A push that moves what counts as an import runs its imports recall gate rows (BACK-2516)."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys

import pytest
import yaml

import test_calls_gate_trigger_back2204 as calls_gate_tests
from test_calls_gate_trigger_back2204 import commit_file, git, run_push_dispatch, shell_only

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / 'scripts' / 'check_imports_gate.py'
repo = calls_gate_tests.repo  # the same throwaway Git checkout fixture
pytestmark = pytest.mark.skipif(shutil.which('git') is None, reason='git required')

MANIFEST = {'corpora': [
    {'language': 'c', 'recall': {'oracle': 'c-include'}},
    {'id': 'go-client_golang', 'language': 'go', 'recall': {'oracle': 'go-list'}},
    {'language': 'javascript', 'recall': {'oracle': 'tsc'}},
    {'language': 'typescript', 'recall': {'oracle': 'tsc'}},
    {'language': 'tsx', 'recall': {'oracle': 'tsc'}},
    {'language': 'scala', 'recall': {'oracle': 'jvm-declared'}},
    {'id': 'scala-cats-effect', 'language': 'scala', 'recall': {'oracle': 'jvm-declared'}},
    {'id': 'python-reveal', 'language': 'python', 'recall': {'oracle': 'python-ast'}},
    {'id': 'python-celery', 'language': 'python', 'call_recall': {'oracle': 'python-ast-callers'}},
    {'id': 'ruby-solidus', 'language': 'ruby'},  # pinned, but no recall oracle
]}
EVERY_ROW = ['c', 'go-client_golang', 'javascript', 'python-reveal', 'scala', 'scala-cats-effect', 'tsx', 'typescript']

# A stand-in for scripts/recall_gate.py: records its argv and exits with $STUB_GATE_EXIT.
STUB_GATE = """import json, os, sys
signal = sys.argv[sys.argv.index('--signal') + 1] if '--signal' in sys.argv else 'imports'
path = os.environ['STUB_GATE_ARGV'] + ('.calls' if signal == 'calls' else '')
with open(path, 'w', encoding='utf-8') as out:
    json.dump(sys.argv[1:], out)
sys.exit(int(os.environ.get('STUB_CALLS_GATE_EXIT' if signal == 'calls' else 'STUB_GATE_EXIT', '0')))
"""


@pytest.fixture
def gate():
    spec = importlib.util.spec_from_file_location('imports_gate_check', HELPER)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(HELPER.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(HELPER.parent))
    return module


@pytest.fixture
def manifested(repo):
    """The repo fixture with a manifest committed as the pushed base."""
    path = repo / 'tests/corpus/manifest.yaml'
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(MANIFEST), encoding='utf-8')
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'manifest')
    git(repo, 'update-ref', 'refs/remotes/origin/master', 'HEAD')
    return repo


def test_unrelated_range_selects_nothing_and_reads_no_manifest(gate, repo):
    commit_file(repo, 'reveal/utils/results.py')
    request = gate.build_request(repo)  # no manifest in this repo: reading one would raise
    assert request['rows'] == [] and request['changed_paths'] == ['reveal/utils/results.py']


@pytest.mark.parametrize('path', [
    'reveal/analyzers/imports/base.py',       # BACK-2497's parse-loss counting change
    'reveal/analyzers/imports/generic.py',    # the JVM and C-family resolver
    'reveal/core/treesitter_parse.py',
    'reveal/treesitter.py',                   # shared with the calls trigger
    'reveal/adapters/imports.py',
    'scripts/recall_oracles.py',
    'tests/corpus/recall_baseline.json',
    'reveal/analyzers/_capability_table.py',  # a shared analyzer helper cannot be narrowed
])
def test_engine_shared_and_gate_inputs_measure_every_row(gate, manifested, path):
    commit_file(manifested, path)
    assert gate.build_request(manifested)['rows'] == EVERY_ROW


@pytest.mark.parametrize('path, rows', [
    ('reveal/analyzers/imports/go.py', ['go-client_golang']),
    ('reveal/analyzers/imports/python.py', ['python-reveal']),
    ('reveal/analyzers/scala.py', ['scala', 'scala-cats-effect']),
    ('reveal/analyzers/_js_function_values.py', ['javascript', 'tsx', 'typescript']),
    ('reveal/analyzers/cpp.py', ['c']),  # c and cpp share one analyzer family; cpp has no row here
])
def test_a_language_file_measures_that_languages_rows(gate, manifested, path, rows):
    commit_file(manifested, path)
    assert gate.build_request(manifested)['rows'] == rows


def test_a_language_without_a_recall_row_is_named_not_measured(gate, manifested):
    commit_file(manifested, 'reveal/analyzers/ruby.py')
    request = gate.build_request(manifested)
    assert request['rows'] == [] and request['no_recall_row'] == ['ruby']


def test_uncommitted_and_earlier_commits_both_count(gate, manifested):
    commit_file(manifested, 'reveal/analyzers/imports/go.py')
    commit_file(manifested, 'README.md', 'later\n')
    (manifested / 'reveal/analyzers/scala.py').write_text('dirty\n', encoding='utf-8')
    assert gate.build_request(manifested)['rows'] == ['go-client_golang', 'scala', 'scala-cats-effect']


def _with_stub_gate(repo):
    (repo / 'scripts').mkdir(exist_ok=True)
    (repo / 'scripts/recall_gate.py').write_text(STUB_GATE, encoding='utf-8')
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'stub gate')
    git(repo, 'update-ref', 'refs/remotes/origin/master', 'HEAD')


def _main(gate, repo, tmp_path, monkeypatch, exit_code=0, *extra):
    argv_file = tmp_path / 'argv.json'
    monkeypatch.setenv('STUB_GATE_ARGV', str(argv_file))
    monkeypatch.setenv('STUB_GATE_EXIT', str(exit_code))
    log = tmp_path / 'imports-gate.jsonl'
    code = gate.main(['--repo', str(repo), '--interpreter', sys.executable, '--corpus-root', str(tmp_path / 'corpora'),
                      '--output', str(tmp_path / 'report.json'), '--log', str(log), *extra])
    records = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()] if log.exists() else []
    argv = json.loads(argv_file.read_text(encoding='utf-8')) if argv_file.exists() else None
    return code, records, argv


def test_selected_rows_are_measured_by_the_gate_script(gate, manifested, tmp_path, monkeypatch):
    _with_stub_gate(manifested)
    commit_file(manifested, 'reveal/analyzers/imports/go.py')
    code, records, argv = _main(gate, manifested, tmp_path, monkeypatch)
    assert code == 0 and argv[argv.index('--corpus') + 1] == 'go-client_golang' and argv.count('--corpus') == 1
    assert argv[argv.index('--corpus-root') + 1] == str(tmp_path / 'corpora')
    assert [r['decision'] for r in records] == ['pass'] and '1 row(s) green' in records[0]['detail']


def test_a_red_row_fails_and_is_logged(gate, manifested, tmp_path, monkeypatch, capsys):
    _with_stub_gate(manifested)
    commit_file(manifested, 'reveal/analyzers/imports/base.py')
    code, records, argv = _main(gate, manifested, tmp_path, monkeypatch, 1)
    assert code == 1 and argv.count('--corpus') == len(EVERY_ROW)
    assert [r['decision'] for r in records] == ['fail'] and 'exited 1' in records[0]['detail']
    assert 'imports gate FAILED' in capsys.readouterr().err


def test_an_unrelated_range_runs_no_measurement(gate, manifested, tmp_path, monkeypatch):
    _with_stub_gate(manifested)
    commit_file(manifested, 'reveal/utils/results.py')
    code, records, argv = _main(gate, manifested, tmp_path, monkeypatch, 1)
    assert code == 0 and argv is None and records[0]['decision'] == 'pass'


def test_a_missing_interpreter_is_a_visible_failure(gate, manifested, tmp_path, monkeypatch):
    _with_stub_gate(manifested)
    commit_file(manifested, 'reveal/analyzers/imports/go.py')
    log = tmp_path / 'log.jsonl'
    code = gate.main(['--repo', str(manifested), '--interpreter', str(tmp_path / 'no-python'), '--log', str(log),
                      '--output', str(tmp_path / 'r.json')])
    assert code == 1 and json.loads(log.read_text(encoding='utf-8'))['decision'] == 'fail'


def test_explicit_skip_persists_its_reason(gate, manifested, tmp_path, monkeypatch):
    commit_file(manifested, 'reveal/analyzers/imports/base.py')
    code, records, argv = _main(gate, manifested, tmp_path, monkeypatch, 1, '--skip-reason', 'reviewed: docs only')
    assert code == 0 and argv is None
    assert records[0]['decision'] == 'skip' and 'reviewed: docs only' in records[0]['detail']


def _dispatch(repo, tmp_path, args, gate_exit='0', changed='reveal/analyzers/imports/go.py', calls_exit='0'):
    """ci-local.sh --push with the suite stubbed, a stub recall gate and this Python as the CI venv."""
    venv = tmp_path / 'venv'
    (venv / 'py3.12/bin').mkdir(parents=True)
    wrapper = venv / 'py3.12/bin/python'  # a symlinked venv interpreter would lose its venv
    wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding='utf-8')
    wrapper.chmod(0o755)
    manifest = repo / 'tests/corpus/manifest.yaml'
    manifest.parent.mkdir(parents=True)
    manifest.write_text(yaml.safe_dump(MANIFEST), encoding='utf-8')
    _with_stub_gate(repo)  # both are gate inputs, so they belong to the pushed base, not the range
    commit_file(repo, changed)
    env = {'REVEAL_CI_VENV_ROOT': str(venv), 'STUB_GATE_ARGV': str(tmp_path / 'argv.json'),
           'STUB_GATE_EXIT': gate_exit, 'STUB_CALLS_GATE_EXIT': calls_exit, 'REVEAL_CORPUS_DIR': str(tmp_path / 'corpora')}
    if '--push' in args:  # extractor paths are calls-gate paths too; that gate is BACK-2204's test
        args = ['--skip-calls-gate', 'imports gate under test', *args]
    result, marker, _ = run_push_dispatch(repo, tmp_path, args, extra_env=env)
    log = tmp_path / 'logs' / 'imports-gate.jsonl'
    records = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()] if log.exists() else []
    return result, marker, records


@shell_only
def test_push_gate_runs_the_touched_rows_after_the_suite(repo, tmp_path):
    result, marker, records = _dispatch(repo, tmp_path, ['--push'])
    assert result.returncode == 0 and marker.exists(), (result.stdout, result.stderr)
    argv = json.loads((tmp_path / 'argv.json').read_text(encoding='utf-8'))
    assert argv.count('--corpus') == 1 and 'go-client_golang' in argv
    assert [r['decision'] for r in records] == ['pass']


@shell_only
def test_push_gate_fails_on_a_red_row(repo, tmp_path):
    result, marker, records = _dispatch(repo, tmp_path, ['--push'], gate_exit='1')
    assert result.returncode == 1 and marker.exists()
    assert 'imports recall gate' in result.stderr and records[0]['decision'] == 'fail'
    assert 'recall_gate.py exited 1' in records[0]['detail']  # the row, not a broken toolchain probe


@shell_only
def test_push_skip_is_logged_and_measures_nothing(repo, tmp_path):
    result, marker, records = _dispatch(repo, tmp_path, ['--push', '--skip-imports-gate', 'pack bump reviewed'],
                                        gate_exit='1')
    assert result.returncode == 0 and marker.exists(), (result.stdout, result.stderr)
    assert not (tmp_path / 'argv.json').exists()
    assert records[0]['decision'] == 'skip' and 'pack bump reviewed' in records[0]['detail']


@shell_only
@pytest.mark.parametrize('args', [
    ['--skip-imports-gate', 'reason'],            # only with --push
    ['--push', '--skip-imports-gate', '   '],     # a reason, not whitespace
    ['--push', '--skip-imports-gate'],
])
def test_imports_gate_options_are_validated_before_the_suite(repo, tmp_path, args):
    result, marker, _ = _dispatch(repo, tmp_path, args)
    assert result.returncode != 0 and not marker.exists()


# BACK-2586: the public callers signal is independent of import-row selection.
@pytest.mark.parametrize('path', [
    'reveal/adapters/calls/index.py', 'reveal/adapters/ast/call_graph.py',
    'reveal/analyzers/python.py', 'reveal/analyzers/imports/python.py',
    'reveal/conventions.py', 'reveal/analyzers/imports/generic.py',
    'reveal/analyzers/imports/base.py', 'reveal/analyzers/new_language.py',
    'tests/corpus/calls_baseline.json',
    'scripts/check_imports_gate.py', 'scripts/check_calls_gate.py',
    'scripts/recall_gate.py', 'scripts/recall_oracles.py',
    'tests/corpus/manifest.yaml', '.github/workflows/recall.yml',
])
def test_public_calls_selects_its_manifest_rows(gate, path):
    assert gate.select([path], MANIFEST, signal='calls') == (['python-celery'], [])


@pytest.mark.parametrize('path', [
    'README.md', 'reveal/analyzers/imports/service.py', 'tests/corpus/recall_baseline.json',
])
def test_public_calls_skips_unrelated_paths(gate, path):
    assert gate.select([path], MANIFEST, signal='calls') == ([], [])


def test_call_selection_preserves_language_scope_and_reports_unmeasured(gate):
    assert gate.select(['reveal/analyzers/go.py'], MANIFEST, signal='calls') == ([], ['go'])
    assert gate.select(['reveal/analyzers/_python_helpers.py'], MANIFEST, signal='calls') == (['python-celery'], [])
    assert gate.select(['reveal/adapters/calls/index.py'], MANIFEST) == ([], [])
    assert gate.select(['tests/corpus/calls_baseline.json'], MANIFEST) == ([], [])


@pytest.mark.parametrize('path', ['scripts/check_imports_gate.py', 'scripts/check_calls_gate.py'])
def test_trigger_inputs_remeasure_import_rows_too(gate, path):
    assert gate.select([path], MANIFEST) == (EVERY_ROW, [])


def test_calls_only_request_does_not_disappear_with_empty_import_rows(gate, manifested):
    commit_file(manifested, 'reveal/adapters/calls/index.py')
    assert gate.build_request(manifested)['rows'] == []
    request = gate.build_request(manifested, signal='calls')
    assert request['rows'] == ['python-celery'] and request['signal'] == 'calls'


@shell_only
@pytest.mark.parametrize('calls_exit', ['0', '1'])
def test_push_runs_public_calls_without_import_rows(repo, tmp_path, calls_exit):
    result, marker, records = _dispatch(repo, tmp_path, ['--push'],
                                      changed='reveal/adapters/calls/index.py', calls_exit=calls_exit)
    assert marker.exists()
    assert result.returncode == int(calls_exit), (result.stdout, result.stderr)
    assert not (tmp_path / 'argv.json').exists()  # no imports measurement
    argv = json.loads((tmp_path / 'argv.json.calls').read_text(encoding='utf-8'))
    assert argv[argv.index('--signal') + 1] == 'calls'
    assert argv[argv.index('--corpus') + 1] == 'python-celery'
    assert argv[argv.index('--output') + 1].endswith('calls-recall-gate-report.json')
    calls = [json.loads(line) for line in (tmp_path / 'logs/calls-recall-gate.jsonl').read_text(encoding='utf-8').splitlines()]
    assert calls[0]['decision'] == ('pass' if calls_exit == '0' else 'fail')
    assert records[0]['decision'] == 'pass'


@shell_only
def test_imports_skip_does_not_skip_public_calls(repo, tmp_path):
    result, _, records = _dispatch(repo, tmp_path, ['--push', '--skip-imports-gate', 'imports reviewed'],
                                   changed='reveal/adapters/calls/index.py', calls_exit='1')
    assert result.returncode == 1 and records[0]['decision'] == 'skip'
    assert (tmp_path / 'argv.json.calls').exists()


@shell_only
def test_public_calls_skip_is_separate_and_logged(repo, tmp_path):
    result, marker, records = _dispatch(repo, tmp_path,
        ['--push', '--skip-calls-recall-gate', 'call population reviewed'], calls_exit='1')
    assert result.returncode == 0 and marker.exists(), (result.stdout, result.stderr)
    assert (tmp_path / 'argv.json').exists() and not (tmp_path / 'argv.json.calls').exists()
    assert records[0]['decision'] == 'pass'
    calls = [json.loads(line) for line in (tmp_path / 'logs/calls-recall-gate.jsonl').read_text(encoding='utf-8').splitlines()]
    assert calls[0]['decision'] == 'skip' and 'call population reviewed' in calls[0]['detail']


@shell_only
@pytest.mark.parametrize('args', [
    ['--skip-calls-recall-gate', 'reason'], ['--push', '--skip-calls-recall-gate', '   '],
    ['--push', '--skip-calls-recall-gate'],
])
def test_public_calls_skip_validated_before_suite(repo, tmp_path, args):
    result, marker, _ = _dispatch(repo, tmp_path, args)
    assert result.returncode != 0 and not marker.exists()


@shell_only
def test_docs_only_push_measures_neither_public_signal(repo, tmp_path):
    result, marker, _ = _dispatch(repo, tmp_path, ['--push'], changed='README.md')
    assert result.returncode == 0 and marker.exists(), (result.stdout, result.stderr)
    assert not (tmp_path / 'argv.json').exists() and not (tmp_path / 'argv.json.calls').exists()


@shell_only
def test_python_change_measures_both_signals_with_distinct_reports(repo, tmp_path):
    result, _, _ = _dispatch(repo, tmp_path, ['--push'], changed='reveal/analyzers/python.py')
    assert result.returncode == 0, (result.stdout, result.stderr)
    imports = json.loads((tmp_path / 'argv.json').read_text(encoding='utf-8'))
    calls = json.loads((tmp_path / 'argv.json.calls').read_text(encoding='utf-8'))
    assert imports[imports.index('--signal') + 1] == 'imports'
    assert imports[imports.index('--output') + 1] != calls[calls.index('--output') + 1]
    assert 'python-reveal' in imports and 'python-celery' in calls


def test_public_signal_defaults_keep_logs_and_reports_separate(gate):
    imports = gate.parse_args(['--interpreter', sys.executable])
    calls = gate.parse_args(['--interpreter', sys.executable, '--signal', 'calls'])
    assert imports.log.name == 'imports-gate.jsonl' and calls.log.name == 'calls-recall-gate.jsonl'
    assert imports.output.name == 'imports-gate-report.json'
    assert calls.output.name == 'calls-recall-gate-report.json'
