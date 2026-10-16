"""BACK-1059: the claude:// and codex:// handlers catch the errors their input can
actually produce (a missing, unreadable or malformed file written by another program)
and let a bug in reveal propagate; a skipped entry is disclosed in the result.

Unexpected failure is injected as ``_InjectedBug`` (a RuntimeError nothing in these
handlers expects). Negative controls: the expected error still takes the old path.
All sessions live under tmp_path; the real ~/.claude is never read.
"""

import json
import os
from pathlib import Path

import pytest

from reveal.adapters.claude.handlers import sessions, system, workspace
from reveal.adapters.codex.handlers import system as codex_system

pytestmark = pytest.mark.component


class _InjectedBug(RuntimeError):
    """A failure no handler here expects: stands in for a bug in reveal."""


def _raise_bug(*_a, **_k):
    raise _InjectedBug('injected')


def _entries_skipped(result, field):
    warnings = (result.get('meta') or {}).get('warnings') or []
    found = [w for w in warnings if w.get('type') == 'entries_skipped' and w.get('field') == field]
    assert len(found) <= 1
    return found[0] if found else None


def _patch_read_text(monkeypatch, target: Path, exc: Exception):
    """Make Path.read_text raise *exc* for *target* only."""
    real = Path.read_text

    def read_text(self, *a, **k):
        if self == target:
            raise exc
        return real(self, *a, **k)

    monkeypatch.setattr(Path, 'read_text', read_text)


def _bad_datetime(exc_type):
    class _Dt:
        @staticmethod
        def fromtimestamp(*_a, **_k):
            raise exc_type('bad mtime')
    return _Dt


# ---------------------------------------------------------------- sessions.py

@pytest.fixture
def projects(tmp_path):
    """conversation_base with one project dir holding one valid session file."""
    base = tmp_path / 'projects'
    proj = base / 'proj-a'
    proj.mkdir(parents=True)
    (proj / 's1.jsonl').write_text(
        json.dumps({'type': 'user', 'message': {'content': 'edit app.py please'}}) + '\n',
        encoding='utf-8')
    return base


_SESSION_FNS = [
    pytest.param(lambda base: sessions.list_sessions(base, {}), id='list'),
    pytest.param(lambda base: sessions.search_sessions(base, {'search': 'x'}), id='search'),
    pytest.param(lambda base: sessions.track_file_sessions(base, 'files/app.py', {}), id='track'),
]


def _error_of(result):
    return result.get('error') or (result.get('data') or {}).get('error')


@pytest.mark.parametrize('call', _SESSION_FNS)
def test_session_scan_bug_propagates(call, projects, monkeypatch):
    monkeypatch.setattr(sessions, '_collect_sessions_from_dir', _raise_bug)
    with pytest.raises(_InjectedBug):
        call(projects)


@pytest.mark.parametrize('call', _SESSION_FNS)
def test_session_scan_unreadable_base_is_still_an_error(call, tmp_path):
    not_a_dir = tmp_path / 'projects.txt'
    not_a_dir.write_text('x', encoding='utf-8')
    assert _error_of(call(not_a_dir))


@pytest.mark.parametrize('call', _SESSION_FNS)
def test_session_scan_vanished_file_is_still_an_error(call, projects, monkeypatch):
    def vanished(_dir):
        raise FileNotFoundError('s1.jsonl vanished between glob and stat')
    monkeypatch.setattr(sessions, '_collect_sessions_from_dir', vanished)
    assert _error_of(call(projects))


def test_track_file_sessions_discloses_a_session_it_could_not_parse(projects):
    # mentions app.py (passes the byte pre-filter) but its message has a shape the
    # file-operation extractor cannot walk: the session is skipped
    bad = projects / 'proj-b'
    bad.mkdir()
    (bad / 's2.jsonl').write_text(
        json.dumps({'type': 'assistant', 'message': 'app.py as a string, not an object'}) + '\n',
        encoding='utf-8')
    result = sessions.track_file_sessions(projects, 'files/app.py', {})
    warning = _entries_skipped(result, 'sessions')
    assert warning, f"a skipped session left no warning: {result.get('meta')}"
    assert warning['count'] == 1 and 's2.jsonl' in warning['files']
    assert 's2.jsonl' in warning['message']


def test_track_file_sessions_clean_run_has_no_skip_warning(projects):
    result = sessions.track_file_sessions(projects, 'files/app.py', {})
    assert _entries_skipped(result, 'sessions') is None
    assert result['match_count'] == 0 and result['sessions_scanned'] == 1


# ------------------------------------------------------------------ system.py

def _history(tmp_path, lines):
    home = tmp_path / 'claude'
    home.mkdir()
    (home / 'history.jsonl').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return home


def test_history_open_bug_propagates(tmp_path, monkeypatch):
    home = _history(tmp_path, ['{"display": "a"}'])
    monkeypatch.setattr(system, 'open', _raise_bug, raising=False)
    with pytest.raises(_InjectedBug):
        system.get_history(home, {})


def test_history_unreadable_file_is_still_an_error(tmp_path, monkeypatch):
    home = _history(tmp_path, ['{"display": "a"}'])

    def denied(*_a, **_k):
        raise PermissionError('denied')
    monkeypatch.setattr(system, 'open', denied, raising=False)
    result = system.get_history(home, {})
    assert 'denied' in result['error'] and result['entries'] == []


def test_history_skips_truncated_and_non_object_lines(tmp_path):
    home = _history(tmp_path, [
        '{"display": "first", "timestamp": 1760000000000}',
        '{"display": "truncated mid-wri',
        '["valid JSON, not an entry"]',
        '{"display": "last", "timestamp": 1760000001000}',
    ])
    result = system.get_history(home, {})
    assert 'error' not in result, result.get('error')
    assert [e['prompt'] for e in result['entries']] == ['last', 'first']


def test_history_timestamp_out_of_range_is_still_an_error(tmp_path):
    home = _history(tmp_path, ['{"display": "a", "timestamp": 1e300}'])
    assert system.get_history(home, {})['error']


def test_settings_read_bug_propagates(tmp_path, monkeypatch):
    home = tmp_path / 'claude'
    home.mkdir()
    (home / 'settings.json').write_text('{}', encoding='utf-8')
    monkeypatch.setattr(system.json, 'load', _raise_bug)
    with pytest.raises(_InjectedBug):
        system.get_settings(home, {})


@pytest.mark.parametrize('payload', [b'{"truncated": ', b'\xff\xfe not utf-8'])
def test_settings_malformed_file_is_still_an_error(tmp_path, payload):
    home = tmp_path / 'claude'
    home.mkdir()
    (home / 'settings.json').write_bytes(payload)
    result = system.get_settings(home, {})
    assert result['error'] and result['settings'] == {}


def test_settings_unreadable_path_is_still_an_error(tmp_path):
    home = tmp_path / 'claude'
    (home / 'settings.json').mkdir(parents=True)   # exists, cannot be opened as a file
    assert system.get_settings(home, {})['error']


def test_config_read_bug_propagates(tmp_path, monkeypatch):
    cfg = tmp_path / '.claude.json'
    cfg.write_text('{}', encoding='utf-8')
    _patch_read_text(monkeypatch, cfg, _InjectedBug('injected'))
    with pytest.raises(_InjectedBug):
        system.get_config(cfg, {})


def test_config_malformed_and_unreadable_are_still_errors(tmp_path, monkeypatch):
    cfg = tmp_path / '.claude.json'
    cfg.write_text('{"projects": ', encoding='utf-8')
    assert system.get_config(cfg, {})['error']
    cfg.write_text('{}', encoding='utf-8')
    _patch_read_text(monkeypatch, cfg, PermissionError('denied'))
    assert 'denied' in system.get_config(cfg, {})['error']


# ------------------------------------------------------------ codex system.py

@pytest.mark.skipif(codex_system.tomllib is None, reason='no TOML parser on this interpreter')
class TestCodexConfig:
    def test_bug_while_masking_propagates(self, tmp_path, monkeypatch):
        (tmp_path / 'config.toml').write_text('model = "x"\n', encoding='utf-8')
        monkeypatch.setattr(codex_system, 'redact_secrets', _raise_bug)
        with pytest.raises(_InjectedBug):
            codex_system.get_config(tmp_path)

    def test_bug_in_parser_propagates(self, tmp_path, monkeypatch):
        (tmp_path / 'config.toml').write_text('model = "x"\n', encoding='utf-8')
        monkeypatch.setattr(codex_system.tomllib, 'load', _raise_bug)
        with pytest.raises(_InjectedBug):
            codex_system.get_config(tmp_path)

    @pytest.mark.parametrize('payload', [b'model = = broken\n', b'model = "\xff\xfe"\n'])
    def test_malformed_file_is_still_an_error(self, tmp_path, payload):
        (tmp_path / 'config.toml').write_bytes(payload)
        result = codex_system.get_config(tmp_path)
        assert result['error'] and result['config'] == {}

    def test_unreadable_path_is_still_an_error(self, tmp_path):
        (tmp_path / 'config.toml').mkdir()
        assert codex_system.get_config(tmp_path)['error']

    def test_valid_file_is_masked_not_an_error(self, tmp_path):
        (tmp_path / 'config.toml').write_text('model = "x"\napi_key = "sk-abcdefghijkl"\n',
                                              encoding='utf-8')
        result = codex_system.get_config(tmp_path)
        assert 'error' not in result and result['config']['model'] == 'x'
        assert 'abcdefghijkl' not in json.dumps(result['config'])


# --------------------------------------------------------------- workspace.py

def test_plan_read_bug_propagates(tmp_path, monkeypatch):
    plan = tmp_path / 'p.md'
    plan.write_text('# t\n', encoding='utf-8')
    _patch_read_text(monkeypatch, plan, _InjectedBug('injected'))
    with pytest.raises(_InjectedBug):
        workspace.get_plans(tmp_path, 'plans/p.md', {})


def test_plan_read_unreadable_is_still_an_error(tmp_path):
    (tmp_path / 'd.md').mkdir()                     # exists, cannot be read as text
    result = workspace.get_plans(tmp_path, 'plans/d.md', {})
    assert result['error'] and result['type'] == 'claude_plan'


def test_agent_read_bug_propagates(tmp_path, monkeypatch):
    agent = tmp_path / 'a.md'
    agent.write_text('---\ndescription: d\n---\n', encoding='utf-8')
    _patch_read_text(monkeypatch, agent, _InjectedBug('injected'))
    with pytest.raises(_InjectedBug):
        workspace.get_agents(tmp_path, 'agents/a.md', {})


def test_agent_read_unreadable_is_still_an_error(tmp_path):
    (tmp_path / 'd.md').mkdir()
    assert workspace.get_agents(tmp_path, 'agents/d.md', {})['error']


def test_hook_file_read_bug_and_unreadable(tmp_path, monkeypatch):
    script = tmp_path / 'on_start.sh'
    script.write_text('#!/bin/sh\n', encoding='utf-8')
    _patch_read_text(monkeypatch, script, _InjectedBug('injected'))
    with pytest.raises(_InjectedBug):
        workspace.get_hooks(tmp_path, 'hooks/on_start.sh')
    _patch_read_text(monkeypatch, script, PermissionError('denied'))
    result = workspace.get_hooks(tmp_path, 'hooks/on_start.sh')
    assert 'denied' in result['error'] and result['event'] == 'on_start.sh'


# The four list loops below share one contract: an unreadable entry is skipped and
# disclosed in meta.warnings; any other exception is a bug and propagates.

def _plans(tmp_path):
    (tmp_path / 'good.md').write_text('# Good plan\n', encoding='utf-8')
    (tmp_path / 'dir.md').mkdir()
    return tmp_path, (lambda d: workspace.get_plans(d, 'plans', {})), 'plans', 'plans'


def _agents(tmp_path):
    (tmp_path / 'good.md').write_text('---\ndescription: d\n---\n', encoding='utf-8')
    (tmp_path / 'dir.md').mkdir()
    return tmp_path, (lambda d: workspace.get_agents(d, 'agents', {})), 'agents', 'agents'


def _memory(tmp_path):
    mem = tmp_path / 'proj' / 'memory'
    mem.mkdir(parents=True)
    (mem / 'good.md').write_text('---\ntype: user\n---\n', encoding='utf-8')
    (mem / 'dir.md').mkdir()
    return tmp_path, (lambda d: workspace.get_memory(d, 'memory', {})), 'memory', 'memories'


def _hook_scripts(tmp_path):
    event = tmp_path / 'PreToolUse'
    event.mkdir()
    (event / 'good.sh').write_text('#!/bin/sh\n', encoding='utf-8')
    (event / 'dir.sh').mkdir()
    return tmp_path, (lambda d: workspace.get_hooks(d, 'hooks/PreToolUse')), 'hook scripts', 'scripts'


def _hook_events(tmp_path):
    (tmp_path / 'good.sh').write_text('#!/bin/sh\n', encoding='utf-8')
    (tmp_path / 'ev').mkdir()
    return tmp_path, (lambda d: workspace.get_hooks(d, 'hooks')), 'hook entries', 'hooks'


# (builder, name the bug-injection patches, expected good names, bad entry name)
_LOOPS = [
    pytest.param(_plans, 'split_lines', 'dir.md', id='plans'),
    pytest.param(_agents, '_parse_agent_frontmatter', 'dir.md', id='agents'),
    pytest.param(_memory, '_parse_agent_frontmatter', 'dir.md', id='memory'),
]
_DATETIME_LOOPS = _LOOPS + [
    pytest.param(_hook_scripts, None, None, id='hook-scripts'),
    pytest.param(_hook_events, None, None, id='hook-entries'),
]


@pytest.mark.parametrize('build,patch_name,bad', _DATETIME_LOOPS)
def test_list_loop_bug_propagates(build, patch_name, bad, tmp_path, monkeypatch):
    target, call, _field, _items = build(tmp_path)
    # a bug while reading an entry's mtime is not an unreadable entry
    class _Dt:
        fromtimestamp = staticmethod(_raise_bug)
    monkeypatch.setattr(workspace, 'datetime', _Dt)
    with pytest.raises(_InjectedBug):
        call(target)


@pytest.mark.parametrize('build,patch_name,bad', _LOOPS)
def test_list_loop_bug_in_entry_processing_propagates(build, patch_name, bad, tmp_path, monkeypatch):
    target, call, _field, _items = build(tmp_path)
    monkeypatch.setattr(workspace, patch_name, _raise_bug)
    with pytest.raises(_InjectedBug):
        call(target)


@pytest.mark.parametrize('exc_type', [OSError, ValueError, OverflowError])
@pytest.mark.parametrize('build,patch_name,bad', _DATETIME_LOOPS)
def test_list_loop_unreadable_mtime_is_skipped_and_disclosed(build, patch_name, bad, exc_type,
                                                              tmp_path, monkeypatch):
    target, call, field, _items = build(tmp_path)
    monkeypatch.setattr(workspace, 'datetime', _bad_datetime(exc_type))
    result = call(target)
    warning = _entries_skipped(result, field)
    assert warning, f"{field}: entries skipped for a bad mtime left no warning: {result.get('meta')}"
    assert warning['count'] >= 1 and warning['message']


@pytest.mark.parametrize('build,patch_name,bad', _LOOPS)
def test_list_loop_unreadable_entry_is_skipped_and_disclosed(build, patch_name, bad, tmp_path):
    target, call, field, items = build(tmp_path)
    result = call(target)
    assert [e['name'] for e in result[items]] == ['good']
    warning = _entries_skipped(result, field)
    assert warning, f"{field}: unreadable {bad} left no warning: {result.get('meta')}"
    assert warning['count'] == 1 and bad in warning['files'] and bad in warning['message']


@pytest.mark.parametrize('build,patch_name,bad', _DATETIME_LOOPS)
def test_list_loop_clean_directory_has_no_skip_warning(build, patch_name, bad, tmp_path):
    # negative control: nothing unreadable in the directory, so no warning
    target, call, field, _items = build(tmp_path)
    for p in list(Path(target).rglob('dir.*')):
        p.rmdir()
    result = call(target)
    assert _entries_skipped(result, field) is None


@pytest.mark.skipif(not hasattr(os, 'symlink') or os.name == 'nt', reason='needs unprivileged symlinks')
def test_broken_symlink_in_a_hooks_dir_is_skipped_and_disclosed(tmp_path):
    event = tmp_path / 'PreToolUse'
    event.mkdir()
    (event / 'good.sh').write_text('#!/bin/sh\n', encoding='utf-8')
    os.symlink(tmp_path / 'nowhere', event / 'dangling.sh')
    result = workspace.get_hooks(tmp_path, 'hooks/PreToolUse')
    assert [s['name'] for s in result['scripts']] == ['good.sh']
    assert 'dangling.sh' in _entries_skipped(result, 'hook scripts')['files']
