"""Codex memory/workspace readers: measured acquisition and outcomes (BACK-2618 Step 3; ruling Q7).

``codex://memories``, ``rules``, ``skills[/NAME]``, ``plugins[/NAME]`` and ``memories/pipeline`` had none of the
evidence the other Codex readers keep (notes #5-#12). Before:

- an unreadable memory or rule was listed with empty content, an unreadable directory was skipped, exit 0;
- an unreadable SKILL.md was dropped, so ``skills/NAME`` for it said "not found";
- a malformed plugin manifest was dropped and a list-shaped one raised ``AttributeError`` (exit 1);
- a missing skills/plugins directory exited 1 while missing memories/rules exited 0;
- the pipeline opened SQLite read-write, cut ``recent_outputs`` at 20 with no marker, and exited 1 on an install
  without ``stage1_outputs``;
- skills/plugins wrote ``str(path)``.

Now (Q7): confirmed absence of the directory or database is a complete empty answer, exit 0, with
``source_absent`` in the receipt; acquisition loss is exit 3 with the readable entries kept and the failure named by
its cause, not its path; a named item that is not there exits 2 only when every definition was read, else 3; the
pipeline reads read-only, says ``table_absent`` for an install without the table, and marks its 20-row cut.
"""
import json
import os
import sqlite3
import sys

import pytest

from codex_session_fixture import CODEX_STAGE1_OUTPUTS_DDL, build_codex_home
from conftest import _run_reveal_direct
from reveal.adapters.codex.adapter import CodexAdapter

posix_permissions = pytest.mark.skipif(
    sys.platform == 'win32' or (hasattr(os, 'geteuid') and os.geteuid() == 0),
    reason='chmod 000 denies reading only for a non-root POSIX user')


@pytest.fixture
def codex(tmp_path, monkeypatch):
    home = build_codex_home(tmp_path / 'home')
    monkeypatch.setattr(CodexAdapter, 'CODEX_HOME', home)
    monkeypatch.setattr(CodexAdapter, 'CODEX_DB', home / 'state_5.sqlite')
    monkeypatch.chdir(tmp_path)
    yield home
    for path in home.rglob('*'):  # restore modes so tmp_path cleanup can remove everything
        try:
            path.chmod(0o755 if path.is_dir() else 0o644)
        except OSError:
            pass


def _json(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run, (json.loads(run.stdout) if run.stdout.strip().startswith('{') else {})


def _proof(doc):
    return doc['meta']['workspace_analysis']


def _write(path, text='x\n'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def _deny(path):
    path.chmod(0)


# --- memories ---------------------------------------------------------------------------------------------------

def test_memories_lists_every_file_with_a_receipt(codex):
    _write(codex / 'memories' / 'a.md', 'alpha\n')
    _write(codex / 'memories' / 'sub' / 'b.md', 'beta\n')
    run, doc = _json('codex://memories')
    assert run.returncode == 0, run.stderr
    assert [m['name'] for m in doc['memories']] == ['a.md', 'b.md'] and doc['total'] == 2
    assert [m['content'] for m in doc['memories']] == ['alpha\n', 'beta\n']
    assert all('\\' not in m['path'] and m['path'].endswith('/' + m['name']) for m in doc['memories'])
    proof = _proof(doc)
    assert (proof['candidate_entries'], proof['analyzed_entries'], proof['failed_entries']) == (2, 2, 0)
    assert proof['source_absent'] is False and proof['failures'] == []
    assert 'project scope' not in proof['count_rule']


def test_absent_memories_directory_is_a_complete_empty_answer(codex):
    run, doc = _json('codex://memories')
    assert run.returncode == 0, run.stderr
    assert doc['memories'] == [] and doc['total'] == 0 and 'error' not in doc
    assert _proof(doc)['source_absent'] is True and not doc['meta']['warnings']


def test_memories_path_that_is_a_file_is_lost_input(codex):
    _write(codex / 'memories', 'not a directory\n')
    run, doc = _json('codex://memories')
    assert run.returncode == 3, run.stderr
    assert _proof(doc)['discovery_failures'] == 1 and _proof(doc)['source_absent'] is False


@posix_permissions
def test_an_unreadable_memory_is_lost_not_empty(codex):
    _write(codex / 'memories' / 'a.md', 'alpha\n')
    _deny(_write(codex / 'memories' / 'b.md', 'secret\n'))
    run, doc = _json('codex://memories')
    assert run.returncode == 3, run.stderr
    assert [m['name'] for m in doc['memories']] == ['a.md'], doc['memories']  # the readable prefix, no empty b.md
    proof = _proof(doc)
    assert (proof['candidate_entries'], proof['analyzed_entries'], proof['failed_entries']) == (2, 1, 1)
    assert proof['failures'][0]['message'] == 'PermissionError: Permission denied'
    assert proof['failures'][0]['source'].endswith('/memories/b.md')
    assert any(w['type'] == 'analysis_incomplete' for w in doc['meta']['warnings'])


@posix_permissions
def test_an_unreadable_memory_directory_is_a_discovery_failure(codex):
    _write(codex / 'memories' / 'a.md')
    _write(codex / 'memories' / 'sub' / 'c.md')
    _deny(codex / 'memories' / 'sub')
    run, doc = _json('codex://memories')
    assert run.returncode == 3, run.stderr
    assert [m['name'] for m in doc['memories']] == ['a.md']
    assert _proof(doc)['discovery_failures'] == 1


def test_a_display_cut_keeps_the_receipt(codex):
    """Positive control: --head is a presentation cut, disclosed, not lost input."""
    _write(codex / 'memories' / 'a.md')
    _write(codex / 'memories' / 'b.md')
    run, doc = _json('codex://memories', '--head', '1')
    assert run.returncode == 0, run.stderr
    assert len(doc['memories']) == 1 and _proof(doc)['analyzed_entries'] == 2
    assert any(w['type'] == 'truncated' for w in doc['meta']['warnings'])


# --- rules ------------------------------------------------------------------------------------------------------

def test_rules_reads_only_rules_files(codex):
    _write(codex / 'rules' / 'a.rules', 'allow\n')
    _write(codex / 'rules' / 'notes.txt')
    run, doc = _json('codex://rules')
    assert run.returncode == 0, run.stderr
    assert [r['name'] for r in doc['rules']] == ['a.rules'] and _proof(doc)['candidate_entries'] == 1


def test_absent_rules_directory_is_a_complete_empty_answer(codex):
    run, doc = _json('codex://rules')
    assert run.returncode == 0 and doc['total'] == 0 and _proof(doc)['source_absent'] is True


@posix_permissions
def test_an_unreadable_rule_is_lost_not_empty(codex):
    _write(codex / 'rules' / 'a.rules')
    _deny(_write(codex / 'rules' / 'b.rules'))
    run, doc = _json('codex://rules')
    assert run.returncode == 3, run.stderr
    assert [r['name'] for r in doc['rules']] == ['a.rules'] and _proof(doc)['failed_entries'] == 1


# --- skills -----------------------------------------------------------------------------------------------------

def test_absent_skills_directory_is_a_complete_empty_answer(codex):
    import shutil
    shutil.rmtree(codex / 'skills')
    run, doc = _json('codex://skills')
    assert run.returncode == 0, run.stderr
    assert doc['skills'] == [] and doc['total'] == 0 and 'error' not in doc
    assert _proof(doc)['source_absent'] is True


def test_a_named_skill_reads_its_definition(codex):
    run, doc = _json('codex://skills/openai-docs')
    assert run.returncode == 0, run.stderr
    assert doc['type'] == 'codex_skill' and doc['name'] == 'openai-docs' and 'Use the docs.' in doc['content']
    assert doc['source'].endswith('/skills/openai-docs/SKILL.md') and '\\' not in doc['source']


@posix_permissions
def test_an_unreadable_skill_is_lost_input_listed_and_named(codex):
    _deny(_write(codex / 'skills' / 'locked' / 'SKILL.md', '---\nname: locked\n---\n'))
    run, doc = _json('codex://skills')
    assert run.returncode == 3, run.stderr
    assert [s['name'] for s in doc['skills']] == ['openai-docs'] and _proof(doc)['failed_entries'] == 1
    run, doc = _json('codex://skills/locked')
    assert run.returncode == 3, (run.returncode, run.stderr)  # it exists: lost input, not "not found" (exit 2)
    assert 'Skill lookup incomplete: locked' in run.stderr, run.stderr
    run, _ = _json('codex://skills/nope')
    assert run.returncode == 3, run.stderr  # absence cannot be confirmed while a definition is unread


# --- plugins ----------------------------------------------------------------------------------------------------

def test_absent_plugins_directory_is_a_complete_empty_answer(codex):
    import shutil
    shutil.rmtree(codex / 'plugins')
    run, doc = _json('codex://plugins')
    assert run.returncode == 0, run.stderr
    assert doc['plugins'] == [] and doc['total'] == 0 and 'error' not in doc and _proof(doc)['source_absent'] is True


@pytest.mark.parametrize('manifest,cause', [('{bad', 'JSONDecodeError'), ('[1, 2]', 'ValueError')])
def test_a_malformed_or_non_object_manifest_is_lost_input(codex, manifest, cause):
    _write(codex / 'plugins' / 'cache' / 'v' / 'bad' / '.codex-plugin' / 'plugin.json', manifest)
    run, doc = _json('codex://plugins')
    assert run.returncode == 3, run.stderr
    assert [p['name'] for p in doc['plugins']] == ['demo']
    proof = _proof(doc)
    assert proof['failed_entries'] == 1 and proof['failures'][0]['cause'] == cause


def test_a_named_plugin_reads_its_manifest(codex):
    run, doc = _json('codex://plugins/demo')
    assert run.returncode == 0, run.stderr
    assert doc['manifest']['version'] == '1.0.0' and '\\' not in doc['source']


def test_skill_and_plugin_paths_go_through_to_posix(codex, monkeypatch):
    """Windows control (BACK-2188): every path the readers publish is serialized by to_posix, never str(path)."""
    from reveal.adapters.codex.handlers import workspace
    seen = []

    def spy(path):
        seen.append(path)
        return 'POSIX:' + str(path)
    monkeypatch.setattr(workspace, 'to_posix', spy)
    skills = CodexAdapter('skills').get_structure()
    plugins = CodexAdapter('plugins').get_structure()
    skill = CodexAdapter('skills/openai-docs').get_structure()
    values = [skills['source'], plugins['source'], skill['source'],
              *(s['path'] for s in skills['skills']), *(p['path'] for p in plugins['plugins'])]
    assert all(value.startswith('POSIX:') for value in values), values


# --- memories/pipeline ------------------------------------------------------------------------------------------

def _pipeline_db(path, rows, selected):
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(CODEX_STAGE1_OUTPUTS_DDL)
        conn.executemany('INSERT INTO stage1_outputs (thread_id, source_updated_at, raw_memory, rollout_summary, '
                         'rollout_slug, generated_at, usage_count, selected_for_phase2) VALUES (?,?,?,?,?,?,?,?)',
                         [(f't{i:03d}', i, 'm', 's', f'slug{i}', i, i, int(i < selected)) for i in range(rows)])
        conn.commit()
    finally:
        conn.close()


def test_pipeline_without_the_table_is_a_complete_empty_answer(codex):
    run, doc = _json('codex://memories/pipeline')
    assert run.returncode == 0, run.stderr
    assert (doc['stage1_total'], doc['stage2_selected'], doc['recent_outputs']) == (0, 0, [])
    assert doc['meta']['pipeline_analysis']['decision'] == 'table_absent' and 'error' not in doc


def test_pipeline_without_a_database_is_a_complete_empty_answer(codex, monkeypatch):
    missing = codex / 'gone.sqlite'
    monkeypatch.setattr(CodexAdapter, 'CODEX_DB', missing)
    run, doc = _json('codex://memories/pipeline')
    assert run.returncode == 0, run.stderr
    assert doc['meta']['pipeline_analysis']['decision'] == 'source_absent'
    assert not missing.exists() and not (codex / 'memories_1.sqlite').exists()  # read-only: nothing created


def test_pipeline_marks_its_twenty_row_cut(codex):
    _pipeline_db(codex / 'memories_1.sqlite', 25, 3)
    run, doc = _json('codex://memories/pipeline')
    assert run.returncode == 0, run.stderr
    assert (doc['stage1_total'], doc['stage2_selected'], len(doc['recent_outputs'])) == (25, 3, 20)
    assert doc['recent_outputs'][0]['thread_id'] == 't024'  # newest first
    cut = [w for w in doc['meta']['warnings'] if w['type'] == 'truncated']
    assert cut and (cut[0]['field'], cut[0]['shown'], cut[0]['total']) == ('recent_outputs', 20, 25)
    assert doc['source'].endswith('/memories_1.sqlite')


def test_a_corrupt_pipeline_database_is_lost_input(codex):
    (codex / 'memories_1.sqlite').write_bytes(b'not a sqlite database' * 50)
    run, doc = _json('codex://memories/pipeline')
    assert run.returncode == 3, run.stderr
    proof = doc['meta']['pipeline_analysis']
    assert proof['failed_operations'] >= 1 and proof['decision'] == 'failed'
    assert str(codex) not in json.dumps(proof['operations'])  # causes, not host paths
