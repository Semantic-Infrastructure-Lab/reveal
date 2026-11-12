"""Codex normalization keeps measured JSONL acquisition/decoding decisions."""
import builtins
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_in
from codex_session_fixture import DOC_SESSION_ID
from reveal import query
from test_codex_declared_api_back2618 import codex


def rollout(home):
    return next((home / 'sessions').rglob('*.jsonl'))


@pytest.mark.parametrize('suffix', ['', '/messages', '/tools', '/errors', '/workflow', '/timeline',
                                    '/digest', '/exchanges', '?last', '?tokens', '/message/0'])
def test_session_views_retain_object_record_decisions(codex, suffix):
    path = rollout(codex)
    count = len(path.read_text(encoding='utf-8').splitlines())
    with path.open('a', encoding='utf-8') as handle:
        handle.write('{broken\n')
    answer = query('codex://' + DOC_SESSION_ID + suffix)
    proof = answer['meta']['rollout_analysis']
    assert proof['candidate_records'] == count + 1
    assert proof['analyzed_records'] == count and proof['failed_records'] == 1
    assert proof['first_failed_line'] == count + 1 and proof['decision'] == 'exhausted'
    assert proof['source'] == str(path) and proof['opened'] is True
    assert any(w['code'] == 'analysis_incomplete' for w in answer['meta']['warnings'])


@pytest.mark.parametrize('line', ['[]\n', 'null\n'])
def test_nonobjects_are_failed_records(codex, line):
    path = rollout(codex)
    with path.open('a', encoding='utf-8') as handle:
        handle.write(line)
    answer = query('codex://' + DOC_SESSION_ID + '/messages')
    assert answer['total_turns'] > 0
    assert answer['meta']['rollout_analysis']['failed_records'] == 1


def test_failed_empty_and_healthy_empty_sources_are_distinct(codex):
    path = rollout(codex)
    path.write_text('{broken\n', encoding='utf-8')
    failed = query('codex://' + DOC_SESSION_ID + '/messages')
    path.write_text('\n \n', encoding='utf-8')
    healthy = query('codex://' + DOC_SESSION_ID + '/messages')
    assert failed['messages'] == healthy['messages'] == []
    assert failed['meta']['rollout_analysis']['failed_records'] == 1
    assert healthy['meta']['rollout_analysis']['candidate_records'] == 0
    assert not healthy['meta']['warnings']


def test_legacy_utf8_replacement_is_measured(codex):
    path = rollout(codex)
    with path.open('ab') as handle:
        handle.write(b'{"type":"event_msg","payload":{"type":"agent_message","message":"repaired:\xff"}}\n')
    answer = query('codex://' + DOC_SESSION_ID + '?last')
    assert answer['messages'][0]['message'] == 'repaired:�'
    assert answer['meta']['rollout_analysis']['recovered_records'] == 1
    assert answer['meta']['rollout_analysis']['failed_records'] == 0


@pytest.mark.parametrize('prefix', [False, True])
def test_read_failure_keeps_acquired_prefix_and_operation_proof(codex, monkeypatch, prefix):
    import reveal.adapters.codex.adapter as module
    path = rollout(codex)
    first = json.dumps({'type': 'event_msg', 'payload': {'type': 'agent_message', 'message': 'known prefix'}}) + '\n'
    class Interrupted:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def __iter__(self):
            yield first
            raise OSError('read interrupted')
    def opener(target, *args, **kwargs):
        if Path(target) == path:
            if prefix:
                return Interrupted()
            raise PermissionError('source denied')
        return builtins.open(target, *args, **kwargs)
    monkeypatch.setattr(module, 'open', opener, raising=False)
    answer = query('codex://' + DOC_SESSION_ID + '/messages')
    assert [row['message'] for row in answer['messages']] == (['known prefix'] if prefix else [])
    proof = answer['meta']['rollout_analysis']
    assert proof['opened'] is prefix and proof['decision'] == 'interrupted'
    assert proof['analyzed_records'] == int(prefix)
    assert proof['failures'][0]['phase'] == 'read'


def test_source_evidence_does_not_claim_execution_policy_adoption(codex):
    with rollout(codex).open('a', encoding='utf-8') as handle:
        handle.write('{broken\n')
    result = _run_reveal_in(codex.parent, 'codex://' + DOC_SESSION_ID + '/messages', '--format', 'json')
    assert result.returncode == 0  # D6 adoption is a separate package step.
    assert json.loads(result.stdout)['meta']['rollout_analysis']['failed_records'] == 1


def test_repeated_adapter_reads_replace_source_decisions(codex):
    from reveal.adapters.codex.adapter import CodexAdapter
    path = rollout(codex)
    original = path.read_bytes()
    path.write_bytes(original + b'{broken\n')
    adapter = CodexAdapter(DOC_SESSION_ID + '/messages')
    assert adapter.get_structure()['meta']['rollout_analysis']['failed_records'] == 1
    path.write_bytes(original)
    assert adapter.get_structure()['meta']['rollout_analysis']['failed_records'] == 0
