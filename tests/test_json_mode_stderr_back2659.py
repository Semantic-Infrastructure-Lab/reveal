"""A JSON answer is the whole answer: no per-file stderr line beside it (BACK-2659, step 4).

Per-file diagnostics that the JSON already states were also printed on stderr in JSON mode:
``Warning: Failed to analyze <file>: <cause>`` (ast, calls, contracts, trace), ``AST parse failed
(syntax error) for <file>`` (metrics' rules, hotspots), I003's ``layer config ... could not be used``
(check) and metrics' ``Check rules failed for <file>``. Over MCP each became a second ``[stderr: ...]``
block beside the JSON (COMMAND_MODEL "Transports": "until then registered MCP sends residual stderr
as a second text block"). In JSON mode they are no longer printed, in pool workers too; a text answer
still prints them.
"""
import asyncio
import json
import logging
import os
import subprocess
import sys

import pytest

from reveal.utils.invocation_log import answer_is_json, log_scope

A_PY = 'def target():\n    return 1\n\n\ndef caller():\n    return target()\n'
B_PY = ('from a import target\n\n\ndef c():\n    return target()\n\n\n'
        'def broken(:\n    pass\n\n\ndef d():\n    return target()\n')

# Every declared noun that reads a directory or a file, with a query its request needs.
NOUNS = [('ast', '?complexity>0'), ('architecture', ''), ('calls', '?callers=target'), ('calls', '?callees=caller'),
         ('contracts', ''), ('deps', ''), ('hotspots', ''), ('imports', ''), ('markdown', ''), ('metrics', ''),
         ('metrics', '?hotspots'), ('overview', ''), ('pack', ''), ('patches', ''), ('surface', ''),
         ('testability', ''), ('trace', '?from=caller'), ('git', ''), ('json', '/ok.json')]
IDS = [f'{noun}{query}' for noun, query in NOUNS]


def _degraded(root):
    """One good file, one with a syntax error, one unreadable notebook, plus a doc and a JSON file."""
    root.mkdir(parents=True)
    (root / 'a.py').write_text(A_PY, encoding='utf-8')
    (root / 'b.py').write_text(B_PY, encoding='utf-8')
    (root / 'bad.ipynb').write_text('{not json', encoding='utf-8')
    (root / 'r.md').write_text('# T\n\n[x](a.md)\n', encoding='utf-8')
    (root / 'ok.json').write_text('{"a": 1}\n', encoding='utf-8')
    return root


def _uri(noun, query, root):
    return f'{noun}://{root.as_posix()}{query}'


def _cli(cwd, *argv, **env):
    full = {key: value for key, value in os.environ.items() if not key.startswith('REVEAL_')}
    full.update(REVEAL_DISK_CACHE='0', XDG_CONFIG_HOME=str(cwd / 'xdg'), **env)
    return subprocess.run([sys.executable, '-m', 'reveal', *argv], capture_output=True, text=True,
                          encoding='utf-8', env=full, cwd=cwd, timeout=180)


@pytest.mark.cli
@pytest.mark.parametrize('noun,query', NOUNS, ids=IDS)
def test_json_answer_has_nothing_beside_it_on_stderr(tmp_path, noun, query):
    root = _degraded(tmp_path / 'proj')
    result = _cli(tmp_path, _uri(noun, query, root), '--format', 'json')
    json.loads(result.stdout)
    assert result.stderr == '', result.stderr


@pytest.mark.cli
@pytest.mark.parametrize('noun,query', [('ast', '?complexity>0'), ('trace', '?from=caller'),
                                        ('hotspots', ''), ('metrics', '?hotspots')])
def test_every_dropped_line_is_stated_in_the_json(tmp_path, noun, query):
    """The text answer's per-file lines name a file whose failure the JSON also names, so not printing
    them beside the JSON loses nothing (BACK-1998's rule for dropping a stderr append)."""
    root = _degraded(tmp_path / 'proj')
    text = _cli(tmp_path, _uri(noun, query, root))
    document = json.dumps(json.loads(_cli(tmp_path, _uri(noun, query, root), '--format', 'json').stdout))
    named = [name for name in ('b.py', 'bad.ipynb') if any(name in line for line in text.stderr.splitlines())]
    assert named, text.stderr  # the text answer still prints them
    for name in named:
        assert name in document, (name, document[:2000])


@pytest.mark.cli
def test_contracts_drops_only_a_line_about_a_file_outside_its_languages(tmp_path):
    """contracts reads the shared structures for Python and interface-family files only, so its JSON
    rightly leaves out the notebook the shared walk failed on; the dropped line was noise (BACK-2649's
    rule for a file outside the answer)."""
    from reveal.adapters.contracts import _uses_shared_structures
    root = _degraded(tmp_path / 'proj')
    text = _cli(tmp_path, _uri('contracts', '', root))
    lines = [line for line in text.stderr.splitlines() if line.startswith('Warning: Failed to analyze')]
    assert lines and all('bad.ipynb' in line for line in lines), text.stderr
    assert not _uses_shared_structures((root / 'bad.ipynb').as_posix())


@pytest.mark.cli
def test_a_pool_worker_prints_no_per_file_line_beside_a_json_answer(tmp_path):
    root = _degraded(tmp_path / 'proj')
    for i in range(12):
        (root / f'broken{i}.py').write_text(B_PY, encoding='utf-8')
    result = _cli(tmp_path, _uri('metrics', '', root), '--format', 'json', REVEAL_MAX_WORKERS='4')
    assert 'broken' in result.stdout
    assert result.stderr == '', result.stderr


@pytest.mark.cli
def test_check_json_states_the_layer_failure_and_stderr_is_empty(tmp_path):
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'a.py').write_text(A_PY, encoding='utf-8')
    (root / '.reveal.yaml').write_text('root: true\narchitecture: 5\n', encoding='utf-8')
    result = _cli(tmp_path, 'check', root.as_posix(), '--format', 'json')
    assert 'could not be used' in result.stdout
    assert 'I003' not in result.stderr, result.stderr
    text = _cli(tmp_path, 'check', root.as_posix())
    assert 'I003: layer config' in text.stderr  # the text answer keeps its line


def _raise_check(*_args, **_kwargs):
    raise RuntimeError('rule run broke')


@pytest.mark.parametrize('is_json,logged', [(True, 0), (False, 1)], ids=['json', 'text'])
def test_metrics_failed_rule_run_is_logged_only_beside_a_text_answer(tmp_path, monkeypatch, caplog, is_json, logged):
    """The failed run is in the file's stats (check_rules_failed) either way."""
    from reveal.adapters.stats import metrics
    from reveal.rules import RuleRegistry
    path = tmp_path / 'a.py'
    path.write_text(A_PY, encoding='utf-8')
    monkeypatch.setattr(RuleRegistry, 'check_file', classmethod(_raise_check))
    with caplog.at_level(logging.WARNING), log_scope(to_stderr=False):
        answer_is_json(is_json)
        counts, failed = metrics._count_local_check_issues(path, {}, A_PY)
    assert failed == ['all rules']
    assert len([r for r in caplog.records if 'Check rules failed' in r.getMessage()]) == logged


BOOM_ANALYZER = (
    "from reveal.base import FileAnalyzer\n"
    "from reveal.registry import register\n\n\n"
    "@register('.boom', name='boom', icon='')\n"
    "class BoomAnalyzer(FileAnalyzer):\n"
    "    def get_structure(self, **kwargs):\n"
    "        raise ValueError('BOOM_ANALYZER_FAILED')\n")
DIFF_URI = 'diff://git://HEAD~1/pkg:git://HEAD/pkg'


def _diff_repo(root):
    """A git repo whose newer commit adds a file a project analyzer plugin raises on: diff's git-directory
    scan skips it (``Skipping <file>@<ref> in directory scan``) and its JSON names it in analysis_failed."""
    pygit2 = pytest.importorskip('pygit2')
    repo = pygit2.init_repository(str(root))
    (root / 'pkg').mkdir()
    (root / '.reveal' / 'analyzers').mkdir(parents=True)
    (root / '.reveal' / 'analyzers' / 'boom_analyzer.py').write_text(BOOM_ANALYZER, encoding='utf-8')
    sig = pygit2.Signature('fixture', 'fixture@example.invalid')
    parents = []
    for files in ({'pkg/a.py': 'def a():\n    return 1\n'}, {'pkg/a.boom': 'x\n'}):
        for name, content in files.items():
            (root / name).write_text(content, encoding='utf-8')
            repo.index.add(name)
        repo.index.write()
        parents = [repo.create_commit('HEAD', sig, sig, 'fixture', repo.index.write_tree(), parents)]
    return root


@pytest.mark.cli
def test_diff_git_directory_skip_is_in_the_json_not_beside_it(tmp_path):
    repo = _diff_repo(tmp_path / 'repo')
    result = _cli(repo, DIFF_URI, '--format', 'json')
    assert result.stderr == '', result.stderr
    (warning,) = [w for w in json.loads(result.stdout)['meta']['warnings'] if w['type'] == 'analysis_failed']
    assert warning['failures'] == [{'path': 'pkg/a.boom', 'cause': 'ValueError',
                                    'reason': 'ValueError: BOOM_ANALYZER_FAILED'}]
    assert 'BOOM_ANALYZER_FAILED' in _cli(repo, DIFF_URI).stderr  # the text answer still prints it


@pytest.mark.mcp
@pytest.mark.component
def test_real_stdio_session_sends_one_block_per_noun_in_json_mode(tmp_path):
    """One server, each noun on its own copy of the fixture (a per-process parse cache would hide a
    second print of the same file). Every JSON answer is one content block: nothing rode beside it."""
    pytest.importorskip('mcp')
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    blocks = {}
    # diff reads the git repository the server runs in (BACK-2659 step 6).
    repo = _diff_repo(tmp_path / 'repo')

    async def exercise():
        env = {key: value for key, value in os.environ.items() if not key.startswith('REVEAL_')}
        env.update(REVEAL_DISK_CACHE='0', XDG_CONFIG_HOME=str(tmp_path / 'xdg'))
        params = StdioServerParameters(command=sys.executable, args=['-m', 'reveal.mcp_server'], env=env,
                                       cwd=str(repo))
        with (tmp_path / 'server-stderr.txt').open('w', encoding='utf-8') as errlog:
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    for index, (noun, query) in enumerate(NOUNS):
                        root = _degraded(tmp_path / f'p{index}')
                        result = await session.call_tool('reveal_query',
                                                         {'uri': _uri(noun, query, root), 'provenance': True})
                        assert not result.is_error, (noun, query, result.content[0].text[:300])
                        json.loads(result.content[0].text)
                        blocks[f'{noun}{query}'] = [block.text for block in result.content[1:]]
                    result = await session.call_tool('reveal_query', {'uri': DIFF_URI, 'provenance': True})
                    assert not result.is_error, result.content[0].text[:300]
                    assert 'BOOM_ANALYZER_FAILED' in result.content[0].text  # the skip reached the JSON
                    blocks['diff'] = [block.text for block in result.content[1:]]

    asyncio.run(asyncio.wait_for(exercise(), timeout=300))
    assert {name: extra for name, extra in blocks.items() if extra} == {}
    # The second block is gone (c1a60cb2), so stray stderr beside a JSON answer would only reach the
    # server's own log: the server's stderr is where zero residual is proven.
    # The SDK's log handler wraps lines at the terminal width, so whitespace is collapsed first.
    server_log = ' '.join((tmp_path / 'server-stderr.txt').read_text(encoding='utf-8').split())
    assert 'beside a JSON answer' not in server_log, server_log[-2000:]


def test_stderr_beside_a_json_answer_is_logged_for_the_operator_not_sent(caplog):
    """The second MCP block is gone. Should a defect still put text on stderr beside a JSON answer,
    the client gets the JSON exactly and the server's log names the text; a text answer keeps it."""
    from reveal import mcp_server
    document = '{"type": "ast_query", "meta": {"warnings": []}}'
    with caplog.at_level(logging.WARNING, logger='reveal.mcp_server'):
        assert mcp_server._with_stderr(document, 'stray line') == document
    assert 'stray line' in caplog.text
    assert mcp_server._with_stderr('text answer\n', 'stray line') == 'text answer\n\n[stderr: stray line]'
