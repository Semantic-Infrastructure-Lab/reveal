"""reveal-mcp over real stdio must carry non-ASCII source under an ASCII locale (BACK-1452).

tests/test_console_encoding.py covers the CLI only; the full ASCII-locale run that used to cover
reveal-mcp was dropped (BACK-1450). The child runs WITHOUT PYTHONIOENCODING (CI sets utf-8, which
hides this), with ``LC_ALL=C PYTHONUTF8=0``, and speaks JSON-RPC to the server's stdin/stdout.
"""
import json
import os
import queue
import subprocess
import sys
import threading

import pytest

pytest.importorskip('mcp')

pytestmark = [pytest.mark.mcp, pytest.mark.component]

_STRIPPED = ('PYTHONIOENCODING', 'PYTHONPYCACHEPREFIX', 'PYTHONUTF8', 'LC_ALL', 'LANG')
_REPLY_TIMEOUT = 60


def _ascii_locale_env():
    env = {k: v for k, v in os.environ.items() if k not in _STRIPPED}
    env.update(PYTHONUTF8='0', PYTHONCOERCECLOCALE='0', LC_ALL='C')
    return env


class _McpChild:
    """One reveal-mcp stdio server; ``call`` returns the raw reply line (bytes) and its JSON."""

    def __init__(self, stderr_file):
        self.proc = subprocess.Popen(
            [sys.executable, '-c', 'from reveal.mcp_server import main; main()'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr_file,
            env=_ascii_locale_env())
        self._lines = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        self._send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
            'protocolVersion': '2025-06-18', 'capabilities': {},
            'clientInfo': {'name': 'encoding-test', 'version': '0'}}})
        self._reply()
        self._send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})

    def _pump(self):
        for line in self.proc.stdout:
            self._lines.put(line)

    def _send(self, message):
        self.proc.stdin.write((json.dumps(message) + '\n').encode('ascii'))
        self.proc.stdin.flush()

    def _reply(self):
        raw = self._lines.get(timeout=_REPLY_TIMEOUT)
        return raw, json.loads(raw.decode('utf-8'))

    def call(self, name, arguments):
        self._send({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                    'params': {'name': name, 'arguments': arguments}})
        return self._reply()

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=15)
        except Exception:  # noqa: BLE001 - teardown: a stuck child must not hide the test result
            self.proc.kill()
            self.proc.wait(timeout=15)


@pytest.fixture
def non_ascii_py(tmp_path):
    f = tmp_path / 'a.py'
    f.write_text('def f():\n    return "❤ →"\n', encoding='utf-8')
    return f


@pytest.fixture
def child(tmp_path):
    with open(tmp_path / 'mcp-stderr.txt', 'wb') as err:
        c = _McpChild(err)
        try:
            yield c
        finally:
            c.close()


@pytest.mark.parametrize('tool, arguments', [
    ('reveal_element', lambda f: {'path': str(f), 'element': 'f'}),
    ('reveal_grep', lambda f: {'path': str(f.parent), 'pattern': 'return'}),
])
def test_tool_output_with_non_ascii_source_survives_ascii_locale(child, non_ascii_py, tool, arguments):
    raw, reply = child.call(tool, arguments(non_ascii_py))
    result = reply['result']
    assert not result['isError'], reply
    text = result['content'][0]['text']
    assert '❤ →' in text, text
    # The wire is UTF-8 (JSON-RPC), whatever the child's locale.
    assert '❤'.encode('utf-8') in raw or b'\\u2764' in raw


def test_config_edits_are_visible_between_live_requests(child, tmp_path):
    root = tmp_path / 'project'
    nested = root / 'nested'
    nested.mkdir(parents=True)
    path = nested / 'demo.py'
    path.write_text('VALUE = "' + 'x' * 80 + '"\n', encoding='utf-8')
    config = root / '.reveal.yaml'

    def threshold(value):
        config.write_text(f'root: true\nrules:\n  E501:\n    max_length: {value}\n', encoding='utf-8')

    def check(server):
        _, answer = server.call('reveal_check', {'path': str(path), 'select': 'E501'})
        assert not answer['result']['isError'], answer
        return answer['result']['content'][0]['text']

    threshold(20)
    assert '[E501]' in check(child)
    threshold(200)
    edited = check(child)
    assert edited == 'No issues found.'
    assert check(child) == edited
    with open(tmp_path / 'fresh-stderr.txt', 'wb') as err:
        fresh = _McpChild(err)
        try:
            assert check(fresh) == edited
        finally:
            fresh.close()
    config.unlink()
    # Removing the root config returns to the default 100-column threshold.
    path.write_text('VALUE = "' + 'x' * 110 + '"\n', encoding='utf-8')
    assert '[E501]' in check(child)
