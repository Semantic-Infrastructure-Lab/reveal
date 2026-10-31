"""Routine cold rule discovery must not corrupt an MCP provenance value."""
import json

import pytest

from test_mcp_expected_errors_back1992 import _run, _text


def test_cold_metrics_provenance_is_one_json_value(tmp_path):
    pytest.importorskip('mcp')
    (tmp_path / 'pyproject.toml').write_text('[project]\nname="cold-metrics"\n', encoding='utf-8')
    (tmp_path / 'app.py').write_text('def work():\n    return 1\n', encoding='utf-8')

    async def scenario(session):
        uri = f'metrics://{tmp_path.as_posix()}?code_only=true'
        for _ in range(2):
            response = await session.call_tool('reveal_query', {'uri': uri, 'provenance': True})
            assert not response.is_error, _text(response)
            payload = json.loads(_text(response))
            assert payload['summary']['total_files'] == 1
            assert [row['file'] for row in payload['files']] == ['app.py']
            assert 'test_scope' not in payload

    _run(tmp_path, scenario)
