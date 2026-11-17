"""One answer on every transport (BACK-2650, BACK-2657, BACK-2325 note #17).

A directory holding one good file, one Python syntax error and one invalid notebook is a
partial-input answer (exit 3) on every noun below. The CLI's JSON is the answer: MCP returns
exactly that JSON (never with stderr appended after it), every diagnostic the CLI prints on
stderr is already in that JSON, the JSON itself says the answer is incomplete (MCP has no exit
code; file sinks and batches lose it too), and a ``--stdin`` batch exits with the most severe
outcome of its requests instead of 0.
"""
import asyncio
import json
import os
import subprocess
import sys

import pytest

from tests.conftest import _run_reveal_in

pytestmark = [pytest.mark.cli]

NOUNS = [
    ('ast', '?complexity>0'),
    ('metrics', ''),
    ('calls', '?callers=target'),
    ('imports', ''),
]
# BACK-2657's request: a retired spelling, whose replaced-by note rides in meta.warnings, not as text.
MCP_NOUNS = NOUNS + [('calls', '?rank=callers')]
FIXTURE_FILES = ('b.py', 'bad.ipynb')


@pytest.fixture(scope='module')
def degraded(tmp_path_factory):
    root = tmp_path_factory.mktemp('degraded')
    (root / 'a.py').write_text('def target():\n    return 1\n\n\ndef caller():\n    return target()\n',
                               encoding='utf-8')
    (root / 'b.py').write_text('from a import target\n\n\ndef c():\n    return target()\n\n\n'
                               'def broken(:\n    pass\n\n\ndef d():\n    return target()\n', encoding='utf-8')
    (root / 'bad.ipynb').write_text('{not json', encoding='utf-8')
    return root


def _uri(noun, query, root):
    return f'{noun}://{root.as_posix()}{query}'


def _cli(*argv, stdin=None):
    """The real process: stderr as a terminal shows it, logging handlers included."""
    env = {**os.environ, 'REVEAL_DISK_CACHE': '0'}
    return subprocess.run([sys.executable, '-m', 'reveal', *argv], capture_output=True, text=True,
                          encoding='utf-8', input=stdin, env=env)


def _answer(document):
    """The answer without the per-invocation provenance manifest (its command line differs by transport)."""
    return {key: value for key, value in document.items() if key != 'execution'}


@pytest.mark.mcp
@pytest.mark.parametrize('noun,query', MCP_NOUNS)
def test_mcp_json_is_exactly_the_cli_json(degraded, noun, query):
    from reveal import mcp_server
    uri = _uri(noun, query, degraded)
    cli = _cli(uri, '--format', 'json', '--provenance')
    assert cli.returncode == 3, cli.stderr
    tool_text = mcp_server.reveal_query(uri, provenance=True)
    assert '[stderr:' not in tool_text and '[note:' not in tool_text
    assert _answer(json.loads(tool_text)) == _answer(json.loads(cli.stdout))


def _states_cause(cause, message):
    """A syntax error's wording differs between the two Python parsers metrics reads with (tree-sitter
    for statistics, ``ast`` inside its quality rules), so for a parse failure the JSON states the class."""
    if 'syntax' in cause.lower():
        return any(word in message for word in ('syntax', 'did not parse'))
    return cause[:20] in message


@pytest.mark.parametrize('noun,query', NOUNS)
def test_every_stderr_diagnostic_is_in_the_json(degraded, noun, query):
    """Dropping the stderr append is a fix only if nothing it carried is lost (BACK-1998)."""
    cli = _cli(_uri(noun, query, degraded), '--format', 'json')
    assert cli.returncode == 3
    warnings = json.loads(cli.stdout)['meta']['warnings']
    named = [line for line in cli.stderr.splitlines() if any(name in line for name in FIXTURE_FILES)]
    for line in named:
        name = next(name for name in FIXTURE_FILES if name in line)
        cause = line.rsplit(f'{name}: ', 1)[-1].strip()
        entries = [w for w in warnings if name in json.dumps(w)]
        assert entries, (line, warnings)
        assert any(_states_cause(cause, w['message']) for w in entries), (line, entries)


def test_metrics_json_names_the_failed_file_and_cause(degraded):
    """Metrics said only '2 file(s) did not parse cleanly'; which file, and why, reached stderr alone."""
    result = _run_reveal_in(degraded, _uri('metrics', '', degraded), '--format', 'json')
    assert result.returncode == 3
    entry = next(w for w in json.loads(result.stdout)['meta']['warnings'] if w['type'] == 'parse_degraded')
    assert 'b.py' in entry['files']
    assert 'b.py' in entry['message']


@pytest.mark.parametrize('noun,query', NOUNS)
def test_an_incomplete_answer_says_so_in_its_json(degraded, noun, query):
    result = _run_reveal_in(degraded, _uri(noun, query, degraded), '--format', 'json')
    assert result.returncode == 3
    kinds = [w['type'] for w in json.loads(result.stdout)['meta']['warnings']]
    assert kinds.count('analysis_incomplete') == 1, kinds


@pytest.mark.parametrize('noun,query', NOUNS)
def test_stdin_batch_exits_like_the_direct_request(degraded, noun, query):
    uri = _uri(noun, query, degraded)
    direct = _run_reveal_in(degraded, uri, '--format', 'json')
    piped = _run_reveal_in(degraded, '--stdin', '--format', 'json', stdin=uri + '\n')
    assert direct.returncode == 3
    assert piped.returncode == direct.returncode, piped.stderr
    assert json.loads(piped.stdout) == json.loads(direct.stdout)


def test_stdin_batch_takes_the_most_severe_outcome(degraded, tmp_path):
    clean = tmp_path / 'clean'
    clean.mkdir()
    (clean / 'ok.py').write_text('def ok():\n    return 1\n', encoding='utf-8')
    lines = f'{_uri("ast", "", clean)}\n{_uri("ast", "?complexity>0", degraded)}\n{_uri("ast", "", clean)}\n'
    assert _run_reveal_in(tmp_path, '--stdin', stdin=lines).returncode == 3


def test_stdin_aggregate_batch_counts_an_incomplete_answer(degraded):
    piped = _run_reveal_in(degraded, '--stdin', '--batch', '--format', 'json',
                           stdin=_uri('calls', '?callers=target', degraded) + '\n')
    assert piped.returncode == 3, piped.stdout
    assert json.loads(piped.stdout)['results'][0]['status'] == 'incomplete'


@pytest.mark.mcp
def test_metrics_text_answer_over_mcp_names_the_failed_file(degraded):
    from reveal import mcp_server
    text = mcp_server.reveal_query(_uri('metrics', '', degraded))
    assert 'b.py' in text and 'did not parse cleanly' in text


@pytest.mark.mcp
@pytest.mark.component
def test_real_stdio_session_returns_parseable_json_per_noun(degraded, tmp_path):
    pytest.importorskip('mcp')
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    seen = {}

    async def exercise():
        params = StdioServerParameters(command=sys.executable, args=['-m', 'reveal.mcp_server'],
                                       env={**os.environ, 'REVEAL_DISK_CACHE': '0'})
        with (tmp_path / 'server-stderr.txt').open('w', encoding='utf-8') as errlog:
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    for noun, query in NOUNS:
                        result = await session.call_tool(
                            'reveal_query', {'uri': _uri(noun, query, degraded), 'provenance': True})
                        assert not result.is_error, noun
                        # The first block is the CLI's JSON exactly; any stderr rides in a second block.
                        seen[noun] = json.loads(result.content[0].text)

    asyncio.run(asyncio.wait_for(exercise(), timeout=180))
    for noun, document in seen.items():
        assert 'analysis_incomplete' in [w['type'] for w in document['meta']['warnings']], noun
