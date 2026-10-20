"""Tree-sitter trees and nodes never cross threads through a cache (BACK-2115).

reveal-mcp runs each tool call on its own worker thread (anyio starts one, the call
finishes, the next call may land on another). With language-pack 1.8.1 a tree-sitter
``Tree``/``Node`` is unsendable: walking one that another thread built raises
``PanicException`` (a ``BaseException``), and dropping one on another thread raises an
unraisable ``RuntimeError``. Any process-wide cache of trees or nodes hands one call's
objects to the next. BACK-2050 made the recent-parse memo per thread; these caches were
still process-wide: markdown's inline-parse cache, the rules' tree-sitter parse lru and
kind index, and ``tree_root``'s root memo.

The two ``reveal_check`` tests panic only on the 1.8.1 binding (newer packs' nodes are
sendable); the identity tests below them fail on any binding when a cache is shared.
"""
import gc
import sys
import threading

import pytest

from reveal import mcp_server
from reveal.analyzers.markdown import MarkdownAnalyzer
from reveal.core import get_tree, tree_root
from reveal.core.treesitter_compat import _ROOT_MEMO_MAX
from reveal.rules.base_mixins import TreeSitterParsingMixin, _kind_buckets, kind_nodes

pytestmark = pytest.mark.mcp

_MD = '# T\n\nSee [a](missing.md) and `code` and [b](#nope).\n'
_JS = ('function f(a) {\n  try { g(a); } catch (e) {}\n'
       '  if (a) { if (a > 1) { if (a > 2) { return 1; } } }\n  return 0;\n}\n')


def _on_new_thread(fn):
    """Run fn on a fresh thread, started and joined before the next (as anyio dispatches).
    Returns (result, BaseException or None): a PanicException is not an Exception."""
    box = {}

    def run():
        try:
            box['result'] = fn()
        except BaseException as e:  # noqa: BLE001 - PanicException derives from BaseException
            box['error'] = e

    worker = threading.Thread(target=run)
    worker.start()
    worker.join()
    return box.get('result'), box.get('error')


def _two_requests(path):
    return [_on_new_thread(lambda: mcp_server.reveal_check(str(path))) for _ in range(2)]


def test_mcp_check_of_a_markdown_file_answers_on_the_next_thread(tmp_path):
    doc = tmp_path / 'doc.md'
    doc.write_text(_MD, encoding='utf-8')
    (first, first_error), (second, second_error) = _two_requests(doc)
    assert first_error is None, repr(first_error)
    assert 'L001' in first, first  # positive control: the request did reach the link rule
    assert second_error is None, f'request 2 raised {type(second_error).__name__}: {second_error}'
    assert second == first


def test_mcp_check_of_a_javascript_file_answers_on_the_next_thread(tmp_path):
    src = tmp_path / 'app.js'
    src.write_text(_JS, encoding='utf-8')
    (first, first_error), (second, second_error) = _two_requests(src)
    assert first_error is None, repr(first_error)
    assert 'B006' in first, first  # positive control: a tree-sitter rule ran on the file
    assert second_error is None, f'request 2 raised {type(second_error).__name__}: {second_error}'
    assert second == first


def test_a_markdown_inline_tree_is_never_handed_to_another_thread(tmp_path):
    doc = tmp_path / 'doc.md'
    doc.write_text(_MD, encoding='utf-8')
    mine = MarkdownAnalyzer(str(doc)).inline_tree
    assert mine is not None
    theirs, error = _on_new_thread(lambda: MarkdownAnalyzer(str(doc)).inline_tree is mine)
    assert error is None, repr(error)
    assert theirs is False, 'a new thread received this thread\'s markdown_inline tree'
    # negative control: a second analyzer on the same thread still shares the one parse
    assert MarkdownAnalyzer(str(doc)).inline_tree is mine


def test_a_rule_parse_is_never_handed_to_another_thread(tmp_path):
    path = str(tmp_path / 'app.js')
    mixin = TreeSitterParsingMixin()
    mine = mixin._parse_treesitter(_JS, path, 'javascript')
    assert mine is not None
    theirs, error = _on_new_thread(lambda: mixin._parse_treesitter(_JS, path, 'javascript') is mine)
    assert error is None, repr(error)
    assert theirs is False, 'a new thread received this thread\'s tree-sitter root'
    # negative control: rules on one thread still share one root, so the kind index hits
    assert mixin._parse_treesitter(_JS, path, 'javascript') is mine


def test_the_kind_index_is_kept_per_thread():
    root = tree_root(get_tree('javascript', _JS))
    assert kind_nodes(root, 'catch_clause')
    size, error = _on_new_thread(lambda: _kind_buckets.cache_info().currsize)
    assert error is None, repr(error)
    assert size == 0, f'a new thread sees {size} kind-index entries built on another thread'


def test_another_threads_parses_never_evict_this_threads_root(monkeypatch):
    unraisable = []
    monkeypatch.setattr(sys, 'unraisablehook', lambda info: unraisable.append(repr(info.exc_value)))
    tree = get_tree('python', 'mine = 1\n')
    root = tree_root(tree)

    def fill_own_memo():
        for i in range(_ROOT_MEMO_MAX + 1):
            tree_root(get_tree('python', f'theirs_{i} = {i}\n'))

    _, error = _on_new_thread(fill_own_memo)
    assert error is None, repr(error)
    assert tree_root(tree) is root, 'another thread\'s parses evicted (and dropped) this thread\'s root'
    assert not [u for u in unraisable if 'another thread' in u], unraisable


def test_markdown_node_lookups_leave_no_cyclic_garbage_holding_nodes(tmp_path):
    """Nodes in a reference cycle are dropped by whichever thread the collector next runs on:
    on the 1.8.1 binding, an unraisable RuntimeError per node when that is not the thread that
    built them (two per two-thread reveal_check of a .md file, from the link lookup)."""
    doc = tmp_path / 'doc.md'
    doc.write_text(_MD, encoding='utf-8')
    analyzer = MarkdownAnalyzer(str(doc))
    gc.collect()
    gc.set_debug(gc.DEBUG_SAVEALL)
    try:
        links = analyzer.get_structure(extract_links=True)['links']
        gc.collect()
        holding = [type(o).__name__ for o in gc.garbage
                   if isinstance(o, list) and any(type(x).__name__ == 'Node' for x in o)]
    finally:
        gc.set_debug(0)
        gc.garbage.clear()
    assert [link['url'] for link in links] == ['missing.md', '#nope']  # positive control
    assert holding == [], f'{len(holding)} unreachable list(s) of nodes left for the cycle collector'
