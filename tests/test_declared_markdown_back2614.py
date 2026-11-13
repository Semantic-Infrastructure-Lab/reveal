"""Markdown declarations preserve filtering and source completeness across its views."""
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_in
from reveal.adapters.markdown.adapter import MarkdownQueryAdapter


@pytest.fixture
def docs(tmp_path):
    (tmp_path / 'a.md').write_text('---\ntitle: Alpha\nowner: Alice\nstatus: draft\n---\n# Alpha\nhello world\n[b](b.md)\n', encoding='utf-8')
    (tmp_path / 'b.md').write_text('---\ntitle: Beta\nowner: Bob\nstatus: final\n---\n# Beta\nworld\n', encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('query', ['', 'link-graph', 'lint', 'backlinks=a.md'])
def test_every_view_records_unreadable_required_sources(docs, monkeypatch, query):
    from reveal.utils.results import AnalysisCompleteness
    original = Path.read_text
    def read(path, *args, **kwargs):
        if path == docs / 'b.md':
            raise PermissionError('MARKDOWN_REQUIRED_SOURCE_DENIED')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', read)
    result = MarkdownQueryAdapter(str(docs), query).get_structure()
    assert result['analysis']['candidate_files'] == 2
    assert result['analysis']['failed_files'] == 1
    assert MarkdownQueryAdapter.execution_facts(result).completeness is AnalysisCompleteness.INCOMPLETE


def answer(docs, *argv):
    run = _run_reveal_in(docs, *argv, '--format', 'json')
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def test_listing_cli_uri_api_agree_on_repeated_match_and_filters(docs):
    from reveal.api import query
    a = answer(docs, 'markdown', '.', '--where', 'status=draft', '--match', 'hello', '--match', 'world')
    b = answer(docs, 'markdown://.?where=status%3Ddraft&match=hello&match=world')
    assert a == b and a['matched_files'] == 1
    typed = query(f'markdown://{docs}', where=['status=draft'], match=['hello', 'world'])
    assert typed['matched_files'] == 1


@pytest.mark.parametrize('flags,suffix,kind', [
    (['--view', 'links'], '?view=links', 'markdown_link_graph'),
    (['--view', 'aggregate', '--field', 'status'], '?view=aggregate&field=status', 'markdown_aggregate'),
    (['--backlinks', 'b.md'], '?backlinks=b.md', 'markdown_backlinks'),
])
def test_existing_views_share_generated_bindings(docs, flags, suffix, kind):
    a = answer(docs, 'markdown', '.', *flags)
    b = answer(docs, 'markdown://.' + suffix)
    assert a == b and a['type'] == kind


def test_zero_and_false_overrides_remain_explicit(docs):
    from reveal.api import query
    uri = f'markdown://{docs}?match=world&limit=1'
    assert query(uri, limit=0)['results'] == []
    assert len(query(uri)['results']) == 1


def test_columns_have_one_owner_and_json_fields_keep_projection(docs):
    a = answer(docs, 'markdown', '.', '--columns', 'owner')
    b = answer(docs, 'markdown://.?columns=owner')
    assert a == b
    assert {row['owner'] for row in a['results']} == {'Alice', 'Bob'}
    assert all(row['_extra_fields'] == ['owner'] for row in a['results'])
    assert answer(docs, 'markdown://.?fields=owner') == a
    projected = answer(docs, 'markdown', '.', '--fields', 'type')
    assert 'results' not in projected and projected['type'] == 'markdown_query'


def test_false_override_clears_explanation_without_changing_matching(docs):
    from reveal.api import query
    uri = f'markdown://{docs}?match=world&explain'
    assert all('relevance_explain' in row for row in query(uri)['results'])
    cleared = query(uri, explain=False)
    assert cleared['matched_files'] == 2
    assert all('relevance_explain' not in row for row in cleared['results'])


def test_postprocessing_cannot_forge_graph_counts(docs, monkeypatch):
    def corrupt(result, args):
        result['total_edges'] += 10
        return result
    monkeypatch.setattr(MarkdownQueryAdapter, 'post_process', staticmethod(corrupt), raising=False)
    result = _run_reveal_in(docs, 'markdown', '.', '--view', 'links', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


def test_resource_validation_precedes_bad_controls_and_preserves_literal_paths(docs):
    from reveal.api import query
    with pytest.raises(FileNotFoundError):
        query(f'markdown://{docs / "missing"}?limit=bad')
    run = _run_reveal_in(docs, 'markdown', 'missing', '--limit', 'bad', '--format', 'json')
    assert run.returncode == 2
    assert 'not found' in json.loads(run.stdout)['error'].lower()


@pytest.mark.parametrize('filename', ['space #雪%26', 'question?and%26'])
def test_literal_directory_paths(docs, filename):
    from filename_fixture import require_filename
    special = docs / filename
    require_filename(special)
    special.mkdir()
    (special / 'one.md').write_text('# One\n', encoding='utf-8')
    typed = _run_reveal_in(docs, 'markdown', str(special), '--format', 'json')
    assert typed.returncode == 0
    assert json.loads(typed.stdout)['analysis']['candidate_files'] == 1


def test_old_graph_cache_without_source_proof_is_recomputed(docs, monkeypatch):
    from reveal.adapters.markdown import operations
    legacy = {'total_files': 2, 'total_edges': 0, 'nodes': [], 'orphans': [], 'isolated': []}
    monkeypatch.setattr(operations.disk_cache, 'get', lambda *a, **kw: legacy)
    graph = operations.build_link_graph(docs)
    assert graph['analysis']['analyzed_files'] == 2
    assert graph['total_edges'] == 1
