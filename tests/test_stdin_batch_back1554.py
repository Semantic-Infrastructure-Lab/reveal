"""BACK-1554: stdin answers each URI through the router, not a dispatcher of its own.

``--stdin --batch`` built each adapter itself as ``adapter_class(uri)``, with the whole URI as
its resource, called only ``get_structure()``, and labelled every returned result 'success'.
The legacy ``--stdin --check`` ssl:// batch called ``check()`` with no arguments and exited 0
while printing "Exit code: 2". Both now take the router's answer (``resolve_uri``).

Invariant 9 of the contract harness (``test_output_contract_compliance.py``) compares every
adapter's --batch entry with its URI form. These tests cover what it can't run: ssl:// checks,
the flag ledger's view of the driver's own flags, a usage error inside a batch, and a static
check that batch never calls an adapter itself.
"""

import ast
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest

from reveal.cli.handlers import batch
from reveal.main import main

pytestmark = pytest.mark.component

# A variable this module sets, not HOME: Windows runners have no HOME, so env://HOME failed
# there, and a failed URI skips the flag ledger, so the ledger tests passed without checking.
_VAR = 'REVEAL_BACK1554_PROBE'


@pytest.fixture(autouse=True)
def _probe_var(monkeypatch):
    monkeypatch.setenv(_VAR, 'x')


_FAILED = {'host': 'expired.example', 'port': 443, 'status': 'failure', 'exit_code': 2,
           'summary': {'total': 1, 'passed': 0, 'warnings': 0, 'failures': 1}, 'checks': []}
_PASSED = {**_FAILED, 'host': 'ok.example', 'status': 'pass', 'exit_code': 0,
           'summary': {'total': 1, 'passed': 1, 'warnings': 0, 'failures': 0}}


def _run(stdin: str, *argv: str):
    """(exit code, stdout, stderr) for `reveal <argv>` with `stdin` piped in."""
    out, err, code = io.StringIO(), io.StringIO(), 0
    with redirect_stdout(out), redirect_stderr(err), patch('sys.stdin', io.StringIO(stdin)):
        try:
            main(['reveal', *argv])
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    return code, out.getvalue(), err.getvalue()


def _check_returning(*results):
    """Patch SSLAdapter.check to return `results` in turn; the list records each call's kwargs."""
    calls = []

    def check(self, **kwargs):
        calls.append(kwargs)
        return results[len(calls) - 1]
    return patch('reveal.adapters.ssl.adapter.SSLAdapter.check', check), calls


def test_legacy_ssl_check_batch_exits_with_its_failures():
    patcher, _ = _check_returning(_PASSED, _FAILED)
    with patcher:
        code, out, _ = _run('ssl://ok.example\nssl://expired.example\n', '--stdin', '--check')
    assert 'Exit code: 2' in out
    assert code == 2, 'the batch printed "Exit code: 2" and exited otherwise'


def test_legacy_ssl_check_batch_passes_clean():
    patcher, _ = _check_returning(_PASSED)
    with patcher:
        code, _, _ = _run('ssl://ok.example\n', '--stdin', '--check')
    assert code == 0


@pytest.mark.parametrize('mode', [['--batch'], []], ids=['batch', 'legacy'])
def test_ssl_check_gets_the_uri_forms_arguments(mode):
    patcher, calls = _check_returning(_PASSED)
    with patcher:
        _run('ssl://ok.example\n', '--stdin', *mode, '--check', '--expiring-within', '7')
    assert calls and calls[0].get('expiring_within') == '7', calls


def test_a_raising_ssl_check_is_a_failed_domain():
    def check(self, **kwargs):
        raise OSError('Connection refused')
    with patch('reveal.adapters.ssl.adapter.SSLAdapter.check', check):
        code, out, _ = _run('ssl://down.example\n', '--stdin', '--check', '--format', 'json')
    result = json.loads(out)
    assert result['summary']['failures'] == 1
    assert 'Connection refused' in result['results'][0]['error']
    assert code == 2


def test_a_usage_error_is_one_failed_entry_and_the_batch_goes_on():
    code, out, _ = _run(f'nope://x\nenv://{_VAR}\n', '--stdin', '--batch', '--format', 'json')
    first, second = json.loads(out)['results']
    assert first['status'] == 'error' and 'Unsupported URI scheme: nope://' in first['error']
    assert second['status'] == 'success' and second['data']['name'] == _VAR
    assert code == 2


@pytest.mark.parametrize('argv', [['--stdin'], ['--stdin', '--batch', '--summary']],
                         ids=['stdin', 'batch'])
def test_the_drivers_own_flags_are_not_reported_unused(argv):
    _, _, err = _run(f'env://{_VAR}\n', *argv)
    assert 'has no effect' not in err, err


@pytest.mark.parametrize('argv', [['--stdin'], ['--stdin', '--batch']], ids=['stdin', 'batch'])
def test_a_flag_nothing_applies_is_still_reported(argv):
    """Positive control for the test above: the ledger still runs per URI, under both drivers."""
    _, _, err = _run(f'env://{_VAR}\n', *argv, '--max-items', '3')
    assert '--max-items has no effect on env://' in err, err


def test_batch_never_calls_an_adapter_itself():
    """Every stdin URI is answered by the router; batch.py builds and calls no adapter."""
    from test_router_failure_seam_back1553 import _ADAPTER_CALLS

    tree = ast.parse(Path(batch.__file__).read_text(encoding='utf-8'))

    def name(call):
        return call.func.attr if isinstance(call.func, ast.Attribute) else getattr(call.func, 'id', None)

    calls = [f'line {n.lineno}: {name(n)}()' for n in ast.walk(tree) if isinstance(n, ast.Call)
             and name(n) in _ADAPTER_CALLS | {'get_adapter_class'}]
    assert not calls, f'batch.py calls adapters outside the router: {calls}'
