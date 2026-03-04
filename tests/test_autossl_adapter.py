"""Tests for the autossl:// adapter."""

import json
import os
import pytest
from unittest.mock import patch

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
