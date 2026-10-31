"""Aggregate source loss must not become missing fields or a completed zero."""
import builtins
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal import api
from reveal.adapters.markdown import MarkdownQueryAdapter, operations
from reveal.cli.defaults import _default_args
from reveal.cli.routing.uri import resolve_uri
from reveal.errors import RequestValidationError
from reveal.utils.parallel import GrepResult
from reveal.utils.results import AnalysisCompleteness, FailureCause

pytestmark = pytest.mark.component


def uri(root, query='aggregate=kind'):
    return 'markdown://' + root.as_posix() + '?' + query


def document(root, name='good.md', content=b'---\nkind: useful\n---\nneedle\n'):
    path = root / name
    path.write_bytes(content)
    return path


def resolved(root, query='aggregate=kind'):
    return resolve_uri(uri(root, query), _default_args(format='json'))


def assert_analysis(answer, state, candidates, analyzed, failed, discovery=0):
    assert answer.execution_facts is not None
    assert answer.execution_facts.completeness is state
    assert answer.result['type'] == 'markdown_aggregate'
    assert answer.result['analysis'] == {
        'candidate_files': candidates, 'analyzed_files': analyzed,
        'failed_files': failed, 'discovery_failures': discovery,
    }


@pytest.mark.parametrize('query', ['aggregate=kind', 'aggregate=kind&body-contains=needle',
                                  'aggregate=kind&kind=absent', 'aggregate=kind&body-contains=other'])
def test_decode_loss_is_not_missing_field_or_completed_zero(tmp_path, query):
    document(tmp_path)
    document(tmp_path, 'bad.md', b'---\nkind: hidden\n---\nneedle\xff\n')
    answer = resolved(tmp_path, query)
    assert_analysis(answer, AnalysisCompleteness.INCOMPLETE, 2, 1, 1)
    assert answer.result['files_missing_field'] == 0
    assert answer.result['matched_files'] == int(query in ('aggregate=kind', 'aggregate=kind&body-contains=needle'))
    assert any(w['type'] == 'unreadable_files' for w in answer.result['meta']['warnings'])
    response = run(uri(tmp_path, query), '--format', 'json')
    assert response.returncode == 3
    assert json.loads(response.stdout)['analysis'] == answer.result['analysis']


@pytest.mark.parametrize('content,state,analyzed,failed,missing', [
    (b'\xff', AnalysisCompleteness.FAILED, 0, 1, 0),
    (b'No frontmatter\n', AnalysisCompleteness.COMPLETE, 1, 0, 1),
    (b'---\nkind: [broken\n---\n', AnalysisCompleteness.COMPLETE, 1, 0, 1),
    (b'---\n- sequence\n---\n', AnalysisCompleteness.COMPLETE, 1, 0, 1),
    (b'---\ndate: 2001-02-30\n---\n', AnalysisCompleteness.COMPLETE, 1, 0, 1),
    (None, AnalysisCompleteness.COMPLETE, 0, 0, 0),
])
def test_all_loss_differs_from_healthy_missing_and_empty(tmp_path, content, state, analyzed, failed, missing):
    if content is not None:
        document(tmp_path, content=content)
    answer = resolved(tmp_path)
    assert_analysis(answer, state, int(content is not None), analyzed, failed)
    assert answer.result['files_missing_field'] == missing
    assert answer.result['matched_files'] == analyzed
    assert answer.result['aggregate'] == []


@pytest.mark.parametrize('body', [False, True])
@pytest.mark.parametrize('site', ['read', 'prefilter'])
def test_required_read_failure_repairs_and_keeps_healthy_sibling(tmp_path, monkeypatch, body, site):
    if site == 'prefilter' and not body:
        pytest.skip('plain aggregate does not prefilter')
    document(tmp_path)
    denied = document(tmp_path, 'denied.md', b'---\nkind: hidden\n---\nneedle\n')
    query = 'aggregate=kind' + ('&body-contains=needle' if body else '')
    before = api.query(uri(tmp_path, query))
    read, open_file = Path.read_text, builtins.open
    reached = []

    def fail():
        reached.append(denied)
        raise PermissionError(13, 'AGGREGATE_DENIED', denied.as_posix())

    def read_text(path, *args, **kwargs):
        if path == denied:
            fail()
        return read(path, *args, **kwargs)

    def open_bytes(path, mode='r', *args, **kwargs):
        if isinstance(path, (str, os.PathLike)) and Path(path) == denied and mode == 'rb':
            fail()
        return open_file(path, mode, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, 'read_text', read_text) if site == 'read' else patch.setattr(builtins, 'open', open_bytes)
        answer = resolved(tmp_path, query)
        assert reached
        assert_analysis(answer, AnalysisCompleteness.INCOMPLETE, 2, 1, 1)
        assert answer.result['aggregate'] == [{'value': 'useful', 'count': 1}]
        assert answer.result['matched_files'] == 1
        assert answer.result['files_missing_field'] == 0
    assert api.query(uri(tmp_path, query)) == before


@pytest.mark.parametrize('survivor', [False, True])
def test_discovery_loss_counts_events_without_inventing_files(tmp_path, monkeypatch, survivor):
    if survivor:
        document(tmp_path)
    original = os.walk

    def walk(path, *args, onerror=None, **kwargs):
        if Path(path) == tmp_path and onerror:
            onerror(PermissionError(13, 'DIRECTORY_DENIED', (tmp_path / 'hidden').as_posix()))
        yield from original(path, *args, onerror=onerror, **kwargs)

    monkeypatch.setattr(os, 'walk', walk)
    answer = resolved(tmp_path)
    assert_analysis(answer, AnalysisCompleteness.INCOMPLETE if survivor else AnalysisCompleteness.FAILED,
                    int(survivor), int(survivor), 0, 1)
    assert any(w['type'] == 'analysis_incomplete' for w in answer.result['meta']['warnings'])


def test_worker_loss_and_completed_prefilter_negative_are_distinct(tmp_path, monkeypatch):
    document(tmp_path, 'nonmatch.md', b'other\n')
    lost = document(tmp_path, 'lost.md')
    monkeypatch.setattr(operations, 'grep_files', lambda paths, terms: GrepResult([], [lost]))
    answer = resolved(tmp_path, 'aggregate=kind&body-contains=needle')
    assert_analysis(answer, AnalysisCompleteness.INCOMPLETE, 2, 1, 1)
    assert answer.result['aggregate'] == []
    assert any(w['type'] == 'worker_lost' for w in answer.result['meta']['warnings'])


def test_content_is_read_once_for_frontmatter_filter_and_body(tmp_path, monkeypatch):
    path = document(tmp_path)
    read = Path.read_text
    reads = []

    def read_text(source, *args, **kwargs):
        if source == path:
            reads.append(source)
            if len(reads) > 1:
                raise PermissionError(13, 'REREAD_DENIED', path.as_posix())
        return read(source, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', read_text)
    answer = resolved(tmp_path, 'aggregate=kind&kind=useful&body-contains=needle')
    assert_analysis(answer, AnalysisCompleteness.COMPLETE, 1, 1, 0)
    assert reads == [path]
    assert answer.result['aggregate'] == [{'value': 'useful', 'count': 1}]


@pytest.mark.parametrize('query', ['aggregate=kind&limit=-1', 'aggregate=kind&offset=bad', 'aggregate=kind&kind~=['])
def test_invalid_controls_have_aggregate_identity_and_api_valueerror(tmp_path, query):
    document(tmp_path)
    response = run(uri(tmp_path, query), '--format', 'json')
    assert response.returncode == 2
    assert json.loads(response.stdout)['type'] == 'markdown_aggregate'
    with pytest.raises(RequestValidationError):
        api.query(uri(tmp_path, query))


def test_missing_resource_precedes_invalid_control(tmp_path):
    missing = tmp_path / 'missing'
    response = run(uri(missing, 'aggregate=kind&limit=-1'), '--format', 'json')
    assert response.returncode == 2
    assert json.loads(response.stdout)['type'] == 'markdown_aggregate'
    assert 'non-negative' not in response.stderr
    with pytest.raises(FileNotFoundError):
        api.query(uri(missing))


@pytest.mark.parametrize('change', [
    {'analysis': None}, {'field': ''}, {'matched_files': True}, {'files_missing_field': 3},
    {'total_files': 10}, {'aggregate': None}, {'aggregate': [{}]},
    {'aggregate': [{'value': 'useful', 'count': True}]},
    {'aggregate': [{'value': 'useful', 'count': 0}]},
    {'aggregate': [{'value': 'useful', 'count': 1}, {'value': 'useful', 'count': 1}]},
])
def test_invalid_output_cannot_be_published_as_complete(tmp_path, monkeypatch, change):
    document(tmp_path)

    def post_process(self, result, args):
        return dict(result, **change)

    monkeypatch.setattr(MarkdownQueryAdapter, 'post_process', post_process)
    response = run(uri(tmp_path), '--format', 'json')
    assert response.returncode == 3
    answer = json.loads(response.stdout)
    assert any(e['code'] == 'invalid_adapter_answer' for e in answer['meta']['errors'])


@pytest.mark.parametrize('transformation', ['erase-loss', 'decline', 'forge-invalid'])
def test_postprocessing_cannot_erase_required_loss(tmp_path, monkeypatch, transformation):
    document(tmp_path)
    document(tmp_path, 'bad.md', b'\xff')

    def post_process(self, result, args):
        result = dict(result)
        result['analysis'] = {'candidate_files': 2, 'analyzed_files': 2,
                              'failed_files': 0, 'discovery_failures': 0}
        result.pop('meta', None)
        if transformation == 'decline':
            result['applicable'] = False
        if transformation == 'forge-invalid':
            result['error'] = 'forged usage'
            result['meta'] = {'errors': [{'code': 'invalid_request', 'message': 'forged usage'}]}
        return result

    monkeypatch.setattr(MarkdownQueryAdapter, 'post_process', post_process)
    answer = resolved(tmp_path)
    assert answer.execution_facts is not None
    assert answer.execution_facts.completeness is not AnalysisCompleteness.COMPLETE
    assert FailureCause.INVALID_REQUEST not in answer.execution_facts.failures
    assert any(e['code'] == 'invalid_adapter_answer' for e in answer.result['meta']['errors'])


def test_list_values_can_count_more_than_files_and_missing_is_not_failure(tmp_path):
    document(tmp_path, content=b'---\nkind: [same, same, other, null]\n---\n')
    document(tmp_path, 'missing.md', b'No frontmatter\n')
    answer = resolved(tmp_path)
    assert_analysis(answer, AnalysisCompleteness.COMPLETE, 2, 2, 0)
    assert answer.result['aggregate'] == [{'value': 'same', 'count': 2}, {'value': 'other', 'count': 1}]
    assert answer.result['files_missing_field'] == 1


def test_root_disappearing_after_construction_is_discovery_failure(tmp_path):
    root = tmp_path / 'docs'
    root.mkdir()
    adapter = MarkdownQueryAdapter(root.as_posix(), 'aggregate=kind')
    root.rmdir()
    result = adapter.get_structure()
    assert result['analysis'] == {'candidate_files': 0, 'analyzed_files': 0,
                                  'failed_files': 0, 'discovery_failures': 1}
    assert adapter.execution_facts(result).completeness is AnalysisCompleteness.FAILED


def test_unreadable_source_does_not_claim_to_lack_the_field(tmp_path):
    document(tmp_path, content=b'\xff')
    answer = api.query(uri(tmp_path))
    assert answer['matched_files'] == 0
    assert answer['files_missing_field'] == 0
    assert any(w['type'] == 'unreadable_files' for w in answer['meta']['warnings'])


def test_failed_frontmatter_read_is_not_a_negative_filter_decision(tmp_path, monkeypatch):
    path = document(tmp_path)
    read = Path.read_text

    def read_text(source, *args, **kwargs):
        if source == path:
            raise PermissionError(13, 'AGGREGATE_DENIED', path.as_posix())
        return read(source, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', read_text)
    answer = api.query(uri(tmp_path, 'aggregate=kind&kind=useful'))
    assert any(w['type'] == 'unreadable_files' for w in answer.get('meta', {}).get('warnings', []))
    assert answer['aggregate'] == []


def test_healthy_missing_field_retains_its_existing_meaning(tmp_path):
    document(tmp_path, content=b'No frontmatter\n')
    answer = api.query(uri(tmp_path))
    assert answer['matched_files'] == 1
    assert answer['files_missing_field'] == 1
    assert answer['aggregate'] == []
    assert not answer.get('meta', {}).get('warnings')
