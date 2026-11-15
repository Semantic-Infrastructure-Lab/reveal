"""BACK-2621 preservation pins and canonical Metrics vocabulary regressions.

TestPreservation pins the Step 1 inventory: answers, diagnostics and exits that the
vocabulary migration must not change. Comparisons drop only spelling-specific
diagnostics: ``retired_spelling`` notes and, where an input is deliberately unread, the
one unread-input warning, which names the spelling the caller typed (``unused_flag``
['--top'] on the subcommand, ``unused_query_param`` ['top'] on the URI).

Every test that cuts the per-file rows passes an explicit sort: the unsorted order is the
filesystem walk order, which differs between platforms (BACK-2652). The hotspot ranking
is cut freely because every fixture score is distinct.

``source`` echoes the caller's spelling of the target (BACK-1366): the subcommand gets the
native ``str(project)`` and the URI, API and MCP addresses ``project.as_posix()``, so
comparisons normalize ``source`` with ``to_posix``.
"""
import copy
import json
import subprocess

import pytest

from conftest import _run_reveal_direct as run
from reveal.api import query
from reveal.utils.path_utils import to_posix


def _branches(name, count):
    """A function of ``count`` sequential if-branches: cyclomatic complexity count + 1."""
    body = ''.join(f'    if v == {i}:\n        return {i}\n' for i in range(count))
    return f'def {name}(v):\n{body}    return -1\n'


FILES = {
    '.reveal.yaml': 'root: true\n',
    'pkg/a.py': ('def a1(x):\n    if x > 1:\n        return 1\n    for i in range(x):\n'
                 '        x += i\n    return x\n\n\ndef a2():\n    return 0\n'),
    'pkg/b.py': 'def b1(y):\n    return y + 1\n',
    'pkg/c.py': _branches('big', 25),
    'pkg/d.py': 'class C:\n    def m(self):\n        return 1\n\n\ndef d1():\n    pass\n',
    'pkg/e.py': _branches('big', 15),
    'pkg/f.py': _branches('big', 18),
    'pkg/g.py': _branches('big', 13),
    'tests/test_a.py': 'from pkg.a import a1\n\n\ndef test_a():\n    assert a1(0) == 0\n',
    'tests/test_big.py': _branches('test_big', 14),
    'data.json': '{"k": 1}\n',
    'config.yaml': 'a: 1\n',
    'notes.xyz': 'no analyzer reads this\n',
}
# Every file with a positive hotspot score, most severe first (each score is distinct).
HOTSPOTS = ['pkg/c.py', 'pkg/f.py', 'pkg/e.py', 'tests/test_big.py', 'pkg/g.py']
SPELLING_WARNINGS = ('retired_spelling',)
UNREAD_WARNINGS = ('unused_flag', 'unused_query_param')


def _write(root, files):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode('utf-8'))


@pytest.fixture
def project(tmp_path, monkeypatch):
    # A subdirectory with its own root marker: nothing from pytest's shared basetemp is scanned.
    root = tmp_path / 'proj'
    _write(root, FILES)
    monkeypatch.chdir(root)
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')
    return root


def _git(root, *args):
    subprocess.run(['git', '-c', 'user.email=t@example.invalid', '-c', 'user.name=t', '-C', str(root), *args],
                   check=True, capture_output=True, timeout=60)


@pytest.fixture
def git_project(project):
    pytest.importorskip('pygit2')
    _git(project, 'init', '-q')
    _git(project, 'add', '-A')
    _git(project, 'commit', '-qm', 'one')
    with (project / 'pkg' / 'c.py').open('a', encoding='utf-8') as handle:
        handle.write('# touched\n')
    _git(project, 'commit', '-qam', 'two')
    # One merge commit that touches pkg/e.py, so excluding merges changes a count.
    _git(project, 'checkout', '-q', '-b', 'side')
    with (project / 'pkg' / 'e.py').open('a', encoding='utf-8') as handle:
        handle.write('# side\n')
    _git(project, 'commit', '-qam', 'side')
    _git(project, 'checkout', '-q', '-')
    _git(project, 'merge', '-q', '--no-ff', 'side', '-m', 'merge')
    return project


@pytest.fixture
def many(tmp_path, monkeypatch):
    """Twelve hotspot files (distinct scores), more than the hotspot view's default cap of 10."""
    root = tmp_path / 'many'
    _write(root, {'.reveal.yaml': 'root: true\n',
                  **{f'm{n:02d}.py': _branches('big', n) for n in range(11, 23)}})
    monkeypatch.chdir(root)
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')
    return root


def uri(project, controls=''):
    base = f'metrics://{project.as_posix()}'
    return f'{base}?{controls}' if controls else base


def cli_json(*args):
    result = run(*args, '--format', 'json')
    try:
        answer = json.loads(result.stdout) if result.stdout.strip() else None
    except json.JSONDecodeError:
        answer = None
    if isinstance(answer, dict):
        answer.pop('execution', None)
    return result, answer


def _without(answer, types):
    result = copy.deepcopy(answer)
    if isinstance(result.get('source'), str):
        result['source'] = to_posix(result['source'])
    if isinstance(result.get('meta'), dict) and 'warnings' in result['meta']:
        result['meta']['warnings'] = [w for w in result['meta']['warnings'] if w.get('type') not in types]
        if result['meta'] == {'warnings': []}:  # a meta block that only carried a dropped note
            del result['meta']
    return result


def without_retirement(answer):
    return _without(answer, SPELLING_WARNINGS)


def assert_equal_answer(actual, expected):
    assert isinstance(actual, dict), f'no parsed answer: {actual!r}'
    assert without_retirement(actual) == without_retirement(expected), 'canonical answer differs'


def warnings_of(answer, *types):
    return [w for w in answer.get('meta', {}).get('warnings', []) if w.get('type') in types]


def notes(answer):
    return [w.get('message', '') for w in warnings_of(answer, 'retired_spelling')]


def unread(answer):
    return warnings_of(answer, *UNREAD_WARNINGS)


def file_rows(answer):
    return [f['file'] for f in answer.get('files') or []]


def hotspot_rows(answer):
    return [h['file'] for h in answer.get('hotspots') or []]


def assert_usage(result, answer, replacement):
    assert result.returncode == 2, f'expected usage exit 2, got {result.returncode}: {result.stderr[-300:]}'
    assert isinstance(answer, dict), f'usage rejection must retain parsed JSON: {result.stderr[-300:]}'
    assert replacement in answer['error'], f'error must name {replacement}: {answer["error"]}'
    assert replacement in result.stderr, f'stderr must name {replacement}: {result.stderr}'


def mcp_answer(address):
    """The MCP JSON answer, or the tool failure text (MCP has no exit code)."""
    from reveal.mcp_server import _ToolFailure, reveal_query
    result = reveal_query(address, provenance=True)
    if isinstance(result, _ToolFailure):
        return None, str(result)
    answer = json.loads(result)
    answer.pop('execution', None)  # provenance is requested only because this tool has no format argument
    return answer, None


class TestPreservation:
    def test_default_view_answer_and_diagnostics(self, project):
        expected = query(uri(project))
        assert expected['type'] == 'stats_summary'
        assert sorted(file_rows(expected)) == sorted(
            ['.reveal.yaml', 'config.yaml', 'data.json', 'pkg/a.py', 'pkg/b.py', 'pkg/c.py', 'pkg/d.py', 'pkg/e.py',
             'pkg/f.py', 'pkg/g.py', 'tests/test_a.py', 'tests/test_big.py'])
        assert expected['population'] == {'summary': 'filtered_analyzed_files', 'analyzed_files': 12,
                                          'filtered_files': 12, 'displayed_files': 12}
        assert expected['summary']['total_files'] == 12 and 'has_findings' not in expected['summary']
        assert 'hotspots' not in expected
        excluded = warnings_of(expected, 'unsupported_extensions')
        assert len(excluded) == 1 and excluded[0]['excluded_by_extension'] == {'.xyz': 1}
        for args in (('metrics', str(project)), (uri(project),)):
            result, answer = cli_json(*args)
            assert result.returncode == 0, result.stderr
            assert_equal_answer(answer, expected)
        answer, failure = mcp_answer(uri(project))
        assert failure is None
        assert_equal_answer(answer, expected)

    def test_provenance_view_answer(self, project):
        expected = query(uri(project, 'view=provenance'))
        assert expected['type'] == 'classify_report'
        assert expected['summary']['total'] == 12
        assert expected['summary']['by_provenance'] == {'first_party': 10, 'test': 2}
        assert expected['summary']['excluded_by_extension'] == {'.xyz': 1}
        for args in (('metrics', str(project), '--view', 'provenance'), (uri(project, 'view=provenance'),)):
            result, answer = cli_json(*args)
            assert result.returncode == 0, result.stderr
            assert_equal_answer(answer, expected)

    def test_provenance_view_warns_on_unread_uri_controls(self, project):
        result, answer = cli_json(uri(project, 'view=provenance&code_only=true&sort=-lines&limit=2'))
        assert result.returncode == 0
        assert answer['type'] == 'classify_report' and answer['summary']['total'] == 12
        fields = [field for warning in unread(answer) for field in warning.get('fields', [])]
        assert {'code_only', 'sort', 'limit'} <= set(fields), unread(answer)

    def test_legacy_hotspots_shape(self, project):
        expected = query(uri(project, 'hotspots=true'))
        assert expected['type'] == 'stats_summary'
        assert hotspot_rows(expected) == HOTSPOTS
        assert len(file_rows(expected)) == 12 and expected['summary']['has_findings'] is True
        assert not warnings_of(expected, 'truncated')
        for entry in expected['hotspots']:
            assert set(entry) >= {'file', 'hotspot_score', 'quality_score', 'issues', 'details', 'provenance'}
        assert [e['provenance'] for e in expected['hotspots']] == [None, None, None, 'test', None]
        for args in (('metrics', str(project), '--hotspots'), (uri(project, 'hotspots=true'),),
                     (uri(project), '--hotspots')):
            result, answer = cli_json(*args)
            assert result.returncode == 0, result.stderr
            assert_equal_answer(answer, expected)

    def test_legacy_hotspots_top_caps_hotspots_and_limit_pages_files(self, project):
        expected = query(uri(project, 'hotspots=true&top=2&limit=3&sort=file'))
        assert hotspot_rows(expected) == HOTSPOTS[:2]
        assert file_rows(expected) == ['.reveal.yaml', 'config.yaml', 'data.json']
        cuts = {w['field']: (w['shown'], w['total']) for w in warnings_of(expected, 'truncated')}
        assert cuts == {'files': (3, 12), 'hotspots': (2, 5)}
        assert expected['summary']['total_files'] == 12
        for args in (('metrics', str(project), '--hotspots', '--top', '2', '--limit', '3', '--sort', 'file'),
                     (uri(project, 'hotspots=true&top=2&limit=3&sort=file'),)):
            result, answer = cli_json(*args)
            assert result.returncode == 0, result.stderr
            assert_equal_answer(answer, expected)
        assert hotspot_rows(query(uri(project, 'hotspots=true&top=0'))) == HOTSPOTS

    @pytest.mark.parametrize('value', ['false', '0'])
    def test_false_hotspots_is_not_selected(self, project, value):
        expected = query(uri(project))
        result, answer = cli_json(uri(project, f'hotspots={value}'))
        assert result.returncode == 0, result.stderr
        assert_equal_answer(answer, expected)
        assert_equal_answer(query(uri(project, f'hotspots={value}')), expected)
        assert_equal_answer(query(uri(project), hotspots=False), expected)
        mcp, failure = mcp_answer(uri(project, f'hotspots={value}'))
        assert failure is None
        assert_equal_answer(mcp, expected)

    def test_filters_keep_the_analyzed_population(self, project):
        expected = query(uri(project, 'lines>=15&sort=file'))
        assert file_rows(expected) == ['pkg/c.py', 'pkg/e.py', 'pkg/f.py', 'pkg/g.py', 'tests/test_big.py']
        assert expected['population']['analyzed_files'] == 12
        assert expected['population']['filtered_files'] == 5
        assert expected['summary']['total_files'] == 5
        legacy = query(uri(project, 'min_lines=15&sort=file'))
        assert_equal_answer(legacy, expected)
        result, answer = cli_json('metrics', str(project), '--min-lines', '15', '--sort', 'file')
        assert result.returncode == 0
        assert_equal_answer(answer, expected)

    def test_caps_cut_the_answer_not_the_input(self, project):
        for controls in ('limit=2&sort=file', 'summary_only=true', 'hotspots=true&top=1'):
            answer = query(uri(project, controls))
            assert answer['population']['analyzed_files'] == 12, controls
            assert answer['summary']['total_files'] == 12, controls
        summary = query(uri(project, 'summary_only=true'))
        assert 'files' not in summary and summary['population']['displayed_files'] == 0

    def test_fail_on_findings_gates_only_the_hotspot_ranking(self, project):
        result, answer = cli_json('metrics', str(project), '--hotspots', '--fail-on', 'findings')
        assert result.returncode == 1 and answer['summary']['has_findings'] is True
        for args in (('metrics', str(project), '--fail-on', 'findings'),
                     (uri(project, 'hotspots=false'), '--fail-on', 'findings'),
                     (uri(project, 'view=provenance'), '--fail-on', 'findings')):
            result, answer = cli_json(*args)
            assert result.returncode == 2, args
            assert 'hotspots' in answer['error'] and '--fail-on' in answer['error']
        result, answer = cli_json('metrics', str(project / 'pkg' / 'b.py'), '--hotspots', '--fail-on', 'findings')
        assert result.returncode == 0 and answer['summary']['has_findings'] is False

    def test_uri_global_zero_limit_is_exact(self, project):
        expected = query(uri(project, 'sort=file'))
        for args in ((uri(project, 'sort=file'), '--limit', '0'), (uri(project, 'sort=file&limit=0'),),
                     ('metrics', str(project), '--sort', 'file', '--limit', '0')):
            result, answer = cli_json(*args)
            assert result.returncode == 0
            assert_equal_answer(answer, expected)
            assert len(file_rows(answer)) == 12 and not warnings_of(answer, 'truncated')

    def test_files_paging_and_sort(self, project):
        expected = query(uri(project, 'sort=-lines&limit=2&offset=1'))
        assert file_rows(expected) == ['pkg/f.py', 'pkg/e.py']
        assert expected['population']['displayed_files'] == 2
        past = query(uri(project, 'sort=file&offset=20&limit=2'))
        assert file_rows(past) == [] and past['summary']['total_files'] == 12
        unknown = query(uri(project, 'sort=bogus&limit=1'))
        assert [w['type'] for w in warnings_of(unknown, 'unknown_sort_field')] == ['unknown_sort_field']
        result, answer = cli_json('metrics', str(project), '--sort', '-lines', '--limit', '2', '--offset', '1')
        assert result.returncode == 0
        assert_equal_answer(answer, expected)

    @pytest.mark.parametrize('args,needle', [
        (('--min-lines', '2.5'), 'whole number'),
        (('--limit', 'abc'), 'whole number'),
        (('--min-complexity', 'abc'), 'number'),
        (('--view', 'other'), 'provenance'),
        (('--hotspots', '--tests', 'only'), "('include', 'exclude')"),
        (('--hotspots', '--tests', 'EXCLUDE'), "('include', 'exclude')"),
    ])
    def test_invalid_values_reject(self, project, args, needle):
        result, answer = cli_json('metrics', str(project), *args)
        assert result.returncode == 2, args
        assert needle in answer['error']

    def test_test_scope_narrows_only_the_ranking(self, project):
        answer = query(uri(project, 'hotspots=true&tests=exclude'))
        assert hotspot_rows(answer) == [f for f in HOTSPOTS if not f.startswith('tests/')]
        assert answer['test_scope']['files_excluded'] == 2 and answer['test_scope']['tests'] == 'exclude'
        assert answer['summary']['total_files'] == 12 and len(file_rows(answer)) == 12

    def test_scope_controls_reach_the_walk(self, project):
        _git(project, 'init', '-q')
        (project / '.gitignore').write_bytes(b'ignored.py\n')
        (project / 'ignored.py').write_bytes(b'def z():\n    return 1\n')
        assert query(uri(project))['summary']['total_files'] == 12
        included = query(uri(project, 'respect_gitignore=false'))
        assert included['summary']['total_files'] == 13
        for args in (('metrics', str(project), '--no-gitignore'), (uri(project), '--no-gitignore')):
            result, answer = cli_json(*args)
            assert result.returncode == 0
            assert_equal_answer(answer, included)
        for args in (('metrics', str(project), '--exclude', 'tests'), (uri(project), '--exclude', 'tests'),
                     ('metrics', str(project), '--view', 'provenance', '--exclude', 'tests')):
            result, answer = cli_json(*args)
            assert result.returncode == 0
            assert answer['summary'].get('total_files', answer['summary'].get('total')) == 10, args

    def test_global_verbose_stays_an_unused_flag(self, project):
        for args in (('metrics', str(project)), (uri(project),)):
            result, answer = cli_json(*args, '--verbose')
            assert result.returncode == 0
            assert [w.get('fields') for w in unread(answer)] == [['--verbose']]

    def test_unused_top_without_ranking_is_disclosed(self, project):
        result, answer = cli_json(uri(project, 'top=3'))
        assert result.returncode == 0 and 'hotspots' not in answer
        assert [w.get('fields') for w in unread(answer)] == [['top']]

    def test_existing_retirement_notes(self, project):
        for old, new, expected_controls in (('stats', 'metrics://', ''), ('classify', 'view=provenance', 'view=provenance')):
            address = f'{old}://{project.as_posix()}'
            result, answer = cli_json(address)
            assert result.returncode == 0
            assert any(f'{old}://' in m and new in m for m in notes(answer)), notes(answer)
            assert f'{old}:// is deprecated' in result.stderr
            assert_equal_answer(answer, query(uri(project, expected_controls)))
        result, answer = cli_json('hotspots', str(project))
        assert result.returncode == 0
        assert any('reveal hotspots' in m and 'reveal metrics' in m for m in notes(answer)), notes(answer)
        result, answer = cli_json(f'hotspots://{project.as_posix()}?files_only')
        assert result.returncode == 0
        assert any('files_only' in m for m in notes(answer)), notes(answer)

    def test_required_output_failure_beats_success_and_recovers(self, project):
        good, full = cli_json('metrics', str(project), '--sort', 'file', '--limit', '1')
        assert good.returncode == 0 and file_rows(full) == ['.reveal.yaml']
        failed, kept = cli_json('metrics', str(project), '--sort', 'file', '--limit', '1',
                                '--output', f'json={project.as_posix()}')
        assert failed.returncode == 3, failed.stderr
        assert file_rows(kept) == file_rows(full)
        recovered, answer = cli_json('metrics', str(project), '--sort', 'file', '--limit', '1')
        assert recovered.returncode == 0
        assert_equal_answer(answer, full)

    def test_edit_between_api_requests_is_seen(self, project):
        before = query(uri(project, 'sort=-lines&limit=1'))
        assert file_rows(before) == ['pkg/c.py']
        (project / 'pkg' / 'b.py').write_bytes(''.join(f'x{i} = {i}\n' for i in range(200)).encode('utf-8'))
        after = query(uri(project, 'sort=-lines&limit=1'))
        assert file_rows(after) == ['pkg/b.py']

    def test_churn_fields_on_and_off(self, git_project):
        on = query(uri(git_project, 'hotspots=true'))
        counts = {h['file']: h['details'].get('commit_count') for h in on['hotspots']}
        assert counts == {'pkg/c.py': 2, 'pkg/f.py': 1, 'pkg/e.py': 3, 'tests/test_big.py': 1, 'pkg/g.py': 1}
        off = query(uri(git_project, 'hotspots=true&churn=false'))
        assert hotspot_rows(off) == HOTSPOTS
        assert all('commit_count' not in h['details'] for h in off['hotspots'])
        late = query(uri(git_project, 'hotspots=true&since=2999-01-01'))
        assert {h['details']['commit_count'] for h in late['hotspots']} == {0}
        result, answer = cli_json('metrics', str(git_project), '--hotspots', '--no-churn')
        assert result.returncode == 0
        assert_equal_answer(answer, off)
        result, answer = cli_json('metrics', str(git_project), '--hotspots', '--since', '2999-01-01')
        assert result.returncode == 0
        assert_equal_answer(answer, late)
        no_merges = query(uri(git_project, 'hotspots=true&no_merges=true'))
        assert {h['file']: h['details']['commit_count'] for h in no_merges['hotspots']}['pkg/e.py'] == 2
        result, answer = cli_json('metrics', str(git_project), '--hotspots', '--no-merges')
        assert result.returncode == 0
        assert_equal_answer(answer, no_merges)

    def test_api_keywords_that_work_today(self, project):
        for keywords, controls in (({'hotspots': True}, 'hotspots=true'), ({'code_only': True}, 'code_only=true'),
                                   ({'min_lines': 15}, 'min_lines=15'), ({'summary_only': True}, 'summary_only=true')):
            assert_equal_answer(query(uri(project), **keywords), query(uri(project, controls)))

    def test_answer_and_usage_guards_detect_wrong_results(self, project):
        expected = query(uri(project, 'sort=file'))
        wrong = copy.deepcopy(expected)
        wrong['files'] = wrong['files'][:1]
        with pytest.raises(AssertionError, match='canonical answer differs'):
            assert_equal_answer(wrong, expected)
        noted = copy.deepcopy(expected)
        noted['meta']['warnings'].append({'type': 'retired_spelling', 'message': 'x is deprecated; use y.'})
        assert_equal_answer(noted, expected)
        native, posix = copy.deepcopy(expected), copy.deepcopy(expected)
        native['source'], posix['source'] = 'C:\\work\\proj', 'C:/work/proj'
        assert_equal_answer(native, posix)
        posix['source'] = 'C:/work/other'
        with pytest.raises(AssertionError, match='canonical answer differs'):
            assert_equal_answer(native, posix)
        bad, answer = cli_json(uri(project, 'view=other'))
        assert_usage(bad, answer, 'provenance')
        good, successful = cli_json(uri(project))
        with pytest.raises(AssertionError, match='expected usage exit 2'):
            assert_usage(good, successful, 'provenance')
