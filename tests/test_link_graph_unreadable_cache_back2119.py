"""The markdown link-graph disk cache never keeps a read failure the content did not cause (BACK-2119).

``build_link_graph`` stored ``unreadable_files`` inside the cached graph. A file that could not
be read (``PermissionError``) left that note in the entry, and ``chmod`` moves only ctime, so the
entry's key (relpath, mtime_ns, size) stayed valid: after the permission was fixed every later
call still answered ``unreadable`` with the file's edges missing, until the file was touched. The
rule BACK-2083/BACK-2084 gave the imports caches applies: an environmental failure is returned
but not stored; a failure the bytes cause (not UTF-8) is the same answer every time, so it may be
stored and must still be disclosed on a hit.
"""
from pathlib import Path

import pytest

from reveal.adapters.markdown import operations
from reveal.core import disk_cache

pytestmark = [pytest.mark.component, pytest.mark.disk_cache]


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """a.md -> b.md, cache dir beside the tree; returns the tree root."""
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')
    root = tmp_path / 'docs'
    root.mkdir()
    (root / 'a.md').write_bytes(b'# A\n\nSee [b](b.md).\n')
    (root / 'b.md').write_bytes(b'# B\n')
    return root


@pytest.fixture
def deny(monkeypatch):
    """Files whose text read raises PermissionError (portable stand-in for chmod 000)."""
    denied = set()
    real = Path.read_text

    def read_text(self, *args, **kwargs):
        if self.name in denied:
            raise PermissionError(13, 'Permission denied', str(self))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', read_text)
    return denied


@pytest.fixture
def hits(monkeypatch):
    """Count of disk_cache.get calls that returned a stored entry."""
    counter = {'n': 0}
    real = disk_cache.get

    def get(namespace, key):
        value = real(namespace, key)
        if value is not None:
            counter['n'] += 1
        return value

    monkeypatch.setattr(disk_cache, 'get', get)
    return counter


def _unreadable(graph):
    return {rel for rel, _ in graph.get('unreadable_files', [])}


def test_permission_fix_is_seen_without_touching_the_file(corpus, deny, hits):
    deny.add('a.md')
    first = operations.build_link_graph(corpus)
    assert _unreadable(first) == {'a.md'}
    assert first['total_edges'] == 0

    deny.clear()  # the chmod fix: mtime and size unchanged
    second = operations.build_link_graph(corpus)
    assert 'unreadable_files' not in second, "a stored environmental failure was served"
    assert second['total_edges'] == 1
    assert hits['n'] == 0, "the failed build must not have been stored"


def test_environmental_failure_is_reported_again_while_it_persists(corpus, deny, hits):
    deny.add('a.md')
    operations.build_link_graph(corpus)
    again = operations.build_link_graph(corpus)
    assert _unreadable(again) == {'a.md'}
    assert hits['n'] == 0


def test_backlinks_answer_follows_the_permission_fix(corpus, deny):
    deny.add('a.md')
    assert operations.get_backlinks(corpus, 'b.md')['linked_by'] == []
    deny.clear()
    assert operations.get_backlinks(corpus, 'b.md')['linked_by'] == ['a.md']


def test_content_caused_failure_is_stored_and_still_disclosed_on_a_hit(corpus, hits):
    (corpus / 'a.md').write_bytes(b'\xff\xfe not utf-8 [b](b.md)\n')
    first = operations.build_link_graph(corpus)
    assert _unreadable(first) == {'a.md'}
    assert hits['n'] == 0

    second = operations.build_link_graph(corpus)
    assert hits['n'] == 1, "unchanged undecodable bytes fail the same way, so the entry may be served"
    assert _unreadable(second) == {'a.md'}
    assert second['unreadable_files'][0][1].startswith('UnicodeDecodeError')
    assert operations.get_backlinks(corpus, 'b.md')['unreadable_files'] == second['unreadable_files']


def test_clean_graph_is_still_stored_and_served(corpus, hits):
    first = operations.build_link_graph(corpus)
    second = operations.build_link_graph(corpus)
    assert hits['n'] == 1
    assert second == first
    assert second['total_edges'] == 1 and 'unreadable_files' not in second
