"""A relevant unmeasured push cannot pass the local gate (BACK-2204)."""
import importlib.util
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


@pytest.mark.skipif(sys.platform == 'win32' or shutil.which('bash') is None,
                    reason='ci-local is a POSIX shell script')
def test_relevant_push_fails_before_suite_when_evidence_is_missing(repo, tmp_path):
    """Execute the actual push-dispatch block with only its expensive suite stubbed."""
    commit_file(repo, 'reveal/analyzers/_js_function_values.py')
    stage = tmp_path / 'gate'
    scripts = stage / 'scripts'
    scripts.mkdir(parents=True)
    source = (ROOT / 'scripts' / 'ci-local.sh').read_text(encoding='utf-8')
    prefix = source.split('# --changed: pytest targets')[0]
    prefix = prefix.replace('"$0" ||', 'touch "$SUITE_MARKER" ||')
    script = scripts / 'ci-local.sh'
    script.write_text(prefix, encoding='utf-8')
    script.chmod(0o755)
    if HELPER.exists():
        shutil.copy2(HELPER, scripts / HELPER.name)
    marker = tmp_path / 'suite.marker'
    env = {k: v for k, v in os.environ.items() if not k.startswith('REVEAL_CALLS_GATE_')}
    env['SUITE_MARKER'] = str(marker)
    result = subprocess.run(
        ['bash', str(script), '--push'], cwd=repo, env=env,
        capture_output=True, text=True, encoding='utf-8', timeout=30,
    )
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert 'calls' in result.stderr.lower() and not marker.exists()
