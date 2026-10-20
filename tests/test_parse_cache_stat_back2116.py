"""The parse cache and the structure disk cache key on the stat the content was read under
(BACK-2116).

The in-process parse cache keyed (abspath, mtime_ns) with no size, and both it and the
structure fingerprint were stat'ed after FileAnalyzer.__init__ had read the content. So an
edit that kept mtime_ns and changed the size got the old tree sliced by the new text (a
function named 'beta_'), and an edit landing between the read and the stat stored the old
structure under the new file's key, where every later process read it until the next edit.
The markdown heading index shares the fingerprint, so it had the same hole.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

import reveal
from reveal import treesitter as ts_mod
from reveal.core import disk_cache
from reveal.registry import get_analyzer

pytestmark = [pytest.mark.component, pytest.mark.disk_cache]

_REPO = Path(reveal.__file__).resolve().parent.parent
_MTIME_NS = 1_700_000_000_000_000_000

_FRESH_PROCESS = '''
import sys
from reveal.registry import get_analyzer
path = sys.argv[1]
structure = get_analyzer(path)(path).get_structure()
items = structure.get('headings') if path.endswith('.md') else structure.get('functions')
print(','.join(item['name'] for item in items or []))
'''


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    ts_mod._get_parse_cache().clear()
    yield
    ts_mod._get_parse_cache().clear()


def _names(analyzer):
    structure = analyzer.get_structure()
    items = structure.get('headings') if str(analyzer.path).endswith('.md') else structure.get('functions')
    return [item['name'] for item in items or []]


def _analyze(path):
    return _names(get_analyzer(str(path))(str(path)))


def _write(path, text, mtime_ns):
    path.write_text(text, encoding='utf-8')
    os.utime(path, ns=(mtime_ns, mtime_ns))


def _fresh_process_names(path, cache_dir):
    env = dict(os.environ, REVEAL_CACHE_DIR=str(cache_dir), REVEAL_DISK_CACHE='1',
               PYTHONPATH=os.pathsep.join(p for p in (str(_REPO), os.environ.get('PYTHONPATH')) if p))
    done = subprocess.run([sys.executable, '-c', _FRESH_PROCESS, str(path)], env=env,
                          capture_output=True, text=True, encoding='utf-8', timeout=120)
    assert done.returncode == 0, done.stderr
    return [name for name in done.stdout.strip().split(',') if name]


def test_a_same_mtime_edit_that_changes_the_size_is_parsed_again(tmp_path):
    src = tmp_path / 'mod.py'
    _write(src, 'def alpha():\n    return 1\n', _MTIME_NS)
    assert _analyze(src) == ['alpha']
    _write(src, 'def beta_longer_name():\n    return 2\n\ndef gamma():\n    return 3\n', _MTIME_NS)
    # the old (path, mtime_ns) key served alpha's tree sliced by the new text: ['beta_']
    assert _analyze(src) == ['beta_longer_name', 'gamma']
    assert _fresh_process_names(src, tmp_path / 'cache') == ['beta_longer_name', 'gamma']


@pytest.mark.parametrize('name, before, after, expected_before, expected_after', [
    ('mod.py', 'def old_one():\n    pass\n', 'def new_one():\n    pass\n\ndef new_two():\n    pass\n',
     ['old_one'], ['new_one', 'new_two']),
    ('doc.md', '# Old\n\ntext\n', '# New\n\ntext\n\n## Two\n\nmore\n', ['Old'], ['New', 'Two']),
], ids=['structure', 'markdown-headings'])
def test_an_edit_between_the_read_and_the_key_is_not_stored_under_the_new_key(
        tmp_path, name, before, after, expected_before, expected_after):
    src = tmp_path / name
    _write(src, before, _MTIME_NS)
    racing = get_analyzer(str(src))(str(src))  # reads the old content now
    _write(src, after, _MTIME_NS + 1_000_000_000)  # an editor saves before the analysis runs
    assert _names(racing) == expected_before  # it analyzes what it read
    # the old code stat'ed the key here, after the edit, and stored the old structure under it
    assert _fresh_process_names(src, tmp_path / 'cache') == expected_after


def test_touch_after_an_edit_the_stat_cannot_see_still_refreshes(tmp_path):
    src = tmp_path / 'mod.py'
    _write(src, 'def aaaa():\n    pass\n', _MTIME_NS)
    assert _analyze(src) == ['aaaa']
    _write(src, 'def bbbb():\n    pass\n', _MTIME_NS)  # same size, same mtime: invisible to a stat key
    _write(src, 'def bbbb():\n    pass\n', _MTIME_NS + 1_000_000_000)  # touch
    assert _analyze(src) == ['bbbb']
    assert _fresh_process_names(src, tmp_path / 'cache') == ['bbbb']


@pytest.mark.parametrize('name, text, namespace, expected', [
    ('mod.py', 'def alpha():\n    pass\n', 'structure', ['alpha']),
    ('doc.md', '# Title\n\n## Part\n', 'markdown-headings', ['Title', 'Part']),
], ids=['structure', 'markdown-headings'])
def test_an_unchanged_file_is_still_served_from_the_disk_cache(
        tmp_path, monkeypatch, name, text, namespace, expected):
    src = tmp_path / name
    _write(src, text, _MTIME_NS)
    assert _analyze(src) == expected
    ts_mod._get_parse_cache().clear()
    hits = []
    real_get = disk_cache.get

    def counting_get(ns, key):
        value = real_get(ns, key)
        if value is not None:
            hits.append(ns)
        return value

    monkeypatch.setattr(disk_cache, 'get', counting_get)
    analyzer = get_analyzer(str(src))(str(src))

    def _boom(*a, **k):
        raise AssertionError('a disk-cache hit parsed the file')

    monkeypatch.setattr(analyzer, '_parse_tree', _boom)
    assert _names(analyzer) == expected
    assert hits == [namespace]
