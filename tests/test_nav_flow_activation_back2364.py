"""Source-authored qualification for the new flow/exits surface (feature work)."""
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from test_conformance_matrix import EXPECTED, _sample_path
from test_nav_flow_contract_back2364 import ROWS, _expected

pytestmark = pytest.mark.component

SELECTED = {'IF', 'ELIF', 'ELSE', 'UNLESS', 'SWITCH', 'CASE', 'DEFAULT',
            'FOR', 'WHILE', 'LOOP', 'DO', 'TRY', 'CATCH', 'EXCEPT', 'FINALLY'}


def _fixture(language):
    if language == 'tsx':
        return Path(__file__).parent / 'fixtures' / 'smoke' / 'tsx' / 'sample.tsx', 'processOrder'
    return _sample_path(language), EXPECTED[language]['entry_function']


def _json(path, element, *flags):
    result = _run_reveal_direct(path, element, *flags, '--format', 'json')
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize('language', sorted(ROWS))
@pytest.mark.parametrize('depth', [1, 3, 8])
def test_bare_flow_retains_source_reviewed_full_records(language, depth):
    path, element = _fixture(language)
    answer = _json(path, element, '--flow', '--depth', str(depth))
    assert answer['findings'] == _expected(language, depth)
    assert answer['meta']['flag'] == 'flow'
    assert answer['meta']['depth'] == depth


@pytest.mark.parametrize('language', sorted(ROWS))
def test_selector_union_deduplicates_full_records_in_source_order(language):
    path, element = _fixture(language)
    answer = _json(path, element, '--flow= try,if,loop,try ')
    assert answer['findings'] == [row for row in _expected(language) if row['keyword'] in SELECTED]
    assert answer['meta']['flow_selectors'] == ['try', 'if', 'loop']


@pytest.mark.parametrize('value', ['', ' ', ',', 'if,', ',try', 'if,,try', 'IF', 'all', 'bogus'])
def test_invalid_selector_rejects_before_resource_acquisition(tmp_path, value):
    result = _run_reveal_direct(tmp_path / 'missing.py', 'work', '--flow=' + value, '--format', 'json')
    assert result.returncode == 2
    assert result.stdout == ''
    assert 'selector' in result.stderr
    assert 'not found' not in result.stderr


@pytest.mark.parametrize('depth', ['0', '-1'])
def test_flow_uses_qualified_positive_depth(tmp_path, depth):
    path = tmp_path / 'work.py'
    path.write_text('def work():\n return 1\n', encoding='utf-8')
    result = _run_reveal_direct(path, 'work', '--flow', '--depth', depth)
    assert result.returncode == 2
    assert 'positive integer' in result.stderr


def test_file_only_flow_uses_literal_source_scope_and_preserves_file_outline(tmp_path):
    path = tmp_path / 'script.py'
    path.write_text('if ready:\n    launch()\n', encoding='utf-8')
    answer = _json(path, '', '--flow')
    assert [(r['keyword'], r['line_start']) for r in answer['findings']] == [('IF', 1)]
    assert answer['meta']['flag'] == 'flow'
    outline = _run_reveal_direct(path, '--outline', '--format', 'json')
    assert 'findings' not in json.loads(outline.stdout)


@pytest.mark.parametrize('language', sorted(ROWS))
def test_exits_preserve_source_kinds_and_expected_gate_lines(language):
    path, element = _fixture(language)
    answer = _json(path, element, '--exits')
    expected = EXPECTED[language] if language != 'tsx' else {
        'exits': [{'kind': 'RETURN', 'line': 16}, {'kind': 'RETURN', 'line': 18}],
        'returns': [{'line': 16, 'gate_lines': [15]}, {'line': 18, 'gate_lines': []}],
    }
    assert [{'kind': row['kind'], 'line': row['line']} for row in answer['findings']] == expected['exits']
    assert [{'line': row['line'], 'gate_lines': [gate['line'] for gate in row['gates']]}
            for row in answer['findings']] == expected['returns']
    assert all(set(row) == {'kind', 'line', 'text', 'gates'} for row in answer['findings'])
    assert all(set(gate) == {'line', 'text'} for row in answer['findings'] for gate in row['gates'])


def test_exits_full_gates_summary_and_empty_selection(tmp_path):
    path = tmp_path / 'work.py'
    path.write_text('def work(a):\n if a:\n  return 1\n return 2\n', encoding='utf-8')
    answer = _json(path, 'work', '--exits')
    assert answer['findings'] == [
        {'kind': 'RETURN', 'line': 3, 'text': 'return 1', 'gates': [{'line': 2, 'text': 'a'}]},
        {'kind': 'RETURN', 'line': 4, 'text': 'return 2', 'gates': []},
    ]
    text = _run_reveal_direct(path, 'work', '--exits').stdout
    assert 'Exit sites (static)' in text
    assert 'RETURN: 2' in text
    assert 'gate: a (L2)' in text
    assert 'unconditional' not in text
    empty = _run_reveal_direct(path, 'work', '--exits', '--range', '1-1')
    assert 'No exits recorded in this selection.' in empty.stdout


def test_registered_mcp_flow_values_and_invalid_selector(tmp_path):
    pytest.importorskip('mcp')
    from test_mcp_expected_errors_back1992 import _run, _text
    path = tmp_path / 'work.py'
    path.write_text('def work(a):\n if a:\n  return 1\n return 2\n', encoding='utf-8')

    async def scenario(session):
        bare = await session.call_tool('reveal_nav', {'path': str(path), 'element': 'work', 'flag': 'flow'})
        assert not bare.is_error
        assert 'RETURN' in _text(bare)
        union = await session.call_tool('reveal_nav', {
            'path': str(path), 'element': 'work', 'flag': 'flow', 'flag_value': 'if,loop,if'})
        assert not union.is_error
        assert 'IF' in _text(union)
        assert 'RETURN' not in _text(union)
        bad = await session.call_tool('reveal_nav', {
            'path': str(tmp_path / 'missing.py'), 'element': 'work', 'flag': 'flow', 'flag_value': 'if,'})
        assert bad.is_error
        assert 'selector' in _text(bad)
        sibling = await session.call_tool('reveal_nav', {
            'path': str(path), 'element': 'work', 'flag': 'callsites', 'flag_value': '2-3'})
        assert not sibling.is_error

    _run(tmp_path, scenario)
