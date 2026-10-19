"""The recent-parse memo is per thread (BACK-2050).

reveal-mcp runs each tool call on its own worker thread. With language-pack 1.8.1 a tree-sitter
``Node`` is unsendable: walking a tree that another thread built panics (``PanicException``,
which is not an ``Exception``), the tool never answers, and the client times out. A
process-global memo of parse trees hands one thread's tree to the next.
"""
import threading

from reveal.core import treesitter_parse
from reveal.core.treesitter_parse import get_tree

_SOURCE = 'def f(x):\n    return x\n'


def _tree_on_a_new_thread():
    box = []
    worker = threading.Thread(target=lambda: box.append(get_tree('python', _SOURCE)))
    worker.start()
    worker.join()
    return box[0]


def test_another_thread_never_receives_this_threads_tree():
    treesitter_parse._parse_recent.cache_clear()
    mine = get_tree('python', _SOURCE)
    assert _tree_on_a_new_thread() is not mine


def test_a_thread_still_reuses_its_own_recent_parse():
    treesitter_parse._parse_recent.cache_clear()
    assert get_tree('python', _SOURCE) is get_tree('python', _SOURCE)


def test_cache_clear_and_the_physical_builder_stay_available():
    # tests that count or inject physical parses (BACK-1912, BACK-1914) use both
    assert callable(treesitter_parse._parse_recent.__wrapped__)
    treesitter_parse._parse_recent.cache_clear()


def test_the_bound_is_per_thread_and_small():
    treesitter_parse._parse_recent.cache_clear()
    first = get_tree('python', 'a = 0\n')
    for i in range(1, 6):
        get_tree('python', f'a = {i}\n')
    assert get_tree('python', 'a = 0\n') is not first, 'the oldest of 5 newer parses was evicted'
