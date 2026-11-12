"""Actual MCP transport for Git's declared query bindings."""
import json

import pytest

from test_git_declared_api_back2616 import repo_path
from test_mcp_expected_errors_back1992 import _run, _text

pytestmark = [pytest.mark.component, pytest.mark.mcp]


def test_sdk_canonical_controls_and_fresh_followup(repo_path):
    async def scenario(session):
        uri = f'git://{repo_path}?view=history'
        result = await session.call_tool('reveal_query', {
            'uri': uri + '&where=message%3Dchange%201', 'provenance': True})
        assert not result.is_error, _text(result)
        answer = json.loads(_text(result))
        assert answer['type'] == 'git_ref'
        assert [c['message'] for c in answer['history']] == ['change 1']
        invalid = await session.call_tool('reveal_query', {'uri': uri + '&where=message~%3D%5B'})
        # Git has not adopted D6 transport policy yet: retain legacy delivery while
        # proving that the new binding rejects the request and the next call recovers.
        assert 'regular expression' in _text(invalid)
        assert not invalid.is_error
        fresh = await session.call_tool('reveal_query', {'uri': uri + '&limit=0', 'provenance': True})
        assert not fresh.is_error and json.loads(_text(fresh))['history'] == []
    _run(repo_path, scenario)
