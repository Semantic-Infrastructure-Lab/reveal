"""BACK-2213 lane b: autossl:// and letsencrypt:// fixes found by the guide review.

CB13: `autossl://latest?user=NAME` printed the run-wide Summary line (and JSON `summary`)
      next to the one user's domain count.
CB14: one unparseable cert.pem widened the letsencrypt:// "common name" column to the
      length of its error message.
"""
from reveal.adapters.autossl.adapter import _apply_autossl_filters
from reveal.adapters.letsencrypt.renderer import _render_cert_table


def _run():
    return {
        'type': 'autossl_run', 'user_count': 2, 'domain_count': 3,
        'summary': {'ok': 2, 'defective': 1},
        'users': [
            {'username': 'alice', 'domain_count': 1, 'summary': {'ok': 1},
             'domains': [{'domain': 'a.example.com', 'tls_status': 'ok'}]},
            {'username': 'bob', 'domain_count': 2, 'summary': {'ok': 1, 'defective': 1},
             'domains': [{'domain': 'b.example.com', 'tls_status': 'defective'},
                         {'domain': 'c.example.com', 'tls_status': 'ok'}]},
        ],
    }


def test_user_filter_summary_counts_only_that_user():
    assert _apply_autossl_filters(_run(), user='alice')['summary'] == {'ok': 1}
    assert _apply_autossl_filters(_run(), user='bob', summary=True)['summary'] == {'ok': 1, 'defective': 1}


def test_user_filter_with_only_failures_keeps_that_users_full_counts():
    result = _apply_autossl_filters(_run(), user='bob', only_failures=True)
    assert result['domain_count'] == 1
    assert result['summary'] == {'ok': 1, 'defective': 1}


def test_no_user_filter_keeps_the_run_summary():
    assert _apply_autossl_filters(_run(), only_failures=True)['summary'] == {'ok': 2, 'defective': 1}


def test_parse_error_cert_does_not_widen_the_common_name_column(capsys):
    certs = [
        {'name': 'example.com', 'common_name': 'example.com', 'days_until_expiry': 87,
         'is_expired': False, 'san': ['example.com']},
        {'name': 'broken.example.com', 'cert_path': '/etc/letsencrypt/live/broken.example.com/cert.pem',
         'error': 'Could not parse certificate: ' + 'x' * 200},
    ]
    _render_cert_table(certs)
    header = capsys.readouterr().out.splitlines()[0]
    assert len(header) < 80, header
