"""Lost directory discovery must not look like a complete graph or backlink answer."""
import errno
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal import api
from reveal.adapters.markdown import operations
from reveal.core import disk_cache
from test_mcp_expected_errors_back1992 import _run, _text

pytestmark = pytest.mark.component


@pytest.fixture
def docs(tmp_path):
    root = tmp_path / 'docs'
    (root / 'hidden').mkdir(parents=True)
    (root / 'target.md').write_text('# Target\n', encoding='utf-8')
    (root / 'hidden' / 'source.md').write_text('[target](../target.md)\n', encoding='utf-8')
    return root


@pytest.fixture
def denied(monkeypatch):
    paths = set()
    original = os.scandir

    def scandir(path):
        if Path(path) in paths:
            raise PermissionError(errno.EACCES, 'PUBLIC_DISCOVERY_DENIED', str(path))
        return original(path)

    monkeypatch.setattr(os, 'scandir', scandir)
    return paths


def _uri(root, mode):
    return 'markdown://' + root.as_posix() + '?' + mode


def _warnings(answer):
    return answer.get('meta', {}).get('warnings', [])


def _loss(answer, directory):
    warnings = _warnings(answer)
    assert len(warnings) == 1
    warning = warnings[0]
    assert warning['type'] == 'analysis_incomplete'
    assert warning['count'] == 1 and warning['unit'] == 'directories'
    assert warning['directories'] == [directory]
    assert 'missing file population is unknown' in warning['message']
    assert warning['causes'] == ['PermissionError: PUBLIC_DISCOVERY_DENIED']


@pytest.mark.parametrize('total', [False, True])
@pytest.mark.parametrize('mode', ['link-graph', 'backlinks=target.md', 'backlinks=hidden/source.md'])
def test_api_loss_and_recovery_keep_observed_population(docs, denied, total, mode):
    healthy = api.query(_uri(docs, mode))
    assert healthy['total_files'] == 2 and not _warnings(healthy)
    denied.add(docs if total else docs / 'hidden')
    lost = api.query(_uri(docs, mode))
    assert lost['total_files'] == (0 if total else 1)
    _loss(lost, '.' if total else 'hidden')
    if mode == 'link-graph':
        assert lost['total_edges'] == 0
        assert [node['file'] for node in lost['nodes']] == ([] if total else ['target.md'])
    else:
        assert lost['linked_by'] == []
        assert lost['found'] is (not total and mode == 'backlinks=target.md')
    assert str(docs) not in json.dumps(lost['meta'])
    denied.clear()
    assert api.query(_uri(docs, mode)) == healthy
    _loss(lost, '.' if total else 'hidden')  # later requests do not mutate old evidence


@pytest.mark.parametrize('mode', ['link-graph', 'backlinks=target.md'])
@pytest.mark.parametrize('output', ['text', 'grep', 'json'])
def test_cli_discloses_loss_in_each_format(docs, denied, mode, output):
    denied.add(docs / 'hidden')
    response = run(_uri(docs, mode), '--format', output)
    assert response.returncode == 3  # source loss is now qualified across Markdown views
    if output == 'json':
        _loss(json.loads(response.stdout), 'hidden')
        assert json.loads(response.stdout) == api.query(_uri(docs, mode))
    else:
        visible = response.stderr if output == 'grep' else response.stdout
        assert 'missing file population is unknown' in visible
        assert 'safe to rename' not in response.stdout
        assert 'PUBLIC_DISCOVERY_DENIED' in visible


def test_healthy_empty_graph_and_missing_backlink_are_not_discovery_loss(tmp_path):
    for mode in ('link-graph', 'backlinks=absent.md'):
        answer = api.query(_uri(tmp_path, mode))
        assert answer['total_files'] == 0 and not _warnings(answer)
        assert run(_uri(tmp_path, mode), '--format', 'json').returncode == 0


@pytest.mark.disk_cache
@pytest.mark.parametrize('warm', [False, True])
@pytest.mark.parametrize('empty_hidden', [False, True])
def test_discovery_loss_bypasses_cache_even_for_same_observed_files(
        docs, denied, monkeypatch, warm, empty_hidden):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(docs.parent / 'cache'))
    # An empty hidden directory has the same file fingerprint whether accessible or denied.
    if empty_hidden:
        (docs / 'hidden' / 'source.md').unlink()
    if warm:
        assert operations.build_link_graph(docs)['total_files'] == (1 if empty_hidden else 2)
    calls = []
    original_get, original_put = disk_cache.get, disk_cache.put

    def get(*args, **kwargs):
        calls.append('get')
        return original_get(*args, **kwargs)

    def put(*args, **kwargs):
        calls.append('put')
        return original_put(*args, **kwargs)

    monkeypatch.setattr(disk_cache, 'get', get)
    monkeypatch.setattr(disk_cache, 'put', put)
    denied.add(docs / 'hidden')
    for _ in range(2):
        _loss(operations.build_link_graph(docs), 'hidden')
        _loss(operations.get_backlinks(docs, 'target.md'), 'hidden')
    assert calls == [], 'a failed discovery must neither serve nor store a graph'
    denied.clear()
    repaired = operations.build_link_graph(docs)
    assert repaired['total_files'] == (1 if empty_hidden else 2) and not _warnings(repaired)
    assert repaired['total_edges'] == (0 if empty_hidden else 1)
    assert calls == (['get'] if warm else ['get', 'put'])


def test_existing_content_loss_and_discovery_loss_both_survive(docs, denied):
    (docs / 'bad.md').write_bytes(b'\xff\n')
    denied.add(docs / 'hidden')
    for mode in ('link-graph', 'backlinks=target.md'):
        answer = api.query(_uri(docs, mode))
        assert answer['total_files'] == 2
        assert {w['type'] for w in _warnings(answer)} == {'unreadable_files', 'analysis_incomplete'}
        response = run(_uri(docs, mode))
        assert response.returncode == 3
        assert 'safe to rename' not in response.stdout
        assert 'could not be read' in response.stdout
        assert 'missing file population is unknown' in response.stdout


def test_graph_owner_records_root_stat_failure(docs, monkeypatch):
    original = Path.stat

    def stat(path, *args, **kwargs):
        if path == docs:
            raise PermissionError(errno.EACCES, 'PUBLIC_DISCOVERY_DENIED', str(path))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'stat', stat)
    answer = operations.build_link_graph(docs)
    assert answer['total_files'] == 0 and answer['nodes'] == []
    _loss(answer, '.')


@pytest.mark.mcp
@pytest.mark.parametrize('provenance', [False, True])
def test_registered_sdk_discloses_loss_then_recovers(docs, tmp_path, provenance):
    marker = tmp_path / 'denied'
    code = '''
import os
from pathlib import Path
from reveal import mcp_server
original = os.scandir
marker, root = Path(MARKER), Path(ROOT)
def scandir(path):
    if marker.exists() and Path(path) == (root if marker.read_bytes() == b'all' else root / 'hidden'):
        raise PermissionError(13, 'PUBLIC_DISCOVERY_DENIED', str(path))
    return original(path)
os.scandir = scandir
mcp_server.main()
'''.replace('MARKER', repr(str(marker))).replace('ROOT', repr(str(docs)))

    async def scenario(client):
        for mode in ('link-graph', 'backlinks=target.md'):
            async def request():
                return await client.call_tool('reveal_query', {
                    'uri': _uri(docs, mode), 'provenance': provenance})
            healthy = await request()
            assert not healthy.is_error
            for value, directory in ((b'partial', 'hidden'), (b'all', '.')):
                marker.write_bytes(value)
                lost = await request()
                if value == b'all':
                    assert lost.is_error and _text(lost).strip()
                    continue
                assert not lost.is_error  # surviving partial evidence remains usable
                text = _text(lost)
                if provenance:
                    _loss(json.loads(text), directory)
                else:
                    assert 'missing file population is unknown' in text
                    assert 'safe to rename' not in text
            marker.unlink()
            repaired = await request()
            assert not repaired.is_error
            assert 'PUBLIC_DISCOVERY_DENIED' not in _text(repaired)
            if provenance:
                assert json.loads(_text(repaired)) == json.loads(_text(healthy))

    _run(tmp_path, scenario, code)
