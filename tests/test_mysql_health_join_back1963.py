"""Health checks consume the performance producer's measured ratios."""
import pytest

from reveal.adapters.mysql.adapter import MySQLAdapter
from reveal.adapters.mysql.performance import PerformanceAnalyzer


class SnapshotConnection:
    """One deterministic SQL snapshot; no credentials or server connection."""

    def __init__(self, ratios):
        scans, misses, disk = ratios
        self.status = {
            'Select_scan': scans, 'Select_range': 100 - scans,
            'Threads_created': misses, 'Connections': 100,
            'Created_tmp_disk_tables': disk, 'Created_tmp_tables': 100,
            'Questions': 1000, 'Threads_connected': 10, 'Max_used_connections': 20,
            'Open_files': 30, 'Innodb_buffer_pool_reads': 1,
            'Innodb_buffer_pool_read_requests': 1000,
        }

    def get_snapshot_context(self):
        return {'uptime_seconds': 100, 'snapshot_time': '2026-10-17T00:00:00+00:00'}

    def execute_query(self, query):
        if query == 'SHOW GLOBAL STATUS':
            values = self.status
        elif query == 'SHOW VARIABLES':
            values = {'max_connections': 100, 'open_files_limit': 100}
        else:
            raise AssertionError(f'unexpected SQL: {query}')
        return [{'Variable_name': key, 'Value': str(value)} for key, value in values.items()]

    def close(self):
        pass


def adapter_for(ratios=(80, 60, 70)):
    # Keep the real adapter delegation and producer; replace only server I/O.
    adapter = object.__new__(MySQLAdapter)
    adapter.conn = SnapshotConnection(ratios)
    adapter.performance = PerformanceAnalyzer(adapter.conn)
    adapter._load_health_check_config = lambda: {'checks': [
        {'name': name, 'metric': metric, 'pass_threshold': 50, 'warn_threshold': 75,
         'severity': severity, 'operator': '<'}
        for name, metric, severity in (
            ('scans', 'table_scan_ratio', 'high'),
            ('threads', 'thread_cache_miss_rate', 'medium'),
            ('disk', 'temp_disk_ratio', 'medium'),
            ('connections', 'connection_pct', 'low'))
    ]}
    return adapter


def test_measured_ratios_reach_configured_health_thresholds():
    answer = adapter_for().check()
    assert {row['name']: (row['value'], row['status']) for row in answer['checks']} == {
        'scans': ('80.0', 'failure'), 'threads': ('60.0', 'warning'),
        'disk': ('70.0', 'warning'), 'connections': ('10.0', 'pass'),
    }
    assert answer['summary'] == {'total': 4, 'passed': 1, 'warnings': 2, 'failures': 1}
    assert answer['status'] == 'failure' and answer['exit_code'] == 2


@pytest.mark.parametrize('controls', [{'only_failures': True}, {'severity': 'critical'}])
def test_display_filter_preserves_unfiltered_health_summary(controls):
    adapter = adapter_for()
    whole = adapter.check()
    shown = adapter.check(**controls)
    assert shown['exit_code'] == whole['exit_code'] == 2
    assert shown['summary'] == whole['summary'] == {
        'total': 4, 'passed': 1, 'warnings': 2, 'failures': 1}
    assert len(shown['checks']) == (3 if controls.get('only_failures') else 0)


@pytest.mark.parametrize('group,field', [
    ('full_table_scans', 'select_scan_ratio'),
    ('thread_cache_efficiency', 'miss_rate'),
    ('temp_tables', 'disk_ratio'),
])
def test_missing_required_producer_measurement_is_not_invented_as_zero(group, field):
    adapter = adapter_for()
    incomplete = adapter._get_performance()
    del incomplete[group][field]
    adapter._get_performance = lambda: incomplete
    with pytest.raises(KeyError, match=field):
        adapter.check()


def test_real_zero_remains_a_completed_pass():
    adapter = adapter_for((0, 0, 0))
    answer = adapter.check(only_failures=True)
    assert answer['checks'] == []
    assert answer['summary'] == {'total': 4, 'passed': 4, 'warnings': 0, 'failures': 0}
    assert answer['status'] == 'pass' and answer['exit_code'] == 0


def test_sibling_performance_view_keeps_measured_values():
    answer = adapter_for().get_element('performance')
    assert answer['full_table_scans']['select_scan_ratio'] == '80.00%'
    assert answer['thread_cache_efficiency']['miss_rate'] == '60.00%'
    assert answer['temp_tables']['disk_ratio'] == '70.00%'
    assert 'tuning_ratios' not in answer


def test_other_health_metrics_are_unchanged():
    metrics = adapter_for()._collect_health_metrics()
    assert metrics['connection_pct'] == 10
    assert metrics['max_used_connections_pct'] == 20
    assert metrics['open_files_pct'] == 30
    assert metrics['buffer_hit_rate'] == pytest.approx(99.9)
