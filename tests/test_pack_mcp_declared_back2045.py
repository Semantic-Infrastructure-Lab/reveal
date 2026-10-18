"""The specialized reveal_pack tool runs on the declared Pack path (BACK-2045, slice 2).

Reds first: the tool ignored architecture and focus graph work, and a total loss of
candidate discovery returned an ordinary packet. Controls pin what must not move: the
8000-token / content-on defaults and the exact text layout, compared against the
historical helper sequence on healthy inputs.
"""
import inspect
import os
import subprocess
from pathlib import Path

import pytest

pytest.importorskip('mcp')

from reveal.adapters import pack
from reveal.mcp_server import reveal_pack
from reveal.rendering.adapters.pack import _format_pack_result

pytestmark = pytest.mark.component


def git(root, *args):
    subprocess.run(['git', '-c', 'user.email=t@example.com', '-c', 'user.name=t', *args],
                   cwd=root, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / 'repo'
    (root / 'pkg').mkdir(parents=True)
    git(root, 'init', '-q')
    (root / 'main.py').write_text('from pkg import util\n\n\ndef main():\n    return util.helper()\n', encoding='utf-8')
    (root / 'pkg' / '__init__.py').write_text('', encoding='utf-8')
    (root / 'pkg' / 'util.py').write_text('def helper():\n    return 1\n', encoding='utf-8')
    git(root, 'add', '.')
    git(root, 'commit', '-q', '-m', 'one')
    (root / 'pkg' / 'util.py').write_text('def helper():\n    return 2\n', encoding='utf-8')
    git(root, 'commit', '-q', '-am', 'two')
    return root


def legacy(path, budget=8000, since='', content=True):
    """The historical specialized sequence, without graph signals, for byte comparison."""
    p = Path(path)
    tokens, lines = pack._parse_budget(str(budget))
    changed, error = set(), None
    if since:
        changed, error = pack._get_changed_files(p, since)
    discovery, files = [], []
    candidates = pack._collect_candidates(p, None, changed, on_error=discovery.append,
                                          on_file_error=files.append)
    selected, meta = pack._apply_budget(candidates, tokens, lines, p)
    pack._record_candidate_discovery_warning(p, discovery, meta)
    pack._record_file_measurement_warning(tuple(files), meta)
    if since:
        meta['since'] = since
        meta['changed_files_count'] = len(changed)
    return _format_pack_result(p, selected, meta, tokens, lines, since_error=error, content=content)


def test_defaults_are_unchanged():
    params = inspect.signature(reveal_pack).parameters
    assert params['budget'].default == 8000 and params['content'].default is True
    assert params['architecture'].default is False and params['since'].default == ''


@pytest.mark.parametrize('kwargs', [
    {}, {'content': False}, {'budget': 1}, {'budget': 0}, {'since': 'HEAD~1'},
    {'since': 'no-such-ref'}, {'since': 'HEAD~1', 'content': False},
])
def test_text_layout_matches_the_historical_sequence_on_healthy_input(repo, kwargs):
    assert reveal_pack(str(repo), **kwargs) == legacy(repo, **kwargs)


def test_architecture_and_focus_compute_the_graph_signals_once(repo, monkeypatch):
    seen = {'fan_in': 0, 'relevance': 0}
    real_fan, real_rel = pack._fetch_fan_in, pack._compute_graph_relevance

    def fan(*args, **kwargs):
        seen['fan_in'] += 1
        return real_fan(*args, **kwargs)

    def rel(*args, **kwargs):
        seen['relevance'] += 1
        return real_rel(*args, **kwargs)

    monkeypatch.setattr(pack, '_fetch_fan_in', fan)
    monkeypatch.setattr(pack, '_compute_graph_relevance', rel)
    text = reveal_pack(str(repo), architecture=True, focus='util')
    assert isinstance(text, str) and seen == {'fan_in': 1, 'relevance': 1}


def test_content_is_collected_once(repo, monkeypatch):
    calls = []
    real = pack._collect_file_contents
    monkeypatch.setattr(pack, '_collect_file_contents', lambda selected: calls.append(1) or real(selected))
    assert 'CONTENT' in reveal_pack(str(repo))
    assert len(calls) == 1


def lose(monkeypatch, denied):
    real_walk, real_scandir = pack._walk_files, os.scandir
    active = {'on': False}

    def walk(*args, **kwargs):
        active['on'] = True
        try:
            yield from real_walk(*args, **kwargs)
        finally:
            active['on'] = False

    def scandir(path):
        if active['on'] and Path(path) in denied:
            raise PermissionError(13, 'controlled Pack candidate directory loss', str(path))
        return real_scandir(path)

    monkeypatch.setattr(pack, '_walk_files', walk)
    monkeypatch.setattr(os, 'scandir', scandir)


def test_total_discovery_loss_is_a_tool_failure_with_the_cause(repo, monkeypatch):
    lose(monkeypatch, {repo})
    answer = reveal_pack(str(repo))
    assert type(answer).__name__ == '_ToolFailure'
    assert 'missing file population is unknown' in str(answer)


def test_partial_discovery_loss_stays_an_ordinary_packet_with_the_disclosure(repo, monkeypatch):
    lose(monkeypatch, {repo / 'pkg'})
    answer = reveal_pack(str(repo))
    assert type(answer) is str and answer.count('missing file population is unknown') == 1
    assert 'main.py' in answer


def test_missing_path_is_still_the_actionable_failure(tmp_path):
    answer = reveal_pack(str(tmp_path / 'gone'))
    assert type(answer).__name__ == '_ToolFailure' and 'not found' in str(answer)


def test_real_stdio_session_sees_packets_edits_and_actionable_errors(tmp_path):
    from test_mcp_expected_errors_back1992 import _run, _text
    root = tmp_path / 'proj'
    root.mkdir()
    source = root / 'main.py'
    source.write_text('def first():\n    return 1\n', encoding='utf-8')

    async def scenario(session):
        before = await session.call_tool('reveal_pack', {'path': str(root)})
        assert not before.is_error and 'main.py' in _text(before)
        source.write_text('def second():\n    return 2\n', encoding='utf-8')
        after = await session.call_tool('reveal_pack', {'path': str(root), 'budget': 0})
        assert not after.is_error and '~0 tokens budget' in _text(after)
        generic = await session.call_tool('reveal_query', {'uri': f'pack://{root}?budget=1000'})
        assert not generic.is_error and 'main.py' in _text(generic)
        missing = await session.call_tool('reveal_pack', {'path': str(root / 'gone')})
        assert missing.is_error and 'not found' in _text(missing)

    _run(tmp_path, scenario)
