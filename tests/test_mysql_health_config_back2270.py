"""BACK-2270: mysql health-check thresholds load without a deprecation line on every run.

Before: `MySQLAdapter._load_health_check_config` went through the deprecated
`reveal.config.load_config`, which logs "load_config('mysql-health-checks.yaml') is
deprecated. Use RevealConfig.get() instead." at WARNING, so every `reveal mysql://... --check`
printed it on stderr.
"""

import logging

import pytest

from reveal.adapters.mysql.adapter import MySQLAdapter
from reveal.config import RevealConfig

_CUSTOM = (
    "checks:\n"
    "  - name: Table Scan Ratio\n"
    "    metric: table_scan_ratio\n"
    "    pass_threshold: 3\n"
    "    warn_threshold: 7\n"
    "    severity: high\n"
    "    operator: '<'\n"
)


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    root = tmp_path / 'proj'
    root.mkdir()
    monkeypatch.chdir(root)
    RevealConfig.reset_request_cache()
    yield root
    RevealConfig.reset_request_cache()


def _load(caplog):
    adapter = object.__new__(MySQLAdapter)  # no server: only the config loader runs
    with caplog.at_level(logging.DEBUG):
        return adapter._load_health_check_config()


def test_project_file_loads_without_deprecation_warning(project, caplog):
    (project / '.reveal').mkdir()
    (project / '.reveal' / 'mysql-health-checks.yaml').write_text(_CUSTOM, encoding='utf-8')
    config = _load(caplog)
    assert config['checks'] == [{
        'name': 'Table Scan Ratio', 'metric': 'table_scan_ratio', 'pass_threshold': 3,
        'warn_threshold': 7, 'severity': 'high', 'operator': '<',
    }]
    assert not [r for r in caplog.records if 'deprecated' in r.getMessage()], caplog.text


def test_defaults_without_a_file_and_without_deprecation_warning(project, caplog):
    """Negative control on the thresholds: no file still yields the seven built-in checks."""
    config = _load(caplog)
    thresholds = {c['metric']: (c['pass_threshold'], c['warn_threshold']) for c in config['checks']}
    assert thresholds == {
        'table_scan_ratio': (10, 25), 'thread_cache_miss_rate': (10, 25),
        'temp_disk_ratio': (25, 50), 'max_used_connections_pct': (80, 100),
        'open_files_pct': (75, 90), 'connection_pct': (80, 95), 'buffer_hit_rate': (99, 95),
    }
    assert not [r for r in caplog.records if 'deprecated' in r.getMessage()], caplog.text
