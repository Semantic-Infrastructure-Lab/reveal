"""check joins the D6 findings gate: ``--fail-on none|findings`` (BACK-2051 slice 2).

``none`` suppresses findings only; lost or degraded analysis still exits 3. The legacy
``--exit-zero`` override stays, disclosed and exclusive with ``--fail-on``. Stdin and URI
checks keep their documented policy and reject the flag.
"""
import json
import os
import subprocess
import sys

import pytest

from reveal.cli.file_checker import check_exit_code

_BAD = "def f(x):\n    try:\n        return 1 / x\n    except:\n        pass\n"
_OK = "def f(x):\n    return x\n"
_BROKEN = "def (:\n    return\n"


def _reveal(cwd, *args, stdin=None):
    env = {**os.environ, 'REVEAL_DISK_CACHE': '0'}
    return subprocess.run([sys.executable, '-m', 'reveal', *args], cwd=cwd, capture_output=True,
                          text=True, env=env, timeout=120, check=False, encoding='utf-8', input=stdin)


@pytest.fixture(scope='module')
def tree(tmp_path_factory):
    """findings/ holds a violation and a clean file; broken/ is apart, because a sibling
    that does not parse makes cross-file rules (I002, D005) report an incomplete scan."""
    root = tmp_path_factory.mktemp('check_fail_on')
    for name, body in (('findings/bad.py', _BAD), ('findings/ok.py', _OK), ('broken/broken.py', _BROKEN)):
        (root / name).parent.mkdir(exist_ok=True)
        (root / name).write_text(body, encoding='utf-8')
    return root


def test_exit_code_owner_gates_findings_only():
    assert check_exit_code(3) == 1
    assert check_exit_code(3, fail_on='findings') == 1
    assert check_exit_code(3, fail_on='none') == 0
    assert check_exit_code(0, fail_on='none') == 0
    # none never hides lost analysis, in any of its three spellings
    assert check_exit_code(3, files_errored=1, fail_on='none') == 3
    assert check_exit_code(3, files_degraded=1, fail_on='none') == 3
    assert check_exit_code(3, scan_incomplete=True, fail_on='none') == 3
    # the legacy override still wins over everything computed
    assert check_exit_code(3, files_errored=1, exit_zero=True) == 0


def test_exit_code_owner_rejects_unknown_policy():
    with pytest.raises(ValueError):
        check_exit_code(1, fail_on='errors')


@pytest.mark.parametrize('argv, expected', [
    (['check', 'findings/bad.py'], 1),
    (['check', 'findings/bad.py', '--fail-on', 'findings'], 1),
    (['check', 'findings/bad.py', '--fail-on', 'none'], 0),
    (['--fail-on', 'none', 'check', 'findings/bad.py'], 0),
    (['findings/bad.py', '--check', '--fail-on', 'none'], 0),
    (['findings/bad.py', '--check', '--fail-on', 'findings'], 1),
    (['check', 'findings/ok.py', '--fail-on', 'findings'], 0),
    (['check', 'findings', '--fail-on', 'none'], 0),
    (['check', 'findings', '--fail-on', 'findings'], 1),
    (['check', 'findings'], 1),
])
def test_fail_on_gates_findings_on_both_spellings(tree, argv, expected):
    assert _reveal(tree, *argv).returncode == expected


def test_json_summary_exit_code_matches_the_gate(tree):
    run = _reveal(tree, 'check', 'findings', '--fail-on', 'none', '--format', 'json')
    assert run.returncode == 0
    summary = json.loads(run.stdout)['summary']
    assert summary['total_issues'] > 0 and summary['exit_code'] == 0


def test_none_does_not_hide_a_degraded_file(tree):
    baseline = _reveal(tree, 'check', 'broken/broken.py').returncode
    assert baseline == 3, 'fixture must be a degraded/unparsed file'
    assert _reveal(tree, 'check', 'broken/broken.py', '--fail-on', 'none').returncode == 3


def test_exit_zero_stays_and_is_exclusive_with_fail_on(tree):
    assert _reveal(tree, 'check', 'findings/bad.py', '--exit-zero').returncode == 0
    for policy in ('none', 'findings'):
        run = _reveal(tree, 'check', 'findings/bad.py', '--exit-zero', '--fail-on', policy)
        assert run.returncode == 2
        assert '--exit-zero' in run.stderr and '--fail-on' in run.stderr


@pytest.mark.parametrize('argv, stdin', [
    (['--stdin', '--check', '--fail-on', 'none'], 'findings/bad.py\n'),
    (['ssl://localhost', '--check', '--fail-on', 'none'], None),
])
def test_stdin_and_uri_checks_still_reject_fail_on(tree, argv, stdin):
    run = _reveal(tree, *argv, stdin=stdin)
    assert run.returncode == 2
    assert 'not supported' in run.stderr


@pytest.mark.parametrize('argv, expected', [
    (['review', 'findings'], 1),
    (['review', 'findings', '--fail-on', 'findings'], 1),
    (['review', 'findings', '--fail-on', 'none'], 0),
    (['--fail-on', 'none', 'review', 'findings'], 0),
    (['review', 'findings/ok.py', '--fail-on', 'findings'], 0),
])
def test_review_fail_on_gates_findings(tree, argv, expected):
    run = _reveal(tree, *argv, '--format', 'json')
    assert run.returncode == expected, run.stderr
    assert json.loads(run.stdout)['exit_code'] == expected


def test_review_fail_on_none_keeps_the_finding_visible(tree):
    report = json.loads(_reveal(tree, 'review', 'findings', '--fail-on', 'none', '--format', 'json').stdout)
    assert report['overall_status'] in ('warn', 'fail') and report['sections']['violations']
