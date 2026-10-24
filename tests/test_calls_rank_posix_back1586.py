"""``calls ?rank=callers`` writes '/' in every record's ``file`` on every OS (BACK-1586).

``find_callers`` already serializes ``file`` through ``to_posix``; the ranking returned the
index's records as built, so a Windows run printed ``pkg\\a.py`` and a caller looked up by
the path the ranking printed no longer matched the one ``find_callers`` printed.
"""

from reveal.adapters.calls import index as calls_index


class _Index(dict):
    """The slice of CallersIndex ``rank_by_callers`` reads: items(), skipped."""

    skipped = ()


def test_rank_by_callers_records_name_their_file_with_forward_slashes(monkeypatch):
    # A record as the index builds it on Windows: the walker's native spelling.
    native = {'file': 'pkg\\a.py', 'caller': 'run', 'line': 3, 'call_expr': 'target'}
    monkeypatch.setattr(calls_index, 'build_callers_index', lambda path: _Index({'target': [native]}))

    ranked = calls_index.rank_by_callers('.', top=0)

    assert [rec['file'] for entry in ranked['entries'] for rec in entry['callers']] == ['pkg/a.py']


def test_rank_by_callers_keeps_a_forward_slash_file_as_it_is(monkeypatch):
    posix = {'file': 'pkg/a.py', 'caller': 'run', 'line': 3, 'call_expr': 'target'}
    monkeypatch.setattr(calls_index, 'build_callers_index', lambda path: _Index({'target': [posix]}))

    ranked = calls_index.rank_by_callers('.', top=0)

    assert [rec['file'] for entry in ranked['entries'] for rec in entry['callers']] == ['pkg/a.py']
