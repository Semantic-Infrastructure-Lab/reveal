"""Logical-depth and visible-pruning controls for navigation (BACK-2388)."""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.ast.nav import element_outline
from reveal.core.treesitter_compat import _zero_arg, ts_parse, tree_root
from reveal.core import node_children
from tree_sitter_language_pack import get_parser
from test_nav_flow_contract_back2364 import ROWS, _context, _answer
from reveal.nav_handlers import _nav_outline

pytestmark = pytest.mark.conformance


def _python_outline(source, depth):
    tree = ts_parse(get_parser('python'), source)
    node = next(iter(node_children(tree_root(tree))))
    data = source.encode('utf-8')
    def text(n):
        return data[_zero_arg(n, 'start_byte'):_zero_arg(n, 'end_byte')].decode('utf-8')
    return element_outline(node, text, max_depth=depth)


@pytest.mark.parametrize('language', sorted(ROWS))
def test_depth_one_retains_all_logical_peer_records(language):
    expected = [dict(zip(('type', 'keyword', 'label', 'line_start', 'line_end', 'depth', 'is_exit'), row))
                for row in ROWS[language] if row[5] == 1]
    assert _answer(_context(language, 1), _nav_outline) == expected


@pytest.mark.parametrize('depth,expected', [
    (1, [('IF', 2, 1), ('ELSE', 10, 1), ('RETURN', 12, 1)]),
    (2, [('IF', 2, 1), ('TRY', 3, 2), ('EXCEPT', 5, 2), ('FINALLY', 7, 2),
         ('ELSE', 10, 1), ('RETURN', 11, 2), ('RETURN', 12, 1)]),
])
def test_nested_alternatives_keep_logical_depth_without_deeper_bodies(depth, expected):
    source = ('def f(a):\n    if a:\n        try:\n            return 1\n'
              '        except ValueError:\n            return 2\n        finally:\n'
              '            return 3\n        a = 0\n    else:\n        return 4\n    return 5\n')
    actual = _python_outline(source, depth)
    assert [(r['keyword'], r['line_start'], r['depth']) for r in actual] == expected
    assert all(r['depth'] <= depth for r in actual)


SOURCE = ('def work(a):\n    try:\n        if a:\n            return 1\n'
          '    except ValueError:\n        return 2\n    return 3\n')


def _file(tmp_path, source=SOURCE):
    p = tmp_path / 'example.py'
    p.write_text(source, encoding='utf-8')
    return p


def _run_json(path, flag='--outline', *extra):
    result = _run_reveal_direct(path, 'work', flag, '--depth', '1', '--format', 'json', *extra)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize('flag', ['--outline', '--ifmap', '--catchmap', '--loopmap', '--fanout'])
def test_depth_budget_is_visible_even_when_projection_is_empty(tmp_path, flag):
    answer = _run_json(_file(tmp_path), flag)
    assert answer['meta']['depth'] == 1
    assert answer['meta']['depth_limited'] is True
    warnings = [w for w in answer['meta']['warnings'] if w['type'] == 'depth_limited']
    assert len(warnings) == 1
    assert 'depth' in warnings[0]['message'].lower()
    assert 'total' not in warnings[0]  # The unvisited subtrees have no exact count.


def test_text_shows_requested_depth_and_one_pruning_note(tmp_path):
    result = _run_reveal_direct(_file(tmp_path), 'work', '--outline', '--depth', '1')
    assert result.returncode == 0, result.stderr
    assert 'depth 1' in result.stdout.lower()
    assert 'EXCEPT' in result.stdout
    assert result.stdout.lower().count('limited by depth') == 1


@pytest.mark.parametrize('flag', ['--outline', '--ifmap', '--catchmap', '--loopmap', '--fanout'])
def test_range_filtering_alone_does_not_claim_depth_pruning(tmp_path, flag):
    answer = _run_json(_file(tmp_path), flag, '--range', '7-7')
    assert answer['meta']['depth'] == 1
    assert answer['meta']['depth_limited'] is False
    assert not any(w.get('type') == 'depth_limited' for w in answer['meta'].get('warnings', []))


@pytest.mark.parametrize('source', [
    'def work(a):\n    return a\n',
    'def work(a):\n    if a:\n        pass\n',
])
def test_complete_shallow_skeleton_has_no_pruning_warning(tmp_path, source):
    answer = _run_json(_file(tmp_path, source))
    assert answer['meta']['depth_limited'] is False
    assert not any(w.get('type') == 'depth_limited' for w in answer['meta'].get('warnings', []))


def test_depth_cut_evidence_does_not_leak_to_next_call(tmp_path):
    p = _file(tmp_path)
    assert _run_json(p)['meta']['depth_limited'] is True
    complete = _run_reveal_direct(p, 'work', '--outline', '--depth', '8', '--format', 'json')
    assert complete.returncode == 0, complete.stderr
    answer = json.loads(complete.stdout)
    assert answer['meta']['depth'] == 8
    assert answer['meta']['depth_limited'] is False


def test_pruned_parent_overlap_does_not_invent_hidden_selector_findings(tmp_path):
    answer = _run_json(_file(tmp_path), '--loopmap', '--range', '4-4')
    assert answer['findings'] == []
    assert answer['meta']['depth_limited'] is True
    message = answer['meta']['warnings'][0]['message']
    assert 'not inspected' in message
    assert 'showing' not in message and 'hidden loops' not in message


def test_collector_inspects_each_visited_subtree_once(monkeypatch):
    from collections import Counter
    from reveal.adapters.ast import nav_outline

    visits = Counter()
    original = nav_outline._children
    def counted(node):
        key = (_zero_arg(node, 'start_byte'), _zero_arg(node, 'end_byte'), _zero_arg(node, 'kind'))
        visits[key] += 1
        return original(node)
    monkeypatch.setattr(nav_outline, '_children', counted)
    rows = _python_outline(SOURCE, 1)
    assert [r['keyword'] for r in rows] == ['TRY', 'EXCEPT', 'RETURN']
    assert max(visits.values()) == 1
    # The IF is the first recognized subtree beyond the budget. Its body is
    # not traversed again to count or characterize hidden selector findings.
    assert not any(kind == 'if_statement' for _, _, kind in visits)


def test_nested_definition_body_obeys_its_depth_budget():
    source = ('def work(a):\n    def inner():\n        if a:\n            return 1\n'
              '    return 2\n')
    rows = _python_outline(source, 1)
    assert [(r['keyword'], r['line_start'], r['depth']) for r in rows] == [
        ('DEF', 2, 1), ('RETURN', 5, 1),
    ]
