"""MCP gives a help page that names nothing as a tool error with the CLI's sentence (BACK-2798, BACK-2787).

``reveal help://ast/bogus`` exits 2: an invalid request (D6) whose answer teaches "Unknown section 'bogus'. Sections of
ast: ...". Over a registered MCP call, ``reveal_run`` and ``reveal_query`` said "Internal error executing tool": the help
adapter declared no public diagnostic, so the MCP server treated the failure as an unauthored one and masked it.
COMMAND_MODEL "Transports": the outcome is the CLI's own, and an invalid request is the caller's to fix, so the client
gets the CLI's sentence.

Called through the registered tool functions (what a client reaches, ``_raise_if_tool_failure`` included), not the
module-level Python functions. Siblings: a page that exists answers, and a topic that is no page at all keeps its own
public message.
"""
import json

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from conftest import _run_reveal_direct
from reveal import mcp_server

pytestmark = pytest.mark.mcp

PAGES = ['help://ast/bogus', 'help://schemas/bogus']


def _registered(name):
    return mcp_server.mcp._tool_manager._tools[name].fn


def _cli_message(uri):
    run = _run_reveal_direct(uri, '--format', 'json')
    assert run.returncode == 2, run.stderr
    return json.loads(run.stdout)['message']


@pytest.mark.parametrize('uri', PAGES)
@pytest.mark.parametrize('tool', ['reveal_run', 'reveal_query'])
def test_a_page_that_names_nothing_is_a_tool_error_with_the_clis_sentence(uri, tool):
    message = _cli_message(uri)
    arguments = {'args': [uri]} if tool == 'reveal_run' else {'uri': uri}
    with pytest.raises(ToolError) as raised:
        _registered(tool)(**arguments)
    text = str(raised.value)
    assert 'Internal error' not in text
    assert message in text


def test_a_page_that_exists_answers():
    assert 'workflows' in _registered('reveal_run')(args=['help://ast']).lower()


def test_a_topic_that_is_no_page_keeps_its_own_public_message():
    with pytest.raises(ToolError, match="Element 'nosuchtopic' not found"):
        _registered('reveal_run')(args=['help://nosuchtopic'])
