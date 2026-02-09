"""Unit tests for MySQL health and performance metrics modules.

Tests for health.py HealthMetrics and performance.py PerformanceAnalyzer classes.
"""

import unittest
from unittest.mock import Mock, MagicMock
from datetime import datetime, timezone
from reveal.adapters.mysql.health import HealthMetrics
from reveal.adapters.mysql.performance import PerformanceAnalyzer


class TestHealthMetrics(unittest.TestCase):
    """Tests for HealthMetrics class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_conn = Mock()
        self.health = HealthMetrics(self.mock_conn)

    def test_get_server_uptime_info_days(self):
        """Test uptime calculation for multi-day uptime."""
        # 2 days, 3 hours, 5 minutes = 183900 seconds
        status_vars = {'Uptime': '183900'}
        self.mock_conn.execute_single.return_value = {'timestamp': '1000000'}

        days, hours, mins, start_time = self.health.get_server_uptime_info(status_vars)

        self.assertEqual(days, 2)
        self.assertEqual(hours, 3)
        self.assertEqual(mins, 5)
        self.assertIsInstance(start_time, datetime)
        self.assertEqual(start_time.tzinfo, timezone.utc)

    def test_get_server_uptime_info_hours_only(self):
        """Test uptime calculation for less than one day."""
        # 5 hours, 30 minutes = 19800 seconds
        status_vars = {'Uptime': '19800'}
        self.mock_conn.execute_single.return_value = {'timestamp': '1000000'}

        days, hours, mins, start_time = self.health.get_server_uptime_info(status_vars)

        self.assertEqual(days, 0)
        self.assertEqual(hours, 5)
        self.assertEqual(mins, 30)

    def test_get_server_uptime_info_zero_uptime(self):
        """Test uptime calculation for zero uptime."""
        status_vars = {'Uptime': '0'}
        self.mock_conn.execute_single.return_value = {'timestamp': '1000000'}

        days, hours, mins, start_time = self.health.get_server_uptime_info(status_vars)

        self.assertEqual(days, 0)
        self.assertEqual(hours, 0)
        self.assertEqual(mins, 0)

    def test_calculate_connection_health_healthy(self):
        """Test connection health with healthy metrics (< 80%)."""
        status_vars = {
            'Threads_connected': '50',
            'Max_used_connections': '75'
        }
        self.mock_conn.execute_single.return_value = {'Value': '100'}

        result = self.health.calculate_connection_health(status_vars)

        self.assertEqual(result['current'], 50)
        self.assertEqual(result['max'], 100)
        self.assertEqual(result['percentage'], 50.0)
        self.assertEqual(result['max_used_ever'], 75)
        self.assertEqual(result['max_used_pct'], 75.0)
        self.assertEqual(result['status'], '✅')
        self.assertEqual(result['max_used_status'], '✅')

    def test_calculate_connection_health_warning(self):
        """Test connection health with warning level (80-95%)."""
        status_vars = {
            'Threads_connected': '85',
            'Max_used_connections': '90'
        }
        self.mock_conn.execute_single.return_value = {'Value': '100'}

        result = self.health.calculate_connection_health(status_vars)

        self.assertEqual(result['percentage'], 85.0)
        self.assertEqual(result['status'], '⚠️')

    def test_calculate_connection_health_critical(self):
        """Test connection health with critical level (>= 95%)."""
        status_vars = {
            'Threads_connected': '96',
            'Max_used_connections': '100'
        }
        self.mock_conn.execute_single.return_value = {'Value': '100'}

        result = self.health.calculate_connection_health(status_vars)

        self.assertEqual(result['percentage'], 96.0)
        self.assertEqual(result['status'], '❌')
        self.assertEqual(result['max_used_status'], '⚠️')  # 100% triggers warning

    def test_calculate_connection_health_zero_max(self):
        """Test connection health with zero max connections (edge case)."""
        status_vars = {
            'Threads_connected': '0',
            'Max_used_connections': '0'
        }
        self.mock_conn.execute_single.return_value = {'Value': '0'}

        result = self.health.calculate_connection_health(status_vars)

        self.assertEqual(result['percentage'], 0)
        self.assertEqual(result['max_used_pct'], 0)

    def test_calculate_innodb_health_excellent(self):
        """Test InnoDB health with excellent hit rate (> 99%)."""
        status_vars = {
            'Innodb_buffer_pool_reads': '100',
            'Innodb_buffer_pool_read_requests': '100000',
            'Innodb_row_lock_waits': '5',
            'Innodb_deadlocks': '1'
        }

        result = self.health.calculate_innodb_health(status_vars)

        self.assertGreater(result['buffer_hit_rate'], 99)
        self.assertEqual(result['status'], '✅')
        self.assertEqual(result['row_lock_waits'], 5)
        self.assertEqual(result['deadlocks'], 1)

    def test_calculate_innodb_health_warning(self):
        """Test InnoDB health with warning level (95-99%)."""
        status_vars = {
            'Innodb_buffer_pool_reads': '3000',
            'Innodb_buffer_pool_read_requests': '100000',
            'Innodb_row_lock_waits': '10',
            'Innodb_deadlocks': '2'
        }

        result = self.health.calculate_innodb_health(status_vars)

        self.assertGreater(result['buffer_hit_rate'], 95)
        self.assertLess(result['buffer_hit_rate'], 99)
        self.assertEqual(result['status'], '⚠️')

    def test_calculate_innodb_health_critical(self):
        """Test InnoDB health with critical level (< 95%)."""
        status_vars = {
            'Innodb_buffer_pool_reads': '10000',
            'Innodb_buffer_pool_read_requests': '100000',
            'Innodb_row_lock_waits': '100',
            'Innodb_deadlocks': '20'
        }

        result = self.health.calculate_innodb_health(status_vars)

        self.assertLess(result['buffer_hit_rate'], 95)
        self.assertEqual(result['status'], '❌')
        self.assertEqual(result['row_lock_waits'], 100)
        self.assertEqual(result['deadlocks'], 20)

    def test_calculate_innodb_health_zero_requests(self):
        """Test InnoDB health with zero requests (edge case)."""
        status_vars = {
            'Innodb_buffer_pool_reads': '0',
            'Innodb_buffer_pool_read_requests': '0',
            'Innodb_row_lock_waits': '0',
            'Innodb_deadlocks': '0'
        }

        result = self.health.calculate_innodb_health(status_vars)

        self.assertEqual(result['buffer_hit_rate'], 0)
        # Should not crash on division by zero

    def test_calculate_resource_limits_healthy(self):
        """Test resource limits with healthy levels (< 75%)."""
        status_vars = {'Open_files': '500'}
        self.mock_conn.execute_single.return_value = {'Value': '1000'}

        result = self.health.calculate_resource_limits(status_vars)

        self.assertEqual(result['open_files']['current'], 500)
        self.assertEqual(result['open_files']['limit'], 1000)
        self.assertEqual(result['open_files']['percentage'], 50.0)
        self.assertEqual(result['open_files']['status'], '✅')

    def test_calculate_resource_limits_warning(self):
        """Test resource limits with warning level (75-90%)."""
        status_vars = {'Open_files': '800'}
        self.mock_conn.execute_single.return_value = {'Value': '1000'}

        result = self.health.calculate_resource_limits(status_vars)

        self.assertEqual(result['open_files']['percentage'], 80.0)
        self.assertEqual(result['open_files']['status'], '⚠️')

    def test_calculate_resource_limits_critical(self):
        """Test resource limits with critical level (>= 90%)."""
        status_vars = {'Open_files': '950'}
        self.mock_conn.execute_single.return_value = {'Value': '1000'}

        result = self.health.calculate_resource_limits(status_vars)

        self.assertEqual(result['open_files']['percentage'], 95.0)
        self.assertEqual(result['open_files']['status'], '❌')

    def test_calculate_resource_limits_zero_limit(self):
        """Test resource limits with zero limit (edge case)."""
        status_vars = {'Open_files': '0'}
        self.mock_conn.execute_single.return_value = {'Value': '0'}

        result = self.health.calculate_resource_limits(status_vars)

        self.assertEqual(result['open_files']['percentage'], 0)


class TestPerformanceAnalyzer(unittest.TestCase):
    """Tests for PerformanceAnalyzer class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_conn = Mock()
        self.analyzer = PerformanceAnalyzer(self.mock_conn)

    def _setup_status_vars(self, **overrides):
        """Helper to create status vars dict with defaults."""
        defaults = {
            'Uptime': '100000',
            'Questions': '50000',
            'Slow_queries': '10',
            'Select_scan': '500',
            'Select_range': '5000',
            'Handler_read_rnd_next': '1000',
            'Threads_created': '100',
            'Connections': '10000',
            'Created_tmp_disk_tables': '200',
            'Created_tmp_tables': '1000',
            'Sort_merge_passes': '5',
            'Innodb_buffer_pool_reads': '1000',
            'Innodb_buffer_pool_read_requests': '100000',
            'Innodb_row_lock_waits': '10',
            'Innodb_row_lock_time_avg': '5',
            'Innodb_deadlocks': '2',
        }
        defaults.update(overrides)
        return [{'Variable_name': k, 'Value': v} for k, v in defaults.items()]

    def test_get_performance_healthy_metrics(self):
        """Test performance metrics with healthy values."""
        self.mock_conn.execute_query.return_value = self._setup_status_vars(
            Select_scan='500',  # 9% scan ratio (healthy)
            Threads_created='500',  # 5% miss rate (healthy)
            Created_tmp_disk_tables='200',  # 20% disk ratio (healthy)
        )
        self.mock_conn.execute_single.return_value = {'timestamp': '1000000'}

        result = self.analyzer.get_performance()

        self.assertEqual(result['type'], 'performance')
        self.assertIn('measurement_window', result)
        self.assertIn('server_start_time', result)
        self.assertIn('queries_per_second', result)
        self.assertIn('slow_queries_total', result)
        self.assertIn('full_table_scans', result)
        self.assertEqual(result['full_table_scans']['status'], '✅')
        self.assertIn('thread_cache_efficiency', result)
        self.assertEqual(result['thread_cache_efficiency']['status'], '✅')
        self.assertIn('temp_tables', result)
        self.assertEqual(result['temp_tables']['status'], '✅')

    def test_get_performance_warning_scans(self):
        """Test performance with warning level full table scans (10-25%)."""
        self.mock_conn.execute_query.return_value = self._setup_status_vars(
            Select_scan='1500',  # 15% scan ratio (warning)
            Select_range='8500',
        )
        self.mock_conn.execute_single.return_value = {'timestamp': '1000000'}

        result = self.analyzer.get_performance()

        self.assertEqual(result['full_table_scans']['status'], '⚠️')

    def test_get_performance_critical_scans(self):
        """Test performance with critical level full table scans (>= 25%)."""
        self.mock_conn.execute_query.return_value = self._setup_status_vars(
            Select_scan='3000',  # 30% scan ratio (critical)
            Select_range='7000',
        )
        self.mock_conn.execute_single.return_value = {'timestamp': '1000000'}

        result = self.analyzer.get_performance()

        self.assertEqual(result['full_table_scans']['status'], '❌')

    def test_get_performance_warning_thread_cache(self):
        """Test performance with warning level thread cache miss rate (10-25%)."""
        self.mock_conn.execute_query.return_value = self._setup_status_vars(
            Threads_created='1500',  # 15% miss rate (warning)
            Connections='10000',
        )
        self.mock_conn.execute_single.return_value = {'timestamp': '1000000'}

        result = self.analyzer.get_performance()

        self.assertEqual(result['thread_cache_efficiency']['status'], '⚠️')

    def test_get_performance_critical_thread_cache(self):
        """Test performance with critical level thread cache miss rate (>= 25%)."""
        self.mock_conn.execute_query.return_value = self._setup_status_vars(
            Threads_created='3000',  # 30% miss rate (critical)
            Connections='10000',
        )
        self.mock_conn.execute_single.return_value = {'timestamp': '1000000'}

        result = self.analyzer.get_performance()

        self.assertEqual(result['thread_cache_efficiency']['status'], '❌')

    def test_get_performance_warning_temp_tables(self):
        """Test performance with warning level temp table disk ratio (25-50%)."""
        self.mock_conn.execute_query.return_value = self._setup_status_vars(
            Created_tmp_disk_tables='400',  # 40% disk ratio (warning)
            Created_tmp_tables='1000',
        )
        self.mock_conn.execute_single.return_value = {'timestamp': '1000000'}

        result = self.analyzer.get_performance()

        self.assertEqual(result['temp_tables']['status'], '⚠️')

    def test_get_performance_critical_temp_tables(self):
        """Test performance with critical level temp table disk ratio (>= 50%)."""
        self.mock_conn.execute_query.return_value = self._setup_status_vars(
            Created_tmp_disk_tables='600',  # 60% disk ratio (critical)
            Created_tmp_tables='1000',
        )
        self.mock_conn.execute_single.return_value = {'timestamp': '1000000'}

        result = self.analyzer.get_performance()

        self.assertEqual(result['temp_tables']['status'], '❌')

    def test_get_performance_zero_select_total(self):
        """Test performance with zero select total (edge case)."""
        self.mock_conn.execute_query.return_value = self._setup_status_vars(
            Select_scan='0',
            Select_range='0',
        )
        self.mock_conn.execute_single.return_value = {'timestamp': '1000000'}

        result = self.analyzer.get_performance()

        # Should not crash on division by zero
        self.assertIn('full_table_scans', result)

    def test_get_performance_zero_connections(self):
        """Test performance with zero connections (edge case)."""
        self.mock_conn.execute_query.return_value = self._setup_status_vars(
            Connections='1',  # Avoid division by zero
            Threads_created='0',
        )
        self.mock_conn.execute_single.return_value = {'timestamp': '1000000'}

        result = self.analyzer.get_performance()

        # Should not crash
        self.assertIn('thread_cache_efficiency', result)

    def test_get_performance_zero_tmp_tables(self):
        """Test performance with zero temp tables (edge case)."""
        self.mock_conn.execute_query.return_value = self._setup_status_vars(
            Created_tmp_disk_tables='0',
            Created_tmp_tables='1',  # Avoid division by zero
        )
        self.mock_conn.execute_single.return_value = {'timestamp': '1000000'}

        result = self.analyzer.get_performance()

        # Should not crash
        self.assertIn('temp_tables', result)

    def test_get_innodb_healthy(self):
        """Test InnoDB metrics with healthy buffer hit rate."""
        self.mock_conn.execute_query.return_value = self._setup_status_vars(
            Innodb_buffer_pool_reads='100',  # 99.9% hit rate
            Innodb_buffer_pool_read_requests='100000',
        )
        self.mock_conn.execute_single.return_value = {'timestamp': '1000000'}

        result = self.analyzer.get_innodb()

        self.assertEqual(result['type'], 'innodb')
        self.assertIn('buffer_pool_hit_rate', result)
        self.assertIn('99', result['buffer_pool_hit_rate'])  # Should be > 99%
        self.assertIn('buffer_pool_reads', result)
        self.assertIn('row_lock_waits', result)
        self.assertIn('deadlocks', result)

    def test_get_innodb_poor_hit_rate(self):
        """Test InnoDB metrics with poor buffer hit rate."""
        self.mock_conn.execute_query.return_value = self._setup_status_vars(
            Innodb_buffer_pool_reads='50000',  # 50% hit rate
            Innodb_buffer_pool_read_requests='100000',
        )
        self.mock_conn.execute_single.return_value = {'timestamp': '1000000'}

        result = self.analyzer.get_innodb()

        self.assertIn('50', result['buffer_pool_hit_rate'])

    def test_get_innodb_zero_requests(self):
        """Test InnoDB metrics with zero requests (edge case)."""
        self.mock_conn.execute_query.return_value = self._setup_status_vars(
            Innodb_buffer_pool_reads='0',
            Innodb_buffer_pool_read_requests='0',
        )
        self.mock_conn.execute_single.return_value = {'timestamp': '1000000'}

        result = self.analyzer.get_innodb()

        # Should not crash on division by zero
        self.assertIn('buffer_pool_hit_rate', result)

    def test_get_performance_uptime_calculation(self):
        """Test uptime calculation in performance metrics."""
        self.mock_conn.execute_query.return_value = self._setup_status_vars(
            Uptime='183900',  # 2 days, 3 hours
        )
        self.mock_conn.execute_single.return_value = {'timestamp': '1000000'}

        result = self.analyzer.get_performance()

        self.assertIn('2d', result['measurement_window'])
        self.assertIn('3h', result['measurement_window'])

    def test_get_innodb_uptime_calculation(self):
        """Test uptime calculation in InnoDB metrics."""
        self.mock_conn.execute_query.return_value = self._setup_status_vars(
            Uptime='183900',  # 2 days, 3 hours
        )
        self.mock_conn.execute_single.return_value = {'timestamp': '1000000'}

        result = self.analyzer.get_innodb()

        self.assertIn('2d', result['measurement_window'])
        self.assertIn('3h', result['measurement_window'])


if __name__ == '__main__':
    unittest.main()
