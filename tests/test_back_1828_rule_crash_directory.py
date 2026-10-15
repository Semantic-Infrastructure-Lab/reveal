"""A rule that raises must read the same for a directory as for a single file (BACK-1828).

A single-file check carries the crash as ``errors`` (exit 3, health FAILED). The directory
check used to leave the file's status ``ok`` and count it as neither errored nor degraded, so
the same crash exited 0, printed "No issues found" and health read ``healthy``.
"""
import contextlib
import io
import json

import pytest

from reveal.cli.commands.health import _code_result
from reveal.rules import RuleRegistry


@pytest.fixture
def crashing_b001(monkeypatch):
    RuleRegistry.discover()
    rule_cls = next(rc for rc in RuleRegistry._rules if rc.code == 'B001')

    def boom(self, *args, **kwargs):
        raise RuntimeError('INJECTED FAULT')

    monkeypatch.setattr(rule_cls, 'check', boom)
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')


def _run_check(monkeypatch, target, *extra):
    from reveal.main import main
    monkeypatch.setattr('sys.argv', ['reveal', 'check', str(target), '--select', 'B001', *extra])
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            main()
            code = 0
        except SystemExit as exc:
            code = exc.code or 0
    return code, out.getvalue()


def _health(data, code):
    checked = data.get('summary', {}).get('files_checked', 1)
    return _code_result(data, code, {'total': checked, 'returned': checked, 'exact': True})


def test_directory_rule_crash_exits_incomplete_and_health_fails(crashing_b001, monkeypatch, tmp_path):
    (tmp_path / 'a.py').write_text('x = 1\n', encoding='utf-8')
    code, out = _run_check(monkeypatch, tmp_path, '--format', 'json')
    data = json.loads(out)
    assert code == 3
    assert data['summary']['files_errored'] == 1
    assert data['summary']['exit_code'] == 3
    assert _health(data, code).outcome == 'failed'


def test_directory_rule_crash_text_does_not_say_clean(crashing_b001, monkeypatch, tmp_path):
    (tmp_path / 'a.py').write_text('x = 1\n', encoding='utf-8')
    code, out = _run_check(monkeypatch, tmp_path)
    assert code == 3
    assert 'rule B001 crashed' in out
    assert 'No issues found' not in out.replace('No findings in the checked population', '')


def test_single_file_and_directory_agree(crashing_b001, monkeypatch, tmp_path):
    f = tmp_path / 'a.py'
    f.write_text('x = 1\n', encoding='utf-8')
    file_code, file_out = _run_check(monkeypatch, f, '--format', 'json')
    dir_code, dir_out = _run_check(monkeypatch, tmp_path, '--format', 'json')
    assert file_code == dir_code == 3
    assert _health(json.loads(file_out), file_code).outcome == _health(json.loads(dir_out), dir_code).outcome


def test_clean_directory_is_still_healthy(monkeypatch, tmp_path):
    RuleRegistry.discover()
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')
    (tmp_path / 'a.py').write_text('x = 1\n', encoding='utf-8')
    code, out = _run_check(monkeypatch, tmp_path, '--format', 'json')
    data = json.loads(out)
    assert code == 0
    assert data['summary']['files_errored'] == 0
    assert _health(data, code).outcome == 'ok'


# --- health child outcomes (BACK-1828 findings 2-4) -------------------------------------

from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

from reveal.cli.commands.health import _check_code, _render_results, _uri_health_result


@pytest.mark.parametrize('returncode, stdout', [
    (-9, ''),
    (1, 'Traceback (most recent call last):\n...'),
    (-9, '{"summary": {"total_issues": 0, "files_checked": 1'),
])
def test_dead_code_checker_is_fail_not_warn(returncode, stdout):
    fake = MagicMock(returncode=returncode, stdout=stdout, stderr='boom: it died\n')
    with patch('subprocess.run', return_value=fake), \
         patch('reveal.cli.file_checker.collect_files_to_check') as collect:
        collect.return_value.files = [1]
        result = _check_code(Path('/nonexistent-health-target'), Namespace(select=None))
    assert (result.exit_code, result.outcome) == (2, 'failed')
    assert 'boom: it died' in result.summary


def test_uri_child_error_text_is_kept():
    result = _uri_health_result('bogus', 1, '', 'Error: Unsupported URI scheme: bogus://\nSupported: a, b\n')
    assert result.outcome == 'failed' and result.exit_code == 2
    assert 'Unsupported URI scheme: bogus://' in result.summary


def test_completed_uri_warning_answer_is_not_partial():
    import json
    warning = {'type': 'ssl_check', 'status': 'warning', 'exit_code': 1,
               'summary': {'total': 3, 'passed': 2, 'warnings': 1, 'failures': 0}}
    result = _uri_health_result('ssl', 1, json.dumps(warning))
    assert (result.exit_code, result.outcome) == (1, 'ok')


def test_capped_uri_answer_stays_partial():
    import json
    capped = {'type': 'ssl_check', 'meta': {'warnings': ['cut']}}
    assert _uri_health_result('ssl', 0, json.dumps(capped)).outcome == 'partial'


def test_fail_banner_does_not_claim_critical_findings(capsys):
    _render_results([{'target': 'code', 'exit_code': 2, 'summary': 'code: 7 violations (7 high, 0 critical)'}])
    out = capsys.readouterr().out
    assert 'Health: FAIL' in out and 'critical issues found' not in out
