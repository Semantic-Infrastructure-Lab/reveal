"""BACK-1059 (git, stats, markdown, python, diff, ast, help_data adapters): a handler
catches the errors its body can actually produce, and a failure that would make a result
look complete is raised or disclosed instead of swallowed.

Unexpected failure is injected as ``_InjectedBug`` (a RuntimeError nothing in these
handlers expects). Negative controls: the expected error still takes the old path.
Every repository is built under tmp_path with pygit2 (no host git config, no network).
"""

import logging
import os
import stat
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.component


class _InjectedBug(RuntimeError):
    """A failure no handler here expects: stands in for a bug in reveal."""


def _raise_bug(*_a, **_k):
    raise _InjectedBug('injected')


# ------------------------------------------------------------------ git fixtures

def _make_repo(tmp_path, commits=3, name='a.txt'):
    """A repo with *commits* commits, each rewriting *name*. Returns (path, tree oids, repo)."""
    pygit2 = pytest.importorskip('pygit2')
    path = tmp_path / 'repo'
    repo = pygit2.init_repository(str(path), initial_head='main')
    parents: list = []
    trees = []
    for i in range(commits):
        sig = pygit2.Signature('T', 't@example.com', 1_700_000_000 + i * 60, 0)
        blob = repo.create_blob(f'def f():\n    return {i}\n'.encode())
        builder = repo.TreeBuilder()
        builder.insert(name, blob, 0o100644)
        tree = builder.write()
        oid = repo.create_commit('refs/heads/main', sig, sig, f'c{i}', tree, parents)
        parents = [oid]
        trees.append(tree)
    return path, trees, repo


def _drop_object(repo, oid) -> None:
    """Delete one loose object: a repository that lost a tree or blob."""
    hexid = str(oid)
    target = Path(repo.path) / 'objects' / hexid[:2] / hexid[2:]
    os.chmod(target, stat.S_IWRITE | stat.S_IREAD)  # git writes objects read-only
    target.unlink()


def _reopen(path):
    import pygit2
    return pygit2.Repository(str(path))


# ---------------------------------------------------------------- git/refs.py

def test_head_info_of_a_corrupt_branch_ref_is_a_failure_not_an_empty_repo(tmp_path):
    from reveal.adapters.git import refs
    path, _trees, repo = _make_repo(tmp_path)
    (Path(repo.path) / 'refs' / 'heads' / 'main').write_text('zzzz\n', encoding='utf-8')
    with pytest.raises(ValueError, match='HEAD'):
        refs.get_head_info(_reopen(path))


def test_repository_overview_of_a_corrupt_branch_ref_fails(tmp_path):
    from reveal.adapters.git.adapter import GitAdapter
    path, _trees, repo = _make_repo(tmp_path)
    (Path(repo.path) / 'refs' / 'heads' / 'main').write_text('zzzz\n', encoding='utf-8')
    with pytest.raises(ValueError):
        GitAdapter(path=str(path)).get_structure()


def test_head_info_of_a_healthy_and_of_an_empty_repo_is_unchanged(tmp_path):
    pygit2 = pytest.importorskip('pygit2')
    from reveal.adapters.git import refs
    path, _trees, _repo = _make_repo(tmp_path)
    info = refs.get_head_info(_reopen(path))
    assert info['branch'] == 'main' and info['commit'] and info['detached'] is False
    empty = pygit2.init_repository(str(tmp_path / 'empty'), initial_head='main')
    assert refs.get_head_info(empty) == {'branch': None, 'commit': None, 'detached': False}


# --------------------------------------------------------------- git/files.py

def test_history_fails_when_a_commit_tree_cannot_be_read(tmp_path):
    from reveal.adapters.git.adapter import GitAdapter
    path, trees, repo = _make_repo(tmp_path)
    _drop_object(repo, trees[1])
    adapter = GitAdapter(path=str(path), subpath='a.txt', query={'type': 'history'})
    with pytest.raises(ValueError, match='history walk failed'):
        adapter.get_structure()


def test_ownership_fails_when_a_commit_tree_cannot_be_read(tmp_path):
    import pygit2
    from reveal.adapters.git.adapter import GitAdapter
    path, trees, repo = _make_repo(tmp_path)
    _drop_object(repo, trees[1])
    adapter = GitAdapter(path=str(path), subpath='a.txt', query={'type': 'ownership'})
    with pytest.raises((ValueError, pygit2.GitError)):
        adapter.get_structure()


def test_history_of_a_healthy_repo_still_lists_every_commit(tmp_path):
    from reveal.adapters.git.adapter import GitAdapter
    path, _trees, _repo = _make_repo(tmp_path)
    result = GitAdapter(path=str(path), subpath='a.txt', query={'type': 'history'}).get_structure()
    assert [c['message'] for c in result['commits']] == ['c2', 'c1', 'c0']


def test_commit_touches_path_of_an_unreadable_tree_raises(tmp_path):
    import pygit2
    from reveal.adapters.git import files
    path, trees, repo = _make_repo(tmp_path)
    _drop_object(repo, trees[0])
    repo = _reopen(path)
    second = repo[repo.head.target].parents[0]  # its parent is the commit whose tree is gone
    with pytest.raises(pygit2.GitError):
        files.commit_touches_path(repo, second, 'a.txt')
    with pytest.raises(pygit2.GitError):
        files.commit_touches_file(repo, second, 'a.txt')


def test_commit_touches_file_of_a_path_absent_from_the_commit_is_false(tmp_path):
    from reveal.adapters.git import files
    path, _trees, _repo = _make_repo(tmp_path)
    repo = _reopen(path)
    head = repo[repo.head.target]
    assert files.commit_touches_file(repo, head, 'no-such-file.txt') is False
    assert files.commit_touches_path(repo, head, 'no-such-file.txt') is False


def test_element_content_of_a_missing_blob_is_a_failure_not_an_absent_element(tmp_path):
    import pygit2
    from reveal.adapters.git import files
    path, _trees, repo = _make_repo(tmp_path, name='a.py')
    middle = repo[repo.head.target].parents[0]
    _drop_object(repo, middle.tree['a.py'].id)
    repo = _reopen(path)
    middle = repo[repo.head.target].parents[0]
    with pytest.raises(pygit2.GitError):
        files._get_element_content_at_commit(repo, middle, 'a.py', 'f')


def test_element_content_of_a_path_absent_from_the_commit_is_none(tmp_path):
    from reveal.adapters.git import files
    path, _trees, _repo = _make_repo(tmp_path, name='a.py')
    repo = _reopen(path)
    head = repo[repo.head.target]
    assert files._get_element_content_at_commit(repo, head, 'gone.py', 'f') is None
    assert 'return 2' in files._get_element_content_at_commit(repo, head, 'a.py', 'f')


def test_content_pattern_search_does_not_swallow_a_bug(tmp_path, monkeypatch):
    from reveal.adapters.git import files
    path, _trees, _repo = _make_repo(tmp_path)
    repo = _reopen(path)
    head = repo[repo.head.target]
    monkeypatch.setattr(subprocess, 'run', _raise_bug)
    with pytest.raises(_InjectedBug):
        files._commit_diff_contains(repo, head, '', 'return')


@pytest.mark.parametrize('exc', [FileNotFoundError('git'),
                                 subprocess.TimeoutExpired('git', 1)], ids=['no-git', 'timeout'])
def test_content_pattern_search_still_discloses_an_unrunnable_git(tmp_path, monkeypatch, exc):
    from reveal.adapters.git import files

    def run(*_a, **_k):
        raise exc

    path, _trees, _repo = _make_repo(tmp_path)
    repo = _reopen(path)
    head = repo[repo.head.target]
    files._reset_content_search_error()
    monkeypatch.setattr(subprocess, 'run', run)
    assert files._commit_diff_contains(repo, head, '', 'return') is False
    assert 'degraded' in files.get_content_search_disclosure()
    files._reset_content_search_error()


# ------------------------------------------------- filters: git, markdown, stats

def _git_adapter(tmp_path):
    from reveal.adapters.git.adapter import GitAdapter
    path, _trees, _repo = _make_repo(tmp_path)
    return GitAdapter(path=str(path), query={'type': 'history', 'author': 'T'})


def _markdown_adapter(tmp_path):
    from reveal.adapters.markdown.adapter import MarkdownQueryAdapter
    (tmp_path / 'a.md').write_text('---\nn: 1\n---\nbody\n', encoding='utf-8')
    return MarkdownQueryAdapter(str(tmp_path), 'n>0')


def _stats_adapter(tmp_path):
    from reveal.adapters.stats.adapter import StatsAdapter
    (tmp_path / 'a.py').write_text('x = 1\n', encoding='utf-8')
    return StatsAdapter(str(tmp_path), 'lines>0')


_FILTER_ADAPTERS = [
    pytest.param(_git_adapter, 'reveal.adapters.git.adapter', id='git'),
    pytest.param(_markdown_adapter, 'reveal.adapters.markdown.adapter', id='markdown'),
    pytest.param(_stats_adapter, 'reveal.adapters.stats.adapter', id='stats'),
]


@pytest.mark.parametrize('make,module', _FILTER_ADAPTERS)
def test_a_filter_that_cannot_be_parsed_fails_the_query(tmp_path, monkeypatch, make, module):
    monkeypatch.setattr(module + '.parse_query_filters', lambda *a, **k: (_ for _ in ()).throw(
        ValueError('bad filter')))
    with pytest.raises(ValueError, match='bad filter'):
        make(tmp_path)


@pytest.mark.parametrize('make,module', _FILTER_ADAPTERS)
def test_a_filter_that_parses_is_applied(tmp_path, make, module):
    adapter = make(tmp_path)
    assert adapter.query_filters, 'the control: a valid filter is parsed and kept'


# ------------------------------------------------------------ diff/resolution.py

class _CtorCounts:
    calls = 0


def _counting_class(exc):
    class Adapter(_CtorCounts):
        calls = 0

        def __init__(self, resource):
            type(self).calls += 1
            raise exc

    return Adapter


@pytest.mark.parametrize('exc', [TypeError('bad resource'), _InjectedBug('injected')],
                         ids=['TypeError', 'bug'])
def test_instantiate_adapter_runs_a_constructor_once_and_shows_its_error(exc):
    from reveal.adapters.diff.resolution import instantiate_adapter
    cls = _counting_class(exc)
    with pytest.raises(type(exc), match=str(exc)):
        instantiate_adapter(cls, 'x', 'thing')
    assert cls.calls == 1


def test_instantiate_adapter_still_handles_a_class_without_a_readable_signature():
    from reveal.adapters.diff.resolution import instantiate_adapter

    def init(self, resource):
        self.resource = resource

    init.__signature__ = 'not a signature'  # inspect.signature raises TypeError for this
    cls = type('Opaque', (), {'__init__': init})
    assert instantiate_adapter(cls, 'x', 'thing').resource == 'thing'


def test_instantiate_adapter_passes_the_resource_only_when_the_constructor_takes_one():
    from reveal.adapters.diff.resolution import instantiate_adapter

    class NoArgs:
        pass

    class OneArg:
        def __init__(self, resource):
            self.resource = resource

    assert isinstance(instantiate_adapter(NoArgs, 'x', 'thing'), NoArgs)
    assert instantiate_adapter(OneArg, 'x', 'thing').resource == 'thing'


# --------------------------------------------------------------- help_data

@pytest.fixture
def help_dir(tmp_path, monkeypatch):
    from reveal.adapters.help_data import HelpDataLoader
    monkeypatch.setattr(HelpDataLoader, '_help_dir', tmp_path)
    monkeypatch.setattr(HelpDataLoader, '_cache', {})
    return tmp_path


def test_help_loader_does_not_swallow_a_bug(help_dir, monkeypatch):
    import yaml
    from reveal.adapters.help_data import HelpDataLoader
    (help_dir / 'x.yaml').write_text('a: 1\n', encoding='utf-8')
    monkeypatch.setattr(yaml, 'safe_load', _raise_bug)
    with pytest.raises(_InjectedBug):
        HelpDataLoader.load('x')


@pytest.mark.parametrize('how', ['directory', 'bad-utf8', 'bad-yaml'])
def test_help_loader_still_reports_an_unreadable_file_and_returns_none(help_dir, caplog, how):
    from reveal.adapters.help_data import HelpDataLoader
    target = help_dir / 'x.yaml'
    if how == 'directory':
        target.mkdir()
    elif how == 'bad-utf8':
        target.write_bytes(b'a: \xff\xfe\n')
    else:
        target.write_text('a: [unclosed\n', encoding='utf-8')
    with caplog.at_level(logging.ERROR):
        assert HelpDataLoader.load('x') is None
    assert 'x.yaml' in caplog.text


# ---------------------------------------------------------------- markdown

def _patch_read_text(monkeypatch, target: Path, exc):
    real = Path.read_text

    def read_text(self, *a, **k):
        if self == target:
            raise exc
        return real(self, *a, **k)

    monkeypatch.setattr(Path, 'read_text', read_text)


_MD_READERS = [
    pytest.param(lambda f, tmp: f.read_body_text(tmp / 'a.md'), '', id='body'),
    pytest.param(lambda f, tmp: f.extract_internal_links(tmp / 'a.md', tmp), [], id='links'),
    pytest.param(lambda f, tmp: f.extract_frontmatter_diagnostic(tmp / 'a.md')['status'],
                 'missing', id='frontmatter'),
]


@pytest.mark.parametrize('read,_expected', _MD_READERS)
def test_markdown_readers_do_not_swallow_a_bug(tmp_path, monkeypatch, read, _expected):
    from reveal.adapters.markdown import files
    (tmp_path / 'a.md').write_text('# t\n', encoding='utf-8')
    _patch_read_text(monkeypatch, tmp_path / 'a.md', _InjectedBug('injected'))
    with pytest.raises(_InjectedBug):
        read(files, tmp_path)


@pytest.mark.parametrize('how', ['permission', 'bad-utf8'])
@pytest.mark.parametrize('read,expected', _MD_READERS)
def test_markdown_readers_still_degrade_on_an_unreadable_file(tmp_path, monkeypatch, read,
                                                               expected, how):
    from reveal.adapters.markdown import files
    (tmp_path / 'a.md').write_text('# t\n', encoding='utf-8')
    if how == 'permission':
        _patch_read_text(monkeypatch, tmp_path / 'a.md', PermissionError('denied'))
    else:
        (tmp_path / 'a.md').write_bytes(b'# t \xff\xfe\n')
    assert read(files, tmp_path) == expected


def test_markdown_sort_over_mixed_value_types_still_sorts(tmp_path):
    from reveal.adapters.markdown.adapter import MarkdownQueryAdapter
    (tmp_path / 'a.md').write_text('---\ntitle: abc\n---\nx\n', encoding='utf-8')
    (tmp_path / 'b.md').write_text('---\ntitle: 10\n---\nx\n', encoding='utf-8')
    result = MarkdownQueryAdapter(str(tmp_path), 'sort=title').get_structure()
    assert [Path(r['path']).name for r in result['results']] == ['b.md', 'a.md']


def test_markdown_sort_over_one_value_type_is_unchanged(tmp_path):
    from reveal.adapters.markdown.adapter import MarkdownQueryAdapter
    (tmp_path / 'a.md').write_text('---\ntitle: 9\n---\nx\n', encoding='utf-8')
    (tmp_path / 'b.md').write_text('---\ntitle: 10\n---\nx\n', encoding='utf-8')
    result = MarkdownQueryAdapter(str(tmp_path), 'sort=title').get_structure()
    assert [Path(r['path']).name for r in result['results']] == ['a.md', 'b.md']


def test_markdown_sort_does_not_swallow_a_bug(monkeypatch):
    from reveal.adapters.markdown import results
    monkeypatch.setattr(results, 'create_sort_key', _raise_bug)
    with pytest.raises(_InjectedBug):
        results.apply_sorting([{'title': 'a'}, {'title': 'b'}], 'title', False)


# ------------------------------------------------------------------ python

def test_check_bytecode_does_not_swallow_a_bug(tmp_path, monkeypatch):
    from reveal.adapters.python import bytecode
    (tmp_path / '__pycache__').mkdir()
    (tmp_path / '__pycache__' / 'm.cpython-312.pyc').write_bytes(b'')
    monkeypatch.setattr(bytecode, '_check_pyc_file', _raise_bug)
    with pytest.raises(_InjectedBug):
        bytecode.check_bytecode(str(tmp_path))


def test_check_bytecode_still_reports_an_unreadable_tree_as_an_error(tmp_path, monkeypatch):
    from reveal.adapters.python import bytecode

    def denied(_pyc):
        raise PermissionError('denied')

    (tmp_path / '__pycache__').mkdir()
    (tmp_path / '__pycache__' / 'm.cpython-312.pyc').write_bytes(b'')
    monkeypatch.setattr(bytecode, '_check_pyc_file', denied)
    result = bytecode.check_bytecode(str(tmp_path))
    assert result['status'] == 'error' and 'denied' in result['error']


def test_doctor_does_not_read_a_failed_bytecode_scan_as_clean(tmp_path, monkeypatch):
    from reveal.adapters.python import bytecode
    from reveal.adapters.python.doctor import run_doctor

    def denied(_pyc):
        raise PermissionError('denied')

    (tmp_path / '__pycache__').mkdir()
    (tmp_path / '__pycache__' / 'm.cpython-312.pyc').write_bytes(b'')
    monkeypatch.setattr(bytecode, '_check_pyc_file', denied)
    monkeypatch.chdir(tmp_path)
    report = run_doctor(lambda: {'active': True})
    assert 'stale_bytecode' in report.get('checks_failed', [])
    assert 'stale_bytecode' not in report['checks_performed']


def test_doctor_does_not_read_unreadable_site_packages_as_no_conflicts(monkeypatch):
    import site
    from reveal.adapters.python.doctor import find_editable_conflict, run_doctor

    def denied():
        raise PermissionError('denied')

    monkeypatch.setattr(site, 'getsitepackages', denied)
    report = run_doctor(lambda: {'active': True})
    assert 'editable_conflicts' in report.get('checks_failed', [])
    assert 'editable_conflicts' not in report['checks_performed']
    with pytest.raises(PermissionError):
        find_editable_conflict('anything')


def test_package_details_of_a_missing_package_still_says_not_found():
    from reveal.adapters.python.packages import get_package_details
    result = get_package_details('reveal-no-such-distribution-back1059')
    assert result['error'].startswith('Package not found')


def test_package_details_of_a_broken_metadata_read_does_not_claim_not_found(monkeypatch):
    import importlib.metadata
    from reveal.adapters.python.packages import get_package_details
    monkeypatch.setattr(importlib.metadata, 'distribution', _raise_bug)
    result = get_package_details('anything')
    assert 'error' in result
    assert 'not found' not in result['error'].lower()
    assert 'injected' in (result['error'] + result.get('details', ''))


# ------------------------------------------------------------------- stats

def _py_tree(tmp_path):
    (tmp_path / 'a.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    return tmp_path


def _warnings(result):
    return (result.get('meta') or {}).get('warnings') or []


def test_stats_discloses_files_whose_check_rules_could_not_run(tmp_path, monkeypatch):
    from reveal.adapters.stats.adapter import StatsAdapter
    from reveal.rules import RuleRegistry
    monkeypatch.setattr(RuleRegistry, 'check_file', staticmethod(_raise_bug))
    result = StatsAdapter(str(_py_tree(tmp_path))).get_structure()
    found = [w for w in _warnings(result) if w['type'] == 'check_rules_failed']
    assert len(found) == 1 and found[0]['count'] == 1
    assert 'a.py' in found[0]['message']
    assert result['summary']['total_files'] == 1  # the file's other statistics still count


def test_stats_without_a_rule_failure_carries_no_check_warning(tmp_path):
    from reveal.adapters.stats.adapter import StatsAdapter
    result = StatsAdapter(str(_py_tree(tmp_path))).get_structure()
    assert not [w for w in _warnings(result) if w['type'] == 'check_rules_failed']


def test_stats_logs_when_rule_config_cannot_be_resolved(tmp_path, monkeypatch, caplog):
    from reveal.adapters.stats import metrics
    from reveal.rules import RuleRegistry
    monkeypatch.setattr(RuleRegistry, 'get_configured_rule', staticmethod(_raise_bug))
    with caplog.at_level(logging.WARNING):
        assert metrics._get_check_thresholds(tmp_path / 'a.py') == (100, 4)
    assert 'injected' in caplog.text


# --------------------------------------------------------------------- ast

def test_ast_analysis_logs_when_import_resolution_fails_and_keeps_the_structure(
        tmp_path, monkeypatch, caplog):
    from reveal.adapters.ast import analysis
    (tmp_path / 'a.py').write_text('import os\n\n\ndef f():\n    return os.getcwd()\n',
                                   encoding='utf-8')
    monkeypatch.setattr(analysis, 'build_symbol_map', _raise_bug)
    with caplog.at_level(logging.WARNING):
        result = analysis.analyze_file(str(tmp_path / 'a.py'))
    assert result and 'f' in [e['name'] for e in result['elements']]
    assert 'injected' in caplog.text


def test_content_pattern_search_discloses_a_git_diff_that_exited_nonzero(tmp_path, monkeypatch):
    """BACK-1854: a failed `git diff` is empty stdout, which read as "pattern not found"."""
    from reveal.adapters.git import files
    path, _trees, _repo = _make_repo(tmp_path)
    repo = _reopen(path)
    head = repo[repo.head.target]
    files._reset_content_search_error()
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(
        a, 128, stdout='', stderr='fatal: bad object\n'))
    assert files._commit_diff_contains(repo, head, '', 'return') is False
    disclosure = files.get_content_search_disclosure()
    assert 'degraded' in disclosure and 'exited 128' in disclosure and 'bad object' in disclosure
    files._reset_content_search_error()
