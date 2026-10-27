"""--check prints every percentage metric as a percentage (BACK-2213).

The default check names 'Max Used Connections %', 'Open Files %' and 'Current Connection %'
contain none of 'rate', 'ratio' or 'pct', so their values printed as a raw float
(85.33333333333333) next to a threshold written as '<80%'.
"""
import pytest

pytest.importorskip('pymysql')

from reveal.adapters.mysql.adapter import HealthCheckThresholds, MySQLAdapter  # noqa: E402


def _evaluate(name, value, operator='<', pass_threshold=80, warn_threshold=100):
    adapter = MySQLAdapter('mysql://localhost')
    thresholds = HealthCheckThresholds(pass_threshold=pass_threshold, warn_threshold=warn_threshold,
                                       severity='critical', operator=operator)
    return adapter._evaluate_health_check(name, value, thresholds)


@pytest.mark.parametrize('name', ['Max Used Connections %', 'Open Files %', 'Current Connection %',
                                  'Thread Cache Miss Rate', 'Table Scan Ratio'])
def test_percentage_checks_format_value_with_percent_sign(name):
    assert _evaluate(name, 85.33333333333333)['value'] == '85.33%'


def test_non_percentage_check_value_is_unchanged():
    # Control: a metric whose name is not a percentage keeps its plain value.
    assert _evaluate('Replication Lag Seconds', 5, pass_threshold=10, warn_threshold=60)['value'] == '5'
