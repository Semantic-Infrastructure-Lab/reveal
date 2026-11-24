"""MCP says a retired URI spelling's error once, with one label (BACK-2802).

``uri.handle_uri`` printed its own ``error: TEXT`` line and exited for a spelling at the error stage, a second owner of
the line ``main.run_contained`` prints; MCP ``reveal_run`` wraps the captured stderr of an exit, so a removed scheme read
``[reveal error: error: python:// was removed; ...]``, where a declared noun's error-stage spelling (which reaches the
process's one owner) reads ``[reveal error: TEXT]``. The CLI prints the one line either way (the control).
"""
from dataclasses import replace

import pytest

from conftest import _run_reveal_in
from reveal.cli.invocation import RETIREMENTS

APP = 'def main():\n    return 0\n'


@pytest.fixture
def proj(tmp_path):
    (tmp_path / 'app.py').write_text(APP, encoding='utf-8')
    return tmp_path


def _shown(argv):
    from reveal.mcp_server import reveal_run
    try:
        return str(reveal_run(argv))
    except Exception as exc:  # a raised tool error is the refusal on MCP; its text is the measured outcome
        return f'[reveal error: {exc}]'


@pytest.mark.parametrize('uri', ['python://', 'python://version'])
def test_mcp_says_a_removed_schemes_text_with_one_label(proj, monkeypatch, uri):
    monkeypatch.chdir(proj)
    assert _shown([uri]) == f"[reveal error: {RETIREMENTS['scheme:python'].text}]"


def test_mcp_says_an_error_stage_scheme_on_the_uri_route_with_one_label(proj, monkeypatch):
    """stats:// is answered by the URI route (no subcommand), as python:// was before its removal."""
    row = replace(RETIREMENTS['scheme:stats'], stage='error')
    monkeypatch.setitem(RETIREMENTS, 'scheme:stats', row)
    monkeypatch.chdir(proj)
    assert _shown(['stats://.']) == f'[reveal error: {row.text}]'


def test_control_a_declared_nouns_error_stage_flag_already_says_one_label(proj, monkeypatch):
    row = replace(RETIREMENTS['param:calls.top'], stage='error')
    monkeypatch.setitem(RETIREMENTS, 'param:calls.top', row)
    monkeypatch.chdir(proj)
    assert _shown(['calls', '.', '--sort=-callers', '--top', '3']) == f'[reveal error: {row.text}]'


def test_control_the_cli_prints_one_error_line(proj):
    result = _run_reveal_in(proj, 'python://')
    assert result.returncode == 2 and result.stdout == ''
    assert [line for line in result.stderr.splitlines() if 'python://' in line] == [
        f"error: {RETIREMENTS['scheme:python'].text}"]
