"""Store-wide candidate acquisition must retain usable entries and discovery loss."""
from pathlib import Path

import pytest

from reveal.api import query
from test_claude_source_evidence_back2617 import transcript, deny_scan


@pytest.mark.parametrize('resource', ['sessions', 'sessions?search=auth', 'files//home/user/proj/auth.py'])
def test_project_enumeration_loss_survives_catalog_consumers(transcript, monkeypatch, resource):
    blocked = transcript.parent.parent / 'blocked-project'
    blocked.mkdir()
    deny_scan(monkeypatch, blocked)
    answer = query('claude://' + resource)
    proof = answer['meta']['session_catalog']
    assert proof['candidate_entries'] == proof['analyzed_entries'] == 3
    assert proof['failed_entries'] == 0 and proof['discovery_failures'] == 1
    assert any(w['code'] == 'analysis_incomplete' for w in answer['meta']['warnings'])
    assert not answer.get('error')


def test_metadata_failure_keeps_other_entries_from_the_same_project(transcript, monkeypatch):
    original = Path.stat
    def stat(path, *args, **kwargs):
        if path == transcript:
            raise PermissionError('injected metadata failure')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', stat)
    answer = query('claude://sessions')
    assert not answer.get('error')
    assert answer['session_count'] == 2
    proof = answer['meta']['session_catalog']
    assert (proof['candidate_entries'], proof['analyzed_entries'], proof['failed_entries']) == (3, 2, 1)


def test_root_enumeration_loss_is_not_an_empty_catalog(transcript, monkeypatch):
    root = transcript.parent.parent
    original = Path.iterdir
    def entries(path):
        if path == root:
            raise PermissionError('injected root enumeration failure')
        return original(path)
    monkeypatch.setattr(Path, 'iterdir', entries)
    # The constructor must not do transcript lookup for a store resource.
    answer = query('claude://sessions')
    assert answer['session_count'] == 0
    proof = answer['meta']['session_catalog']
    assert proof['analyzed_entries'] == 0 and proof['discovery_failures'] == 1
    assert any(w['code'] == 'analysis_incomplete' for w in answer['meta']['warnings'])


@pytest.mark.parametrize('suffix', ['', '?filter=definitely-absent'])
def test_listing_outcome_uses_catalog_before_name_filter(transcript, monkeypatch, suffix):
    from conftest import _run_reveal_in
    blocked = transcript.parent.parent / 'blocked-project'
    blocked.mkdir()
    deny_scan(monkeypatch, blocked)
    result = _run_reveal_in(transcript.parent, 'claude://sessions' + suffix, '--format', 'json')
    assert result.returncode == 3


def test_healthy_empty_catalog_is_complete(transcript):
    import json
    from conftest import _run_reveal_in
    for path in transcript.parent.glob('*.jsonl'):
        path.unlink()
    result = _run_reveal_in(transcript.parent, 'claude://sessions', '--format', 'json')
    assert result.returncode == 0
    assert json.loads(result.stdout)['meta']['session_catalog']['analyzed_entries'] == 0


@pytest.mark.parametrize('erase', ['proof', 'rows'])
def test_listing_presentation_cannot_erase_acquired_evidence(transcript, monkeypatch, erase):
    import json
    from conftest import _run_reveal_in
    from reveal.adapters.claude.adapter import ClaudeAdapter
    def post_process(self, result, args):
        if erase == 'proof':
            result['meta'].pop('session_catalog')
        else:
            result['recent_sessions'] = []
        return result
    monkeypatch.setattr(ClaudeAdapter, 'post_process', post_process)
    result = _run_reveal_in(transcript.parent, 'claude://sessions', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


def test_listing_display_cut_retains_acquisition_receipt(transcript):
    import json
    from conftest import _run_reveal_in
    result = _run_reveal_in(transcript.parent, 'claude://sessions', '--head', '1', '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    assert len(answer['recent_sessions']) == 1
    assert answer['meta']['session_catalog']['analyzed_entries'] == 3
    assert any(w.get('field') == 'recent_sessions' and w.get('shown') == 1 and w.get('total') == 3
               for w in answer['meta']['warnings'])


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_listing_reports_failed_metadata_and_fresh_followup(transcript, monkeypatch):
    import json
    from test_mcp_expected_errors_back1992 import _run, _text
    monkeypatch.setenv('REVEAL_CLAUDE_HOME', str(transcript.parent.parent.parent))
    monkeypatch.setenv('REVEAL_CLAUDE_DIR', str(transcript.parent.parent))
    broken = transcript.parent / 'unreadable.jsonl'
    broken.symlink_to(transcript.parent / 'absent.jsonl')
    async def scenario(session):
        request = {'uri': 'claude://sessions', 'provenance': True}
        partial = await session.call_tool('reveal_query', request)
        assert not partial.is_error, _text(partial)
        proof = json.loads(_text(partial))['meta']['session_catalog']
        assert proof['analyzed_entries'] == 3 and proof['failed_entries'] == 1
        broken.unlink()
        healthy = await session.call_tool('reveal_query', request)
        assert not healthy.is_error, _text(healthy)
        assert json.loads(_text(healthy))['meta']['session_catalog']['failed_entries'] == 0
    _run(transcript.parent, scenario)
