"""A URI answer is freed when its request ends, not by a later garbage collection (BACK-2674).

An Answer whose printer closed over the Answer itself formed a reference cycle, so the answer, and the adapter
its printer holds, outlived the request until the cyclic collector ran. On the MCP server that collection runs
during some later tool call, on whatever thread is current: a SQLiteAdapter's ``__del__`` then closed a
connection another thread created (``sqlite3.ProgrammingError``), and Python's "Exception ignored in" report
landed in that later call's captured stderr, as a second block after its JSON answer.
"""
import gc
import sqlite3
import sys
import threading
import weakref
from contextlib import closing, contextmanager, redirect_stderr, redirect_stdout
from io import StringIO

import pytest

from reveal import mcp_server
from reveal.adapters.sqlite.adapter import SQLiteAdapter
from reveal.cli.defaults import _default_args
from reveal.cli.routing import handle_uri

pytestmark = pytest.mark.component


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'proj').mkdir()
    (tmp_path / 'proj' / 'app.py').write_text('def main():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'proj' / 'old.py').write_text('def main():\n    return 0\n', encoding='utf-8')  # diff://'s other side
    with closing(sqlite3.connect(tmp_path / 'data.db')) as connection, connection:
        connection.execute('CREATE TABLE items (id INTEGER)')
    return tmp_path


@contextmanager
def _no_cyclic_collection():
    """Only reference counting frees objects inside the block, as between two collector runs."""
    gc.collect()
    enabled = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if enabled:
            gc.enable()


@pytest.fixture
def sqlite_adapters(monkeypatch):
    """Weak references to every SQLiteAdapter built while the test runs."""
    made = []
    original = SQLiteAdapter.__init__

    def recording(self, *args, **kwargs):
        original(self, *args, **kwargs)
        made.append(weakref.ref(self))

    monkeypatch.setattr(SQLiteAdapter, '__init__', recording)
    return made


# One request per Answer builder that printed through a closure: the structure answer (diff://, an undeclared
# noun, and ast:// and sqlite://, declared ones; sqlite since BACK-2626), the router's answer for a failed read, and the
# declared invalid-request answer.
REQUESTS = {'structure, undeclared noun': 'diff://proj/app.py:proj/old.py',
            'structure, declared noun': 'ast://proj',
            'structure, declared noun with a connection': 'sqlite://data.db',
            'router failure': 'sqlite://data.db/no_such_table',
            'declared invalid request': 'metrics://proj?limit=-1'}


@pytest.mark.parametrize('uri', list(REQUESTS.values()), ids=list(REQUESTS))
def test_an_answer_is_freed_when_the_request_ends(project, uri):
    answers = []

    def consume(answer):
        answers.append(weakref.ref(answer))
        answer.emit()

    with _no_cyclic_collection():
        with redirect_stdout(StringIO()) as out, redirect_stderr(StringIO()):
            try:
                handle_uri(uri, None, _default_args(path=uri, format='json'), answer_consumer=consume)
            except SystemExit:
                pass
        assert out.getvalue().strip().startswith('{'), out.getvalue()[:200]  # control: it answered
        assert len(answers) == 1
        assert answers[0]() is None, f'{uri}: the Answer outlived its request (a reference cycle keeps it)'


def test_the_sqlite_adapter_is_freed_on_the_thread_that_used_it(project, sqlite_adapters):
    uri = f'sqlite://{project / "data.db"}'  # declared (BACK-2626): ?bogus=1 is refused before an adapter exists
    replies = []
    with _no_cyclic_collection():
        worker = threading.Thread(target=lambda: replies.append(mcp_server.reveal_query(uri, provenance=True)))
        worker.start()
        worker.join(timeout=120)
        assert replies and str(replies[0]).lstrip().startswith('{'), replies  # control: it answered
        assert len(sqlite_adapters) == 1
        assert sqlite_adapters[0]() is None, 'the adapter (and its open connection) outlived the request'


def test_a_later_tool_call_keeps_no_stderr_from_an_earlier_request(project, monkeypatch):
    """The reported symptom: a collection during a later captured call must not add a stderr block to it."""
    # The server runs without pytest's unraisable-exception hook (it turns the report into a warning): restore
    # the interpreter's own, which writes "Exception ignored in ..." to the current sys.stderr.
    monkeypatch.setattr(sys, 'unraisablehook', sys.__unraisablehook__)
    uri = f'sqlite://{project / "data.db"}'  # declared (BACK-2626): ?bogus=1 is refused before an adapter exists
    with _no_cyclic_collection():
        worker = threading.Thread(target=lambda: mcp_server.reveal_query(uri, provenance=True))
        worker.start()
        worker.join(timeout=120)

        def later_call():
            gc.collect()  # the collector runs on this thread, inside the later call's capture
            print('{}')

        reply = mcp_server._run_and_capture(later_call)
    assert getattr(reply, 'stderr', '') == '' and 'Exception ignored' not in str(reply), str(reply)[:400]
    assert str(reply).strip() == '{}'
