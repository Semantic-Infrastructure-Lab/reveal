"""MCP ``reveal_element`` answers as ``reveal PATH ELEMENT`` does (BACK-2775, D21, rulings S6 of BACK-2325).

The tool had its own extraction path: a miss said "element 'b' not found in bad.xml" for a file whose parse failed
(``reveal bad.xml b`` exits 3 naming the XML error), "no analyzer found for d" for a directory, and it answered under a
missing ``REVEAL_CONFIG`` the CLI refuses. Now it runs the CLI's own command line, as ``reveal_structure`` and
``reveal_run`` do: its text is the CLI's stdout (S6: nothing added or removed), a failed parse is a tool error naming the
cause, a miss names the miss with the CLI's hint, an invalid request is a tool error with the CLI's text.

The unaffected sibling is ``reveal_structure`` over the same files (its route moved in BACK-2762).
"""
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from reveal import mcp_server

pytestmark = pytest.mark.mcp

OK_PY = 'import os\n\n\ndef foo():\n    return 1\n\n\nclass K:\n    def m(self):\n        return os.sep\n'


@pytest.fixture
def fx(tmp_path, monkeypatch):
    files = {'ok.py': OK_PY, 'bad.xml': '<a><b></a>\n', 'bad.ipynb': 'nope', 'shape.ipynb': '[1, 2, 3]\n',
             'bad.docx': 'notzip', 'README.rst': 'Title\n=====\n'}
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding='utf-8')
    (tmp_path / 'd').mkdir()
    (tmp_path / 'd' / 'a.py').write_text(OK_PY, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _cli(path, element):
    """What ``reveal PATH ELEMENT`` answers through the MCP transport's command-line tool."""
    return mcp_server.reveal_run(['--format', 'text', '--', path, element])


def _registered(name):
    return mcp_server.mcp._tool_manager._tools[name].fn


@pytest.mark.parametrize('path, element, cause', [
    ('bad.xml', 'b', 'XML parse error'),
    ('bad.ipynb', 'x', 'Expecting value'),
    ('bad.docx', 'x', 'Invalid ZIP archive'),
    ('shape.ipynb', 'x', 'not a notebook'),
])
def test_a_file_that_could_not_be_read_names_the_cause(fx, path, element, cause):
    text = mcp_server.reveal_element(path, element)
    assert isinstance(text, mcp_server._ToolFailure)
    assert cause in text and 'not found' not in text
    assert text == _cli(path, element)
    with pytest.raises(ToolError, match=cause):
        _registered('reveal_element')(path=path, element=element)


def test_a_miss_names_the_miss_with_the_clis_hint(fx):
    text = mcp_server.reveal_element('ok.py', 'nosuch')
    assert isinstance(text, mcp_server._ToolFailure)
    assert "Element 'nosuch' not found in ok.py" in text
    assert 'Available: foo, m, K' in text
    assert text == _cli('ok.py', 'nosuch')


@pytest.mark.parametrize('path, element, says', [
    ('README.rst', 'Title', "No analyzer found for file 'README.rst'"),
    ('d', 'foo', "d is a directory; it has no element 'foo'"),
])
def test_an_invalid_request_is_a_tool_error_with_the_clis_text(fx, path, element, says):
    text = mcp_server.reveal_element(path, element)
    assert isinstance(text, mcp_server._ToolFailure) and says in text
    assert text == _cli(path, element)
    with pytest.raises(ToolError, match=says):
        _registered('reveal_element')(path=path, element=element)


def test_a_missing_reveal_config_is_refused(fx, monkeypatch):
    monkeypatch.setenv('REVEAL_CONFIG', str(fx / 'no-such-dir' / 'config.yaml'))
    text = mcp_server.reveal_element('ok.py', 'foo')
    assert isinstance(text, mcp_server._ToolFailure)
    assert text == _cli('ok.py', 'foo')


@pytest.mark.parametrize('element', ['foo', 'K.m', ':4'])
def test_an_element_is_the_clis_stdout(fx, element):
    text = mcp_server.reveal_element('ok.py', element)
    assert not isinstance(text, mcp_server._ToolFailure)
    assert text == _cli('ok.py', element)


# --- controls: the same before and after ---------------------------------------------------------------------------------

def test_control_a_missing_path_keeps_the_tools_own_check(fx):
    assert mcp_server.reveal_element('missing.py', 'foo') == '[reveal error: path not found: missing.py]'


def test_control_an_element_spelled_like_a_flag_is_an_element(fx):
    text = mcp_server.reveal_element('ok.py', '-x')
    assert isinstance(text, mcp_server._ToolFailure) and "'-x' not found" in text


def test_control_the_element_body_is_unchanged(fx):
    text = mcp_server.reveal_element('ok.py', 'foo')
    assert text.startswith('ok.py:4-5 | foo\n\n')
    assert '      4  def foo():\n      5      return 1' in text


@pytest.mark.parametrize('path, cause', [('bad.xml', 'XML parse error'), ('bad.docx', 'Invalid ZIP archive')])
def test_control_reveal_structure_names_the_same_cause(fx, path, cause):
    text = mcp_server.reveal_structure(path)
    assert isinstance(text, mcp_server._ToolFailure) and cause in text


def test_control_reveal_structure_answers_a_valid_file(fx):
    text = mcp_server.reveal_structure('ok.py')
    assert not isinstance(text, mcp_server._ToolFailure) and 'foo()' in text
