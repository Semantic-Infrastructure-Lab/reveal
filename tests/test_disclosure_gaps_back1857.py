"""Small disclosure gaps from the BACK-1059 reports (BACK-1857)."""
from unittest.mock import patch

from reveal.adapters.cpanel.adapter import CpanelAdapter
from reveal.adapters.mysql.renderer import _performance_schema_text


def test_ps_status_error_is_unknown_not_disabled():
    text = _performance_schema_text({'enabled': False, 'error': 'performance_schema status query failed: 1142'})
    assert text.startswith('unknown (') and '1142' in text


def test_ps_status_reset_check_error_keeps_the_enabled_state():
    text = _performance_schema_text({'enabled': True, 'error': 'digest query failed: gone'})
    assert text.startswith('enabled (') and 'gone' in text


def test_ps_status_plain_states():
    assert _performance_schema_text({'enabled': True}) == 'enabled'
    assert _performance_schema_text({'enabled': False}) == 'disabled'


@patch('reveal.adapters.cpanel.adapter._list_user_domains', return_value=[])
@patch('os.path.exists', return_value=True)
def test_full_audit_nginx_error_is_a_failure(_exists, _domains):
    with patch('reveal.analyzers.nginx.NginxAnalyzer', side_effect=OSError('conf unreadable')):
        result = CpanelAdapter('cpanel://myuser/full-audit').get_structure()
    assert result['nginx']['error'] == 'conf unreadable'
    assert result['has_failures'] is True
