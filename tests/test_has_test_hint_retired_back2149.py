"""BACK-2149 S4: `has_test_hint` is retired with a note (the D8 pattern of `calls ?uncalled`), not moved.

It was an unmeasured test-name heuristic (a function counts as tested when a test file or test symbol name
resembles it), with its own test-directory rule beside TestLayout. Until the hotspots noun is removed at
the cut it answers unchanged; its help and schema say it is retired and that no field replaces it, and
neither metrics nor ast emits it.
"""
import json

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.hotspots import HotspotsAdapter

pytestmark = pytest.mark.component

BRANCHY = 'def branchy(x):\n' + ''.join(f'    if x == {n}:\n        return {n}\n' for n in range(12)) + '    return -1\n'


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / 'proj'
    (root / 'tests').mkdir(parents=True)
    (root / 'app.py').write_text(BRANCHY, encoding='utf-8')
    (root / 'tests' / 'test_app.py').write_text('def test_branchy():\n    assert True\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return root


def _says_retired(text):
    text = ' '.join(text.replace('`', '').replace('*', '').split())  # a guide's Markdown emphasis is not wording
    return ('has_test_hint is retired' in text and 'unmeasured test-name heuristic' in text
            and 'no field replaces it' in text)


def test_the_help_says_it_is_retired_with_no_replacement_field():
    help_data = HotspotsAdapter.get_help()
    assert _says_retired(' '.join(help_data['features'] + help_data['notes']))
    assert not any('Heuristic test-coverage hint' in line for line in help_data['features'])


def test_the_schema_says_it_is_retired_with_no_replacement_field():
    assert _says_retired(' '.join(HotspotsAdapter.get_schema()['notes']))


def test_the_rendered_help_page_says_so():
    result = run('help://hotspots')
    assert result.returncode == 0, result.stderr
    assert _says_retired(result.stdout)


def test_it_answers_unchanged_until_the_cut(project):
    """Control: retired is not removed. The hint is still on every function entry, with its old value."""
    result = run('hotspots', 'proj', '--functions-only', '--format', 'json', '--no-gitignore')
    assert result.returncode == 0, result.stderr
    fns = json.loads(result.stdout)['function_hotspots']
    assert [(fn['name'], fn['has_test_hint']) for fn in fns] == [('branchy', True)]


@pytest.mark.parametrize('argv, field', [
    (['metrics', 'proj', '--hotspots'], 'hotspots'),
    (['ast://proj?complexity>=10&sort=-complexity&limit=10'], 'results'),
])
def test_it_is_not_moved_to_the_replacement_homes(project, argv, field):
    result = run(*argv, '--format', 'json', '--no-gitignore')
    assert result.returncode == 0, result.stderr
    entries = json.loads(result.stdout)[field]
    assert entries, 'the fixture must give the replacement home something to rank'
    assert all('has_test_hint' not in entry for entry in entries)
