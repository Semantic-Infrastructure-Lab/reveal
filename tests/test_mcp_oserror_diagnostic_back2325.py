"""MCP says an unreadable file's cause as the CLI does, not ``str(OSError)`` (ruling S5 of BACK-2325).

Since the path read's unreadable-file Answer carries its ``PermissionError`` (the Python API raises it), MCP's outcome
mapping read ``str(exception)`` first: ``[Errno 13] Permission denied: 'denied.py'``, a Python spelling with the path in
it, where the CLI says ``Error: cannot read denied.py: Permission denied`` and MCP said that too before. Now an answer
that carries both an ``OSError`` and its owner's public diagnostic answers the diagnostic; an ``OSError`` alone still
answers its text, and nothing else moves.

Sibling: ``reveal_nav`` on the same file, which always said the CLI's line.
"""
import os
import sys

import pytest

from reveal import api, mcp_server
from reveal.cli.routing.uri import Answer
from reveal.errors import ConfigLoadError
from reveal.utils.results import FailureCause, failure_execution_facts

pytestmark = pytest.mark.mcp

POSIX_ONLY = pytest.mark.skipif(sys.platform == 'win32', reason='chmod 000 has no effect on Windows')
NOT_ROOT = pytest.mark.skipif(hasattr(os, 'geteuid') and os.geteuid() == 0, reason='root reads a mode-000 file')

THE_CLIS_LINE = '[reveal error: Error: cannot read denied.py: Permission denied]'


@pytest.fixture
def denied(tmp_path, monkeypatch):
    path = tmp_path / 'denied.py'
    path.write_text('def x():\n    pass\n', encoding='utf-8')
    os.chmod(path, 0)
    monkeypatch.chdir(tmp_path)
    yield path
    os.chmod(path, 0o644)


@POSIX_ONLY
@NOT_ROOT
@pytest.mark.parametrize('call', [
    lambda: mcp_server.reveal_structure('denied.py'),
    lambda: mcp_server.reveal_run(['denied.py']),
    lambda: mcp_server.reveal_element('denied.py', 'x'),
    lambda: mcp_server.reveal_run(['denied.py', 'x']),
], ids=['reveal_structure', 'reveal_run file', 'reveal_element', 'reveal_run element'])
def test_an_unreadable_file_says_the_clis_line(denied, call):
    text = call()
    assert isinstance(text, mcp_server._ToolFailure) and text.public
    assert text == THE_CLIS_LINE


@POSIX_ONLY
@NOT_ROOT
def test_control_reveal_nav_says_the_same_line(denied):
    assert mcp_server.reveal_nav('denied.py', 'x', 'boundary') == THE_CLIS_LINE


@POSIX_ONLY
@NOT_ROOT
def test_control_the_python_api_still_raises_the_cause(denied):
    with pytest.raises(PermissionError):
        api.analyze('denied.py')


def _answer(exception=None, diagnostic=None):
    return Answer({}, 'router', lambda *_a, **_k: None, execution_facts=failure_execution_facts(FailureCause.ANALYSIS),
                  exception=exception, public_diagnostic=diagnostic)


def test_an_oserror_beside_a_public_diagnostic_answers_the_diagnostic():
    failure = mcp_server._declared_failure(_answer(PermissionError(13, 'Permission denied', 'f.py'),
                                                   'Error: cannot read f.py: Permission denied'))
    assert failure == '[reveal error: Error: cannot read f.py: Permission denied]' and failure.public


def test_control_an_oserror_alone_answers_its_text():
    failure = mcp_server._declared_failure(_answer(PermissionError(13, 'Permission denied', 'f.py')))
    assert failure == "[reveal error: [Errno 13] Permission denied: 'f.py']" and failure.public


def test_control_a_config_load_error_keeps_its_text():
    failure = mcp_server._declared_failure(_answer(ConfigLoadError('bad config'), 'a diagnostic'))
    assert 'bad config' in failure and 'a diagnostic' not in failure and failure.public


def test_control_another_exception_stays_masked():
    failure = mcp_server._declared_failure(_answer(RuntimeError('PRIVATE'), 'a diagnostic'))
    assert not failure.public
