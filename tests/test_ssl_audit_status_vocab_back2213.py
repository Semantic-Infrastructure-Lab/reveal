"""ACME/cPanel audits must fail on bad live certs (BACK-2213, CB5/CB12).

check_ssl_health reports pass/warning/failure; the audit tables used to
compare against healthy/expired, so a failing live cert exited 0.
"""
import pytest

from reveal.adapters.nginx.handlers import (
    _fetch_acme_ssl_data, _format_acme_ssl_col, _load_live_cert, _format_live_col,
)
from reveal.adapters.ssl.certificate import live_cert_state


def _result(status, days=None, checks=None, error=None):
    r = {'status': status, 'checks': checks or []}
    if days is not None:
        r['certificate'] = {'days_until_expiry': days, 'not_after': '2026-12-01T00:00:00Z'}
    if error:
        r['error'] = error
    return r


@pytest.mark.parametrize('result,state', [
    (_result('pass', 59), 'healthy'),
    (_result('warning', 20), 'warning'),
    (_result('failure', -3, [{'name': 'certificate_expiry', 'status': 'failure', 'message': 'x'}]), 'expired'),
    (_result('failure', 3, [{'name': 'certificate_expiry', 'status': 'failure', 'message': 'x'}]), 'critical'),
    (_result('failure', error='dns', checks=[{'name': 'connection', 'status': 'failure', 'message': 'dns'}]), 'error'),
])
def test_live_cert_state(result, state):
    assert live_cert_state(result)[0] == state


@pytest.mark.parametrize('result,is_failure', [
    (_result('pass', 59), False),
    (_result('failure', -3), True),
    (_result('failure', error='dns', checks=[{'name': 'connection', 'status': 'failure', 'message': 'dns'}]), True),
])
def test_acme_rows_flag_failures(result, is_failure):
    rows = _fetch_acme_ssl_data([{'domain': 'a.test'}], lambda *a, **k: result)
    col, failed = _format_acme_ssl_col(rows[0]['ssl_status'], rows[0]['ssl_days'], rows[0]['ssl_not_after'])
    assert failed is is_failure
    assert col not in ('pass', 'failure')


def test_live_expired_is_failure():
    live = _load_live_cert('a.test', lambda *a, **k: _result('failure', -3))
    assert _format_live_col(live)[1] is True
