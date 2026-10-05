"""Synthetic Codex home for tests: one rollout JSONL plus the state_5.sqlite thread index.

Shared by tests/adapters/test_codex_adapter.py and the executable-docs gate
(tests/test_example_recipes_run.py), so codex:// examples run as written (BACK-1594).
"""

import json
import sqlite3
from pathlib import Path

SESSION_UUID = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'

FIXTURE_LINES = [
    # session_meta
    {'timestamp': '2026-05-24T10:00:00Z', 'type': 'session_meta',
     'payload': {'session_id': SESSION_UUID, 'model': 'gpt-5.5'}},
    # turn_context
    {'timestamp': '2026-05-24T10:00:01Z', 'type': 'turn_context',
     'payload': {'cwd': '/home/user/project'}},
    # user_message
    {'timestamp': '2026-05-24T10:00:02Z', 'type': 'event_msg',
     'payload': {'type': 'user_message', 'message': 'Help me refactor this module.'}},
    # agent_message (first)
    {'timestamp': '2026-05-24T10:00:10Z', 'type': 'event_msg',
     'payload': {'type': 'agent_message', 'message': "Sure, I'll start by reading the file.", 'phase': 'thinking'}},
    # token_count — real Codex format: info.last_token_usage + info.total_token_usage
    {'timestamp': '2026-05-24T10:00:11Z', 'type': 'event_msg',
     'payload': {'type': 'token_count', 'info': {
         'last_token_usage': {'input_tokens': 500, 'cached_input_tokens': 0,
                              'output_tokens': 120, 'reasoning_output_tokens': 0, 'total_tokens': 620},
         'total_token_usage': {'input_tokens': 500, 'cached_input_tokens': 0,
                               'output_tokens': 120, 'reasoning_output_tokens': 0, 'total_tokens': 620},
         'model_context_window': 128000,
     }}},
    # task_complete
    {'timestamp': '2026-05-24T10:00:15Z', 'type': 'event_msg',
     'payload': {'type': 'task_complete', 'turn_id': 'turn-1',
                 'last_agent_message': 'Done.', 'duration_ms': 8000, 'time_to_first_token_ms': 500}},
    # function_call
    {'timestamp': '2026-05-24T10:00:20Z', 'type': 'response_item',
     'payload': {'type': 'function_call', 'name': 'read_file',
                 'namespace': 'default', 'arguments': '{"path": "foo.py"}', 'call_id': 'call-001'}},
    # function_call_output
    {'timestamp': '2026-05-24T10:00:21Z', 'type': 'response_item',
     'payload': {'type': 'function_call_output', 'call_id': 'call-001',
                 'output': 'def foo(): pass\n'}},
    # exec_command_end — real Codex format (no begin event; end has all info)
    {'timestamp': '2026-05-24T10:00:26Z', 'type': 'event_msg',
     'payload': {'type': 'exec_command_end', 'call_id': 'call-shell-001',
                 'command': ['/bin/bash', '-lc', 'ls -la'],
                 'cwd': '/home/user/project', 'exit_code': 0,
                 'aggregated_output': 'total 8\ndrwxr-xr-x 2 user user 4096 May 24 10:00 .\n',
                 'duration': {'secs': 0, 'nanos': 120_000_000}, 'status': 'completed'}},
    # error event
    {'timestamp': '2026-05-24T10:00:30Z', 'type': 'event_msg',
     'payload': {'type': 'error', 'message': 'Something went wrong.'}},
    # warning event
    {'timestamp': '2026-05-24T10:00:31Z', 'type': 'event_msg',
     'payload': {'type': 'warning', 'message': 'Rate limit approaching.'}},
    # second agent_message (last)
    {'timestamp': '2026-05-24T10:00:40Z', 'type': 'event_msg',
     'payload': {'type': 'agent_message', 'message': 'Refactoring complete!', 'phase': 'final'}},
]

FIXTURE_JSONL = '\n'.join(json.dumps(line) for line in FIXTURE_LINES) + '\n'


def write_fixture_jsonl(tmp_path: Path) -> Path:
    p = tmp_path / 'rollout-2026-05-24T10-00-00Z-a1b2c3d4.jsonl'
    p.write_text(FIXTURE_JSONL, encoding='utf-8')
    return p


def make_sqlite_db(tmp_path: Path, jsonl_path: Path, session_id: str = SESSION_UUID) -> Path:
    db_path = tmp_path / 'state_5.sqlite'
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE threads (
            id TEXT PRIMARY KEY,
            rollout_path TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'cli',
            cwd TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            first_user_message TEXT NOT NULL DEFAULT '',
            preview TEXT NOT NULL DEFAULT '',
            model TEXT,
            model_provider TEXT NOT NULL DEFAULT 'openai',
            reasoning_effort TEXT,
            tokens_used INTEGER NOT NULL DEFAULT 0,
            git_sha TEXT, git_branch TEXT, git_origin_url TEXT,
            cli_version TEXT NOT NULL DEFAULT '',
            archived INTEGER NOT NULL DEFAULT 0,
            thread_source TEXT,
            approval_mode TEXT,
            sandbox_policy TEXT,
            has_user_event INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        INSERT INTO threads (id, rollout_path, created_at, updated_at, source, cwd,
            title, first_user_message, model, model_provider, tokens_used, thread_source, archived)
        VALUES (?, ?, ?, ?, 'cli', '/home/user/project',
            'Help me refactor this module.', 'Help me refactor this module.',
            'gpt-5.5', 'openai', 620, NULL, 0)
    """, (session_id, str(jsonl_path), 1716544800, 1716544900))
    # Add a subagent row (should be filtered out)
    conn.execute("""
        INSERT INTO threads (id, rollout_path, created_at, updated_at, source, cwd,
            title, first_user_message, model, model_provider, tokens_used, thread_source, archived)
        VALUES ('subagent-0001', ?, ?, ?, 'cli', '/tmp', 'sub', 'sub', 'gpt-4', 'openai', 0, 'subagent', 0)
    """, (str(jsonl_path), 1716544700, 1716544750))
    conn.commit()
    conn.close()
    return db_path


DOC_SESSION_ID = '019e5cc5-0000-7000-8000-000000000001'


def build_codex_home(home: Path) -> Path:
    """Create ``home/.codex`` with a thread index, one rollout, config, a skill and a plugin.

    The session id starts ``019e5cc5`` and mentions ``authentication`` and ``auth-refactor``,
    the names the codex:// schema examples use.
    """
    codex = home / '.codex'
    rollout = codex / 'sessions' / 'rollout-2026-07-02T10-00-00Z-019e5cc5.jsonl'
    rollout.parent.mkdir(parents=True, exist_ok=True)
    lines = list(FIXTURE_LINES)
    lines.insert(3, {'timestamp': '2026-07-02T10:00:05Z', 'type': 'event_msg',
                     'payload': {'type': 'user_message',
                                 'message': 'auth-refactor: simplify the authentication module'}})
    rollout.write_text(''.join(json.dumps(line) + '\n' for line in lines), encoding='utf-8')
    (codex / 'state_5.sqlite').unlink(missing_ok=True)  # a thinner index from a base fixture
    db = make_sqlite_db(codex, rollout, DOC_SESSION_ID)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("UPDATE threads SET title = 'auth-refactor', updated_at = 1783000000, "
                     "created_at = 1782990000 WHERE id = ?", (DOC_SESSION_ID,))
        conn.commit()
    finally:
        conn.close()
    (codex / 'config.toml').write_text('model = "gpt-5.5"\n', encoding='utf-8')
    skill = codex / 'skills' / 'openai-docs'
    skill.mkdir(parents=True, exist_ok=True)
    (skill / 'SKILL.md').write_text(
        '---\nname: openai-docs\ndescription: Look up OpenAI documentation\n---\nUse the docs.\n',
        encoding='utf-8')
    manifest = codex / 'plugins' / 'cache' / 'vendor' / 'demo' / '.codex-plugin' / 'plugin.json'
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({'name': 'demo', 'version': '1.0.0', 'description': 'Demo plugin'}),
                        encoding='utf-8')
    return codex
