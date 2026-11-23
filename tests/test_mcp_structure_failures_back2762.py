"""MCP ``reveal_structure`` and ``reveal_run`` give the file route's failure (BACK-2762, BACK-2588 item 2).

A file whose structure failed (XML or notebook that does not parse, a notebook of the wrong shape, an Office file that
is not a zip) makes the CLI exit 3 or 2 naming the cause; MCP ``reveal_structure`` answered it as an empty success
(``File: bad.xml (12B, 1 line)``, ``is_error=False``) and ``reveal_run`` on bad XML returned the CLI's stdout as a
success. ``reveal_structure`` of a directory under a ``REVEAL_CONFIG`` naming no file said "Internal error executing
tool" where the CLI exits 2 naming the path. COMMAND_MODEL "Transports": the outcome is the CLI's own, checked over a
real stdio session. Siblings in the same session (a good file, a recovered parse, a directory) stay answers.
"""
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip('mcp')
sys.path.insert(0, str(Path(__file__).parent))
from conftest import _run_reveal_direct  # noqa: E402
from test_mcp_expected_errors_back1992 import _run, _text  # noqa: E402  (the repo's real stdio harness)

pytestmark = [pytest.mark.mcp, pytest.mark.component]

# name -> (content, the CLI's exit)
FAILED = {
    'bad.xml': ('<root></bad>', 3),
    'bad.ipynb': ('{"cells": [}', 3),
    'shape.ipynb': ('[]', 2),
    'bad.docx': ('not zip', 2),
    'bad.xlsx': ('not zip', 2),
}


@pytest.fixture
def files(tmp_path):
    root = tmp_path / 'fx'
    root.mkdir()
    for name, (content, _) in FAILED.items():
        (root / name).write_text(content, encoding='utf-8')
    (root / 'ok.py').write_text('def ok():\n    return 1\n', encoding='utf-8')
    (root / 'syn.py').write_text('def f(:\n  pass\n', encoding='utf-8')
    return root


def _cli_json(path):
    run = _run_reveal_direct(path, '--format', 'json')
    return run.returncode, json.loads(run.stdout)


@pytest.mark.parametrize('name', sorted(FAILED))
def test_the_cli_exit_names_the_cause(files, name):
    """The contract the MCP tools must carry: the CLI's exit and the cause in its answer."""
    code, doc = _cli_json(files / name)
    assert code == FAILED[name][1], (name, code)
    assert doc.get('error'), doc


def test_structure_reports_each_failed_file_as_a_tool_error_over_stdio(files):
    causes = {name: _cli_json(files / name)[1]['error'] for name in FAILED}
    seen = {}

    async def scenario(session):
        for name in FAILED:
            result = await session.call_tool('reveal_structure', {'path': str(files / name)})
            seen[name] = (result.is_error, _text(result))

    _run(files.parent, scenario)
    for name, (is_error, text) in seen.items():
        assert is_error, f'{name}: a silent success: {text!r}'
        assert causes[name] in text, (name, text)


def test_structure_answers_a_good_file_and_a_recovered_parse_over_stdio(files):
    seen = {}

    async def scenario(session):
        for name in ('ok.py', 'syn.py'):
            result = await session.call_tool('reveal_structure', {'path': str(files / name)})
            seen[name] = (result.is_error, _text(result))
        result = await session.call_tool('reveal_structure', {'path': str(files)})
        seen['dir'] = (result.is_error, _text(result))

    _run(files.parent, scenario)
    assert seen['ok.py'][0] is False and 'ok()' in seen['ok.py'][1]
    assert seen['syn.py'][0] is False, seen['syn.py']
    assert seen['dir'][0] is False and 'ok.py' in seen['dir'][1] and 'bad.xml' in seen['dir'][1]


def test_run_reports_failed_xml_as_a_tool_error_over_stdio(files):
    path = files / 'bad.xml'
    code, doc = _cli_json(path)
    seen = {}

    async def scenario(session):
        seen['text'] = await session.call_tool('reveal_run', {'args': [str(path)]})
        seen['json'] = await session.call_tool('reveal_run', {'args': [str(path), '--format', 'json']})

    _run(files.parent, scenario)
    assert code == 3
    assert seen['text'].is_error, _text(seen['text'])
    assert doc['error'] in _text(seen['text'])
    # JSON mode: the failure's text is the CLI's JSON document exactly (COMMAND_MODEL "Transports").
    assert seen['json'].is_error, _text(seen['json'])
    assert json.loads(_text(seen['json'])) == doc


def test_run_answers_a_good_file_over_stdio(files):
    seen = {}

    async def scenario(session):
        seen['ok'] = await session.call_tool('reveal_run', {'args': [str(files / 'ok.py')]})

    _run(files.parent, scenario)
    assert seen['ok'].is_error is False and 'ok()' in _text(seen['ok'])


def _directory_over_stdio(files, monkeypatch, config):
    if config is not None:
        monkeypatch.setenv('REVEAL_CONFIG', config)
    seen = {}

    async def scenario(session):
        seen['dir'] = await session.call_tool('reveal_structure', {'path': str(files)})

    _run(files.parent, scenario)
    return seen['dir']


def test_structure_of_a_directory_under_a_missing_config_is_the_invalid_request(files, monkeypatch):
    missing = files.parent / 'no-such-dir' / 'reveal.yaml'
    monkeypatch.setenv('REVEAL_CONFIG', str(missing))
    cli = _run_reveal_direct(files)
    assert cli.returncode == 2 and 'reveal.yaml' in cli.stderr, (cli.returncode, cli.stderr)
    result = _directory_over_stdio(files, monkeypatch, str(missing))
    assert result.is_error
    assert 'Internal error' not in _text(result), _text(result)
    assert 'reveal.yaml' in _text(result), _text(result)


def test_structure_of_a_directory_without_a_selected_config_answers(files, monkeypatch):
    monkeypatch.delenv('REVEAL_CONFIG', raising=False)
    result = _directory_over_stdio(files, monkeypatch, None)
    assert result.is_error is False and 'ok.py' in _text(result)


@pytest.mark.parametrize('name', sorted(FAILED))
def test_direct_structure_returns_the_failure(files, name):
    """The direct Python call (the tool function itself) keeps its string contract: the failure sentinel."""
    from reveal import mcp_server
    out = mcp_server.reveal_structure(str(files / name))
    assert isinstance(out, mcp_server._ToolFailure), out
    assert _cli_json(files / name)[1]['error'] in out


@pytest.mark.parametrize('name,needle', [('ok.py', 'ok()'), ('syn.py', 'f(')])
def test_direct_structure_of_a_good_file_is_an_answer(files, name, needle):
    from reveal import mcp_server
    out = mcp_server.reveal_structure(str(files / name))
    assert not isinstance(out, mcp_server._ToolFailure), out
    assert needle in out
