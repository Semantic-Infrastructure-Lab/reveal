"""Ordinary Markdown body searches qualify source work before selecting answers."""
import builtins
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal import api
from reveal.adapters.markdown import MarkdownQueryAdapter
from reveal.adapters.markdown import operations
from reveal.cli.defaults import _default_args
from reveal.cli.routing.uri import _uri_execution_facts, resolve_uri
from reveal.errors import RequestValidationError
from reveal.utils.parallel import GrepResult
from reveal.utils.results import AnalysisCompleteness, FailureCause

pytestmark = pytest.mark.component


def test_invalid_constructor_types_do_not_escape_as_attribute_errors():
    with pytest.raises(TypeError):
        MarkdownQueryAdapter(123, 456)


def uri(root, query='body-contains=needle'):
    return 'markdown://' + root.as_posix() + '?' + query


def document(root, name, content=b'needle\n'):
    path = root / name
    path.write_bytes(content)
    return path


def resolved(root, query='body-contains=needle'):
    return resolve_uri(uri(root, query), _default_args(format='json'))


def assert_analysis(answer, state, candidates, analyzed, failed, discovery=0):
    assert answer.execution_facts is not None
    assert answer.execution_facts.completeness is state
    assert answer.result['analysis'] == {
        'candidate_files': candidates, 'analyzed_files': analyzed,
        'failed_files': failed, 'discovery_failures': discovery,
    }


@pytest.mark.parametrize('healthy,query,expected', [
    (b'needle\n', 'body-contains=needle', ['good.md']),
    (b'other\n', 'body-contains=needle', []),
    (b'---\ntitle: other\n---\nneedle\n', 'body-contains=needle&title=wanted', []),
    (b'needle\n', 'body-contains=needle&limit=0', []),
])
def test_successful_source_survives_selection_with_decode_loss(tmp_path, healthy, query, expected):
    document(tmp_path, 'good.md', healthy)
    document(tmp_path, 'bad.md', b'needle caf\xe9\n')
    answer = resolved(tmp_path, query)
    assert_analysis(answer, AnalysisCompleteness.INCOMPLETE, 2, 1, 1)
    assert [Path(row['path']).name for row in answer.result['results']] == expected
    response = run(uri(tmp_path, query), '--format', 'json')
    assert response.returncode == 3
    assert json.loads(response.stdout)['analysis'] == answer.result['analysis']
    assert any(w['type'] == 'unreadable_files' for w in answer.result['meta']['warnings'])


@pytest.mark.parametrize('content,state,counts,code', [
    (b'needle caf\xe9\n', AnalysisCompleteness.FAILED, (1, 0, 1), 3),
    (b'needle\n', AnalysisCompleteness.COMPLETE, (1, 1, 0), 0),
    (b'other\n', AnalysisCompleteness.COMPLETE, (1, 1, 0), 0),
    (None, AnalysisCompleteness.COMPLETE, (0, 0, 0), 0),
])
def test_total_loss_and_healthy_zero_have_distinct_facts(tmp_path, content, state, counts, code):
    if content is not None:
        document(tmp_path, 'only.md', content)
    answer = resolved(tmp_path)
    assert_analysis(answer, state, *counts)
    assert run(uri(tmp_path), '--format', 'json').returncode == code


@pytest.mark.parametrize('failure_site', ['prefilter', 'read', 'stat'])
def test_required_file_loss_keeps_sibling_and_repairs(tmp_path, monkeypatch, failure_site):
    good = document(tmp_path, 'good.md')
    denied = document(tmp_path, 'denied.md')
    before = api.query(uri(tmp_path))
    original_open, original_read, original_stat = builtins.open, Path.read_text, Path.stat
    reached = []

    def fail(path):
        reached.append(path)
        raise PermissionError(13, 'BODY_SOURCE_DENIED', denied.as_posix())

    def open_file(path, mode='r', *args, **kwargs):
        if isinstance(path, (str, os.PathLike)) and Path(path) == denied and mode == 'rb':
            fail(path)
        return original_open(path, mode, *args, **kwargs)

    def read_file(path, *args, **kwargs):
        if path == denied:
            fail(path)
        return original_read(path, *args, **kwargs)

    def stat_file(path, *args, **kwargs):
        if path == denied:
            fail(path)
        return original_stat(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        if failure_site == 'prefilter':
            patch.setattr(builtins, 'open', open_file)
        else:
            patch.setattr(Path, 'read_text' if failure_site == 'read' else 'stat',
                          read_file if failure_site == 'read' else stat_file)
        answer = resolved(tmp_path)
        assert reached
        assert_analysis(answer, AnalysisCompleteness.INCOMPLETE, 2, 1, 1)
        assert [row['path'] for row in answer.result['results']] == [good.as_posix()]
        assert api.query(uri(tmp_path))['analysis'] == answer.result['analysis']
    assert api.query(uri(tmp_path)) == before
    denied.write_bytes(b'other\n')
    assert api.query(uri(tmp_path))['matched_files'] == 1


@pytest.mark.parametrize('survivor', [False, True])
def test_discovery_failure_counts_events_without_guessing_missing_files(tmp_path, monkeypatch, survivor):
    if survivor:
        document(tmp_path, 'good.md', b'other\n')
    original = os.walk

    def walk(path, *args, onerror=None, **kwargs):
        if Path(path) == tmp_path:
            if onerror:
                onerror(PermissionError(13, 'DIRECTORY_DENIED', (tmp_path / 'hidden').as_posix()))
        yield from original(path, *args, onerror=onerror, **kwargs)

    monkeypatch.setattr(os, 'walk', walk)
    answer = resolved(tmp_path)
    assert_analysis(answer, AnalysisCompleteness.INCOMPLETE if survivor else AnalysisCompleteness.FAILED,
                    int(survivor), int(survivor), 0, 1)
    assert any(w['type'] == 'analysis_incomplete' for w in answer.result['meta']['warnings'])


def test_worker_loss_is_distinct_from_successful_nonmatch(tmp_path, monkeypatch):
    nonmatch = document(tmp_path, 'other.md', b'other\n')
    lost = document(tmp_path, 'lost.md')
    monkeypatch.setattr(operations, 'grep_files', lambda paths, terms: GrepResult([], [lost]))
    answer = resolved(tmp_path)
    assert_analysis(answer, AnalysisCompleteness.INCOMPLETE, 2, 1, 1)
    assert answer.result['results'] == []
    assert any(w['type'] == 'worker_lost' for w in answer.result['meta']['warnings'])
    assert nonmatch.exists()


def test_source_is_read_once_for_frontmatter_body_and_relevance(tmp_path, monkeypatch):
    path = document(tmp_path, 'good.md', b'---\ntitle: guide\n---\n# needle\nneedle\n')
    original = Path.read_text
    reads = []

    def read(source, *args, **kwargs):
        if source == path:
            reads.append(source)
            if len(reads) > 1:
                raise PermissionError(13, 'REREAD_DENIED', path.as_posix())
        return original(source, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', read)
    answer = resolved(tmp_path, 'body-contains=needle&title=guide&explain')
    assert_analysis(answer, AnalysisCompleteness.COMPLETE, 1, 1, 0)
    assert reads == [path]
    assert answer.result['results'][0]['relevance_score'] == 5
    assert answer.result['results'][0]['relevance_explain']['term_counts'] == {'needle': 2}


@pytest.mark.parametrize('query', ['body-contains=needle&limit=-1', 'body-contains=needle&offset=bad',
                                  'body-contains=needle&title~=['])
def test_authored_validation_is_invalid_and_api_remains_valueerror(tmp_path, query):
    document(tmp_path, 'good.md')
    response = run(uri(tmp_path, query), '--format', 'json')
    assert response.returncode == 2
    assert json.loads(response.stdout)['type'] == 'markdown_query'
    with pytest.raises(RequestValidationError):
        api.query(uri(tmp_path, query))


def test_resource_validation_precedes_controls_and_preserves_api_missing_exception(tmp_path):
    missing = tmp_path / 'missing'
    response = run(uri(missing, 'body-contains=needle&limit=-1'), '--format', 'json')
    assert response.returncode == 2
    assert json.loads(response.stdout)['type'] == 'markdown_query'
    assert 'non-negative' not in response.stderr
    with pytest.raises(FileNotFoundError):
        api.query(uri(missing))
    file = document(tmp_path, 'single.md')
    assert run(uri(file), '--format', 'json').returncode == 2


@pytest.mark.parametrize('query', ['body-contains=', 'body-contains', 'title=guide',
    'body-contains=needle&aggregate=title', 'body-contains=needle&link-graph',
    'body-contains=needle&link_graph', 'body-contains=needle&lint',
    'body-contains=needle&backlinks=good.md'])
def test_sibling_modes_remain_outside_execution_admission(tmp_path, query):
    document(tmp_path, 'good.md', b'---\ntitle: guide\n---\nneedle\n')
    assert _uri_execution_facts(MarkdownQueryAdapter, uri(tmp_path, query).split('://', 1)[1],
                                None, _default_args()) is None
    answer = resolved(tmp_path, query)
    assert answer.execution_facts is None
    assert 'analysis' not in answer.result


def test_malformed_frontmatter_is_completed_content_and_lint_keeps_its_verdict(tmp_path):
    document(tmp_path, 'bad.md', b'---\ndate: 2001-02-30\n---\nneedle\n')
    answer = resolved(tmp_path)
    assert_analysis(answer, AnalysisCompleteness.COMPLETE, 1, 1, 0)
    assert answer.result['matched_files'] == 1
    lint = resolved(tmp_path, 'lint')
    assert lint.execution_facts is None
    assert lint.result['issues_found'] == 1
    assert lint.result['issues'][0]['issue'] == 'malformed_yaml'


@pytest.mark.parametrize('transformation', ['drop-analysis', 'invalid-counts', 'forge-invalid'])
def test_postprocessing_cannot_hide_proof_or_forge_request_rejection(tmp_path, monkeypatch, transformation):
    document(tmp_path, 'good.md')
    document(tmp_path, 'bad.md', b'needle caf\xe9\n')

    def post_process(self, result, args):
        result = dict(result)
        if transformation == 'drop-analysis':
            result.pop('analysis', None)
        elif transformation == 'invalid-counts':
            result['analysis'] = {'candidate_files': 2, 'analyzed_files': 2,
                                  'failed_files': 1, 'discovery_failures': 0}
        else:
            result['error'] = 'forged usage'
            result['meta'] = {'errors': [{'code': 'invalid_request', 'message': 'forged usage'}]}
        return result

    monkeypatch.setattr(MarkdownQueryAdapter, 'post_process', post_process)
    answer = resolved(tmp_path)
    assert answer.execution_facts is not None
    assert answer.execution_facts.completeness is not AnalysisCompleteness.COMPLETE
    assert FailureCause.INVALID_REQUEST not in answer.execution_facts.failures
    assert any(e['code'] == 'invalid_adapter_answer' for e in answer.result['meta']['errors'])


@pytest.mark.parametrize('copy', [False, True])
@pytest.mark.parametrize('decline', [False, True])
def test_postprocessing_cannot_publish_loss_free_counts_after_required_loss(tmp_path, monkeypatch, copy, decline):
    document(tmp_path, 'good.md')
    document(tmp_path, 'bad.md', b'needle caf\xe9\n')

    def post_process(self, result, args):
        if copy:
            result = dict(result)
        result['analysis'] = {'candidate_files': 2, 'analyzed_files': 2,
                              'failed_files': 0, 'discovery_failures': 0}
        result.pop('meta', None)
        if decline:
            result['applicable'] = False
        return result

    monkeypatch.setattr(MarkdownQueryAdapter, 'post_process', post_process)
    answer = resolved(tmp_path)
    assert answer.execution_facts is not None
    assert answer.execution_facts.completeness in (AnalysisCompleteness.INCOMPLETE, AnalysisCompleteness.FAILED)
    assert any(e['code'] == 'invalid_adapter_answer' for e in answer.result['meta']['errors'])


def test_returned_producer_error_cannot_classify_itself_as_request_validation(tmp_path, monkeypatch):
    from reveal.utils.results import ResultBuilder

    def get_structure(self, **kwargs):
        return ResultBuilder.create('markdown_query', tmp_path, error='returned source failure',
                                    errors=[{'code': 'invalid_request', 'message': 'returned source failure'}])

    monkeypatch.setattr(MarkdownQueryAdapter, 'get_structure', get_structure)
    answer = resolved(tmp_path)
    assert answer.execution_facts.completeness is AnalysisCompleteness.FAILED
    assert answer.execution_facts.failures == frozenset({FailureCause.ANALYSIS})
    assert run(uri(tmp_path), '--format', 'json').returncode == 3


def test_root_disappearing_after_construction_is_discovery_failure(tmp_path):
    root = tmp_path / 'docs'
    root.mkdir()
    adapter = MarkdownQueryAdapter(root.as_posix(), 'body-contains=needle')
    root.rmdir()
    result = adapter.get_structure()
    assert result['analysis'] == {'candidate_files': 0, 'analyzed_files': 0,
                                  'failed_files': 0, 'discovery_failures': 1}
    assert adapter.execution_facts(result).completeness is AnalysisCompleteness.FAILED


@pytest.mark.parametrize('change', [{}, {'path': ''}, {'relative_path': ''},
    {'relevance_score': True}, {'relevance_score': -1}, {'has_frontmatter': 'false'}])
def test_unusable_observation_is_required_output_failure(tmp_path, monkeypatch, change):
    document(tmp_path, 'good.md')

    def post_process(self, result, args):
        result = dict(result)
        row = dict(result['results'][0]) if change else {}
        row.update(change)
        result['results'] = [row]
        return result

    monkeypatch.setattr(MarkdownQueryAdapter, 'post_process', post_process)
    response = run(uri(tmp_path), '--format', 'json')
    assert response.returncode == 3
    answer = json.loads(response.stdout)
    assert any(error['code'] == 'invalid_adapter_answer' for error in answer['meta']['errors'])


@pytest.mark.parametrize('format', ['text', 'grep', 'json'])
@pytest.mark.parametrize('survivor', [False, True])
def test_required_loss_diagnostic_is_visible_exactly_once(tmp_path, format, survivor):
    if survivor:
        document(tmp_path, 'good.md')
    document(tmp_path, 'bad.md', b'needle caf\xe9\n')
    response = run(uri(tmp_path), '--format', format)
    assert response.returncode == 3
    if format == 'json':
        warnings = json.loads(response.stdout)['meta']['warnings']
        assert len([warning for warning in warnings if warning['type'] == 'unreadable_files']) == 1
    else:
        combined = response.stdout + response.stderr
        assert combined.count('required document evidence is missing') == 1
        assert 'bad.md' in combined
        if format == 'grep':
            assert 'required document evidence is missing' in response.stderr
            assert 'bad.md' not in response.stdout
