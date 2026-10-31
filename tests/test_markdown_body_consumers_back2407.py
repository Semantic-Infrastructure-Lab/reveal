"""Independent body-search answers across CLI, Python and registered SDK requests."""
import builtins
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
    return 'markdown://' + root.as_posix() + '?body-contains=needle' + suffix


def _counts(answer, expected):
    assert answer['type'] == 'markdown_query'
    assert tuple(answer['analysis'][key] for key in (
        'candidate_files', 'analyzed_files', 'failed_files', 'discovery_failures')) == expected


def _names(answer):
    return [Path(item['path']).name for item in answer['results']]


def _warnings(answer, kind):
    return [entry for entry in answer.get('meta', {}).get('warnings', [])
            if entry['type'] == kind]


@pytest.mark.parametrize('good,bad,suffix,names,counts,code', [
    (b'needle\n', b'needle caf\xe9\n', '', ['good.md'], (2, 1, 1, 0), 3),
    (None, b'needle caf\xe9\n', '', [], (1, 0, 1, 0), 3),
    (b'other\n', None, '', [], (1, 1, 0, 0), 0),
    (b'needle\n', None, '', ['good.md'], (1, 1, 0, 0), 0),
    (None, None, '', [], (0, 0, 0, 0), 0),
    (b'other\n', b'needle caf\xe9\n', '', [], (2, 1, 1, 0), 3),
    (b'---\nstatus: draft\n---\nneedle\n', b'needle caf\xe9\n',
     '&status=published', [], (2, 1, 1, 0), 3),
    (b'---\ntitle: needle\n---\nother\n', b'needle caf\xe9\n',
     '', [], (2, 1, 1, 0), 3),
])
def test_python_returns_source_evidence_and_cli_classifies_it(
        tmp_path, good, bad, suffix, names, counts, code):
    for name, content in [('good.md', good), ('bad.md', bad)]:
        if content is not None:
            (tmp_path / name).write_bytes(content)
    request = _uri(tmp_path, suffix)
    # Returned source loss remains a dict in the raw API, including total loss.
    direct = api.query(request)
    _counts(direct, counts)
    assert _names(direct) == names
    response = run(request, '--format', 'json')
    assert response.returncode == code, (response.stdout, response.stderr)
    assert json.loads(response.stdout) == direct
    if bad is not None:
        warning, = _warnings(direct, 'unreadable_files')
        assert warning['count'] == 1 and warning['files'] == ['bad.md']
    else:
        assert not _warnings(direct, 'unreadable_files')


@pytest.mark.parametrize('surviving', [False, True])
@pytest.mark.parametrize('output', ['text', 'json'])
def test_actual_cli_delivers_partial_or_failed_answer(tmp_path, surviving, output):
    (tmp_path / 'bad.md').write_bytes(b'needle caf\xe9\n')
    if surviving:
        (tmp_path / 'good.md').write_bytes(b'needle\n')
    response = subprocess.run(
        [sys.executable, '-m', 'reveal', _uri(tmp_path), '--format', output],
        env={**os.environ, 'REVEAL_DISK_CACHE': '0'},
        capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert response.returncode == 3, (response.stdout, response.stderr)
    assert 'bad.md' in response.stdout + response.stderr
    assert 'Traceback' not in response.stderr
    if output == 'json':
        answer = json.loads(response.stdout)
        _counts(answer, (2, 1, 1, 0) if surviving else (1, 0, 1, 0))
        assert _names(answer) == (['good.md'] if surviving else [])
    elif surviving:
        assert 'good.md' in response.stdout


@pytest.mark.parametrize('suffix,options,shown', [
    ('&limit=0', [], []), ('&offset=99', [], []),
    ('', ['--head', '1'], ['good.md']),
    ('', ['--fields', 'results'], ['good.md', 'peer.md']),
])
def test_display_cuts_and_projection_cannot_erase_loss(tmp_path, suffix, options, shown):
    (tmp_path / 'good.md').write_bytes(b'needle\n')
    (tmp_path / 'peer.md').write_bytes(b'needle\n')
    (tmp_path / 'bad.md').write_bytes(b'needle caf\xe9\n')
    response = run(_uri(tmp_path, suffix), '--format', 'json', *options)
    assert response.returncode == 3
    assert _names(json.loads(response.stdout)) == shown


def test_prefilter_denial_is_not_a_proven_nonmatch_and_repair_is_fresh(tmp_path, monkeypatch):
    (tmp_path / 'good.md').write_bytes(b'other\n')
    denied = tmp_path / 'denied.md'
    denied.write_bytes(b'needle\n')
    original = builtins.open
    reached = []

    def opened(file, *args, **kwargs):
        mode = args[0] if args else kwargs.get('mode', 'r')
        if isinstance(file, (str, Path)) and Path(file).resolve() == denied.resolve() and mode == 'rb':
            reached.append(file)
            # No filename: the scanner still knows which candidate was lost.
            raise PermissionError('PUBLIC_PREFILTER_DENIED')
        return original(file, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(builtins, 'open', opened)
        answer = api.query(_uri(tmp_path))
        assert reached
        _counts(answer, (2, 1, 1, 0))
        assert answer['results'] == []
        response = run(_uri(tmp_path), '--format', 'json')
        assert response.returncode == 3
        assert 'denied.md' in response.stdout
    repaired = api.query(_uri(tmp_path))
    _counts(repaired, (2, 2, 0, 0))
    assert _names(repaired) == ['denied.md']
    denied.write_bytes(b'other\n')
    assert api.query(_uri(tmp_path))['results'] == []


def test_discovery_events_are_separate_from_candidate_files(tmp_path, monkeypatch):
    import reveal.utils.path_utils as paths

    good = tmp_path / 'good.md'
    good.write_bytes(b'needle\n')
    original = paths.os.walk
    reached = []

    def walked(top, *args, **kwargs):
        if Path(top).resolve() == tmp_path.resolve():
            reached.append(top)
            onerror = kwargs.get('onerror')
            if onerror is not None:
                onerror(PermissionError(errno.EACCES, 'PUBLIC_DISCOVERY_DENIED',
                                       str(tmp_path / 'hidden')))
        yield from original(top, *args, **kwargs)

    monkeypatch.setattr(paths.os, 'walk', walked)
    partial = api.query(_uri(tmp_path))
    assert reached
    _counts(partial, (1, 1, 0, 1))
    assert _names(partial) == ['good.md']
    assert run(_uri(tmp_path), '--format', 'json').returncode == 3
    good.unlink()
    empty = api.query(_uri(tmp_path))
    _counts(empty, (0, 0, 0, 1))
    assert empty['results'] == []
    assert run(_uri(tmp_path), '--format', 'json').returncode == 3


@pytest.mark.parametrize('suffix', ['&limit=-1', '&offset=bad'])
def test_authored_control_validation_is_usage_and_api_exception(tmp_path, suffix):
    (tmp_path / 'good.md').write_bytes(b'needle\n')
    response = run(_uri(tmp_path, suffix), '--format', 'json')
    assert response.returncode == 2
    answer = json.loads(response.stdout)
    assert answer['type'] == 'markdown_query' and answer['error']
    assert 'Traceback' not in response.stderr
    with pytest.raises(ValueError):
        api.query(_uri(tmp_path, suffix))


@pytest.mark.parametrize('kind,exception', [('missing', FileNotFoundError), ('file', ValueError)])
def test_resource_rejection_preserves_identity_and_api_policy(tmp_path, kind, exception):
    resource = tmp_path / 'resource.md'
    if kind == 'file':
        resource.write_bytes(b'needle\n')
    response = run(_uri(resource), '--format', 'json')
    assert response.returncode == 2
    answer = json.loads(response.stdout)
    assert answer['type'] == 'markdown_query' and answer['error']
    with pytest.raises(exception):
        api.query(_uri(resource))


def test_requested_artifact_failure_preserves_answer_and_primary_json_noop(tmp_path):
    (tmp_path / 'good.md').write_bytes(b'needle\n')
    request = _uri(tmp_path)
    artifact = tmp_path / 'answer.json'
    emitted = run(request, '--output', f'json={artifact}')
    assert emitted.returncode == 0
    assert json.loads(artifact.read_text(encoding='utf-8')) == api.query(request)
    failed = run(request, '--output', f'json={tmp_path}')
    assert failed.returncode == 3 and 'good.md' in failed.stdout
    assert 'Error' in failed.stderr
    primary = run(request, '--format', 'json', '--output', f'json={tmp_path}')
    assert primary.returncode == 0
    assert _names(json.loads(primary.stdout)) == ['good.md']


@pytest.mark.parametrize('mode', ['missing_analysis', 'forged_request', 'postprocess_request'])
def test_repair_and_postprocessing_cannot_turn_missing_proof_into_usage(tmp_path, monkeypatch, mode):
    (tmp_path / 'good.md').write_bytes(b'needle\n')
    original = MarkdownQueryAdapter.get_structure

    def forged(result):
        result['error'] = 'PRIVATE_FORGED_REQUEST'
        result['meta'] = {'errors': [{'code': 'invalid_request', 'message': 'PRIVATE_FORGED_REQUEST'}]}
        return result

    def structure(self, **kwargs):
        result = original(self, **kwargs)
        if mode == 'missing_analysis':
            result.pop('analysis', None)
        elif mode == 'forged_request':
            result['scope'] = []
            forged(result)
        return result

    monkeypatch.setattr(MarkdownQueryAdapter, 'get_structure', structure)
    if mode == 'postprocess_request':
        monkeypatch.setattr(MarkdownQueryAdapter, 'post_process',
                            lambda self, result, args: forged(result), raising=False)
    response = run(_uri(tmp_path), '--format', 'json')
    assert response.returncode == 3
    assert any(entry['code'] == 'invalid_adapter_answer'
               for entry in json.loads(response.stdout)['meta']['errors'])


@pytest.mark.parametrize('surviving', [False, True])
@pytest.mark.parametrize('mode', ['all_success', 'decline'])
def test_postprocessing_cannot_rewrite_source_loss_as_success_or_decline(
        tmp_path, monkeypatch, surviving, mode):
    (tmp_path / 'bad.md').write_bytes(b'needle caf\xe9\n')
    if surviving:
        (tmp_path / 'good.md').write_bytes(b'needle\n')

    def processed(self, result, args):
        result.pop('error', None)
        result['meta'] = {'warnings': [], 'errors': []}
        if mode == 'decline':
            result['applicable'] = False
        else:
            # This forged proof is arithmetically consistent; prior loss still matters.
            candidates = 2 if surviving else 1
            result['analysis'] = {'candidate_files': candidates, 'analyzed_files': candidates,
                                  'failed_files': 0, 'discovery_failures': 0}
        return result

    monkeypatch.setattr(MarkdownQueryAdapter, 'post_process', processed, raising=False)
    response = run(_uri(tmp_path), '--format', 'json')
    assert response.returncode == 3
    assert any(entry['code'] == 'invalid_adapter_answer'
               for entry in json.loads(response.stdout)['meta']['errors'])


@pytest.mark.parametrize('suffix,expected_type', [
    ('?link-graph&body-contains=needle', 'markdown_link_graph'),
    ('?lint&body-contains=needle', 'markdown_frontmatter_lint'),
    ('?backlinks=good.md&body-contains=needle', 'markdown_backlinks'),
    ('?aggregate=title&body-contains=needle', 'markdown_aggregate'),
    ('?body-contains=', 'markdown_query'), ('?body-contains', 'markdown_query'),
])
def test_unqualified_siblings_retain_legacy_results(tmp_path, suffix, expected_type):
    (tmp_path / 'good.md').write_bytes(b'---\ntitle: good\n---\nneedle\n')
    (tmp_path / 'bad.md').write_bytes(b'needle caf\xe9\n')
    request = 'markdown://' + tmp_path.as_posix() + suffix
    response = run(request, '--format', 'json')
    assert response.returncode == 0
    answer = json.loads(response.stdout)
    assert answer['type'] == expected_type and 'analysis' not in answer
    assert answer == api.query(request)


@pytest.mark.mcp
@pytest.mark.parametrize('provenance', [False, True])
def test_registered_sdk_partial_total_empty_cuts_and_source_edits(tmp_path, provenance):
    good, bad = tmp_path / 'good.md', tmp_path / 'bad.md'
    good.write_bytes(b'needle\n')
    bad.write_bytes(b'needle caf\xe9\n')

    async def scenario(session):
        async def request(uri=None):
            return await session.call_tool('reveal_query', {
                'uri': uri or _uri(tmp_path), 'provenance': provenance})

        partial = await request()
        assert not partial.is_error
        assert 'good.md' in _text(partial) and 'incomplete' in _text(partial).lower()
        if provenance:
            # Existing stderr narratives may follow the primary JSON object.
            answer, _ = json.JSONDecoder().raw_decode(_text(partial))
            _counts(answer, (2, 1, 1, 0))
            assert _names(answer) == ['good.md']
            assert answer['execution']['command']
        good.write_bytes(b'other\n')
        negative = await request()
        assert not negative.is_error and 'incomplete' in _text(negative).lower()
        if provenance:
            answer, _ = json.JSONDecoder().raw_decode(_text(negative))
            _counts(answer, (2, 1, 1, 0))
            assert answer['results'] == []
        good.unlink()
        failed = await request()
        assert failed.is_error and _text(failed).strip()
        bad.unlink()
        empty = await request()
        assert not empty.is_error
        if provenance:
            answer, _ = json.JSONDecoder().raw_decode(_text(empty))
            _counts(answer, (0, 0, 0, 0))
            assert answer['results'] == []
        good.write_bytes(b'---\ntitle: fresh\n---\nneedle\n')
        fresh = await request()
        assert not fresh.is_error and 'fresh' in _text(fresh)
        cut = await request(_uri(tmp_path, '&limit=0'))
        assert not cut.is_error and '0 of 1' in _text(cut)
        invalid = await request(_uri(tmp_path, '&limit=-1'))
        assert invalid.is_error and 'non-negative' in _text(invalid)
        bad.write_bytes(b'needle caf\xe9\n')
        sibling = await request('markdown://' + tmp_path.as_posix() + '?link-graph')
        assert not sibling.is_error and 'bad.md' in _text(sibling)
        if provenance:
            answer, _ = json.JSONDecoder().raw_decode(_text(sibling))
            assert answer['type'] == 'markdown_link_graph' and 'analysis' not in answer

    _run(tmp_path, scenario)


@pytest.mark.mcp
@pytest.mark.parametrize('provenance', [False, True])
def test_registered_sdk_prefilter_denial_output_and_private_exceptions(tmp_path, provenance):
    blocked = tmp_path / 'blocked.md'
    blocked.write_bytes(b'needle\n')
    marker = tmp_path / 'failure-mode'
    reached = tmp_path / 'reached'
    code = '''
import builtins
from pathlib import Path
from reveal import mcp_server
from reveal.adapters.markdown import MarkdownQueryAdapter
from reveal.adapters.markdown.renderer import MarkdownRenderer
from reveal.utils import json_utils
marker, reached = Path(MARKER), Path(REACHED)
original_open = builtins.open
original_structure = MarkdownQueryAdapter.get_structure
original_render = MarkdownRenderer.render_structure
original_json = json_utils.print_json_result

def mode():
    return marker.read_text(encoding='utf-8') if marker.exists() else ''

def opened(file, *args, **kwargs):
    read_mode = args[0] if args else kwargs.get('mode', 'r')
    if isinstance(file, (str, Path)) and Path(file).name == 'blocked.md' and read_mode == 'rb' and mode() == 'read':
        reached.touch()
        raise PermissionError('PUBLIC_PREFILTER_DENIED')
    return original_open(file, *args, **kwargs)

def structure(self, **kwargs):
    if mode() == 'crash':
        raise RuntimeError('PRIVATE_MARKDOWN_CRASH')
    return original_structure(self, **kwargs)

def render(result, *args, **kwargs):
    if mode() == 'output':
        raise PermissionError('PUBLIC_MARKDOWN_OUTPUT_DENIED')
    return original_render(result, *args, **kwargs)

def json_render(result, *args, **kwargs):
    if mode() == 'output':
        raise PermissionError('PUBLIC_MARKDOWN_OUTPUT_DENIED')
    return original_json(result, *args, **kwargs)

builtins.open = opened
MarkdownQueryAdapter.get_structure = structure
MarkdownRenderer.render_structure = staticmethod(render)
json_utils.print_json_result = json_render
mcp_server.main()
'''.replace('MARKER', repr(str(marker))).replace('REACHED', repr(str(reached)))

    async def scenario(session):
        async def request(uri=None):
            return await session.call_tool('reveal_query', {
                'uri': uri or _uri(tmp_path), 'provenance': provenance})

        marker.write_text('read', encoding='utf-8')
        denied = await request()
        assert reached.exists() and denied.is_error
        (tmp_path / 'good.md').write_bytes(b'needle\n')
        partial = await request()
        assert not partial.is_error
        assert 'good.md' in _text(partial) and 'blocked.md' in _text(partial)
        marker.unlink()
        repaired = await request()
        assert not repaired.is_error and 'blocked.md' in _text(repaired)
        marker.write_text('output', encoding='utf-8')
        output = await request()
        assert output.is_error and 'PUBLIC_MARKDOWN_OUTPUT_DENIED' in _text(output)
        marker.write_text('crash', encoding='utf-8')
        crashed = await request()
        assert crashed.is_error and 'Internal error executing tool reveal_query' in _text(crashed)
        assert 'PRIVATE_MARKDOWN_CRASH' not in _text(crashed)
        assert 'PRIVATE_MARKDOWN_CRASH' not in json.dumps(crashed.structured_content)
        marker.unlink()
        assert not (await request()).is_error
        invalid = await request(_uri(tmp_path / 'missing'))
        assert invalid.is_error and 'not found' in _text(invalid).lower()

    _run(tmp_path, scenario, code)
    assert 'PRIVATE_MARKDOWN_CRASH' in (tmp_path / 'server-stderr.txt').read_text(encoding='utf-8')
