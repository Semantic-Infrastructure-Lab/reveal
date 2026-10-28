"""AST owner evidence reaches real SDK stdio request and response conversion."""

import json

import pytest

from test_mcp_expected_errors_back1992 import _run, _text

pytestmark = [pytest.mark.mcp, pytest.mark.component]


@pytest.mark.parametrize('provenance', [False, True])
def test_ast_validation_partial_and_freshness_through_stdio(tmp_path, provenance):
    path = tmp_path / 'app.py'
    path.write_text('def alpha():\n    return 1\n', encoding='utf-8')

    async def scenario(session):
        invalid = await session.call_tool('reveal_query', {
            'uri': f'ast://{tmp_path}?name~=[', 'provenance': provenance})
        assert invalid.is_error
        assert 'regular expression' in _text(invalid)
        before = await session.call_tool('reveal_query', {
            'uri': f'ast://{tmp_path}', 'provenance': provenance})
        assert not before.is_error
        assert 'alpha' in _text(before)
        path.write_text('def beta():\n    return 2\n', encoding='utf-8')
        after = await session.call_tool('reveal_query', {
            'uri': f'ast://{tmp_path}', 'provenance': provenance})
        assert not after.is_error
        assert 'beta' in _text(after)
        assert 'alpha' not in _text(after)
        (tmp_path / 'broken.py').write_text('def broken(:\n', encoding='utf-8')
        partial = await session.call_tool('reveal_query', {
            'uri': f'ast://{tmp_path}', 'provenance': provenance})
        assert not partial.is_error
        assert 'beta' in _text(partial)
        assert 'incomplete' in _text(partial).lower()
        if provenance:
            answer = json.loads(_text(partial))
            assert answer['execution']['command']
            assert answer['type'] == 'ast_query'

    _run(tmp_path, scenario)
