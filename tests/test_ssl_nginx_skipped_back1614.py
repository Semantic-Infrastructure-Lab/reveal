"""BACK-1614: ssl://nginx:// names a config it could not read instead of
returning fewer domains (or "no ssl_certificate directives") as if complete."""

import pytest

from reveal.adapters.ssl import adapter as ssl_adapter
from reveal.adapters.ssl.adapter import SSLAdapter
from reveal.adapters.ssl.renderer import SSLRenderer

_GOOD = 'server {\n    listen 443 ssl;\n    server_name good.example.com;\n    ssl_certificate /x/cert.pem;\n}\n'


@pytest.fixture
def conf_dir(tmp_path, monkeypatch):
    (tmp_path / 'good.conf').write_text(_GOOD, encoding='utf-8')
    (tmp_path / 'bad.conf').write_text(_GOOD.replace('good', 'bad'), encoding='utf-8')
    real = ssl_adapter.NginxAnalyzer

    def _analyzer(path):
        if path.endswith('bad.conf'):
            raise PermissionError(13, 'Permission denied')
        return real(path)

    monkeypatch.setattr(ssl_adapter, 'NginxAnalyzer', _analyzer)
    return tmp_path


def test_domains_name_the_skipped_config(conf_dir, capsys):
    result = SSLAdapter(f'ssl://nginx://{conf_dir.as_posix()}/*.conf').get_structure()
    assert result['domains'] == ['good.example.com']
    skipped, = result['files_skipped']
    assert skipped['file'].endswith('bad.conf') and skipped['error'].startswith('PermissionError')
    SSLRenderer._render_ssl_nginx_domains(result)
    assert '⚠ Skipped' in capsys.readouterr().out


def test_cert_check_says_configs_were_unreadable(conf_dir):
    (conf_dir / 'good.conf').unlink()
    adapter = SSLAdapter(f'ssl://nginx://{conf_dir.as_posix()}/*.conf')
    result = adapter._check_nginx_cert_files()
    assert result['error'].startswith('No nginx config could be read')
    assert len(result['files_skipped']) == 1
