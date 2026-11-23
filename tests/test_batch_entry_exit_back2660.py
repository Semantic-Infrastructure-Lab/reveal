"""Every ``--stdin --batch`` entry exits as its direct request does (BACK-2660; COMMAND_MODEL "Transports", Scott
2026-11-17).

Before: an entry with no execution facts (a legacy, undeclared scheme) carried no ``exit_code`` and counted in the
batch exit through its status: a failed answer exited 2 although ``reveal URI`` exits 1 for it (``stats://``,
``nginx://``). Now each entry carries the exit its URI form has alone and the batch exits with the highest one: a
legacy failed answer 1, a legacy check its own verdict (failure 2, warning 1: BACK-1557), a usage error 2 as
``reveal nope://x`` exits, a declared answer its execution exit as before.
"""
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

import pytest

from conftest import _run_reveal_direct
from reveal.main import main

pytestmark = pytest.mark.component

_VAR = 'REVEAL_BACK2660_PROBE'


@pytest.fixture(autouse=True)
def _tree(tmp_path, monkeypatch):
    (tmp_path / 'proj').mkdir()
    (tmp_path / 'proj' / 'sample.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(_VAR, 'x')


def _batch(*lines, argv=()):
    """(batch exit code, its entries) for `lines` piped to `reveal --stdin --batch --format json <argv>`."""
    out, err, code = io.StringIO(), io.StringIO(), 0
    with redirect_stdout(out), redirect_stderr(err), patch('sys.stdin', io.StringIO(''.join(f'{x}\n' for x in lines))):
        try:
            main(['reveal', '--stdin', '--batch', '--format', 'json', *argv])
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    return code, json.loads(out.getvalue())['results']


def _direct(uri, *argv):
    return _run_reveal_direct(uri, '--format', 'json', *argv).returncode


# (URI, the exit its direct request has): legacy failed answers exit 1 alone, not the batch's old 2.
LEGACY_FAILED = [
    ('stats://proj/nosuch', 1),
    ('nginx://nosuch.example', 1),
]


@pytest.mark.parametrize('uri,code', LEGACY_FAILED, ids=['stats', 'nginx'])
def test_a_legacy_failed_entry_exits_as_its_uri_form(uri, code):
    assert _direct(uri) == code
    batch_code, (entry,) = _batch(uri)
    assert entry['status'] == 'error', entry
    assert entry.get('exit_code') == code, entry
    assert batch_code == code


def test_a_reveal_section_entry_exits_as_its_uri_form():
    """reveal:// carries its invalid-request facts since BACK-2761, so its entry already matched; a control here."""
    assert _direct('reveal://no-such') == 2
    batch_code, (entry,) = _batch('reveal://no-such')
    assert entry.get('exit_code') == 2 and batch_code == 2, entry


def test_a_usage_error_entry_keeps_2():
    """`reveal nope://x` exits 2 (a usage error), so its entry does too, beside a successful one."""
    assert _run_reveal_direct('nope://x').returncode == 2
    batch_code, (first, second) = _batch('nope://x', f'env://{_VAR}')
    assert first['status'] == 'error' and first.get('exit_code') == 2, first
    assert second['status'] == 'success' and second.get('exit_code') == 0, second
    assert batch_code == 2


def test_the_batch_exits_with_the_highest_entry_exit():
    batch_code, entries = _batch('stats://proj/nosuch', f'env://{_VAR}')
    assert [e.get('exit_code') for e in entries] == [1, 0], entries
    assert batch_code == 1
    batch_code, entries = _batch('stats://proj/nosuch', 'nope://x', f'env://{_VAR}')
    assert [e.get('exit_code') for e in entries] == [1, 2, 0], entries
    assert batch_code == 2


def test_a_successful_legacy_entry_exits_0():
    """Negative control: a legacy answer that succeeds exits 0 in both forms and the batch passes."""
    assert _direct('stats://proj') == 0
    batch_code, (entry,) = _batch('stats://proj')
    assert entry['status'] == 'success' and entry.get('exit_code') == 0, entry
    assert batch_code == 0


_FAILED = {'host': 'expired.example', 'port': 443, 'status': 'failure', 'exit_code': 2,
           'summary': {'total': 1, 'passed': 0, 'warnings': 0, 'failures': 1}, 'checks': []}
_WARNING = {**_FAILED, 'host': 'soon.example', 'status': 'warning', 'exit_code': 1,
            'summary': {'total': 1, 'passed': 0, 'warnings': 1, 'failures': 0}}
_PASSED = {**_FAILED, 'host': 'ok.example', 'status': 'pass', 'exit_code': 0,
           'summary': {'total': 1, 'passed': 1, 'warnings': 0, 'failures': 0}}


@pytest.mark.parametrize('result,code', [(_FAILED, 2), (_WARNING, 1), (_PASSED, 0)],
                         ids=['failure', 'warning', 'pass'])
def test_a_legacy_check_entry_exits_with_its_verdict(result, code):
    """A legacy check's verdict is its direct exit (BACK-1557: failure 2, warning 1); the batch keeps it."""
    with patch('reveal.adapters.ssl.adapter.SSLAdapter.check', lambda self, **kwargs: result):
        assert _direct(f'ssl://{result["host"]}', '--check') == code
        batch_code, (entry,) = _batch(f'ssl://{result["host"]}', argv=('--check',))
    assert entry['status'] == result['status'], entry
    assert entry.get('exit_code') == code, entry
    assert batch_code == code


def test_a_declared_entry_keeps_its_execution_exit():
    """Negative control: declared entries already carried the direct exit (BACK-2325)."""
    assert _direct('ast://proj/nosuch') == 2
    batch_code, (entry,) = _batch('ast://proj/nosuch')
    assert entry.get('exit_code') == 2 and batch_code == 2, entry


# The one mapping of a legacy answer to its exit (cli/routing/uri.py ``legacy_exit_code``): the check and structure
# emitters exit with it, and the batch gives each legacy entry the same exit.

def _hook(code):
    def exit_code(result, output_format):
        assert output_format == 'json'
        return code
    return exit_code


@pytest.mark.parametrize('result,kind,hook,code', [
    ({'status': 'failure', 'exit_code': 2}, 'check', None, 2),
    ({'status': 'warning', 'exit_code': 1}, 'check', None, 1),
    ({'status': 'pass'}, 'check', None, 0),
    ('not a dict', 'check', None, 0),
    ({'type': 'x', 'error': 'boom'}, 'structure', _hook(2), 1),
    ({'type': 'x', 'error': 'boom'}, 'router', None, 1),
    ({'type': 'nginx_fleet_audit', 'has_gaps': True}, 'structure', _hook(2), 2),
    ({'type': 'x'}, 'element', None, 0),
], ids=['check-failure', 'check-warning', 'check-pass', 'check-non-dict', 'failed-beats-findings', 'router-failed',
        'findings', 'success'])
def test_legacy_exit_code(result, kind, hook, code):
    from reveal.cli.routing.uri import legacy_exit_code
    assert legacy_exit_code(result, kind, hook, 'json') == code
