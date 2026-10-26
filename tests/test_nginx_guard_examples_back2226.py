"""BACK-2226: the nginx guard suggested `nginx://nginx.conf?check-acl=true`, which never worked
(nginx:// takes a domain and ignores query parameters: warning, then "No nginx config found"),
and help said the nginx:// scheme is "not yet implemented" although it exists.
"""
from reveal.adapters.help import HelpAdapter
from reveal.adapters.nginx.adapter import NginxUriAdapter


def test_guarded_flag_examples_only_show_forms_that_work():
    assert NginxUriAdapter.GUARDED_FLAGS
    for flag in NginxUriAdapter.GUARDED_FLAGS:
        assert 'nginx://' not in flag.examples, flag.flag
        assert flag.flag in flag.examples


def test_file_analyzer_help_does_not_deny_the_scheme_exists():
    info = HelpAdapter.__new__(HelpAdapter)._get_file_analyzer_help('nginx')
    assert 'not yet implemented' not in info['note']
    assert 'nginx://example.com' in info['note']


def test_negative_control_nginx_scheme_really_ignores_query_parameters(capsys):
    adapter = NginxUriAdapter('nginx.conf', 'check-acl=true')
    assert adapter.domain == 'nginx.conf'
    assert 'does not support query parameters' in capsys.readouterr().err
