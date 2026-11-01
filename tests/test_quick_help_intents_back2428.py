"""Quick-help commands answer their advertised project, boundary and document intents."""
import json
import shlex

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.help import HelpAdapter

pytestmark = pytest.mark.component


def intent(phrase):
    rows = HelpAdapter('').get_element('quick')['decision_tree']
    matches = [row for row in rows if phrase in row['want']]
    assert len(matches) == 1, matches
    return matches[0]


def command(row, *flags):
    return run(*shlex.split(row['example'])[1:], *flags)


def test_overview_intent_promises_the_compact_map(tmp_path, monkeypatch):
    src = tmp_path / 'src'
    src.mkdir()
    (src / 'app.py').write_text('from leaf import value\n', encoding='utf-8')
    (src / 'leaf.py').write_text('value = 1\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    row = intent('get oriented')
    response = command(row, '--format', 'json')
    assert response.returncode == 0, response.stderr
    answer = json.loads(response.stdout)
    assert answer['map_status'] == 'complete'
    assert answer['scope']['total_code_files'] == 2
    assert answer['map']['fan_in']['rows'] == [
        {'file': 'leaf.py', 'fan_in': 1, 'fan_out': 0}]
    assert not {'stats', 'architecture', 'git_log', 'complex_functions'} & answer.keys()
    assert not any(claim in row['want'] for claim in ('quality', 'hotspots', 'activity'))


def test_boundary_intent_retains_env_alongside_http(tmp_path, monkeypatch):
    src = tmp_path / 'src'
    src.mkdir()
    (src / 'app.py').write_text(
        'import os\nfrom flask import Flask\napp = Flask(__name__)\n'
        '@app.route("/items")\ndef items():\n    return os.getenv("ITEM_TOKEN")\n',
        encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    response = command(intent('env vars'), '--format', 'json')
    assert response.returncode == 0, response.stderr
    surfaces = json.loads(response.stdout)['surfaces']
    assert {row['path'] for row in surfaces['http']} == {'/items'}
    assert {row['name'] for row in surfaces.get('env', [])} == {'ITEM_TOKEN'}
    # The narrower HTTP route remains available and continues to filter other categories.
    http = intent('map HTTP routes')
    response = command(http, '--format', 'json')
    assert response.returncode == 0, response.stderr
    surfaces = json.loads(response.stdout)['surfaces']
    assert set(surfaces) == {'http'}
    assert {row['path'] for row in surfaces['http']} == {'/items'}


def test_markdown_section_intent_returns_body_not_outline(tmp_path, monkeypatch):
    (tmp_path / 'README.md').write_text(
        '# Project\n\n## Building\nUse cargo build --release.\n'
        '\n## Testing\nUse cargo test.\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    response = command(intent('one section of a markdown'))
    assert response.returncode == 0, response.stderr
    assert 'Use cargo build --release.' in response.stdout
    assert 'Use cargo test.' not in response.stdout


def test_callers_intent_is_unchanged_and_finds_the_caller(tmp_path, monkeypatch):
    row = intent('know who calls a function')
    assert row == {
        'want': 'know who calls a function', 'use': 'calls://',
        'example': "reveal 'calls://src/?callers=my_fn'"}
    src = tmp_path / 'src'
    src.mkdir()
    (src / 'app.py').write_text(
        'def my_fn():\n    return 1\ndef caller():\n    return my_fn()\n',
        encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    response = command(row, '--format', 'json')
    assert response.returncode == 0, response.stderr
    answer = json.loads(response.stdout)
    assert answer['total_callers'] == 1
    assert answer['levels'][0]['callers'][0]['caller'] == 'caller'
