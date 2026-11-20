"""MCP reveal_run(args): the CLI's grammar, answer and outcome over one tool (BACK-2710, plan D20).

COMMAND_MODEL "Transports": in JSON mode MCP returns exactly the CLI's JSON answer, the outcome is mapped from the
CLI's own outcome and never re-decided, and text mode is the CLI's stdout followed by its stderr. reveal_run runs the
CLI's own dispatch in process, so these tests compare it with the CLI on every declared noun, then pin the outcome
mapping (invalid request -> tool error, findings -> result) and the read-only refusals.
"""
import asyncio
import json
import os
import sys

import pytest

pytest.importorskip('mcp')

from conftest import _run_reveal_direct  # noqa: E402
from test_declared_parity_back2053 import NOUNS, argv_for, project  # noqa: E402,F401  (project is a fixture)
from reveal import mcp_server  # noqa: E402
from reveal.cli.routing.declared import declared_adapter_class  # noqa: E402
from reveal.mcp_server import _ToolFailure, reveal_query, reveal_run  # noqa: E402


def _cli_argv(noun, spelling):
    walk = ['--respect-gitignore=off'] if declared_adapter_class(noun).RESOURCE_SPEC.walks else []
    return [*argv_for(noun, spelling), *walk]


def _failed(result):
    return isinstance(result, _ToolFailure)


def _error_text(result):
    assert _failed(result), str(result)[:300]
    return str(result)[len('[reveal error: '):-1]


@pytest.fixture
def app(tmp_path, monkeypatch):
    (tmp_path / 'app.py').write_text(
        'import os\n\n\ndef process_order(order):\n    total = order["total"]\n    return total\n\n\n'
        'def main():\n    return process_order({"total": 1})\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_reveal_run_is_one_registered_tool_taking_a_list_of_strings():
    tools = {tool.name: tool for tool in asyncio.run(mcp_server.mcp.list_tools())}
    schema = tools['reveal_run'].input_schema
    assert schema['required'] == ['args']
    assert schema['properties']['args']['type'] == 'array'
    assert schema['properties']['args']['items'] == {'type': 'string'}
    assert tools['reveal_run'].annotations.read_only_hint is True


@pytest.mark.parametrize('noun', NOUNS)
def test_json_answer_is_the_clis_json_exactly_on_every_declared_noun(project, noun):  # noqa: F811
    argv = [*_cli_argv(noun, 'cli'), '--format', 'json']
    cli = _run_reveal_direct(*argv)
    assert cli.returncode == 0, cli.stderr
    expected = json.loads(cli.stdout)
    assert expected.get('type'), 'an empty answer would compare equal vacuously'
    result = reveal_run(argv)
    assert not _failed(result), str(result)[:300]
    assert json.loads(result) == expected


@pytest.mark.parametrize('noun', NOUNS)
def test_a_uri_through_reveal_run_answers_as_reveal_query_does(project, noun):  # noqa: F811
    uri = argv_for(noun, 'uri')[0]
    assert reveal_run([uri]) == reveal_query(uri)


def test_text_mode_is_the_clis_stdout(app):
    argv = ['calls', '.', '--callers', 'process_order']
    cli = _run_reveal_direct(*argv)
    assert cli.returncode == 0 and 'main' in cli.stdout
    assert reveal_run(argv) == cli.stdout


def test_an_invalid_request_is_a_tool_error_naming_what_the_noun_accepts(app):
    cli = _run_reveal_direct('calls', '.', '--nope')
    assert cli.returncode == 2
    text = _error_text(reveal_run(['calls', '.', '--nope']))
    assert "unsupported control '--nope'" in text and 'callers' in text


def test_an_invalid_request_in_json_mode_is_a_tool_error_carrying_the_clis_document(app):
    argv = ['calls', '.', '--nope', '--format', 'json']
    cli = _run_reveal_direct(*argv)
    assert cli.returncode == 2
    document = json.loads(_error_text(reveal_run(argv)))
    assert document == json.loads(cli.stdout)
    assert document['meta']['errors'][0]['code'] == 'invalid_request'


def test_an_argparse_usage_error_is_a_tool_error_not_a_result(app):
    """Exit 2 with nothing on stdout (the parser's own error) must not read as an answer."""
    cli = _run_reveal_direct('ast', '.', '--format', 'yaml')
    assert cli.returncode == 2 and not cli.stdout.strip()
    assert 'yaml' in _error_text(reveal_run(['ast', '.', '--format', 'yaml']))


def test_a_target_that_matches_nothing_is_a_tool_error(app):
    assert _run_reveal_direct('calls', '.', '--callers', 'no_such_fn').returncode == 2
    assert 'no_such_fn' in _error_text(reveal_run(['calls', '.', '--callers', 'no_such_fn']))


def test_findings_are_a_result_not_an_error(app):
    argv = ['check', 'app.py', '--fail-on', 'low']
    cli = _run_reveal_direct(*argv)
    assert cli.returncode == 1, (cli.stdout, cli.stderr)  # positive control: the fixture has a finding
    result = reveal_run(argv)
    assert not _failed(result)
    assert result.startswith(cli.stdout.rstrip('\n'))


@pytest.mark.parametrize('argv,cause', [
    (['calls', '.', '--callers', 'main', '--output', 'json=out.json'], '--output FORMAT=PATH'),
    (['app.py', '--also-json', 'out.json'], '--output FORMAT=PATH'),
    (['app.py', '--copy'], '--copy'),
    (['--stdin'], "--stdin reads this server's own input"),
    (['dev', 'new-rule', 'C999', 'my_rule'], 'reveal dev'),
    (['offline'], 'reveal offline'),
])
def test_writing_requests_are_refused_before_anything_runs(app, argv, cause):
    """Refused by reveal_run's own admission (its message names the tool), not by a parser error, and nothing
    in the working directory changes."""
    before = sorted(p.name for p in app.iterdir())
    text = _error_text(reveal_run(argv))
    assert cause in text and 'reveal_run' in text
    assert sorted(p.name for p in app.iterdir()) == before


def test_args_must_be_a_list_of_strings(app):
    assert 'list of strings' in _error_text(reveal_run('calls . --callers main'))


def test_process_global_flags_end_with_the_request(app):
    from reveal.utils import json_utils
    from reveal.utils.gitignore import gitignore_enabled
    reveal_run(['ast', '.', '--respect-gitignore', 'off', '--provenance', '--format', 'json'])
    assert gitignore_enabled() is True
    assert json_utils._provenance_enabled is False


def test_the_outcome_mapping_reads_the_exit_code_when_no_answer_was_emitted():
    """Negative controls for _run_outcome: an exit 2 with a document is an error carrying it; exit 0 is a result."""
    from reveal.mcp_server import _Captured, _run_outcome
    document = '{"type": "x", "meta": {"errors": [{"code": "invalid_request"}]}}'
    assert _error_text(_run_outcome(_Captured(document, '', 2))) == document
    assert _error_text(_run_outcome(_Captured('', 'error: bad', 2))) == 'error: bad'
    assert _run_outcome(_Captured('answer\n', '', 0)) == 'answer\n'
    assert _run_outcome(_Captured('answer\n', '', 1)) == 'answer\n'  # findings
    assert _error_text(_run_outcome(_Captured('', 'boom', 3))) == 'boom'


@pytest.mark.mcp
@pytest.mark.component
def test_reveal_run_over_a_real_stdio_session(app, tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    seen = {}

    async def exercise():
        env = {key: value for key, value in os.environ.items() if not key.startswith('REVEAL_')}
        env.update(REVEAL_DISK_CACHE='0', XDG_CONFIG_HOME=str(tmp_path / 'xdg'))
        params = StdioServerParameters(command=sys.executable, args=['-m', 'reveal.mcp_server'], env=env,
                                       cwd=str(app))
        with (tmp_path / 'server-stderr.txt').open('w', encoding='utf-8') as errlog:
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    seen['ok'] = await session.call_tool(
                        'reveal_run', {'args': ['calls', '.', '--callers', 'process_order', '--format', 'json']})
                    seen['bad'] = await session.call_tool('reveal_run', {'args': ['calls', '.', '--nope']})

    asyncio.run(asyncio.wait_for(exercise(), timeout=120))
    assert not seen['ok'].is_error, seen['ok'].content[0].text[:300]
    assert len(seen['ok'].content) == 1
    assert json.loads(seen['ok'].content[0].text)['type'] == 'calls_query'
    assert seen['bad'].is_error
    assert "unsupported control '--nope'" in seen['bad'].content[0].text
