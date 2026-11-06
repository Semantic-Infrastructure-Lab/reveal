"""BACK-2149 S5: the hotspots noun is retired at the note stage (D5): it answers as before, exit code
included, and prints one "is deprecated; use ..." note naming its replacements (ground rule 7).

Files: `reveal metrics <path> --hotspots` (`metrics://<path>?hotspots=true`), with the findings gate.
Functions: `ast://<path>?complexity>=10&sort=-complexity&limit=10`. The two only-flags retire into the
same two commands. has_test_hint has no replacement field, and the note says so. Each replacement the
rows name is run here and must give the ranking hotspots gives.
"""
import json

import pytest

from conftest import _run_reveal_direct as run
from reveal.cli.invocation import RETIREMENTS

pytestmark = pytest.mark.component

BRANCHY = 'def branchy(x):\n' + ''.join(f'    if x == {n}:\n        return {n}\n' for n in range(24)) + '    return -1\n'
LONG = 'def long0():\n' + ''.join(f'    v{i} = {i}\n' for i in range(130)) + '    return v0\n'
MEDIUM = 'def medium(x):\n' + ''.join(f'    if x == {n}:\n        return {n}\n' for n in range(11)) + '    return -1\n'

ROWS = ('subcommand:hotspots', 'scheme:hotspots', 'param:hotspots.functions_only', 'param:hotspots.files_only')


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / 'proj'
    (root / 'pkg').mkdir(parents=True)
    (root / 'app.py').write_text(BRANCHY, encoding='utf-8')
    (root / 'pkg' / 'long.py').write_text(LONG + '\n\n' + MEDIUM, encoding='utf-8')
    (root / 'pkg' / 'clean.py').write_text('def add(a, b):\n    return a + b\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return root


def _json(*argv):
    result = run(*argv, '--format', 'json', '--no-gitignore')
    return result, json.loads(result.stdout)


def _retired(doc):
    return [w for w in doc.get('meta', {}).get('warnings', []) if w.get('code') == 'retired_spelling']


def _unretired(doc):
    meta = doc.get('meta', {})
    meta['warnings'] = [w for w in meta.get('warnings', []) if w.get('code') != 'retired_spelling']
    if not meta['warnings']:
        del meta['warnings']
    return doc


def test_each_row_is_a_note_that_names_a_replacement():
    for key in ROWS:
        entry = RETIREMENTS[key]
        assert entry.stage == 'note' and not entry.removed, key
    for key in ('subcommand:hotspots', 'scheme:hotspots'):
        text = RETIREMENTS[key].text
        assert 'metrics' in text and 'hotspots' in text.split('use ', 1)[1], text
        assert 'ast://<path>?complexity>=10&sort=-complexity&limit=10' in text, text
        assert 'has_test_hint' in text and 'unmeasured test-name heuristic' in text, text
        assert 'no replacement field' in text, text
    assert 'ast://<path>?complexity>=10&sort=-complexity' in RETIREMENTS['param:hotspots.functions_only'].text
    assert 'metrics' in RETIREMENTS['param:hotspots.files_only'].text


@pytest.mark.parametrize('argv, keys', [
    (['hotspots', 'proj'], ['subcommand:hotspots']),
    (['hotspots://proj'], ['scheme:hotspots']),
    (['hotspots', 'proj', '--functions-only'], ['subcommand:hotspots', 'param:hotspots.functions_only']),
    (['hotspots://proj?files_only=true'], ['scheme:hotspots', 'param:hotspots.files_only']),
])
def test_a_retired_spelling_notes_once_and_answers_as_before(project, monkeypatch, argv, keys):
    noted, noted_doc = _json(*argv)
    text = run(*argv, '--no-gitignore')
    for key in keys:
        assert noted.stderr.count(f'note: {RETIREMENTS[key].text}') == 1, (key, noted.stderr)
        assert text.stderr.count(f'note: {RETIREMENTS[key].text}') == 1, (key, text.stderr)
    assert sorted(w['field'] for w in _retired(noted_doc)) == sorted(keys)
    for key in ROWS:
        monkeypatch.delitem(RETIREMENTS, key)
    plain, plain_doc = _json(*argv)
    plain_text = run(*argv, '--no-gitignore')
    assert 'deprecated' not in plain.stderr
    assert noted.returncode == plain.returncode == 0
    assert text.stdout == plain_text.stdout
    assert _unretired(noted_doc) == _unretired(plain_doc)


@pytest.mark.parametrize('argv', [['hotspots', 'proj'], ['hotspots://proj']])
def test_the_gate_still_answers_at_the_note_stage(project, argv):
    """Not the cut error: --fail-on findings still exits 1 (branchy has complexity 25)."""
    result = run(*argv, '--fail-on', 'findings', '--format', 'json', '--no-gitignore')
    assert result.returncode == 1, result.stderr
    assert json.loads(result.stdout)['summary']['has_findings'] is True


def test_the_file_replacement_gives_the_same_ranking_and_gate(project):
    _, hot = _json('hotspots', 'proj', '--files-only', '--fail-on', 'findings')
    for argv in (['metrics', 'proj', '--hotspots'], ['metrics://proj?hotspots=true']):
        result, met = _json(*argv, '--fail-on', 'findings')
        assert met['hotspots'] == hot['file_hotspots'], argv
        assert result.returncode == 1 and met['summary']['has_findings'] is True


def test_the_function_replacement_gives_the_same_ranking(project):
    _, hot = _json('hotspots', 'proj', '--functions-only')
    _, ast = _json('ast://proj?complexity>=10&sort=-complexity&limit=10')
    def rows(entries):
        return [(e['name'], e['line'], e['complexity']) for e in entries]
    assert [(name, cx) for name, _, cx in rows(hot['function_hotspots'])] == [('branchy', 25), ('medium', 12)]
    assert rows(ast['results']) == rows(hot['function_hotspots'])
