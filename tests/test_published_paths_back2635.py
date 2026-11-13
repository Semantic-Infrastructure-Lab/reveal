"""Windows path spellings are portable even on the Linux regression runner."""
from pathlib import Path, PureWindowsPath

from reveal.adapters.calls.adapter import CallsAdapter
from reveal.adapters.claude.handlers.sessions import list_sessions, _collect_sessions_from_dir


def test_calls_answer_normalizes_query_path(monkeypatch):
    import reveal.adapters.calls.adapter as module
    monkeypatch.setattr(module, '_call_graph_meta', lambda *args, **kwargs: {'warnings': []})
    adapter = CallsAdapter('.', 'callers=sink')
    adapter.path = r'C:\project\src'
    answer = adapter._answer('calls_query', {'path': adapter.path, 'total_callers': 1})
    assert answer['path'] == 'C:/project/src'
    assert answer['source'] == 'C:/project/src'


def test_claude_catalog_source_serializes_windows_path(monkeypatch):
    import reveal.adapters.claude.handlers.sessions as module
    from reveal.adapters.claude.catalog import SessionEntries
    monkeypatch.setattr(module, 'collect_session_entries', lambda *args: SessionEntries())
    answer = list_sessions(PureWindowsPath('C:/home/.claude/projects'), {})
    assert answer['source'] == 'C:/home/.claude/projects'


def test_claude_catalog_transcript_serializes_windows_path(tmp_path, monkeypatch):
    import reveal.adapters.claude.handlers.sessions as module
    transcript = tmp_path / 'fixture.jsonl'
    transcript.write_text('{}\n', encoding='utf-8')
    original = module.Path
    # The publication value itself must work for a PureWindowsPath as on Windows.
    class Entry:
        name = 'fixture.jsonl'
        stem = 'fixture'
        def match(self, pattern): return pattern == '*.jsonl'
        def stat(self): return transcript.stat()
        def __str__(self): return r'C:\home\.claude\projects\proj\fixture.jsonl'
        def as_posix(self): return 'C:/home/.claude/projects/proj/fixture.jsonl'
    monkeypatch.setattr(module, 'directory_entries', lambda *args: [Entry()])
    rows = _collect_sessions_from_dir(original('proj'))
    assert rows[0]['path'] == 'C:/home/.claude/projects/proj/fixture.jsonl'
