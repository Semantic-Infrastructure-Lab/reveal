"""nginx flag handlers return a FlagOutput; only file_handler writes it out (BACK-916)."""
from types import SimpleNamespace

import pytest

from reveal import file_handler
from reveal.adapters.nginx import handlers


class _Analyzer:
    def detect_location_conflicts(self):
        return [{'severity': 'warning', 'server': 's', 'note': 'n',
                 'location_a': {'path': '/a', 'line': 1},
                 'location_b': {'path': '~ /a', 'line': 2}}]

    def extract_ssl_domains(self, canonical_only=False):
        return ['a.com']


def test_handler_returns_output_and_prints_nothing(capsys):
    out = handlers._handle_check_conflicts(_Analyzer())
    assert isinstance(out, handlers.FlagOutput)
    assert out.code == 2
    assert "Conflicts (1)" in out.stdout
    assert capsys.readouterr().out == ""


def test_unsupported_analyzer_is_an_error_on_stderr_not_stdout():
    out = handlers._handle_check_acl(object())
    assert out.code == 1 and out.out == []
    assert "--check-acl not supported for object" in out.stderr


def test_file_handler_writes_stdout_stderr_and_exit(capsys):
    with pytest.raises(SystemExit) as exc:
        file_handler._handle_check_conflicts(_Analyzer())
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "Conflicts (1)" in captured.out and captured.err == ''

    with pytest.raises(SystemExit) as exc:
        file_handler._handle_check_acl(object())
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == '' and "not supported" in captured.err


def test_clean_run_does_not_exit(capsys):
    file_handler._handle_extract_option(_Analyzer(), 'domains', args=SimpleNamespace())
    assert capsys.readouterr().out == "ssl://a.com\n"
