"""MCP gives a failed analysis (the CLI's exit 3) as a tool error in reveal's own words (BACK-2786, ruling 3a).

``reveal ast bad.xml`` exits 3: its JSON carries one ``analysis_failed`` warning whose authored ``message`` names the
file and the class of its cause. Over a registered MCP call, ``reveal_run`` and ``reveal_query`` said "Internal error
executing tool": the answer has no authored public diagnostic, so the server masked it, and the text it logged (and a
direct Python call returned) was the Python repr of the warnings list. The tool error is now the text the Python API
raises for the same answer (``results.analysis_failure_text``), and in JSON mode the CLI's JSON document exactly
(COMMAND_MODEL "Transports").

Called through the registered tool functions (what a client reaches, ``_raise_if_tool_failure`` included). Controls:
the path read keeps its own public text (``reveal_structure``, the parser's reason, BACK-2762); a failure with no
authored ``analysis_failed`` message stays masked (``json://`` of a malformed file, ``metrics`` of one file, whose
``error`` embeds the parser's text: ruling 3a leaves those masks unchanged); a clean request answers.
"""
import json
import os
import sys

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from conftest import _run_reveal_direct
from reveal import mcp_server
from reveal.utils.results import analysis_failure_text

pytestmark = pytest.mark.mcp

PREFIX = 'reveal error: '


@pytest.fixture
def fx(tmp_path, monkeypatch):
    (tmp_path / 'bad.xml').write_text('<root', encoding='utf-8')
    (tmp_path / 'broken.json').write_text('{bad', encoding='utf-8')
    (tmp_path / 'proj').mkdir()
    (tmp_path / 'proj' / 'app.py').write_text('def main():\n    return 1\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _registered(name):
    return mcp_server.mcp._tool_manager._tools[name].fn


def _cli_json(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run.returncode, json.loads(run.stdout)


def _tool_error(tool, **arguments):
    with pytest.raises(ToolError) as raised:
        _registered(tool)(**arguments)
    return str(raised.value)


def _assert_authored(text, document):
    expected = analysis_failure_text(document)
    assert expected, document
    assert 'Internal error' not in text
    assert text == PREFIX + expected
    assert '[{' not in text and "'type':" not in text


@pytest.mark.parametrize('tool, arguments, cli', [
    ('reveal_run', {'args': ['ast', 'bad.xml']}, ('ast', 'bad.xml')),
    ('reveal_run', {'args': ['ast://bad.xml']}, ('ast://bad.xml',)),
    ('reveal_query', {'uri': 'ast://bad.xml'}, ('ast://bad.xml',)),
], ids=['run-noun', 'run-uri', 'query-uri'])
def test_a_failed_analysis_is_a_tool_error_with_reveals_own_sentence(fx, tool, arguments, cli):
    code, document = _cli_json(*cli)
    assert code == 3
    _assert_authored(_tool_error(tool, **arguments), document)


def test_in_json_mode_the_tool_error_is_the_clis_json_document(fx):
    code, document = _cli_json('ast', 'bad.xml')
    assert code == 3
    text = _tool_error('reveal_run', args=['ast', 'bad.xml', '--format', 'json'])
    assert text.startswith(PREFIX), text
    assert json.loads(text[len(PREFIX):]) == document


@pytest.mark.skipif(sys.platform == 'win32', reason='chmod 000 does not deny reads on Windows')
def test_an_unreadable_file_names_its_cause_class_not_the_os_text(fx):
    if hasattr(os, 'geteuid') and os.geteuid() == 0:
        pytest.skip('root reads a chmod 000 file')
    locked = fx / 'proj' / 'locked.py'
    locked.write_text('def g():\n    return 2\n', encoding='utf-8')
    locked.chmod(0)
    try:
        code, document = _cli_json('calls', 'proj', '--callers', 'main')
        assert code == 3
        text = _tool_error('reveal_run', args=['calls', 'proj', '--callers', 'main'])
    finally:
        locked.chmod(0o644)
    _assert_authored(text, document)
    assert 'PermissionError' in text and 'Permission denied' not in text


def test_a_direct_call_returns_the_same_sentence_as_a_public_failure(fx):
    _, document = _cli_json('ast', 'bad.xml')
    result = mcp_server.reveal_run(['ast', 'bad.xml'])
    assert getattr(result, 'public', None) is True
    assert result == f'[{PREFIX}{analysis_failure_text(document)}]'


# --- controls ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('tool, arguments', [('reveal_structure', {'path': 'bad.xml'}),
                                             ('reveal_run', {'args': ['bad.xml']})], ids=['structure', 'run-path'])
def test_the_path_read_keeps_its_own_public_text(fx, tool, arguments):
    text = _tool_error(tool, **arguments)
    assert text.startswith(PREFIX + 'XML parse error: '), text


@pytest.mark.parametrize('args', [['json://broken.json'], ['metrics', 'bad.xml']], ids=['json-malformed', 'metrics-file'])
def test_a_failure_with_no_authored_analysis_message_stays_masked(fx, args):
    assert _tool_error('reveal_run', args=args).endswith('Internal error executing tool reveal_run')


def test_a_clean_request_answers(fx):
    assert 'main' in _registered('reveal_run')(args=['ast', 'proj'])
