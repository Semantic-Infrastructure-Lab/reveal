"""BACK-2093: ``reveal.api.check`` serves project-wide rule memos built before an edit.

I002's import-graph memo (``_graph_cache``) is a request-registered cache: a long-lived MCP
host revalidates it at every request, and ``reveal.api.query`` does since it runs as a host
request (``request_cache.host_request``). ``reveal.api.check`` took no request, so a library
host that broke an import cycle in place still got the cycle back from the second call. A
sibling MCP sequence and a reset are the controls.
"""

import os
import time

import pytest

from reveal import api, mcp_server
from reveal.utils import request_cache

pytestmark = pytest.mark.component


def write(path, source, *, age=60):
    """Files modified at or after a request start are never stamped as current."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding='utf-8')
    stamp = time.time_ns() - age * 1_000_000_000
    os.utime(path, ns=(stamp, stamp))


def cycle_findings(root):
    return [d for d in api.check(str(root / 'a.py'), select=['I002'])]


@pytest.fixture(autouse=True)
def memo_only(monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    request_cache._STAMPS.clear()
    yield
    request_cache._STAMPS.clear()


@pytest.fixture
def cycle(tmp_path):
    root = tmp_path / 'cyc'
    write(root / 'a.py', 'import b\n')
    write(root / 'b.py', 'import a\n')
    return root


def test_check_sees_a_cycle_broken_in_place(cycle):
    assert len(cycle_findings(cycle)) == 1
    write(cycle / 'b.py', 'x = 1\n', age=30)
    assert cycle_findings(cycle) == []


def test_unchanged_cycle_is_still_reported(cycle):
    assert len(cycle_findings(cycle)) == 1
    assert len(cycle_findings(cycle)) == 1


def test_mcp_sibling_sees_the_broken_cycle(cycle):
    first = mcp_server.reveal_check(str(cycle / 'a.py'), select='I002')
    assert 'I002' in first
    write(cycle / 'b.py', 'x = 1\n', age=30)
    assert 'I002' not in mcp_server.reveal_check(str(cycle / 'a.py'), select='I002')
