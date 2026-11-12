"""Catalog date scopes apply before canonical pages and reach native API readers."""
import json
import os

import pytest

from conftest import _run_reveal_in
from reveal.api import query
from test_claude_source_evidence_back2617 import transcript


@pytest.mark.parametrize('date_control,cutoff,expected', [('since', '2021-01-01', 2), ('until', '2021-01-01', 1)])
def test_catalog_dates_reach_api_and_both_command_forms_before_paging(transcript, date_control, cutoff, expected):
    os.utime(transcript, (1577836800, 1577836800))  # 2020-01-01 UTC
    api = query('claude://sessions', limit=0, **{date_control: cutoff})
    assert api['session_count'] == expected
    assert api['meta']['session_catalog']['analyzed_entries'] == 3
    for args in (['claude', 'sessions', '--' + date_control, cutoff, '--limit', '0'],
                 ['claude://sessions?' + date_control + '=' + cutoff + '&limit=0']):
        result = _run_reveal_in(transcript.parent, *args, '--format', 'json')
        assert result.returncode == 0
        answer = json.loads(result.stdout)
        assert answer['session_count'] == expected
        assert answer['meta']['pagination']['total'] == expected


def test_presentation_cannot_remove_native_catalog_date_scope(transcript, monkeypatch):
    from reveal.adapters.claude.adapter import ClaudeAdapter
    def post_process(self, result, args):
        result['scope'].pop('date_window')
        return result
    monkeypatch.setattr(ClaudeAdapter, 'post_process', post_process)
    result = _run_reveal_in(transcript.parent, 'claude://sessions?since=2021-01-01', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])
