"""BACK-2276: ``meta.budget.next_cursor`` continues from the request's own ``?offset=``.

``--max-items`` cuts the adapter's page and writes ``next_cursor: offset=<returned>``. On a
request that already had ``?offset=M`` the adapter's page starts at item M, so the next page
is ``offset=M+returned``; the cursor said ``offset=<returned>`` and a paging loop that
followed it re-read the same page forever. Every adapter that applies ``?offset=``
(ast, markdown, metrics/stats, git log) shares the router's cut; one that does not take
``?offset=`` (calls://) must keep ``offset=<returned>``.
"""

import json

import pytest

from conftest import _run_reveal_direct
from reveal.utils.query_control import apply_budget_limits

pytestmark = pytest.mark.component


def _budget(uri, max_items):
    proc = _run_reveal_direct(uri, f'--max-items={max_items}', '--format=json')
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)['meta']['budget']


@pytest.fixture
def py_tree(tmp_path):
    root = tmp_path / 'src'
    root.mkdir()
    body = ''.join(f'def f{i}():\n    return {i}\n\n\n' for i in range(9))
    (root / 'm.py').write_text(body + 'def main():\n    f0()\n    f1()\n', encoding='utf-8')
    return root


@pytest.fixture
def md_tree(tmp_path):
    root = tmp_path / 'docs'
    root.mkdir()
    for i in range(7):
        (root / f'd{i}.md').write_text(f'---\ntitle: d{i}\n---\n# D{i}\n', encoding='utf-8')
    return root


def test_ast_cursor_adds_the_request_offset(py_tree):
    budget = _budget(f'ast://{py_tree.as_posix()}?type=function&offset=3', 2)
    assert budget['returned'] == 2
    assert budget['next_cursor'] == 'offset=5'


def test_markdown_cursor_adds_the_request_offset(md_tree):
    assert _budget(f'markdown://{md_tree.as_posix()}?offset=2', 2)['next_cursor'] == 'offset=4'


def test_metrics_cursor_adds_the_request_offset(py_tree):
    for i in range(6):
        (py_tree / f'extra{i}.py').write_text(f'X = {i}\n', encoding='utf-8')
    assert _budget(f'metrics://{py_tree.as_posix()}?offset=1', 3)['next_cursor'] == 'offset=4'


def test_git_log_cursor_adds_the_request_offset(tmp_path):
    pygit2 = pytest.importorskip('pygit2')
    root = tmp_path / 'repo'
    root.mkdir()
    repo = pygit2.init_repository(str(root))
    author = pygit2.Signature('Test', 'test@example.com')
    parents = []
    for i in range(8):
        (root / 'f.txt').write_text(f'{i}\n', encoding='utf-8')
        repo.index.add_all()
        repo.index.write()
        tree = repo.index.write_tree()
        parents = [repo.create_commit('HEAD', author, author, f'c{i}', tree, parents)]
    budget = _budget(f'git://{root.as_posix()}?type=log&offset=2', 3)
    assert budget['next_cursor'] == 'offset=5'


def test_following_the_cursor_reaches_the_next_page(py_tree):
    """The cursor's page is the one after the current page, never a repeat of it."""
    uri = f'ast://{py_tree.as_posix()}?type=function'
    proc = _run_reveal_direct(f'{uri}&sort=name', '--format=json')
    names = [r['name'] for r in json.loads(proc.stdout)['results']]
    page2 = _run_reveal_direct(f'{uri}&sort=name&offset=2', '--max-items=2', '--format=json')
    payload = json.loads(page2.stdout)
    assert [r['name'] for r in payload['results']] == names[2:4]
    cursor = payload['meta']['budget']['next_cursor']
    page3 = _run_reveal_direct(f'{uri}&sort=name&{cursor}', '--max-items=2', '--format=json')
    assert [r['name'] for r in json.loads(page3.stdout)['results']] == names[4:6]


# Negative controls: what must not change.

def test_no_offset_cursor_is_the_returned_count(py_tree):
    assert _budget(f'ast://{py_tree.as_posix()}?type=function', 2)['next_cursor'] == 'offset=2'


def test_adapter_without_offset_keeps_the_returned_count(py_tree):
    """calls:// does not take ?offset= (it warns and ignores it): its list is not shifted,
    so the cursor must not claim it was."""
    proc = _run_reveal_direct(f'calls://{py_tree.as_posix()}?uncalled&offset=3',
                              '--max-items=1', '--format=json')
    payload = json.loads(proc.stdout)
    assert payload['meta']['budget']['next_cursor'] == 'offset=1'


def test_budget_limits_offset_unit():
    items = [{'n': n} for n in range(10)]
    assert apply_budget_limits(items, max_items=3)['meta']['next_cursor'] == 'offset=3'
    assert apply_budget_limits(items, max_items=3, offset=7)['meta']['next_cursor'] == 'offset=10'
    assert 'next_cursor' not in apply_budget_limits(items, max_items=20, offset=7)['meta']


def test_page_start_is_not_a_read():
    """The router asking where the page starts must not tell the flag ledger the adapter
    used ``?offset=``: a view that ignores it still gets its "no effect" note."""
    from reveal.utils.query_control import parse_result_control
    _, control = parse_result_control('offset=4&limit=2')
    vars(control)['_reads'] = reads = set()
    assert control.page_start() == 4
    assert reads == set()
    assert control.offset == 4 and reads == {'offset'}  # a real read still counts
    assert parse_result_control('')[1].page_start() == 0
