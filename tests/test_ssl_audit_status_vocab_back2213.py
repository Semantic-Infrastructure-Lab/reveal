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
    col, failed = _format_acme_ssl_col(rows[0]['ssl_status'], rows[0]['ssl_days'], rows[0]['ssl_not_after'], rows[0]['ssl_message'])
    assert failed is is_failure
    assert col not in ('pass', 'failure')


def test_live_expired_is_failure():
    live = _load_live_cert('a.test', lambda *a, **k: _result('failure', -3))
    assert _format_live_col(live)[1] is True


EXP = {'name': 'certificate_expiry', 'status': 'failure', 'message': 'expires in 3 days'}
HOST = {'name': 'hostname_match', 'status': 'failure', 'message': 'hostname does not match'}
CHAIN_WARN = {'name': 'chain_verification', 'status': 'warning', 'message': 'incomplete chain'}


def test_critical_live_cert_fails_the_audit_like_ssl_check():
    rows = _fetch_acme_ssl_data([{'domain': 'a.test'}], lambda *a, **k: _result('failure', 3, [EXP]))
    col, failed = _format_acme_ssl_col(rows[0]['ssl_status'], rows[0]['ssl_days'], rows[0]['ssl_not_after'], rows[0]['ssl_message'])
    assert failed is True and 'expires in 3d' in col
    assert _format_live_col(_load_live_cert('a.test', lambda *a, **k: _result('failure', 3, [EXP])))[1] is True


def test_a_hostname_failure_is_not_hidden_behind_expiry():
    state, message = live_cert_state(_result('failure', 3, [EXP, HOST]))
    assert state == 'error' and 'hostname' in message


def test_chain_warning_is_not_labelled_as_expiry():
    rows = _fetch_acme_ssl_data([{'domain': 'a.test'}], lambda *a, **k: _result('warning', 200, [CHAIN_WARN]))
    col, failed = _format_acme_ssl_col(rows[0]['ssl_status'], rows[0]['ssl_days'], rows[0]['ssl_not_after'], rows[0]['ssl_message'])
    assert failed is False and 'incomplete chain' in col and 'expires' not in col
    assert 'incomplete chain' in _format_live_col(
        _load_live_cert('a.test', lambda *a, **k: _result('warning', 200, [CHAIN_WARN])))[0]


def test_expiry_warning_still_reads_expires_in():
    rows = _fetch_acme_ssl_data([{'domain': 'a.test'}], lambda *a, **k: _result(
        'warning', 20, [{'name': 'certificate_expiry', 'status': 'warning', 'message': 'x'}]))
    assert 'expires in 20d' in _format_acme_ssl_col(
        rows[0]['ssl_status'], rows[0]['ssl_days'], rows[0]['ssl_not_after'], rows[0]['ssl_message'])[0]
