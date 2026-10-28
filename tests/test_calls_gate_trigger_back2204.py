"""A relevant unmeasured push cannot pass the local gate (BACK-2204)."""
import importlib.util
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / 'scripts' / 'check_calls_gate.py'
pytestmark = pytest.mark.skipif(shutil.which('git') is None, reason='git required')


def git(repo, *args):
    return subprocess.run(
        ['git', '-C', str(repo), *args], check=True, capture_output=True,
        text=True, encoding='utf-8', timeout=30,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / 'repo'
    root.mkdir()
    git(root, 'init', '-q')
    git(root, 'config', 'user.name', 'gate test')
    git(root, 'config', 'user.email', 'gate@example.invalid')
    git(root, 'config', 'commit.gpgsign', 'false')
    (root / 'README.md').write_text('initial\n', encoding='utf-8')
    git(root, 'add', 'README.md')
    git(root, 'commit', '-qm', 'base')
    git(root, 'update-ref', 'refs/remotes/origin/master', 'HEAD')
    return root


def commit_file(repo, path, content='changed\n'):
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8')
    git(repo, 'add', path)
    git(repo, 'commit', '-qm', 'change')


@pytest.fixture
def gate():
    spec = importlib.util.spec_from_file_location('calls_gate_check', HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def baseline(tmp_path):
    path = tmp_path / 'baseline.json'
    path.write_text(json.dumps({f'{lang}/{mode}': {} for lang in
                               ['python', 'go', 'typescript', 'js_excalidraw', 'js_threejs']
                               for mode in ['callers', 'depth2', 'callees']}), encoding='utf-8')
    return path


def request(gate, repo, baseline, rows=None):
    return gate.build_request(repo, baseline, Path(sys.executable), rows)


def evidence_for(req):
    return {**req, 'measured_at': datetime.now(timezone.utc).isoformat(), 'failures': [],
            'measurements': {key: {'reveal_sha': req['head'], 'oracle_edges': 1,
                                   'sample_size': 1, 'targets': {'sample': [1, 1]},
                                   'found_edges': 1, 'false_positive_edges': 0, 'recall': 1.0}
                             for key in req['required_rows']}}


def test_unrelated_changes_need_neither_baseline_nor_interpreter(gate, repo):
    commit_file(repo, 'reveal/utils/results.py')
    req = gate.build_request(repo, None, Path('not-an-interpreter'))
    assert req['required_rows'] == []


def test_js_helper_requires_all_nine_population_rows(gate, repo, baseline):
    commit_file(repo, 'reveal/analyzers/_js_function_values.py')
    req = request(gate, repo, baseline)
    assert len(req['required_rows']) == 9
    assert {key.split('/')[0] for key in req['required_rows']} == {
        'typescript', 'js_excalidraw', 'js_threejs'}


@pytest.mark.parametrize('path', [
    'reveal/conventions.py', 'reveal/core/new_boundary.py',
    'reveal/analyzers/_new_function_values.py', 'reveal/adapters/calls/index.py',
    'reveal/treesitter.py', 'reveal/structure.py',
    'reveal/adapters/ast/analysis.py', 'reveal/adapters/ast/node_taxonomy.py',
    'reveal/defaults.py', 'reveal/config.py', 'reveal/utils/path_utils.py',
    'reveal/utils/gitignore.py', 'reveal/utils/exclusions.py', 'reveal/utils/lines.py',
    'reveal/analyzers/imports/base.py', 'reveal/analyzers/imports/generic.py',
])
def test_shared_or_unknown_boundary_requires_every_row(gate, repo, baseline, path):
    commit_file(repo, path)
    assert request(gate, repo, baseline)['required_rows'] == sorted(json.loads(baseline.read_text(encoding='utf-8')))


def test_alias_extractor_is_gated_but_graph_orchestration_is_unrelated(gate, repo, baseline):
    commit_file(repo, 'reveal/analyzers/imports/service.py')
    assert request(gate, repo, baseline)['required_rows'] == []
    commit_file(repo, 'reveal/analyzers/imports/python.py')
    assert request(gate, repo, baseline)['required_rows'] == [
        'python/callees', 'python/callers', 'python/depth2']


def test_range_includes_earlier_commits_and_both_renamed_paths(gate, repo, baseline):
    commit_file(repo, 'reveal/analyzers/python.py')
    commit_file(repo, 'README.md', 'later unrelated commit\n')
    req = request(gate, repo, baseline)
    assert req['required_rows'] == ['python/callees', 'python/callers', 'python/depth2']
    git(repo, 'update-ref', 'refs/remotes/origin/master', 'HEAD')
    git(repo, 'mv', 'reveal/analyzers/python.py', 'moved.py')
    git(repo, 'commit', '-qm', 'move analyzer out of tree')
    req = request(gate, repo, baseline)
    assert req['required_rows'] == ['python/callees', 'python/callers', 'python/depth2']
    assert 'moved.py' in req['changed_paths']
    assert 'reveal/analyzers/python.py' in req['changed_paths']


@pytest.mark.parametrize('state', ['unstaged', 'staged', 'untracked'])
def test_dirty_analysis_cannot_reuse_head_evidence(gate, repo, baseline, state):
    commit_file(repo, 'reveal/analyzers/python.py')
    target = repo / ('new.py' if state == 'untracked' else 'reveal/analyzers/python.py')
    target.write_text('new change\n', encoding='utf-8')
    if state == 'staged':
        git(repo, 'add', '.')
    with pytest.raises(ValueError, match='clean analyzed checkout'):
        request(gate, repo, baseline)


def test_green_evidence_matches_exact_request(gate, repo, baseline):
    commit_file(repo, 'reveal/analyzers/python.py')
    req = request(gate, repo, baseline)
    assert gate.validate_evidence(req, evidence_for(req)) is None


@pytest.mark.parametrize('field', [
    'schema_version', 'checkout', 'head', 'tree', 'base', 'changed_paths',
    'required_rows', 'baseline_sha256', 'toolchain',
])
def test_mismatched_identity_is_refused(gate, repo, baseline, field):
    commit_file(repo, 'reveal/analyzers/python.py')
    req = request(gate, repo, baseline)
    evidence = evidence_for(req)
    evidence[field] = 'stale or another checkout'
    with pytest.raises(ValueError, match=field):
        gate.validate_evidence(req, evidence)


@pytest.mark.parametrize('kind', ['missing-row', 'wrong-sha', 'zero-sample', 'negative-count',
                                  'empty-targets', 'failed', 'missing-failures', 'malformed'])
def test_partial_failed_or_empty_measurements_are_refused(gate, repo, baseline, kind):
    commit_file(repo, 'reveal/analyzers/python.py')
    req = request(gate, repo, baseline)
    evidence = evidence_for(req)
    key = req['required_rows'][0]
    if kind == 'missing-row':
        del evidence['measurements'][key]
    elif kind == 'wrong-sha':
        evidence['measurements'][key]['reveal_sha'] = 'old'
    elif kind == 'zero-sample':
        evidence['measurements'][key]['sample_size'] = 0
    elif kind == 'negative-count':
        evidence['measurements'][key]['oracle_edges'] = -1
    elif kind == 'empty-targets':
        evidence['measurements'][key]['targets'] = {}
    elif kind == 'failed':
        evidence['failures'] = ['measured regression']
    elif kind == 'missing-failures':
        del evidence['failures']
    else:
        evidence = []
    with pytest.raises(ValueError, match='calls gate'):
        gate.validate_evidence(req, evidence)


def test_recorder_rows_override_is_describe_only(gate, repo, baseline, capsys):
    req = request(gate, repo, baseline, ['go/callers'])
    assert req['required_rows'] == ['go/callers']
    with pytest.raises(SystemExit) as caught:
        gate.parse_args(['--interpreter', sys.executable, '--rows', 'go/callers'])
    assert caught.value.code == 2
    assert 'request-only' in capsys.readouterr().err


def test_describe_emits_exact_clean_recorder_request(gate, repo, baseline, capsys):
    rows = ['typescript/callers', 'typescript/depth2', 'typescript/callees']
    args = ['--repo', str(repo), '--baseline', str(baseline),
            '--interpreter', sys.executable, '--describe', '--rows', *rows]
    assert gate.main(args) == 0
    captured = capsys.readouterr()
    req = json.loads(captured.out)
    assert captured.err == ''
    assert req == request(gate, repo, baseline, rows)
    assert req['checkout'] == str(repo.resolve())
    assert req['head'] == git(repo, 'rev-parse', 'HEAD')
    assert req['changed_paths'] == [] and req['required_rows'] == sorted(rows)
    assert req['toolchain']['executable'] == sys.executable


@pytest.mark.parametrize(('field', 'value'), [
    ('found_edges', None), ('false_positive_edges', -1), ('recall', float('nan')),
    ('recall', 1.1), ('targets', 'fake'), ('targets', {'sample': [1]}),
    ('targets', {'sample': [1, -1]}), ('targets', {'sample': [1, True]}),
])
def test_malformed_row_metrics_are_rejected(gate, repo, baseline, field, value):
    commit_file(repo, 'reveal/analyzers/python.py')
    req = request(gate, repo, baseline)
    evidence = evidence_for(req)
    evidence['measurements'][req['required_rows'][0]][field] = value
    with pytest.raises(ValueError, match='calls gate row'):
        gate.validate_evidence(req, evidence)


def test_explicit_skip_persists_its_reason(gate, repo, tmp_path, capsys):
    log = tmp_path / 'audit.jsonl'
    assert gate.main(['--repo', str(repo), '--interpreter', sys.executable,
                      '--skip-reason', 'reviewed bounded emergency', '--log', str(log)]) == 0
    record = json.loads(log.read_text(encoding='utf-8'))
    assert record['decision'] == 'skip' and 'reviewed bounded emergency' in record['detail']
    assert record['timestamp'] and 'SKIPPED' in capsys.readouterr().err


def test_invalid_json_is_a_visible_logged_failure(gate, repo, baseline, tmp_path, capsys):
    commit_file(repo, 'reveal/analyzers/python.py')
    bad = tmp_path / 'bad.json'
    bad.write_text('{', encoding='utf-8')
    log = tmp_path / 'audit.jsonl'
    assert gate.main(['--repo', str(repo), '--interpreter', sys.executable,
                      '--baseline', str(baseline), '--evidence', str(bad), '--log', str(log)]) == 1
    assert 'FAILED' in capsys.readouterr().err
    assert json.loads(log.read_text(encoding='utf-8'))['decision'] == 'fail'


@pytest.mark.skipif(sys.platform == 'win32' or shutil.which('bash') is None,
                    reason='ci-local is a POSIX shell script')
def test_relevant_push_fails_before_suite_when_evidence_is_missing(repo, tmp_path):
    """Execute the actual push-dispatch block with only its expensive suite stubbed."""
    commit_file(repo, 'reveal/analyzers/_js_function_values.py')
    result, marker, _ = run_push_dispatch(repo, tmp_path, ['--push'])
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert 'calls' in result.stderr.lower() and not marker.exists()


def run_push_dispatch(repo, tmp_path, args, suite_body='', extra_env=None):
    scripts = repo / 'scripts'
    scripts.mkdir(parents=True)
    source = (ROOT / 'scripts' / 'ci-local.sh').read_text(encoding='utf-8')
    prefix = source.split('# --changed: pytest targets')[0]
    prefix = prefix.replace('"$0" ||', 'bash "$SUITE_SCRIPT" ||')
    script = scripts / 'ci-local.sh'
    script.write_text(prefix, encoding='utf-8')
    script.chmod(0o755)
    if HELPER.exists():
        shutil.copy2(HELPER, scripts / HELPER.name)
    git(repo, 'add', 'scripts')
    git(repo, 'commit', '-qm', 'stage push dispatcher')
    marker = tmp_path / 'suite.marker'
    suite = tmp_path / 'suite.sh'
    suite.write_text('touch "$SUITE_MARKER"\n' + suite_body, encoding='utf-8')
    env = {k: v for k, v in os.environ.items() if not k.startswith('REVEAL_CALLS_GATE_')}
    env['SUITE_MARKER'] = str(marker)
    env['SUITE_SCRIPT'] = str(suite)
    env['REVEAL_CI_LOG_DIR'] = str(tmp_path / 'logs')
    env.update(extra_env or {})
    result = subprocess.run(
        ['bash', str(script), *args], cwd=repo, env=env,
        capture_output=True, text=True, encoding='utf-8', timeout=30,
    )
    return result, marker, tmp_path / 'logs' / 'calls-gate.jsonl'


shell_only = pytest.mark.skipif(sys.platform == 'win32' or shutil.which('bash') is None,
                                reason='ci-local is a POSIX shell script')


@shell_only
def test_unrelated_push_retains_default_suite(repo, tmp_path):
    commit_file(repo, 'reveal/utils/results.py')
    result, marker, log = run_push_dispatch(repo, tmp_path, ['--push'])
    assert result.returncode == 0 and marker.exists(), (result.stdout, result.stderr)
    assert len(log.read_text(encoding='utf-8').splitlines()) == 2


@shell_only
def test_explicit_push_skip_logs_reason_and_still_runs_suite(repo, tmp_path):
    commit_file(repo, 'reveal/treesitter.py')
    result, marker, log = run_push_dispatch(repo, tmp_path,
                                           ['--push', '--skip-calls-gate', 'reviewed exception'])
    assert result.returncode == 0 and marker.exists(), (result.stdout, result.stderr)
    records = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
    assert len(records) == 2 and all(row['decision'] == 'skip' for row in records)
    assert all('reviewed exception' in row['detail'] for row in records)


@shell_only
def test_push_revalidates_changes_after_the_suite(repo, tmp_path):
    body = 'mkdir -p reveal/analyzers\nprintf changed > reveal/analyzers/python.py\n'
    result, marker, _ = run_push_dispatch(repo, tmp_path, ['--push'], suite_body=body)
    assert marker.exists() and result.returncode == 1
    assert 'calls gate FAILED' in result.stderr


@shell_only
@pytest.mark.parametrize('args', [
    ['--push', '--no-tests'], ['--calls-evidence', 'record.json'],
    ['--push', '--skip-calls-gate', '   '], ['--push', '--calls-evidence'],
])
def test_push_option_validation_still_refuses_invalid_combinations(repo, tmp_path, args):
    result, marker, _ = run_push_dispatch(repo, tmp_path, args)
    assert result.returncode != 0 and not marker.exists()
