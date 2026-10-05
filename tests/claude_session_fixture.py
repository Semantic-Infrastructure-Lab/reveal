"""A small recorded Claude Code home for tests that run claude:// examples as written (BACK-1594).

Builds ``<home>/.claude`` with one project, the sessions the schema and recipe examples
name, a prompt history, settings, a plan, a memory file, an agent and a hook. The content
is what those examples search for (``validate_token``, ``path traversal``, ``auth``), so a
documented claim can be checked against a positive match instead of being skipped.
"""

import json
from pathlib import Path

SESSION_NAMES = ('infernal-earth-0118', 'my-session', '2627362f-6f72-45e1-b7bb-d5a61519a388')
PROJECT_DIR = '-home-user-proj'


def _record(kind: str, session: str, index: int, message: dict) -> dict:
    return {
        'parentUuid': None if index == 0 else f'{session}-{index - 1}',
        'isSidechain': False, 'type': kind, 'message': message,
        'uuid': f'{session}-{index}', 'timestamp': f'2026-03-28T10:{index:02d}:00.000Z',
        'cwd': '/home/user/proj', 'sessionId': session, 'version': '2.1.0',
        'gitBranch': 'main',
    }


def _tool_use(call_id: str, name: str, **tool_input) -> dict:
    return {'type': 'tool_use', 'id': call_id, 'name': name, 'input': tool_input}


def _tool_result(call_id: str, text: str, is_error: bool = False) -> dict:
    return {'type': 'tool_result', 'tool_use_id': call_id, 'content': text, 'is_error': is_error}


def _session_records(session: str) -> list:
    turns = [
        ('user', {'role': 'user', 'content': 'Fix the auth bug: validate_token allows a path traversal'}),
        ('assistant', {'role': 'assistant', 'model': 'claude-opus-4-7', 'content': [
            {'type': 'thinking', 'thinking': 'The path traversal is in validate_token; read it first.'},
            {'type': 'text', 'text': 'I will read validate_token and check the path handling.'},
            _tool_use('t1', 'Read', file_path='/home/user/proj/auth.py')],
            'usage': {'input_tokens': 10, 'output_tokens': 20}}),
        ('user', {'role': 'user', 'content': [_tool_result('t1', 'def validate_token(t): return t')]}),
        ('assistant', {'role': 'assistant', 'model': 'claude-opus-4-7', 'content': [
            {'type': 'text', 'text': 'Running the tests.'},
            _tool_use('t2', 'Bash', command='pytest tests/test_auth.py')],
            'usage': {'input_tokens': 12, 'output_tokens': 8}}),
        ('user', {'role': 'user', 'content': [_tool_result('t2', 'Error: 1 failed', is_error=True)]}),
        ('assistant', {'role': 'assistant', 'model': 'claude-opus-4-7', 'content': [
            {'type': 'text', 'text': 'Patching auth.py to reject ../ in the token path.'},
            _tool_use('t3', 'Edit', file_path='/home/user/proj/auth.py',
                      old_string='return t', new_string='return t.replace("../", "")')],
            'usage': {'input_tokens': 14, 'output_tokens': 9}}),
        ('user', {'role': 'user', 'content': [_tool_result('t3', 'File edited')]}),
        ('assistant', {'role': 'assistant', 'model': 'claude-opus-4-7', 'content': [
            {'type': 'text', 'text': 'Fixed: validate_token now strips path traversal.'}],
            'usage': {'input_tokens': 15, 'output_tokens': 11}}),
    ]
    return [_record(kind, session, i, message) for i, (kind, message) in enumerate(turns)]


def _write_jsonl(path: Path, records: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r) + '\n' for r in records), encoding='utf-8')


def build_claude_home(home: Path) -> Path:
    """Create ``home/.claude`` and ``home/.claude.json``; return the ``.claude`` directory."""
    claude = home / '.claude'
    for name in SESSION_NAMES:
        _write_jsonl(claude / 'projects' / PROJECT_DIR / f'{name}.jsonl', _session_records(name))
    _write_jsonl(claude / 'history.jsonl', [
        {'display': 'fix validate_token', 'timestamp': 1774692000000, 'project': '/home/user/frono',
         'sessionId': 'infernal-earth-0118'},
        {'display': 'review auth', 'timestamp': 1774778400000, 'project': '/home/user/proj',
         'sessionId': 'my-session'},
    ])
    (claude / 'settings.json').write_text(json.dumps({
        'model': 'opus', 'permissions': {'additionalDirectories': ['/home/user/shared']},
        'hooks': {'PostToolUse': [{'matcher': 'Bash', 'hooks': [
            {'type': 'command', 'command': '~/.claude/hooks/PostToolUse'}]}]},
    }), encoding='utf-8')
    (claude / 'plans').mkdir(exist_ok=True)
    (claude / 'plans' / 'gentle-foraging-candy.md').write_text(
        '# Plan\n\nReplace the token check with a signed token.\n', encoding='utf-8')
    memory = claude / 'projects' / 'my-project' / 'memory'
    memory.mkdir(parents=True, exist_ok=True)
    (memory / 'feedback_tests.md').write_text(
        '---\nname: feedback-tests\ntype: feedback\n---\nRun the feedback tests first.\n', encoding='utf-8')
    (claude / 'agents').mkdir(exist_ok=True)
    (claude / 'agents' / 'reveal-codereview.md').write_text(
        '---\nname: reveal-codereview\ndescription: Review code\n---\nReview the diff.\n', encoding='utf-8')
    (claude / 'hooks').mkdir(exist_ok=True)
    hook = claude / 'hooks' / 'PostToolUse'
    hook.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
    (home / '.claude.json').write_text(json.dumps({
        'projects': {'/path/to/proj': {'mcpServers': {'reveal': {'command': 'reveal-mcp'}}}},
    }), encoding='utf-8')
    return claude
