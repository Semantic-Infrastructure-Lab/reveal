"""Git command adoption must respect the repository namespace and existing view owners."""
import json

import pytest

from conftest import _run_reveal_in
from test_git_declared_api_back2616 import repo_path


@pytest.mark.parametrize('suffix,controls,query,kind', [
    ('', [], '', 'git_repository'),
    ('@HEAD~1', [], '', 'git_ref'),
    ('/code.py', [], '', 'git_file_structure'),
    ('/code.py@HEAD~1', ['--detail', 'raw'], '?detail=raw', 'git_file'),
    ('/code.py', ['--view', 'history'], '?view=history', 'git_file_history'),
    ('/code.py', ['--view', 'blame'], '?view=blame', 'git_file_blame'),
    ('/code.py', ['--view', 'diff'], '?view=diff', 'git_file_diff'),
    ('', ['--view', 'ownership'], '?view=ownership', 'git_ownership'),
    ('', ['--view', 'history', '--bucket', 'month'], '?view=history&bucket=month', 'git_timeline'),
])
def test_cli_uri_share_existing_view_identity(repo_path, suffix, controls, query, kind):
    path = str(repo_path) + suffix
    cli = _run_reveal_in(repo_path, 'git', path, *controls, '--format', 'json')
    uri = _run_reveal_in(repo_path, 'git://' + path + query, '--format', 'json')
    assert cli.returncode == uri.returncode == 0, (cli.stderr, uri.stderr)
    a, b = json.loads(cli.stdout), json.loads(uri.stdout)
    assert a == b and a['type'] == kind
    assert a['meta']['errors'] == []


def test_historical_file_is_valid_after_worktree_deletion(repo_path):
    (repo_path / 'code.py').unlink()
    result = _run_reveal_in(repo_path, 'git', str(repo_path / 'code.py') + '@HEAD~1',
                            '--detail', 'raw', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert 'return 1' in json.loads(result.stdout)['content']


def test_ref_request_error_and_output_failure_are_distinct(repo_path):
    path = str(repo_path) + '@not-a-real-ref'
    result = _run_reveal_in(repo_path, 'git', path, '--format', 'json')
    assert result.returncode == 2
    answer = json.loads(result.stdout)
    assert answer['type'] == 'git_ref' and answer['meta']['errors'][0]['code'] == 'invalid_request'
    failed_output = _run_reveal_in(repo_path, 'git', path, '--format', 'json',
                                   '--also-json', str(repo_path / 'missing-dir' / 'answer.json'))
    assert failed_output.returncode == 3
    assert json.loads(failed_output.stdout)['error'] == answer['error']


def commit_bytes(repo_path, content):
    import pygit2
    repo = pygit2.Repository(str(repo_path))
    (repo_path / 'code.py').write_bytes(content)
    repo.index.add('code.py')
    repo.index.write()
    sig = pygit2.Signature('Scott', 'scott@example.com', 1700000020, 0)
    repo.create_commit('HEAD', sig, sig, 'damaged source', repo.index.write_tree(), [repo.head.target])


def test_recovered_structure_is_incomplete_instead_of_clean(repo_path):
    commit_bytes(repo_path, b'def retained():\n    return 1\n\ndef broken(:\n')
    result = _run_reveal_in(repo_path, f'git://{repo_path}/code.py', '--format', 'json')
    assert result.returncode == 3
    data = json.loads(result.stdout)
    assert data['structure']['functions']
    assert any(w.get('code') == 'analysis_incomplete' for w in data['meta']['warnings'])


def test_replacement_decoding_keeps_text_but_discloses_required_loss(repo_path):
    commit_bytes(repo_path, b'def retained():\n    return 1\n# \xff\n')
    result = _run_reveal_in(repo_path, f'git://{repo_path}/code.py?detail=raw', '--format', 'json')
    assert result.returncode == 3
    data = json.loads(result.stdout)
    assert 'def retained' in data['content']
    assert any(w.get('code') == 'analysis_incomplete' for w in data['meta']['warnings'])


def test_semantic_blame_uses_the_requested_revision_after_worktree_deletion(repo_path):
    (repo_path / 'code.py').unlink()
    result = _run_reveal_in(repo_path, f'git://{repo_path}/code.py@HEAD~1?view=blame&element=answer', '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    assert answer['element']['name'] == 'answer'
    assert not result.stderr


def test_element_history_cannot_count_parser_failure_as_absence(repo_path, monkeypatch):
    import reveal.registry
    class FailedAnalyzer:
        def __init__(self, *args, **kwargs):
            pass
        def get_structure(self):
            raise ValueError('semantic source could not be analyzed')
    monkeypatch.setattr(reveal.registry, 'get_analyzer', lambda *a, **kw: FailedAnalyzer)
    result = _run_reveal_in(repo_path, f'git://{repo_path}/code.py?view=history&element=answer', '--format', 'json')
    assert result.returncode == 3
    assert 'semantic source could not be analyzed' in json.loads(result.stdout)['error']


def test_proven_absent_blame_element_is_a_request_error(repo_path):
    result = _run_reveal_in(repo_path, f'git://{repo_path}/code.py?view=blame&element=absent', '--format', 'json')
    assert result.returncode == 2
    assert 'Element not found' in json.loads(result.stdout)['error']


@pytest.mark.parametrize('view', ['diff', 'blame', 'ownership'])
def test_named_tree_path_missing_at_ref_is_usage(repo_path, view):
    result = _run_reveal_in(repo_path, f'git://{repo_path}/absent.py?view={view}', '--format', 'json')
    assert result.returncode == 2
    assert json.loads(result.stdout)['meta']['errors'][0]['code'] == 'invalid_request'


def test_content_search_decode_loss_keeps_known_matches_and_is_incomplete(repo_path):
    commit_bytes(repo_path, b'def answer():\n    return 2\n# \xff\n')
    result = _run_reveal_in(repo_path, f'git://{repo_path}/code.py?view=history&where=content~%3Dreturn', '--format', 'json')
    assert result.returncode == 3
    data = json.loads(result.stdout)
    assert data['commits']
    assert any(w.get('code') == 'analysis_incomplete' for w in data['meta']['warnings'])

    followup = _run_reveal_in(repo_path, f'git://{repo_path}?view=history&limit=1', '--format', 'json')
    assert followup.returncode == 0, followup.stdout
    assert not any(w.get('code') == 'analysis_incomplete' for w in json.loads(followup.stdout)['meta']['warnings'])


@pytest.mark.parametrize('kind', ['branch', 'tag'])
def test_unreadable_enumerated_ref_does_not_look_like_a_complete_list(repo_path, monkeypatch, kind):
    import pygit2
    from reveal.adapters.git import refs
    if kind == 'tag':
        repo = pygit2.Repository(str(repo_path))
        repo.create_reference('refs/tags/release', repo.head.target)
    monkeypatch.setattr(refs, '_get_' + kind + '_info', lambda *args: None)
    result = _run_reveal_in(repo_path, f'git://{repo_path}', '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['head']
    proof = answer['meta']['ref_sources']['branches' if kind == 'branch' else 'tags']
    assert proof['failed'] == 1 and proof['candidates'] == proof['analyzed'] + proof['failed']



def test_native_ref_read_failure_is_analysis_instead_of_invalid_name(repo_path, monkeypatch):
    import pygit2
    from reveal.adapters.git.adapter import GitAdapter
    real = pygit2.Repository(str(repo_path))
    class BrokenRepo:
        def revparse_single(self, ref):
            raise pygit2.GitError('required object read failed')
        def __getattr__(self, name):
            return getattr(real, name)
    monkeypatch.setattr(GitAdapter, '_open_repository', lambda self: BrokenRepo())
    result = _run_reveal_in(repo_path, f'git://{repo_path}@HEAD~1', '--format', 'json')
    assert result.returncode == 3
    assert json.loads(result.stdout)['meta']['errors'][0]['code'] != 'invalid_request'


@pytest.mark.parametrize('query', ['view=history&bucket=month&scan-limit=1', 'view=ownership&scan-limit=1'])
def test_input_window_cut_is_incomplete_but_a_list_page_is_complete(repo_path, query):
    limited = _run_reveal_in(repo_path, f'git://{repo_path}?{query}', '--format', 'json')
    assert limited.returncode == 3
    assert any(w.get('code') == 'analysis_incomplete' for w in json.loads(limited.stdout)['meta']['warnings'])
    page = _run_reveal_in(repo_path, f'git://{repo_path}?view=history&limit=1', '--format', 'json')
    assert page.returncode == 0 and len(json.loads(page.stdout)['history']) == 1


def test_content_match_keeps_literal_operator_semantics(repo_path):
    from reveal.api import query
    result = query(f'git://{repo_path}/code.py?view=history', where=['content~=['])
    assert result['commits'] == []


@pytest.mark.parametrize('kind,field', [('history', 'history'), ('ownership', 'authors')])
def test_postprocessing_cannot_erase_required_observations(repo_path, monkeypatch, kind, field):
    from reveal.adapters.git.adapter import GitAdapter
    def erase(self, result, args):
        result.pop(field)
        return result
    monkeypatch.setattr(GitAdapter, 'post_process', erase, raising=False)
    result = _run_reveal_in(repo_path, f'git://{repo_path}?view={kind}', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


def test_recovered_source_failure_survives_projection(repo_path):
    commit_bytes(repo_path, b'def retained():\n    return 1\n\ndef broken(:\n')
    result = _run_reveal_in(repo_path, f'git://{repo_path}/code.py', '--fields', 'type', '--format', 'json')
    assert result.returncode == 3


def test_measured_empty_structure_and_unsupported_analyzer_stay_distinct(repo_path):
    import pygit2
    commit_bytes(repo_path, b'')
    empty = _run_reveal_in(repo_path, f'git://{repo_path}/code.py', '--format', 'json')
    assert empty.returncode == 0 and json.loads(empty.stdout)['meta']['blob_analysis']['available'] is True
    repo = pygit2.Repository(str(repo_path))
    (repo_path / 'plain.unknown_reveal_kind').write_text('some text\n', encoding='utf-8')
    repo.index.add('plain.unknown_reveal_kind')
    repo.index.write()
    sig = pygit2.Signature('Scott', 'scott@example.com', 1700000030, 0)
    repo.create_commit('HEAD', sig, sig, 'unsupported file', repo.index.write_tree(), [repo.head.target])
    unsupported = _run_reveal_in(repo_path, f'git://{repo_path}/plain.unknown_reveal_kind', '--format', 'json')
    assert unsupported.returncode == 0
    data = json.loads(unsupported.stdout)
    assert data['structure'] == {} and data['meta']['blob_analysis']['available'] is False
    assert any(w['code'] == 'not_applicable' for w in data['meta']['warnings'])


@pytest.mark.parametrize('view,field,extra', [('ownership', 'authors', ''), ('history', 'buckets', '&bucket=month')])
def test_canonical_aggregate_limit_is_a_display_cap_with_full_counts(repo_path, view, field, extra):
    result = _run_reveal_in(repo_path, f'git://{repo_path}?view={view}{extra}&limit=0', '--format', 'json')
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data[field] == []
    assert data['total_commits' if view == 'ownership' else 'commit_count'] == 3


def test_scan_limit_is_distinct_from_rows_and_keeps_legacy_window(repo_path):
    from reveal.api import query
    limited = _run_reveal_in(repo_path, f'git://{repo_path}?view=ownership&scan-limit=1&limit=0', '--format', 'json')
    assert limited.returncode == 3
    data = json.loads(limited.stdout)
    assert data['authors'] == [] and data['total_commits'] == 1
    assert data['scope']['history_window']['complete'] is False
    legacy = query(f'git://{repo_path}?type=ownership&limit=1')
    assert legacy['total_commits'] == 1 and len(legacy['authors']) == 1
    modern = query(f'git://{repo_path}?type=ownership&limit=1', limit=0)
    assert modern['total_commits'] == 3 and modern['authors'] == []


def test_scan_limit_rejects_a_view_without_an_input_budget(repo_path):
    result = _run_reveal_in(repo_path, f'git://{repo_path}?view=history&scan-limit=1', '--format', 'json')
    assert result.returncode == 2


@pytest.mark.parametrize('mark', ['?', '@'])
def test_typed_resource_keeps_literal_namespace_punctuation(repo_path, mark):
    import os
    import pygit2
    if mark == '?' and os.name == 'nt':
        pytest.skip('Windows filenames cannot contain a question mark')
    path = repo_path / ('literal' + mark + 'repo')
    repo = pygit2.init_repository(str(path))
    (path / 'value.py').write_text('value = 42\n', encoding='utf-8')
    repo.index.add('value.py')
    repo.index.write()
    sig = pygit2.Signature('Scott', 'scott@example.com', 1700000040, 0)
    repo.create_commit('HEAD', sig, sig, 'literal source', repo.index.write_tree(), [])
    result = _run_reveal_in(repo_path, 'git', path.name, '--view', 'history', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['history'][0]['message'] == 'literal source'


@pytest.mark.parametrize('suffix', ['', '/code.py?view=blame'])
def test_raw_detail_rejects_views_without_raw_content(repo_path, suffix):
    join = '&' if '?' in suffix else '?'
    result = _run_reveal_in(repo_path, f'git://{repo_path}{suffix}{join}detail=raw', '--format', 'json')
    assert result.returncode == 2


def test_original_resource_control_scope_is_validated_before_overrides(repo_path):
    from reveal.api import query
    with pytest.raises(ValueError, match='raw'):
        query(f'git://{repo_path}?detail=raw', detail=None)


@pytest.mark.parametrize('view,extra', [('ownership', ''), ('history', '&bucket=month'), ('blame', '')])
def test_content_predicate_rejects_views_without_that_analysis(repo_path, view, extra):
    result = _run_reveal_in(repo_path, f'git://{repo_path}/code.py?view={view}{extra}&where=content~%3Dreturn', '--format', 'json')
    assert result.returncode == 2


def test_row_sort_and_offset_apply_after_aggregation(repo_path):
    import pygit2
    repo = pygit2.Repository(str(repo_path))
    for name, timestamp, value in [('Amy', 1702680000, 3), ('Zed', 1705358400, 4)]:
        (repo_path / 'code.py').write_text(f'def answer():\n    return {value}\n', encoding='utf-8')
        repo.index.add('code.py')
        repo.index.write()
        sig = pygit2.Signature(name, name.lower() + '@example.com', timestamp, 0)
        repo.create_commit('HEAD', sig, sig, name, repo.index.write_tree(), [repo.head.target])
    result = _run_reveal_in(repo_path, 'git', str(repo_path), '--view', 'ownership', '--sort', 'name',
                            '--offset', '1', '--limit', '1', '--format', 'json')
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data['total_commits'] == 5 and data['contributor_count'] == 3
    assert [a['name'] for a in data['authors']] == ['Scott']
    timeline = _run_reveal_in(repo_path, 'git', str(repo_path), '--view', 'history', '--bucket', 'month',
                              '--sort=-period', '--offset', '1', '--limit', '1', '--format', 'json')
    assert timeline.returncode == 0, timeline.stderr
    data = json.loads(timeline.stdout)
    assert data['commit_count'] == 5 and data['distinct_author_count'] == 3
    assert [b['period'] for b in data['buckets']] == ['2023-12']
    from reveal.api import query
    overlay = query(f'git://{repo_path}?type=ownership&limit=1', sort='name', offset=1)
    assert overlay['total_commits'] == 5 and [a['name'] for a in overlay['authors']] == ['Scott']


@pytest.mark.parametrize('expression', ['limit=0', 'type=history', 'ref=HEAD~1'])
def test_where_cannot_change_controls_instead_of_filtering_data(repo_path, expression):
    from urllib.parse import quote
    result = _run_reveal_in(repo_path, f'git://{repo_path}?where={quote(expression, safe="")}', '--format', 'json')
    assert result.returncode == 2


@pytest.mark.parametrize('expression', ['content', 'content~', 'content~='])
def test_changed_content_predicate_requires_literal_text(repo_path, expression):
    from urllib.parse import quote
    result = _run_reveal_in(repo_path, f'git://{repo_path}?where={quote(expression, safe="")}', '--format', 'json')
    assert result.returncode == 2


def test_missing_object_behind_a_known_ref_is_required_source_loss(repo_path, monkeypatch):
    import pygit2
    from reveal.adapters.git.adapter import GitAdapter
    real = pygit2.Repository(str(repo_path))
    class MissingObjectRepo:
        def revparse_single(self, ref):
            raise KeyError(ref)
        def __getattr__(self, name):
            return getattr(real, name)
    monkeypatch.setattr(GitAdapter, '_open_repository', lambda self: MissingObjectRepo())
    result = _run_reveal_in(repo_path, f'git://{repo_path}?view=history', '--format', 'json')
    assert result.returncode == 3


@pytest.mark.parametrize('view', ['ownership', 'timeline', 'repository'])
def test_removed_rows_need_a_matching_truncation_receipt(repo_path, monkeypatch, view):
    from reveal.adapters.git.adapter import GitAdapter
    def erase_rows(self, result, args):
        if view == 'ownership':
            result['authors'] = []
        elif view == 'timeline':
            result['buckets'] = []
        else:
            result['branches']['recent'] = []
        return result
    monkeypatch.setattr(GitAdapter, 'post_process', erase_rows, raising=False)
    query = {'ownership': '?view=ownership', 'timeline': '?view=history&bucket=month', 'repository': ''}[view]
    result = _run_reveal_in(repo_path, f'git://{repo_path}{query}', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


def test_declared_presentation_cut_keeps_source_counts(repo_path, monkeypatch):
    from reveal.adapters.git.adapter import GitAdapter
    from reveal.utils.results import note_truncation
    def cut(self, result, args):
        total = len(result['authors'])
        result['authors'] = []
        note_truncation(result, 'authors', 0, total, 'presentation')
        return result
    monkeypatch.setattr(GitAdapter, 'post_process', cut, raising=False)
    result = _run_reveal_in(repo_path, f'git://{repo_path}?view=ownership', '--format', 'json')
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload['authors'] == []
    assert payload['contributor_count'] > 0
