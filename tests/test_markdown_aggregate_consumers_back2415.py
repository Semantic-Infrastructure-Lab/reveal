"""Independent aggregate answers and loss evidence through real consumers."""
import errno
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal import api
from reveal.adapters.markdown import MarkdownQueryAdapter
from test_mcp_expected_errors_back1992 import _run, _text

pytestmark = pytest.mark.component


def _uri(root, suffix=''):
    return 'markdown://' + root.as_posix() + '?aggregate=kind' + suffix


def _counts(answer, expected):
    assert answer['type'] == 'markdown_aggregate'
    assert tuple(answer['analysis'][key] for key in (
        'candidate_files', 'analyzed_files', 'failed_files', 'discovery_failures')) == expected


def _values(answer):
    return {row['value']: row['count'] for row in answer['aggregate']}


@pytest.mark.parametrize('good,bad,suffix,counts,matched,missing,values,code', [
    (b'---\nkind: guide\n---\nneedle\n', b'caf\xe9\n', '', (2, 1, 1, 0), 1, 0, {'guide': 1}, 3),
    (None, b'caf\xe9\n', '', (1, 0, 1, 0), 0, 0, {}, 3),
    (b'plain\n', None, '', (1, 1, 0, 0), 1, 1, {}, 0),
    (b'---\nkind: [\n---\n', None, '', (1, 1, 0, 0), 1, 1, {}, 0),
    (None, None, '', (0, 0, 0, 0), 0, 0, {}, 0),
    (b'---\nkind: guide\n---\n', b'caf\xe9\n', '&kind=hidden', (2, 1, 1, 0), 0, 0, {}, 3),
    (b'other\n', b'caf\xe9\n', '&body-contains=needle', (2, 1, 1, 0), 0, 0, {}, 3),
    (b'---\nkind: [guide, reference]\n---\nneedle\n', None, '&body-contains=needle',
     (1, 1, 0, 0), 1, 0, {'guide': 1, 'reference': 1}, 0),
])
def test_api_and_cli_keep_aggregate_source_decisions(
        tmp_path, good, bad, suffix, counts, matched, missing, values, code):
    for name, content in [('good.md', good), ('bad.md', bad)]:
        if content is not None:
            (tmp_path / name).write_bytes(content)
    answer = api.query(_uri(tmp_path, suffix))
    assert (answer['matched_files'], answer['files_missing_field']) == (matched, missing)
    assert _values(answer) == values
    _counts(answer, counts)
    response = run(_uri(tmp_path, suffix), '--format', 'json')
    assert response.returncode == code, (response.stdout, response.stderr)
    assert json.loads(response.stdout) == answer
    warnings = answer.get('meta', {}).get('warnings', [])
    assert any(w['type'] == 'unreadable_files' for w in warnings) is (bad is not None)


@pytest.mark.parametrize('content,matched,missing,values', [
    ('No frontmatter\n', 1, 1, {}),
    ('---\nkind: [\n---\n', 1, 1, {}),
    ('---\nkind: [guide, reference]\n---\n', 1, 0, {'guide': 1, 'reference': 1}),
])
def test_existing_healthy_frontmatter_meanings_survive(tmp_path, content, matched, missing, values):
    (tmp_path / 'good.md').write_text(content, encoding='utf-8')
    response = run(_uri(tmp_path), '--format', 'json')
    assert response.returncode == 0
    answer = json.loads(response.stdout)
    assert answer['matched_files'] == matched and answer['files_missing_field'] == missing
    assert _values(answer) == values


@pytest.mark.parametrize('output', ['text', 'json'])
def test_subprocess_cli_preserves_partial_counts_and_failure_exit(tmp_path, output):
    (tmp_path / 'good.md').write_text('---\nkind: guide\n---\n', encoding='utf-8')
    (tmp_path / 'bad.md').write_bytes(b'caf\xe9\n')
    response = subprocess.run(
        [sys.executable, '-m', 'reveal', _uri(tmp_path), '--format', output],
        env={**os.environ, 'REVEAL_DISK_CACHE': '0'}, capture_output=True,
        text=True, encoding='utf-8', timeout=30)
    assert response.returncode == 3
    assert 'guide' in response.stdout and 'Traceback' not in response.stderr
    if output == 'json':
        answer = json.loads(response.stdout)
        assert (answer['matched_files'], answer['files_missing_field']) == (1, 0)
        _counts(answer, (2, 1, 1, 0))


@pytest.mark.parametrize('output', ['text', 'grep', 'json'])
def test_io_denial_is_visible_without_incidental_read_logs(tmp_path, monkeypatch, output):
    (tmp_path / 'good.md').write_text('---\nkind: guide\n---\n', encoding='utf-8')
    denied = tmp_path / 'denied.md'
    denied.write_text('---\nkind: hidden\n---\n', encoding='utf-8')
    original = Path.read_text
    reached = []

    def read(path, *args, **kwargs):
        if path == denied:
            reached.append(path)
            raise PermissionError(errno.EACCES, 'PUBLIC_AGGREGATE_DENIED', str(path))
        return original(path, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(Path, 'read_text', read)
        response = run(_uri(tmp_path), '--format', output)
    assert reached and response.returncode == 3
    assert 'denied.md' in response.stdout + response.stderr
    assert 'could not be read' in response.stdout + response.stderr
    if output == 'json':
        answer = json.loads(response.stdout)
        _counts(answer, (2, 1, 1, 0))
        assert _values(answer) == {'guide': 1}
    elif output == 'grep':
        assert 'could not be read' in response.stderr
    else:
        assert 'could not be read' in response.stdout
    restored = api.query(_uri(tmp_path))
    _counts(restored, (2, 2, 0, 0))
    assert _values(restored) == {'guide': 1, 'hidden': 1}


@pytest.mark.parametrize('healthy', [False, True])
def test_discovery_loss_is_not_a_clean_empty_population(tmp_path, monkeypatch, healthy):
    import reveal.utils.path_utils as paths

    if healthy:
        (tmp_path / 'good.md').write_text('No frontmatter\n', encoding='utf-8')
    original = paths.os.walk

    def walked(top, *args, **kwargs):
        if Path(top).resolve() == tmp_path.resolve():
            callback = kwargs.get('onerror')
            if callback:
                callback(PermissionError(errno.EACCES, 'PUBLIC_DISCOVERY_DENIED',
                                         str(tmp_path / 'hidden')))
        yield from original(top, *args, **kwargs)

    monkeypatch.setattr(paths.os, 'walk', walked)
    answer = api.query(_uri(tmp_path))
    _counts(answer, (int(healthy), int(healthy), 0, 1))
    assert answer['files_missing_field'] == int(healthy)
    assert run(_uri(tmp_path), '--format', 'json').returncode == 3


@pytest.mark.parametrize('suffix', ['&limit=-1', '&offset=bad'])
def test_invalid_aggregate_controls_are_usage_failures(tmp_path, suffix):
    response = run(_uri(tmp_path, suffix), '--format', 'json')
    assert response.returncode == 2
    assert json.loads(response.stdout)['type'] == 'markdown_aggregate'
    with pytest.raises(ValueError):
        api.query(_uri(tmp_path, suffix))


@pytest.mark.parametrize('kind,exception', [('missing', FileNotFoundError), ('file', ValueError)])
def test_invalid_resources_keep_aggregate_identity(tmp_path, kind, exception):
    resource = tmp_path / 'resource.md'
    if kind == 'file':
        resource.write_text('plain\n', encoding='utf-8')
    response = run(_uri(resource), '--format', 'json')
    assert response.returncode == 2
    assert json.loads(response.stdout)['type'] == 'markdown_aggregate'
    with pytest.raises(exception):
        api.query(_uri(resource))


def test_projection_and_output_failure_keep_source_policy(tmp_path):
    (tmp_path / 'good.md').write_text('---\nkind: guide\n---\n', encoding='utf-8')
    bad = tmp_path / 'bad.md'
    bad.write_bytes(b'caf\xe9\n')
    projected = run(_uri(tmp_path), '--format', 'json', '--fields', 'aggregate')
    assert projected.returncode == 3
    assert _values(json.loads(projected.stdout)) == {'guide': 1}
    bad.unlink()
    artifact = tmp_path / 'answer.json'
    emitted = run(_uri(tmp_path), '--output', f'json={artifact}')
    assert emitted.returncode == 0
    assert _values(json.loads(artifact.read_text(encoding='utf-8'))) == {'guide': 1}
    failed = run(_uri(tmp_path), '--output', f'json={tmp_path}')
    assert failed.returncode == 3 and 'guide' in failed.stdout
    primary = run(_uri(tmp_path), '--format', 'json', '--output', f'json={tmp_path}')
    assert primary.returncode == 0


@pytest.mark.parametrize('mode', ['missing_analysis', 'success', 'decline', 'request'])
def test_postprocessing_cannot_erase_or_forge_source_proof(tmp_path, monkeypatch, mode):
    (tmp_path / 'good.md').write_text('---\nkind: guide\n---\n', encoding='utf-8')
    (tmp_path / 'bad.md').write_bytes(b'caf\xe9\n')

    def processed(self, answer, args):
        answer['meta'] = {'warnings': [], 'errors': []}
        if mode == 'missing_analysis':
            answer.pop('analysis', None)
        elif mode == 'success':
            answer['analysis'] = dict(candidate_files=2, analyzed_files=2,
                                      failed_files=0, discovery_failures=0)
        elif mode == 'decline':
            answer['applicable'] = False
        else:
            answer['error'] = 'PRIVATE_FORGED_REQUEST'
            answer['meta']['errors'] = [{'code': 'invalid_request', 'message': 'PRIVATE_FORGED_REQUEST'}]
        return answer

    monkeypatch.setattr(MarkdownQueryAdapter, 'post_process', processed, raising=False)
    response = run(_uri(tmp_path), '--format', 'json')
    assert response.returncode == 3
    answer = json.loads(response.stdout)
    assert any(e['code'] == 'invalid_adapter_answer' for e in answer['meta']['errors'])


@pytest.mark.mcp
@pytest.mark.parametrize('provenance', [False, True])
def test_registered_sdk_partial_failed_empty_and_fresh_repair(tmp_path, provenance):
    good, bad = tmp_path / 'good.md', tmp_path / 'bad.md'
    good.write_text('---\nkind: guide\n---\n', encoding='utf-8')
    bad.write_bytes(b'caf\xe9\n')

    async def scenario(client):
        async def request(suffix=''):
            return await client.call_tool('reveal_query', {
                'uri': _uri(tmp_path, suffix), 'provenance': provenance})

        partial = await request()
        assert not partial.is_error
        assert 'guide' in _text(partial) and 'incomplete' in _text(partial).lower()
        if provenance:
            answer, _ = json.JSONDecoder().raw_decode(_text(partial))
            _counts(answer, (2, 1, 1, 0))
            assert answer['files_missing_field'] == 0
        no_match = await request('&kind=hidden')
        assert not no_match.is_error and 'incomplete' in _text(no_match).lower()
        good.unlink()
        failed = await request()
        assert failed.is_error and _text(failed).strip()
        bad.write_text('No frontmatter\n', encoding='utf-8')
        healthy_missing = await request()
        assert not healthy_missing.is_error and 'incomplete' not in _text(healthy_missing).lower()
        bad.write_text('---\nkind: restored\n---\n', encoding='utf-8')
        restored = await request()
        assert not restored.is_error and 'restored' in _text(restored)
        bad.unlink()
        assert not (await request()).is_error
        rejected = await request('&limit=-1')
        assert rejected.is_error and 'non-negative' in _text(rejected)

    _run(tmp_path, scenario)


@pytest.mark.mcp
@pytest.mark.parametrize('provenance', [False, True])
def test_sdk_read_loss_recovery_and_unexpected_failure_privacy(tmp_path, provenance):
    path = tmp_path / 'denied.md'
    path.write_text('---\nkind: hidden\n---\n', encoding='utf-8')
    marker = tmp_path / 'deny'
    code = '''
from pathlib import Path
import os
from reveal import mcp_server
from reveal.adapters.markdown import MarkdownQueryAdapter
from reveal.adapters.markdown.renderer import MarkdownRenderer
from reveal.utils import json_utils
original = Path.read_text
original_walk = os.walk
original_render = MarkdownRenderer.render_structure
original_json = json_utils.print_json_result
marker = Path(MARKER)
def read(path, *args, **kwargs):
    if path.name == 'denied.md' and marker.exists() and marker.read_bytes() == b'deny':
        raise PermissionError(13, 'PUBLIC_AGGREGATE_DENIED', str(path))
    return original(path, *args, **kwargs)
def walked(top, *args, **kwargs):
    if Path(top) == marker.parent and marker.exists() and marker.read_bytes() == b'scan':
        callback = kwargs.get('onerror')
        if callback:
            callback(PermissionError(13, 'PUBLIC_DISCOVERY_DENIED', str(marker.parent / 'hidden')))
    yield from original_walk(top, *args, **kwargs)
def render(result, *args, **kwargs):
    if marker.exists() and marker.read_bytes() == b'output':
        raise PermissionError(13, 'PUBLIC_AGGREGATE_OUTPUT_DENIED')
    return original_render(result, *args, **kwargs)
def print_json(result, *args, **kwargs):
    if marker.exists() and marker.read_bytes() == b'output':
        raise PermissionError(13, 'PUBLIC_AGGREGATE_OUTPUT_DENIED')
    return original_json(result, *args, **kwargs)
def processed(self, result, args):
    if marker.exists() and marker.read_bytes() == b'crash':
        raise RuntimeError('PRIVATE_AGGREGATE_CRASH')
    return result
Path.read_text = read
os.walk = walked
MarkdownQueryAdapter.post_process = processed
MarkdownRenderer.render_structure = staticmethod(render)
json_utils.print_json_result = print_json
mcp_server.main()
'''.replace('MARKER', repr(str(marker)))

    async def scenario(client):
        async def request():
            return await client.call_tool('reveal_query', {
                'uri': _uri(tmp_path), 'provenance': provenance})
        assert not (await request()).is_error
        marker.write_bytes(b'deny')
        denied = await request()
        assert denied.is_error
        marker.unlink()
        assert 'hidden' in _text(await request())
        marker.write_bytes(b'scan')
        discovery = await request()
        assert not discovery.is_error and 'incomplete' in _text(discovery).lower()
        assert 'hidden' in _text(discovery)
        marker.write_bytes(b'output')
        output = await request()
        assert output.is_error and _text(output).strip()
        marker.write_bytes(b'crash')
        failed = await request()
        assert failed.is_error
        assert 'PRIVATE_AGGREGATE_CRASH' not in _text(failed)
        assert 'Internal error' in _text(failed)
        marker.unlink()
        assert not (await request()).is_error

    _run(tmp_path, scenario, code)
