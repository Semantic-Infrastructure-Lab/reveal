"""Tests for the autossl:// adapter."""

import json
import os
import sys
import pytest
from unittest.mock import patch

# AutoSSL is a cPanel/Linux-only feature; timestamps like 2026-01-01T00:00:00Z
# contain colons which are illegal in Windows directory names.
pytestmark = pytest.mark.skipif(
    sys.platform == 'win32',
    reason="autossl is a cPanel/Linux-only feature; colon timestamps invalid on Windows paths",
)

from reveal.adapters.autossl.adapter import AutosslAdapter
from reveal.adapters.autossl.parser import (
    AUTOSSL_LOG_DIR,
    _extract_defect_code,
    _new_domain_entry,
    get_run_metadata,
    list_runs,
    parse_run,
)
from reveal.adapters.autossl.renderer import AutosslRenderer

# cPanel uses Unicode curly quotes
_LQ = '\u201c'
_RQ = '\u201d'
_AP = '\u2019'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(contents, indent=0, rtype='out', timestamp='2026-01-01T00:00:00Z'):
    return json.dumps({
        'timestamp': timestamp,
        'indent': indent,
        'contents': contents,
        'type': rtype,
        'pid': 1,
        'partial': 0,
    })


def _write_run(tmp_path, timestamp, records):
    """Write a minimal autossl run directory with a json log file."""
    run_dir = tmp_path / timestamp
    run_dir.mkdir(parents=True)
    json_path = run_dir / 'json'
    json_path.write_text('\n'.join(records) + '\n', encoding='utf-8')
    # Symlinks
    os.symlink('LetsEncrypt', run_dir / 'provider')
    os.symlink('12345.111.222', run_dir / 'upid')
    os.symlink('*', run_dir / 'username')
    return str(tmp_path)


def _user_analyzing(username):
    return _make_record(f'Analyzing {_LQ}{username}{_RQ}{_AP}s domains \u2026', indent=1)


def _user_dcv(username):
    return _make_record(f'Processing {_LQ}{username}{_RQ}{_AP}s local DCV results \u2026', indent=0)


def _domain_analyzing(domain):
    return _make_record(f'Analyzing {_LQ}{domain}{_RQ} (website) \u2026', indent=2)


def _domain_dcv(domain):
    return _make_record(f'Analyzing {_LQ}{domain}{_RQ}{_AP}s DCV results \u2026', indent=1)


def _tls_ok():
    return _make_record('TLS Status: OK', indent=3, rtype='success')


def _tls_incomplete():
    return _make_record('TLS Status: Incomplete', indent=3, rtype='out')


def _tls_defective():
    return _make_record('TLS Status: Defective', indent=3, rtype='error')


def _cert_expiry(days, direction='from now'):
    return _make_record(f'Certificate expiry: 1/1/27 (+{abs(days)} days {direction})', indent=3)


def _defect(msg):
    return _make_record(f'Defect: {msg}', indent=3, rtype='error')


def _impediment(code, detail):
    return _make_record(f'Impediment: {code}: {detail}', indent=2, rtype='error')


# ---------------------------------------------------------------------------
# Tests: list_runs
# ---------------------------------------------------------------------------

class TestListRuns:
    def test_returns_empty_when_dir_missing(self, tmp_path):
        assert list_runs(str(tmp_path / 'nonexistent')) == []

    def test_returns_timestamps_newest_first(self, tmp_path):
        for ts in ['2026-01-01T00:00:00Z', '2026-01-03T00:00:00Z', '2026-01-02T00:00:00Z']:
            (tmp_path / ts).mkdir()
        runs = list_runs(str(tmp_path))
        assert runs == ['2026-01-03T00:00:00Z', '2026-01-02T00:00:00Z', '2026-01-01T00:00:00Z']

    def test_skips_files(self, tmp_path):
        (tmp_path / '2026-01-01T00:00:00Z').mkdir()
        (tmp_path / 'not-a-dir.txt').write_text('x')
        runs = list_runs(str(tmp_path))
        assert runs == ['2026-01-01T00:00:00Z']


# ---------------------------------------------------------------------------
# Tests: get_run_metadata
# ---------------------------------------------------------------------------

class TestGetRunMetadata:
    def test_reads_symlinks(self, tmp_path):
        ts = '2026-01-01T00:00:00Z'
        run_dir = tmp_path / ts
        run_dir.mkdir()
        os.symlink('LetsEncrypt', run_dir / 'provider')
        os.symlink('999.111.222', run_dir / 'upid')
        os.symlink('myuser', run_dir / 'username')
        meta = get_run_metadata(ts, str(tmp_path))
        assert meta['provider'] == 'LetsEncrypt'
        assert meta['upid'] == '999.111.222'
        assert meta['username'] == 'myuser'

    def test_defaults_when_no_symlinks(self, tmp_path):
        ts = '2026-01-01T00:00:00Z'
        (tmp_path / ts).mkdir()
        meta = get_run_metadata(ts, str(tmp_path))
        assert meta['provider'] == 'unknown'
        assert meta['username'] == '*'


# ---------------------------------------------------------------------------
# Tests: _extract_defect_code
# ---------------------------------------------------------------------------

class TestExtractDefectCode:
    def test_extracts_openssl_code(self):
        msg = "OPENSSL_VERIFY: The certificate chain failed (0:18:DEPTH_ZERO_SELF_SIGNED_CERT)."
        assert _extract_defect_code(msg) == 'DEPTH_ZERO_SELF_SIGNED_CERT'

    def test_extracts_expired_code(self):
        msg = "OPENSSL_VERIFY: The certificate chain failed (0:10:CERT_HAS_EXPIRED)."
        assert _extract_defect_code(msg) == 'CERT_HAS_EXPIRED'

    def test_fallback_to_truncated_string(self):
        msg = "Some unknown defect without parenthetical code"
        result = _extract_defect_code(msg)
        assert len(result) <= 60
        assert 'Some unknown' in result


# ---------------------------------------------------------------------------
# Tests: parse_run — core parsing
# ---------------------------------------------------------------------------

class TestParseRunBasic:
    def test_returns_correct_type(self, tmp_path):
        ts = '2026-01-01T00:00:00Z'
        records = [
            _user_analyzing('testuser'),
            _domain_analyzing('example.com'),
            _tls_ok(),
        ]
        log_dir = _write_run(tmp_path, ts, records)
        result = parse_run(ts, log_dir)
        assert result['type'] == 'autossl_run'

    def test_parses_ok_domain(self, tmp_path):
        ts = '2026-01-01T00:00:00Z'
        records = [
            _user_analyzing('alice'),
            _domain_analyzing('good.example.com'),
            _tls_ok(),
            _cert_expiry(90),
        ]
        log_dir = _write_run(tmp_path, ts, records)
        result = parse_run(ts, log_dir)
        assert result['user_count'] == 1
        user = result['users'][0]
        assert user['username'] == 'alice'
        domain = user['domains'][0]
        assert domain['domain'] == 'good.example.com'
        assert domain['tls_status'] == 'ok'
        assert domain['cert_expiry_days'] == 90.0

    def test_parses_defective_domain(self, tmp_path):
        ts = '2026-01-01T00:00:00Z'
        records = [
            _user_analyzing('alice'),
            _domain_analyzing('bad.example.com'),
            _tls_defective(),
            _defect('OPENSSL_VERIFY: failed (0:10:CERT_HAS_EXPIRED).'),
        ]
        log_dir = _write_run(tmp_path, ts, records)
        result = parse_run(ts, log_dir)
        domain = result['users'][0]['domains'][0]
        assert domain['tls_status'] == 'defective'
        assert domain['defect_codes'] == ['CERT_HAS_EXPIRED']

    def test_parses_incomplete_domain(self, tmp_path):
        ts = '2026-01-01T00:00:00Z'
        records = [
            _user_analyzing('alice'),
            _domain_analyzing('partial.example.com'),
            _tls_incomplete(),
        ]
        log_dir = _write_run(tmp_path, ts, records)
        result = parse_run(ts, log_dir)
        domain = result['users'][0]['domains'][0]
        assert domain['tls_status'] == 'incomplete'

    def test_parses_multiple_users(self, tmp_path):
        ts = '2026-01-01T00:00:00Z'
        records = [
            _user_analyzing('alice'),
            _domain_analyzing('alice.com'),
            _tls_ok(),
            _user_analyzing('bob'),
            _domain_analyzing('bob.com'),
            _tls_defective(),
        ]
        log_dir = _write_run(tmp_path, ts, records)
        result = parse_run(ts, log_dir)
        assert result['user_count'] == 2
        usernames = {u['username'] for u in result['users']}
        assert usernames == {'alice', 'bob'}

    def test_parses_multiple_domains_per_user(self, tmp_path):
        ts = '2026-01-01T00:00:00Z'
        records = [
            _user_analyzing('alice'),
            _domain_analyzing('a.com'),
            _tls_ok(),
            _domain_analyzing('b.com'),
            _tls_defective(),
            _domain_analyzing('c.com'),
            _tls_incomplete(),
        ]
        log_dir = _write_run(tmp_path, ts, records)
        result = parse_run(ts, log_dir)
        user = result['users'][0]
        assert user['domain_count'] == 3

    def test_expired_cert_has_negative_days(self, tmp_path):
        ts = '2026-01-01T00:00:00Z'
        records = [
            _user_analyzing('alice'),
            _domain_analyzing('expired.com'),
            _tls_defective(),
            _make_record('Certificate expiry: 6/1/25, 12:00 PM UTC (214.72 days ago)', indent=3),
        ]
        log_dir = _write_run(tmp_path, ts, records)
        result = parse_run(ts, log_dir)
        domain = result['users'][0]['domains'][0]
        assert domain['cert_expiry_days'] == pytest.approx(-214.72)

    def test_error_when_json_file_missing(self, tmp_path):
        ts = '2026-01-01T00:00:00Z'
        run_dir = tmp_path / ts
        run_dir.mkdir()
        # No json file
        result = parse_run(ts, str(tmp_path))
        assert result['type'] == 'autossl_run'
        assert 'error' in result


# ---------------------------------------------------------------------------
# Tests: parse_run — DCV impediments
# ---------------------------------------------------------------------------

class TestParseRunDCV:
    def test_parses_dcv_impediment(self, tmp_path):
        ts = '2026-01-01T00:00:00Z'
        records = [
            # Analyzing phase
            _user_analyzing('alice'),
            _domain_analyzing('blocked.com'),
            _tls_defective(),
            # DCV phase
            _user_dcv('alice'),
            _domain_dcv('blocked.com'),
            _impediment('TOTAL_DCV_FAILURE', 'Every domain failed DCV.'),
        ]
        log_dir = _write_run(tmp_path, ts, records)
        result = parse_run(ts, log_dir)
        domain = result['users'][0]['domains'][0]
        assert len(domain['impediments']) == 1
        assert domain['impediments'][0]['code'] == 'TOTAL_DCV_FAILURE'

    def test_dcv_impediment_on_new_domain(self, tmp_path):
        """Domain appears only in DCV phase, not in analyzing phase."""
        ts = '2026-01-01T00:00:00Z'
        records = [
            _user_analyzing('alice'),
            # no domains in analyzing phase
            _user_dcv('alice'),
            _domain_dcv('dcv-only.com'),
            _impediment('NO_UNSECURED_DOMAIN_PASSED_DCV', 'Every unsecured domain failed DCV.'),
        ]
        log_dir = _write_run(tmp_path, ts, records)
        result = parse_run(ts, log_dir)
        user = result['users'][0]
        assert user['domain_count'] == 1
        domain = user['domains'][0]
        assert domain['domain'] == 'dcv-only.com'
        assert domain['impediments'][0]['code'] == 'NO_UNSECURED_DOMAIN_PASSED_DCV'


# ---------------------------------------------------------------------------
# Tests: parse_run — detail field (BUG-137)
# ---------------------------------------------------------------------------

class TestParseRunDetailField:
    """BUG-137: domain entries must include a synthesized `detail` field for JSON consumers."""

    def test_ok_domain_has_empty_detail(self, tmp_path):
        ts = '2026-01-01T00:00:00Z'
        records = [_user_analyzing('alice'), _domain_analyzing('ok.com'), _tls_ok()]
        log_dir = _write_run(tmp_path, ts, records)
        result = parse_run(ts, log_dir)
        domain = result['users'][0]['domains'][0]
        assert 'detail' in domain
        assert domain['detail'] == ''

    def test_defective_domain_detail_has_defect_code(self, tmp_path):
        ts = '2026-01-01T00:00:00Z'
        records = [
            _user_analyzing('alice'),
            _domain_analyzing('bad.com'),
            _tls_defective(),
            _defect('OPENSSL_VERIFY: failed (0:10:CERT_HAS_EXPIRED).'),
        ]
        log_dir = _write_run(tmp_path, ts, records)
        result = parse_run(ts, log_dir)
        domain = result['users'][0]['domains'][0]
        assert domain['detail'] == 'CERT_HAS_EXPIRED'

    def test_impediment_code_appears_in_detail(self, tmp_path):
        ts = '2026-01-01T00:00:00Z'
        records = [
            _user_analyzing('alice'),
            _domain_analyzing('blocked.com'),
            _tls_defective(),
            _user_dcv('alice'),
            _domain_dcv('blocked.com'),
            _impediment('TOTAL_DCV_FAILURE', 'Every domain failed DCV.'),
        ]
        log_dir = _write_run(tmp_path, ts, records)
        result = parse_run(ts, log_dir)
        domain = result['users'][0]['domains'][0]
        # Uses same short code as text renderer (DCV:TOTAL, not full DCV:TOTAL_DCV_FAILURE)
        assert 'DCV:TOTAL' in domain['detail']
        assert domain['detail'] == 'DCV:TOTAL'

    def test_detail_combines_defect_and_impediment(self, tmp_path):
        ts = '2026-01-01T00:00:00Z'
        records = [
            _user_analyzing('alice'),
            _domain_analyzing('combo.com'),
            _tls_defective(),
            _defect('OPENSSL_VERIFY: failed (0:10:CERT_HAS_EXPIRED).'),
            _user_dcv('alice'),
            _domain_dcv('combo.com'),
            _impediment('TOTAL_DCV_FAILURE', 'Every domain failed DCV.'),
        ]
        log_dir = _write_run(tmp_path, ts, records)
        result = parse_run(ts, log_dir)
        domain = result['users'][0]['domains'][0]
        assert domain['detail'] == 'CERT_HAS_EXPIRED, DCV:TOTAL'


# ---------------------------------------------------------------------------
# Tests: parse_run — summary
# ---------------------------------------------------------------------------

class TestParseRunSummary:
    def test_summary_counts_correct(self, tmp_path):
        ts = '2026-01-01T00:00:00Z'
        records = [
            _user_analyzing('alice'),
            _domain_analyzing('a.com'), _tls_ok(),
            _domain_analyzing('b.com'), _tls_ok(),
            _domain_analyzing('c.com'), _tls_incomplete(),
            _domain_analyzing('d.com'), _tls_defective(),
        ]
        log_dir = _write_run(tmp_path, ts, records)
        result = parse_run(ts, log_dir)
        assert result['summary']['ok'] == 2
        assert result['summary']['incomplete'] == 1
        assert result['summary']['defective'] == 1

    def test_domains_sorted_failures_first(self, tmp_path):
        ts = '2026-01-01T00:00:00Z'
        records = [
            _user_analyzing('alice'),
            _domain_analyzing('ok.com'), _tls_ok(),
            _domain_analyzing('bad.com'), _tls_defective(),
            _domain_analyzing('partial.com'), _tls_incomplete(),
        ]
        log_dir = _write_run(tmp_path, ts, records)
        result = parse_run(ts, log_dir)
        domains = result['users'][0]['domains']
        assert domains[0]['tls_status'] == 'defective'
        assert domains[1]['tls_status'] == 'incomplete'
        assert domains[2]['tls_status'] == 'ok'

    def test_metadata_in_result(self, tmp_path):
        ts = '2026-01-01T00:00:00Z'
        records = [_user_analyzing('alice'), _domain_analyzing('x.com'), _tls_ok()]
        log_dir = _write_run(tmp_path, ts, records)
        result = parse_run(ts, log_dir)
        assert result['provider'] == 'LetsEncrypt'
        assert result['run_timestamp'] == ts
        assert result['global_run'] is True  # username symlink → '*'


# ---------------------------------------------------------------------------
# Tests: AutosslAdapter
# ---------------------------------------------------------------------------

class TestAutosslAdapter:
    def test_no_arg_raises(self):
        with pytest.raises(TypeError):
            AutosslAdapter()

    def test_invalid_scheme_raises(self):
        with pytest.raises(ValueError):
            AutosslAdapter('ssl://something')

    def test_empty_path_means_list_runs(self):
        a = AutosslAdapter('autossl://')
        assert a.timestamp is None

    def test_latest_sets_timestamp(self):
        a = AutosslAdapter('autossl://latest')
        assert a.timestamp == 'latest'

    def test_specific_timestamp(self):
        a = AutosslAdapter('autossl://2026-01-01T00:00:00Z')
        assert a.timestamp == '2026-01-01T00:00:00Z'

    def test_get_structure_list_runs(self, tmp_path):
        for ts in ['2026-01-02T00:00:00Z', '2026-01-01T00:00:00Z']:
            (tmp_path / ts).mkdir()
        a = AutosslAdapter('autossl://')
        with patch('reveal.adapters.autossl.adapter.AUTOSSL_LOG_DIR', str(tmp_path)), \
             patch('reveal.adapters.autossl.adapter.list_runs',
                   side_effect=lambda: ['2026-01-02T00:00:00Z', '2026-01-01T00:00:00Z']):
            result = a.get_structure()
        assert result['type'] == 'autossl_runs'
        assert result['run_count'] == 2

    def test_get_structure_latest_resolves(self, tmp_path):
        ts = '2026-01-01T00:00:00Z'
        records = [_user_analyzing('u'), _domain_analyzing('d.com'), _tls_ok()]
        log_dir = _write_run(tmp_path, ts, records)
        a = AutosslAdapter('autossl://latest')
        with patch('reveal.adapters.autossl.adapter.AUTOSSL_LOG_DIR', log_dir), \
             patch('reveal.adapters.autossl.adapter.list_runs', return_value=[ts]):
            result = a.get_structure()
        assert result['type'] == 'autossl_run'
        assert result['run_timestamp'] == ts

    def test_latest_raises_when_no_runs(self):
        a = AutosslAdapter('autossl://latest')
        with patch('reveal.adapters.autossl.adapter.list_runs', return_value=[]):
            with pytest.raises(ValueError, match='No AutoSSL runs'):
                a.get_structure()


# ---------------------------------------------------------------------------
# Tests: AutosslRenderer
# ---------------------------------------------------------------------------

class TestAutosslRenderer:
    def test_render_runs_shows_count(self, capsys):
        result = {
            'type': 'autossl_runs',
            'log_dir': '/var/cpanel/logs/autossl',
            'run_count': 3,
            'runs': ['2026-01-03T00:00:00Z', '2026-01-02T00:00:00Z', '2026-01-01T00:00:00Z'],
            'next_steps': [],
        }
        AutosslRenderer.render_structure(result)
        out = capsys.readouterr().out
        assert '3 total' in out
        assert '2026-01-03T00:00:00Z' in out

    def test_render_run_shows_summary(self, capsys):
        result = {
            'type': 'autossl_run',
            'run_timestamp': '2026-01-01T00:00:00Z',
            'run_start': '2026-01-01T00:00:01Z',
            'run_end': '2026-01-01T00:14:01Z',
            'provider': 'LetsEncrypt',
            'upid': '123',
            'global_run': True,
            'log_dir': '/var/cpanel/logs/autossl/2026-01-01T00:00:00Z',
            'user_count': 2,
            'domain_count': 10,
            'summary': {'ok': 5, 'incomplete': 3, 'defective': 2},
            'users': [],
        }
        AutosslRenderer.render_structure(result)
        out = capsys.readouterr().out
        assert '2026-01-01T00:00:00Z' in out
        assert 'LetsEncrypt' in out
        assert '5 ok' in out
        assert '2 defective' in out

    def test_render_domain_table(self, capsys):
        result = {
            'type': 'autossl_run',
            'run_timestamp': '2026-01-01T00:00:00Z',
            'run_start': '2026-01-01T00:00:01Z',
            'run_end': '2026-01-01T00:05:01Z',
            'provider': 'LetsEncrypt',
            'upid': '123',
            'global_run': True,
            'log_dir': '/x',
            'user_count': 1,
            'domain_count': 2,
            'summary': {'ok': 1, 'defective': 1},
            'users': [{
                'username': 'testuser',
                'domain_count': 2,
                'summary': {'ok': 1, 'defective': 1},
                'domains': [
                    {
                        'domain': 'bad.example.com',
                        'tls_status': 'defective',
                        'cert_expiry_days': -30.0,
                        'defects': ['CERT_HAS_EXPIRED'],
                        'defect_codes': ['CERT_HAS_EXPIRED'],
                        'impediments': [],
                        'user_excluded': False,
                    },
                    {
                        'domain': 'good.example.com',
                        'tls_status': 'ok',
                        'cert_expiry_days': 80.0,
                        'defects': [],
                        'defect_codes': [],
                        'impediments': [],
                        'user_excluded': False,
                    },
                ],
            }],
        }
        AutosslRenderer.render_structure(result)
        out = capsys.readouterr().out
        assert 'bad.example.com' in out
        assert 'good.example.com' in out
        assert 'CERT_HAS_EXPIRED' in out

    def test_render_json_format(self, capsys):
        result = {
            'type': 'autossl_runs',
            'log_dir': '/x',
            'run_count': 0,
            'runs': [],
            'next_steps': [],
        }
        AutosslRenderer.render_structure(result, format='json')
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed['type'] == 'autossl_runs'

    def test_render_error_result(self, capsys):
        result = {
            'type': 'autossl_run',
            'error': 'File not found',
            'run_timestamp': '2026-01-01T00:00:00Z',
            'log_dir': '/nonexistent',
        }
        AutosslRenderer.render_structure(result)
        out = capsys.readouterr().out
        assert 'Error' in out
        assert 'File not found' in out

    def test_render_no_runs(self, capsys):
        result = {
            'type': 'autossl_runs',
            'log_dir': '/var/cpanel/logs/autossl',
            'run_count': 0,
            'runs': [],
            'next_steps': [],
        }
        AutosslRenderer.render_structure(result)
        out = capsys.readouterr().out
        assert 'no runs found' in out.lower()

# ---------------------------------------------------------------------------
# BACK-048: autossl filters (--only-failures, --summary, --user)
# ---------------------------------------------------------------------------

class TestApplyAutosslFilters:
    """BACK-048: _apply_autossl_filters reduces 78KB autossl output."""

    from reveal.adapters.autossl.adapter import _apply_autossl_filters  # noqa: E402

    def _make_run(self, users=None):
        """Build a minimal autossl_run dict for filter testing."""
        if users is None:
            users = [
                {
                    'username': 'alice',
                    'domain_count': 3,
                    'summary': {'ok': 2, 'incomplete': 1},
                    'domains': [
                        {'domain': 'a.com', 'tls_status': 'ok'},
                        {'domain': 'b.com', 'tls_status': 'ok'},
                        {'domain': 'c.com', 'tls_status': 'incomplete'},
                    ],
                },
                {
                    'username': 'bob',
                    'domain_count': 2,
                    'summary': {'ok': 2},
                    'domains': [
                        {'domain': 'd.com', 'tls_status': 'ok'},
                        {'domain': 'e.com', 'tls_status': 'ok'},
                    ],
                },
            ]
        return {
            'type': 'autossl_run',
            'run_timestamp': '2026-01-01T00:00:00Z',
            'provider': 'LetsEncrypt',
            'run_start': '',
            'run_end': '',
            'user_count': len(users),
            'domain_count': sum(u['domain_count'] for u in users),
            'summary': {'ok': 4, 'incomplete': 1},
            'users': users,
        }

    def test_only_failures_removes_ok_domains(self):
        from reveal.adapters.autossl.adapter import _apply_autossl_filters
        result = _apply_autossl_filters(self._make_run(), only_failures=True)
        # alice has 1 failure, bob has 0 → bob dropped
        assert result['user_count'] == 1
        assert result['users'][0]['username'] == 'alice'
        assert len(result['users'][0]['domains']) == 1
        assert result['users'][0]['domains'][0]['domain'] == 'c.com'

    def test_only_failures_drops_users_with_no_failures(self):
        from reveal.adapters.autossl.adapter import _apply_autossl_filters
        result = _apply_autossl_filters(self._make_run(), only_failures=True)
        usernames = [u['username'] for u in result['users']]
        assert 'bob' not in usernames

    def test_summary_strips_users_key(self):
        from reveal.adapters.autossl.adapter import _apply_autossl_filters
        result = _apply_autossl_filters(self._make_run(), summary=True)
        assert 'users' not in result
        assert result['type'] == 'autossl_run'
        assert 'summary' in result

    def test_summary_preserves_counts(self):
        from reveal.adapters.autossl.adapter import _apply_autossl_filters
        result = _apply_autossl_filters(self._make_run(), summary=True)
        assert result['user_count'] == 2
        assert result['domain_count'] == 5

    def test_user_filter_returns_matching_user(self):
        from reveal.adapters.autossl.adapter import _apply_autossl_filters
        result = _apply_autossl_filters(self._make_run(), user='alice')
        assert result['user_count'] == 1
        assert result['users'][0]['username'] == 'alice'

    def test_user_filter_raises_on_unknown_user(self):
        from reveal.adapters.autossl.adapter import _apply_autossl_filters
        with pytest.raises(ValueError, match="User 'nobody' not found"):
            _apply_autossl_filters(self._make_run(), user='nobody')

    def test_combined_user_and_only_failures(self):
        from reveal.adapters.autossl.adapter import _apply_autossl_filters
        result = _apply_autossl_filters(self._make_run(), user='alice', only_failures=True)
        assert result['user_count'] == 1
        assert len(result['users'][0]['domains']) == 1
        assert result['users'][0]['domains'][0]['tls_status'] == 'incomplete'

    def test_no_filters_returns_all_data(self):
        from reveal.adapters.autossl.adapter import _apply_autossl_filters
        run = self._make_run()
        result = _apply_autossl_filters(run)
        assert result['user_count'] == 2
        assert 'users' in result
        assert len(result['users'][0]['domains']) == 3


class TestAutosslErrorCodes:
    """BACK-057: autossl://error-codes returns taxonomy of known error codes."""

    def test_error_codes_uri_returns_taxonomy(self):
        from reveal.adapters.autossl.adapter import AutosslAdapter
        a = AutosslAdapter('autossl://error-codes')
        result = a.get_structure()
        assert result['type'] == 'autossl_error_codes'

    def test_taxonomy_has_openssl_defect_codes(self):
        from reveal.adapters.autossl.adapter import AutosslAdapter
        a = AutosslAdapter('autossl://error-codes')
        result = a.get_structure()
        codes = result.get('openssl_defect_codes', [])
        assert len(codes) >= 3
        assert any(e['code'] == 'DEPTH_ZERO_SELF_SIGNED_CERT' for e in codes)
        assert any(e['code'] == 'CERT_HAS_EXPIRED' for e in codes)

    def test_taxonomy_has_dcv_impediment_codes(self):
        from reveal.adapters.autossl.adapter import AutosslAdapter
        a = AutosslAdapter('autossl://error-codes')
        result = a.get_structure()
        codes = result.get('dcv_impediment_codes', [])
        assert len(codes) >= 2
        assert any(e['code'] == 'TOTAL_DCV_FAILURE' for e in codes)

    def test_each_openssl_entry_has_required_fields(self):
        from reveal.adapters.autossl.adapter import AutosslAdapter
        a = AutosslAdapter('autossl://error-codes')
        result = a.get_structure()
        for entry in result['openssl_defect_codes']:
            assert 'code' in entry
            assert 'meaning' in entry
            assert 'fix' in entry

    def test_taxonomy_has_tls_status_values(self):
        from reveal.adapters.autossl.adapter import AutosslAdapter
        a = AutosslAdapter('autossl://error-codes')
        result = a.get_structure()
        tls = result.get('tls_status_values', {})
        assert 'ok' in tls
        assert 'defective' in tls

    def test_renderer_produces_output(self, capsys):
        from reveal.adapters.autossl.adapter import AutosslAdapter
        from reveal.adapters.autossl.renderer import AutosslRenderer
        a = AutosslAdapter('autossl://error-codes')
        result = a.get_structure()
        AutosslRenderer.render_structure(result, 'text')
        out = capsys.readouterr().out
        assert 'DEPTH_ZERO_SELF_SIGNED_CERT' in out
        assert 'TOTAL_DCV_FAILURE' in out


class TestAutosslDomainHistory:
    """Tests for autossl://DOMAIN domain-history drill-down (BACK-144)."""

    def _write_run_with_domain(self, tmp_path, timestamp, domain, status='ok'):
        """Write a minimal run containing a specific domain."""
        records = [
            _user_analyzing('testuser'),
            _domain_analyzing(domain),
            _tls_ok() if status == 'ok' else _tls_defective(),
        ]
        _write_run(tmp_path, timestamp, records)

    def test_domain_uri_sets_domain_attribute(self):
        from reveal.adapters.autossl.adapter import AutosslAdapter
        a = AutosslAdapter('autossl://app.example.com')
        assert a.domain == 'app.example.com'
        assert a.timestamp is None

    def test_domain_uri_does_not_set_timestamp(self):
        from reveal.adapters.autossl.adapter import AutosslAdapter
        a = AutosslAdapter('autossl://sub.domain.io')
        assert a.timestamp is None

    def test_timestamp_uri_does_not_set_domain(self):
        from reveal.adapters.autossl.adapter import AutosslAdapter
        a = AutosslAdapter('autossl://2026-01-01T00:00:00Z')
        assert a.domain is None
        assert a.timestamp == '2026-01-01T00:00:00Z'

    def test_latest_does_not_set_domain(self):
        from reveal.adapters.autossl.adapter import AutosslAdapter
        a = AutosslAdapter('autossl://latest')
        assert a.domain is None

    def test_empty_uri_does_not_set_domain(self):
        from reveal.adapters.autossl.adapter import AutosslAdapter
        a = AutosslAdapter('autossl://')
        assert a.domain is None

    def test_domain_history_returns_correct_type(self, tmp_path):
        from reveal.adapters.autossl.adapter import AutosslAdapter
        ts = '2026-01-01T00:00:00Z'
        self._write_run_with_domain(tmp_path, ts, 'app.example.com', status='ok')
        a = AutosslAdapter('autossl://app.example.com')
        with patch('reveal.adapters.autossl.adapter.list_runs', return_value=[ts]), \
             patch('reveal.adapters.autossl.adapter.parse_run',
                   side_effect=lambda t: __import__('reveal.adapters.autossl.parser',
                       fromlist=['parse_run']).parse_run(t, log_dir=str(tmp_path))):
            result = a.get_structure()
        assert result['type'] == 'autossl_domain_history'

    def test_domain_history_finds_domain_across_runs(self, tmp_path):
        from reveal.adapters.autossl.adapter import AutosslAdapter
        from reveal.adapters.autossl.parser import parse_run
        ts1 = '2026-01-02T00:00:00Z'
        ts2 = '2026-01-01T00:00:00Z'
        for ts in [ts1, ts2]:
            self._write_run_with_domain(tmp_path, ts, 'app.example.com', status='ok')

        a = AutosslAdapter('autossl://app.example.com')
        with patch('reveal.adapters.autossl.adapter.list_runs', return_value=[ts1, ts2]), \
             patch('reveal.adapters.autossl.adapter.parse_run',
                   side_effect=lambda t: parse_run(t, log_dir=str(tmp_path))):
            result = a.get_structure()
        assert result['run_count'] == 2
        assert len(result['history']) == 2

    def test_domain_history_missing_domain_returns_empty(self, tmp_path):
        from reveal.adapters.autossl.adapter import AutosslAdapter
        from reveal.adapters.autossl.parser import parse_run
        ts = '2026-01-01T00:00:00Z'
        self._write_run_with_domain(tmp_path, ts, 'other.example.com', status='ok')

        a = AutosslAdapter('autossl://missing.example.com')
        with patch('reveal.adapters.autossl.adapter.list_runs', return_value=[ts]), \
             patch('reveal.adapters.autossl.adapter.parse_run',
                   side_effect=lambda t: parse_run(t, log_dir=str(tmp_path))):
            result = a.get_structure()
        assert result['run_count'] == 0
        assert result['history'] == []

    def test_domain_history_summary_counts(self, tmp_path):
        from reveal.adapters.autossl.adapter import AutosslAdapter
        from reveal.adapters.autossl.parser import parse_run
        ts1 = '2026-01-02T00:00:00Z'
        ts2 = '2026-01-01T00:00:00Z'
        self._write_run_with_domain(tmp_path, ts1, 'app.example.com', status='ok')
        self._write_run_with_domain(tmp_path, ts2, 'app.example.com', status='defective')

        a = AutosslAdapter('autossl://app.example.com')
        with patch('reveal.adapters.autossl.adapter.list_runs', return_value=[ts1, ts2]), \
             patch('reveal.adapters.autossl.adapter.parse_run',
                   side_effect=lambda t: parse_run(t, log_dir=str(tmp_path))):
            result = a.get_structure()
        assert result['summary']['ok'] == 1
        assert result['summary']['defective'] == 1

    def test_domain_history_entry_has_expected_fields(self, tmp_path):
        from reveal.adapters.autossl.adapter import AutosslAdapter
        from reveal.adapters.autossl.parser import parse_run
        ts = '2026-01-01T00:00:00Z'
        self._write_run_with_domain(tmp_path, ts, 'app.example.com', status='ok')

        a = AutosslAdapter('autossl://app.example.com')
        with patch('reveal.adapters.autossl.adapter.list_runs', return_value=[ts]), \
             patch('reveal.adapters.autossl.adapter.parse_run',
                   side_effect=lambda t: parse_run(t, log_dir=str(tmp_path))):
            result = a.get_structure()
        entry = result['history'][0]
        assert 'run_timestamp' in entry
        assert 'username' in entry
        assert 'tls_status' in entry
        assert 'defect_codes' in entry
        assert 'impediments' in entry

    def test_domain_history_no_runs_returns_empty(self):
        from reveal.adapters.autossl.adapter import AutosslAdapter
        a = AutosslAdapter('autossl://app.example.com')
        with patch('reveal.adapters.autossl.adapter.list_runs', return_value=[]):
            result = a.get_structure()
        assert result['type'] == 'autossl_domain_history'
        assert result['run_count'] == 0

    def test_renderer_domain_history_text(self, capsys):
        from reveal.adapters.autossl.renderer import AutosslRenderer
        result = {
            'contract_version': '1.0',
            'type': 'autossl_domain_history',
            'domain': 'app.example.com',
            'run_count': 1,
            'summary': {'ok': 1, 'defective': 0, 'incomplete': 0},
            'history': [{
                'run_timestamp': '2026-01-01T00:00:00Z',
                'run_start': None,
                'username': 'testuser',
                'tls_status': 'ok',
                'cert_expiry_days': 45.0,
                'defect_codes': [],
                'impediments': [],
                'detail': '',
            }],
            'next_steps': [],
        }
        AutosslRenderer.render_structure(result, 'text')
        out = capsys.readouterr().out
        assert 'app.example.com' in out
        assert 'testuser' in out
        assert 'ok' in out

    def test_renderer_domain_history_no_results(self, capsys):
        from reveal.adapters.autossl.renderer import AutosslRenderer
        result = {
            'contract_version': '1.0',
            'type': 'autossl_domain_history',
            'domain': 'missing.example.com',
            'run_count': 0,
            'summary': {'ok': 0, 'defective': 0, 'incomplete': 0},
            'history': [],
            'next_steps': [],
        }
        AutosslRenderer.render_structure(result, 'text')
        out = capsys.readouterr().out
        assert 'missing.example.com' in out
        assert 'not found' in out

    def test_renderer_domain_history_none_tls_status(self, capsys):
        from reveal.adapters.autossl.renderer import AutosslRenderer
        result = {
            'contract_version': '1.0',
            'type': 'autossl_domain_history',
            'domain': 'app.example.com',
            'run_count': 1,
            'summary': {'ok': 0, 'defective': 0, 'incomplete': 1},
            'history': [{
                'run_timestamp': '2026-01-01T00:00:00Z',
                'run_start': None,
                'username': 'testuser',
                'tls_status': None,
                'cert_expiry_days': None,
                'defect_codes': [],
                'impediments': [],
                'detail': '',
            }],
            'next_steps': [],
        }
        AutosslRenderer.render_structure(result, 'text')
        out = capsys.readouterr().out
        assert 'app.example.com' in out
        assert 'unknown' in out

    # --- T0410-haunted-viper: row cap + --all ---

    def test_domain_history_truncation_caps_at_20(self, tmp_path):
        from reveal.adapters.autossl.adapter import AutosslAdapter
        from reveal.adapters.autossl.parser import parse_run
        timestamps = [f'2026-01-{i:02d}T00:00:00Z' for i in range(1, 26)]
        for ts in timestamps:
            self._write_run_with_domain(tmp_path, ts, 'app.example.com', status='ok')
        a = AutosslAdapter('autossl://app.example.com')
        with patch('reveal.adapters.autossl.adapter.list_runs', return_value=timestamps), \
             patch('reveal.adapters.autossl.adapter.parse_run',
                   side_effect=lambda t: parse_run(t, log_dir=str(tmp_path))):
            result = a.get_structure()
        assert result['run_count'] == 25
        assert len(result['history']) == 20
        assert result['truncated'] is True

    def test_domain_history_show_all_bypasses_cap(self, tmp_path):
        from reveal.adapters.autossl.adapter import AutosslAdapter
        from reveal.adapters.autossl.parser import parse_run
        timestamps = [f'2026-01-{i:02d}T00:00:00Z' for i in range(1, 26)]
        for ts in timestamps:
            self._write_run_with_domain(tmp_path, ts, 'app.example.com', status='ok')
        a = AutosslAdapter('autossl://app.example.com')
        with patch('reveal.adapters.autossl.adapter.list_runs', return_value=timestamps), \
             patch('reveal.adapters.autossl.adapter.parse_run',
                   side_effect=lambda t: parse_run(t, log_dir=str(tmp_path))):
            result = a.get_structure(**{'all': True})
        assert result['run_count'] == 25
        assert len(result['history']) == 25
        assert result['truncated'] is False

    def test_renderer_shows_truncation_note(self, capsys):
        from reveal.adapters.autossl.renderer import AutosslRenderer
        history = [{'run_timestamp': f'2026-01-{i:02d}', 'username': 'u',
                    'tls_status': 'defective', 'cert_expiry_days': None,
                    'defect_codes': [], 'impediments': []} for i in range(1, 21)]
        result = {
            'type': 'autossl_domain_history',
            'domain': 'app.example.com',
            'run_count': 25,
            'truncated': True,
            'oldest_run_timestamp': None,
            'summary': {'ok': 0, 'defective': 25, 'incomplete': 0, 'dcv_failed': 0},
            'history': history,
            'next_steps': [],
        }
        AutosslRenderer.render_structure(result, 'text')
        out = capsys.readouterr().out
        assert '5 older runs not shown' in out
        assert '--all' in out

    # --- T0410-neural-panther: always show ok count ---

    def test_renderer_always_shows_ok_count_when_zero(self, capsys):
        from reveal.adapters.autossl.renderer import AutosslRenderer
        result = {
            'type': 'autossl_domain_history',
            'domain': 'bad.example.com',
            'run_count': 3,
            'truncated': False,
            'oldest_run_timestamp': '2026-01-01',
            'summary': {'ok': 0, 'defective': 3, 'incomplete': 0, 'dcv_failed': 0},
            'history': [{'run_timestamp': '2026-01-03', 'username': 'u',
                         'tls_status': 'defective', 'cert_expiry_days': None,
                         'defect_codes': [], 'impediments': []}],
            'next_steps': [],
        }
        AutosslRenderer.render_structure(result, 'text')
        out = capsys.readouterr().out
        assert '0 ok' in out

    # --- T0410-chrome-spark: failing since ---

    def test_renderer_shows_failing_since_when_no_ok(self, capsys):
        from reveal.adapters.autossl.renderer import AutosslRenderer
        result = {
            'type': 'autossl_domain_history',
            'domain': 'bad.example.com',
            'run_count': 2,
            'truncated': False,
            'oldest_run_timestamp': '2026-03-12_03-00-00',
            'summary': {'ok': 0, 'defective': 2, 'incomplete': 0, 'dcv_failed': 0},
            'history': [{'run_timestamp': '2026-03-13', 'username': 'u',
                         'tls_status': 'defective', 'cert_expiry_days': None,
                         'defect_codes': [], 'impediments': []}],
            'next_steps': [],
        }
        AutosslRenderer.render_structure(result, 'text')
        out = capsys.readouterr().out
        assert 'Failing since' in out
        assert '2026-03-12' in out

    def test_renderer_no_failing_since_when_ok_exists(self, capsys):
        from reveal.adapters.autossl.renderer import AutosslRenderer
        result = {
            'type': 'autossl_domain_history',
            'domain': 'mixed.example.com',
            'run_count': 2,
            'truncated': False,
            'oldest_run_timestamp': '2026-03-12_03-00-00',
            'summary': {'ok': 1, 'defective': 1, 'incomplete': 0, 'dcv_failed': 0},
            'history': [{'run_timestamp': '2026-03-13', 'username': 'u',
                         'tls_status': 'ok', 'cert_expiry_days': 30,
                         'defect_codes': [], 'impediments': []}],
            'next_steps': [],
        }
        AutosslRenderer.render_structure(result, 'text')
        out = capsys.readouterr().out
        assert 'Failing since' not in out
