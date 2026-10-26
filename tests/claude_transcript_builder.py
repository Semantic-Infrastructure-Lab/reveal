"""Build a small anonymised Claude Code transcript and run claude:// URIs against it (BACK-2239/2240/1624).

The record shapes are the ones Claude Code writes (checked against local transcripts): a
typed prompt is a bare string, tool results ride on role=user records, one assistant
message is split over several records that share ``message.id``, and an Agent call's
``toolUseResult`` is camelCase except for its ``usage`` block, which is snake_case.
"""

import json
from pathlib import Path

from conftest import _run_reveal_direct

SESSION = '0a1b2c3d-1111-4222-8333-444455556666'
PROJECT_DIR = '-home-user-proj'


def record(kind: str, index: int, message: dict, **extra) -> dict:
    rec = {'type': kind, 'uuid': f'u{index}', 'parentUuid': None if index == 0 else f'u{index - 1}',
           'timestamp': f'2026-10-01T10:{index:02d}:00.000Z', 'message': message,
           'cwd': '/home/user/proj', 'gitBranch': 'main', 'version': '2.1.0'}
    rec.update(extra)
    return rec


def prompt(index: int, text) -> dict:
    return record('user', index, {'role': 'user', 'content': text})


def assistant(index: int, blocks: list, message_id: str, **extra) -> dict:
    return record('assistant', index, {'role': 'assistant', 'id': message_id, 'content': blocks,
                                       'usage': {'input_tokens': 5, 'output_tokens': 7,
                                                 'cache_read_input_tokens': 11,
                                                 'cache_creation_input_tokens': 3}}, **extra)


def tool_use(call_id: str, name: str, **tool_input) -> dict:
    return {'type': 'tool_use', 'id': call_id, 'name': name, 'input': tool_input}


def tool_result(index: int, call_id: str, text: str, **extra) -> dict:
    return record('user', index, {'role': 'user', 'content': [
        {'type': 'tool_result', 'tool_use_id': call_id, 'content': text}]}, **extra)


def install(monkeypatch, tmp_path: Path, records: list, extra_files: dict = None) -> Path:
    """Write ``records`` as ``<projects>/<proj>/<SESSION>.jsonl`` and point the adapter at it."""
    from reveal.adapters.claude.adapter import ClaudeAdapter
    projects = tmp_path / 'projects'
    project = projects / PROJECT_DIR
    project.mkdir(parents=True)
    transcript = project / f'{SESSION}.jsonl'
    transcript.write_text(''.join(json.dumps(r) + '\n' for r in records), encoding='utf-8')
    for name, text in (extra_files or {}).items():
        (project / name).write_text(text, encoding='utf-8')
    monkeypatch.setattr(ClaudeAdapter, 'CONVERSATION_BASE', projects)
    return transcript


def run_json(uri: str) -> dict:
    result = _run_reveal_direct(uri, '--format', 'json')
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def run_text(uri: str) -> str:
    result = _run_reveal_direct(uri)
    assert result.returncode == 0, result.stderr
    return result.stdout
