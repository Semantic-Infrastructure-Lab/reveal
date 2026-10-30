"""Encoded AST resources cross the actual optional SDK stdio boundary."""

from urllib.parse import quote

import pytest

pytest.importorskip('mcp')
from test_mcp_expected_errors_back1992 import _run, _text

pytestmark = [pytest.mark.mcp, pytest.mark.component]


@pytest.mark.parametrize('provenance', [False, True])
def test_ast_encoded_resource_and_literal_structure_control(tmp_path, provenance):
    root = tmp_path / 'space Ω & % +'
    root.mkdir()
    path = root / 'app.py'
    path.write_text('def alpha():\n    return 1\n', encoding='utf-8')

    async def scenario(session):
        sibling = await session.call_tool('reveal_structure', {'path': path.as_posix()})
        assert not sibling.is_error
        assert 'alpha' in _text(sibling)
        answer = await session.call_tool('reveal_query', {
            'uri': 'ast://' + quote(root.as_posix(), safe='/:') + '?name=alpha',
            'provenance': provenance})
        assert not answer.is_error, _text(answer)
        assert 'alpha' in _text(answer)
        invalid = await session.call_tool('reveal_query', {
            'uri': 'ast://' + root.as_posix() + '/%FF', 'provenance': provenance})
        assert invalid.is_error
        assert _text(invalid).strip()

    _run(tmp_path, scenario)
