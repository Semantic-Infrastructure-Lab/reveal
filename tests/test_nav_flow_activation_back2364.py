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
    assert 'ignored' not in result.stderr
    answer = json.loads(result.stdout)
    assert not any(w['type'] == 'retired_spelling' for w in answer.get('meta', {}).get('warnings', []))
    return answer


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
    result = _run_reveal_direct(path, '--flow', '--format', 'json')
    assert result.returncode == 0, result.stderr
    answer = json.loads(result.stdout)
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
        # L16 is in TRY (no branch gate); L18 is inside CATCH at L17.
        'returns': [{'line': 16, 'gate_lines': []}, {'line': 18, 'gate_lines': [17]}],
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


def test_nested_sibling_and_exception_gates_are_full_source_facts(tmp_path):
    path = tmp_path / 'nested.py'
    path.write_text('def work(a, b):\n if a:\n  if b:\n   return 1\n'
                    '  else:\n   return 2\n else:\n  try:\n   return 3\n'
                    '  except ValueError:\n   return 4\n return 5\n', encoding='utf-8')
    rows = _json(path, 'work', '--exits')['findings']
    a, b = {'line': 2, 'text': 'a'}, {'line': 3, 'text': 'b'}
    not_a, not_b = {'line': 2, 'text': 'not (a)'}, {'line': 3, 'text': 'not (b)'}
    assert rows == [
        {'kind': 'RETURN', 'line': 4, 'text': 'return 1', 'gates': [a, b]},
        {'kind': 'RETURN', 'line': 6, 'text': 'return 2', 'gates': [a, not_b]},
        {'kind': 'RETURN', 'line': 9, 'text': 'return 3', 'gates': [not_a]},
        {'kind': 'RETURN', 'line': 11, 'text': 'return 4',
         'gates': [not_a, {'line': 10, 'text': 'on exception'}]},
        {'kind': 'RETURN', 'line': 12, 'text': 'return 5', 'gates': []},
    ]


def test_root_inventory_and_one_line_range_retain_recorded_gates(tmp_path):
    path = tmp_path / 'region.py'
    path.write_text('def first(a):\n if a:\n  return 1\n return 2\n'
                    'def second():\n return 3\n', encoding='utf-8')
    first = {'kind': 'RETURN', 'line': 3, 'text': 'return 1', 'gates': [{'line': 2, 'text': 'a'}]}
    result = _run_reveal_direct(path, '--exits', '--format', 'json')
    answer = json.loads(result.stdout)
    assert answer['findings'] == [first,
        {'kind': 'RETURN', 'line': 4, 'text': 'return 2', 'gates': []},
        {'kind': 'RETURN', 'line': 6, 'text': 'return 3', 'gates': []}]
    assert answer['meta']['exit_scope']['mode'] == 'source_scope'
    selected = _json(path, 'first', '--exits', '--range', '3-3')
    literal = _json(path, ':3-3', '--exits')
    assert selected['findings'] == literal['findings'] == [first]
    assert selected['meta']['exit_scope']['mode'] == 'selected_callable'
    assert literal['meta']['exit_scope']['mode'] == 'source_scope'


def test_empty_flow_projection_retains_actual_depth_cut(tmp_path):
    path = tmp_path / 'depth.py'
    path.write_text('def work(a):\n try:\n  if a:\n   return 1\n'
                    ' except ValueError:\n  return 2\n', encoding='utf-8')
    answer = _json(path, 'work', '--flow=if', '--depth', '1')
    assert answer['findings'] == []
    assert answer['meta']['depth_limited'] is True
    assert [warning['type'] for warning in answer['meta']['warnings']] == ['depth_limited']


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


@pytest.mark.parametrize('flag', ['--flow', '--flow=if', '--exits'])
@pytest.mark.parametrize('fmt', ['text', 'json'])
def test_active_spellings_have_no_retirement_or_ignored_flag_note(tmp_path, flag, fmt):
    path = tmp_path / 'work.py'
    path.write_text('def work(a):\n if a:\n  return 1\n', encoding='utf-8')
    result = _run_reveal_direct(path, 'work', flag, '--format', fmt)
    assert result.returncode == 0
    assert 'deprecated' not in result.stderr
    assert 'ignored' not in result.stderr
    if fmt == 'json':
        assert not any(w['type'] in {'retired_spelling', 'ignored_flag'}
                       for w in json.loads(result.stdout)['meta'].get('warnings', []))


@pytest.mark.parametrize('flag', ['--flow', '--exits'])
@pytest.mark.parametrize('fmt', ['grep', 'typed'])
def test_flow_and_exits_reject_unsupported_formats(tmp_path, flag, fmt):
    path = tmp_path / 'work.py'
    path.write_text('def work():\n return 1\n', encoding='utf-8')
    result = _run_reveal_direct(path, 'work', flag, '--format', fmt)
    assert result.returncode == 2
    assert result.stdout == ''
    assert 'supported: text, json' in result.stderr


@pytest.mark.parametrize('flag', ['flow', 'exits'])
def test_registered_navigation_text_contract_overrides_cli_format_environment(tmp_path, monkeypatch, flag):
    pytest.importorskip('mcp')
    from test_mcp_expected_errors_back1992 import _run, _text
    monkeypatch.setenv('REVEAL_FORMAT', 'json')
    path = tmp_path / 'work.py'
    path.write_text('def work():\n return 1\n', encoding='utf-8')

    async def scenario(session):
        result = await session.call_tool('reveal_nav', {
            'path': str(path), 'element': 'work', 'flag': flag})
        assert not result.is_error
        assert not _text(result).lstrip().startswith('{')
        assert ('Navigation depth' if flag == 'flow' else 'Exit sites (static)') in _text(result)
        sibling = await session.call_tool('reveal_nav', {
            'path': str(path), 'element': 'work', 'flag': 'callsites'})
        assert not sibling.is_error
        assert not _text(sibling).lstrip().startswith('{')

    _run(tmp_path, scenario)


def test_cli_keeps_its_format_environment(monkeypatch):
    monkeypatch.setenv('REVEAL_FORMAT', 'json')
    result = _run_reveal_direct(_sample_path('python'), 'process_order', '--flow')
    assert result.returncode == 0
    assert json.loads(result.stdout)['meta']['flag'] == 'flow'
