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

    def test_global_switches_reach_the_uri_form(self, project):
        """The main parser's --hotspots and --code-only on metrics:// answer as the URI keys do."""
        for flag, controls in (('--hotspots', 'hotspots=true'), ('--code-only', 'code_only=true')):
            result, answer = cli_json(uri(project), flag)
            assert result.returncode == 0, result.stderr
            assert not unread(answer), unread(answer)
            assert_equal_answer(answer, query(uri(project, controls)))
        assert query(uri(project, 'code_only=true'))['summary']['total_files'] == 10

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


def _first_note_with(answer, *needles):
    return [m for m in notes(answer) if all(n in m for n in needles)]


class TestProposedChanges:
    """Discriminating REDs, one group per Scott decision (BACK-2621 note #3) and folded bug B1-B8.

    The hotspot view keeps the legacy row field name ``hotspots`` for its ranked rows.
    """

    # -- Decision 1: --view hotspots; --limit caps it (default 10), top is its retired alias --------------

    @pytest.mark.parametrize('transport', ['cli', 'uri', 'api-uri', 'api-keyword', 'mcp'])
    def test_hotspot_view_rows_are_the_ranking(self, project, transport):
        legacy = query(uri(project, 'hotspots=true&top=0'))
        if transport == 'cli':
            result, answer = cli_json('metrics', str(project), '--view', 'hotspots')
            assert result.returncode == 0, result.stderr[-300:]
        elif transport == 'uri':
            result, answer = cli_json(uri(project, 'view=hotspots'))
            assert result.returncode == 0, result.stderr[-300:]
        elif transport == 'mcp':
            answer, failure = mcp_answer(uri(project, 'view=hotspots'))
            assert failure is None, failure
        else:
            answer = (query(uri(project, 'view=hotspots')) if transport == 'api-uri'
                      else query(uri(project), view='hotspots'))
        assert hotspot_rows(answer) == HOTSPOTS, answer.get('error') or answer.get('type')
        assert answer['summary'] == {**legacy['summary']}, 'the view keeps the summary block'
        assert not notes(answer), notes(answer)

    def test_hotspot_view_has_no_per_file_rows(self, project):
        result, answer = cli_json(uri(project, 'view=hotspots'))
        assert result.returncode == 0, result.stderr[-300:]
        assert 'files' not in answer, 'the ranked hotspot files are the rows of this view'

    def test_hotspot_view_default_cap_is_ten_and_disclosed(self, many):
        result, answer = cli_json('metrics', str(many), '--view', 'hotspots')
        assert result.returncode == 0, result.stderr[-300:]
        full = hotspot_rows(query(uri(many, 'hotspots=true&top=0')))
        assert len(full) == 12
        assert hotspot_rows(answer) == full[:10]
        cuts = [(w['field'], w['shown'], w['total']) for w in warnings_of(answer, 'truncated')]
        assert cuts == [('hotspots', 10, 12)], cuts

    @pytest.mark.parametrize('controls,slice_', [('limit=0', slice(None)), ('limit=3', slice(0, 3)),
                                                 ('limit=3&offset=2', slice(2, 5))])
    def test_limit_and_offset_page_the_hotspot_view(self, many, controls, slice_):
        full = hotspot_rows(query(uri(many, 'hotspots=true&top=0')))
        flags = [arg for part in controls.split('&') for arg in ('--' + part.split('=')[0], part.split('=')[1])]
        expected = query(uri(many, f'view=hotspots&{controls}'))
        assert hotspot_rows(expected) == full[slice_]
        assert expected['summary']['total_files'] == 12, 'totals stay those of the filtered population'
        result, answer = cli_json('metrics', str(many), '--view', 'hotspots', *flags)
        assert result.returncode == 0, result.stderr[-300:]
        assert_equal_answer(answer, expected)
        keywords = {k: int(v) for k, v in (part.split('=') for part in controls.split('&'))}
        assert_equal_answer(query(uri(many), view='hotspots', **keywords), expected)
        mcp, failure = mcp_answer(uri(many, f'view=hotspots&{controls}'))
        assert failure is None, failure
        assert_equal_answer(mcp, expected)

    @pytest.mark.parametrize('transport', ['cli', 'uri', 'api-keyword'])
    def test_top_is_the_retired_alias_of_limit_in_the_hotspot_view(self, many, transport):
        expected = query(uri(many, 'view=hotspots&limit=2'))
        assert len(hotspot_rows(expected)) == 2
        if transport == 'cli':
            result, answer = cli_json('metrics', str(many), '--view', 'hotspots', '--top', '2')
            assert result.returncode == 0, result.stderr[-300:]
            assert 'deprecated' in result.stderr
        elif transport == 'uri':
            result, answer = cli_json(uri(many, 'view=hotspots&top=2'))
            assert result.returncode == 0, result.stderr[-300:]
        else:
            answer = query(uri(many), view='hotspots', top=2)
        assert_equal_answer(answer, expected)
        assert _first_note_with(answer, 'top', 'limit'), notes(answer)

    def test_top_and_limit_conflict_or_agree(self, many):
        result, answer = cli_json(uri(many, 'view=hotspots&top=2&limit=3'))
        assert_usage(result, answer, 'limit')
        result, answer = cli_json(uri(many, 'view=hotspots&top=2&limit=2'))
        assert result.returncode == 0, result.stderr[-300:]
        assert_equal_answer(answer, query(uri(many, 'view=hotspots&limit=2')))

    def test_hotspot_view_carries_the_findings_gate(self, project):
        for args in (('metrics', str(project), '--view', 'hotspots'), (uri(project, 'view=hotspots'),)):
            result, answer = cli_json(*args, '--fail-on', 'findings')
            assert result.returncode == 1, f'{args}: {result.returncode} {result.stderr[-200:]}'
            assert answer['summary']['has_findings'] is True

    def test_hotspot_view_test_scope(self, project):
        answer = query(uri(project, 'view=hotspots&tests=exclude'))
        assert hotspot_rows(answer) == [f for f in HOTSPOTS if not f.startswith('tests/')]
        assert answer['test_scope']['files_excluded'] == 2

    # -- Decision 2 and B6: legacy --hotspots notes; conflicts exit 2 --------------------------------------

    @pytest.mark.parametrize('args', [('--hotspots',), ()])
    def test_legacy_hotspots_names_the_view(self, project, args):
        expected = query(uri(project, 'hotspots=true'))
        address = ('metrics', str(project), *args) if args else (uri(project, 'hotspots=true'),)
        result, answer = cli_json(*address)
        assert result.returncode == 0, result.stderr[-300:]
        assert_equal_answer(answer, expected)
        assert _first_note_with(answer, 'hotspots', 'view'), notes(answer)
        assert 'deprecated' in result.stderr

    def test_equal_view_and_legacy_flag_are_accepted_once(self, project):
        expected = query(uri(project, 'view=hotspots'))
        result, answer = cli_json('metrics', str(project), '--view', 'hotspots', '--hotspots')
        assert result.returncode == 0, result.stderr[-300:]
        assert_equal_answer(answer, expected)
        assert not unread(answer), unread(answer)

    @pytest.mark.parametrize('args', [
        ('URI', 'hotspots=false', '--hotspots'),
        ('CLI', '--view', 'provenance', '--hotspots'),
        ('URI', 'view=provenance&hotspots=true'),
    ])
    def test_conflicting_hotspot_requests_reject(self, project, args):
        """B6: today the URI false wins silently and provenance drops the ranking."""
        if args[0] == 'URI':
            result, answer = cli_json(uri(project, args[1]), *args[2:])
        else:
            result, answer = cli_json('metrics', str(project), *args[1:])
        assert_usage(result, answer, 'hotspots')
        if args == ('URI', 'view=provenance&hotspots=true'):
            mcp, failure = mcp_answer(uri(project, args[1]))
            assert mcp is None and 'hotspots' in failure, f'MCP must reject: {mcp and mcp.get("type")}'
            with pytest.raises(ValueError, match='hotspots'):
                query(uri(project, args[1]))

    # -- Decision 3 and B1: declared repeatable where -----------------------------------------------------

    @pytest.mark.parametrize('transport', ['cli', 'uri-where', 'api-uri-where', 'api-keyword', 'api-list', 'mcp'])
    def test_where_is_declared_on_every_transport(self, project, transport):
        expected = query(uri(project, 'lines>=15&sort=file'))
        assert file_rows(expected) == ['pkg/c.py', 'pkg/e.py', 'pkg/f.py', 'pkg/g.py', 'tests/test_big.py']
        if transport == 'cli':
            result, answer = cli_json('metrics', str(project), '--where', 'lines>=15', '--sort', 'file')
            assert result.returncode == 0, result.stderr[-300:]
        elif transport == 'uri-where':
            result, answer = cli_json(uri(project, 'where=lines>=15&sort=file'))
            assert result.returncode == 0, result.stderr[-300:]
        elif transport == 'api-uri-where':
            answer = query(uri(project, 'where=lines>=15&sort=file'))
        elif transport == 'mcp':
            answer, failure = mcp_answer(uri(project, 'where=lines>=15&sort=file'))
            assert failure is None, failure
        else:
            answer = query(uri(project, 'sort=file'), where='lines>=15' if transport == 'api-keyword' else ['lines>=15'])
        assert file_rows(answer) == file_rows(expected), 'B1: where must filter, not match nothing'
        assert_equal_answer(answer, expected)
        assert not warnings_of(answer, 'unknown_query_param', 'unknown_filter_field')

    def test_repeated_where_is_anded(self, project):
        expected = query(uri(project, 'lines>=15&complexity<20&sort=file'))
        assert file_rows(expected) == ['pkg/e.py', 'pkg/f.py', 'pkg/g.py', 'tests/test_big.py']
        result, answer = cli_json('metrics', str(project), '--where', 'lines>=15', '--where', 'complexity<20',
                                  '--sort', 'file')
        assert result.returncode == 0, result.stderr[-300:]
        assert_equal_answer(answer, expected)
        assert_equal_answer(query(uri(project, 'where=lines>=15&where=complexity<20&sort=file')), expected)

    def test_avg_complexity_is_the_file_average(self, project):
        expected = query(uri(project, 'complexity>15&sort=file'))
        assert file_rows(expected) == ['pkg/c.py', 'pkg/e.py', 'pkg/f.py']
        answer = query(uri(project, 'avg_complexity>15&sort=file'))
        assert not warnings_of(answer, 'unknown_filter_field'), warnings_of(answer, 'unknown_filter_field')
        assert_equal_answer(answer, expected)

    @pytest.mark.parametrize('transport', ['cli', 'uri', 'api-keyword'])
    @pytest.mark.parametrize('legacy,value,canonical', [
        ('min_lines', 15, 'lines>='), ('max_lines', 10, 'lines<='), ('min_functions', 2, 'functions>='),
        ('min_complexity', 15, 'avg_complexity>='), ('max_complexity', 15, 'avg_complexity<='),
    ])
    def test_legacy_thresholds_are_where_codecs(self, project, transport, legacy, value, canonical):
        expected = query(uri(project, f'where={canonical}{value}&sort=file'))
        assert_equal_answer(expected, query(uri(project, f'{legacy}={value}&sort=file')))
        if transport == 'cli':
            result, answer = cli_json('metrics', str(project), '--' + legacy.replace('_', '-'), str(value),
                                      '--sort', 'file')
            assert result.returncode == 0, result.stderr[-300:]
        elif transport == 'uri':
            result, answer = cli_json(uri(project, f'{legacy}={value}&sort=file'))
            assert result.returncode == 0, result.stderr[-300:]
        else:
            answer = query(uri(project, 'sort=file'), **{legacy: value})
        assert_equal_answer(answer, expected)
        assert _first_note_with(answer, legacy, canonical), notes(answer)
        assert not _first_note_with(answer, 'max_complexity<'), 'never translate to the highest-function field'

    # -- Decision 4: --churn off and merges on/off ---------------------------------------------------------

    @pytest.mark.parametrize('transport', ['cli', 'uri-off', 'api-off', 'api-false'])
    def test_churn_off_is_the_switch(self, git_project, transport):
        expected = query(uri(git_project, 'hotspots=true&churn=false'))
        assert all('commit_count' not in h['details'] for h in expected['hotspots'])
        if transport == 'cli':
            result, answer = cli_json('metrics', str(git_project), '--hotspots', '--churn', 'off')
            assert result.returncode == 0, result.stderr[-300:]
        elif transport.startswith('uri'):
            result, answer = cli_json(uri(git_project, f'hotspots=true&churn={transport[4:]}'))
            assert result.returncode == 0, result.stderr[-300:]
        else:
            answer = query(uri(git_project, 'hotspots=true'), churn='off' if transport == 'api-off' else False)
        assert_equal_answer(answer, expected)
        assert not _first_note_with(answer, 'churn'), notes(answer)

    def test_no_churn_names_churn_off(self, git_project):
        result, answer = cli_json('metrics', str(git_project), '--hotspots', '--no-churn')
        assert result.returncode == 0
        assert _first_note_with(answer, 'no-churn', 'churn off'), notes(answer)

    @pytest.mark.parametrize('transport', ['cli', 'uri', 'api'])
    def test_merges_off_excludes_merge_commits(self, git_project, transport):
        expected = query(uri(git_project, 'hotspots=true&no_merges=true'))
        assert {h['file']: h['details']['commit_count'] for h in expected['hotspots']}['pkg/e.py'] == 2
        if transport == 'cli':
            result, answer = cli_json('metrics', str(git_project), '--hotspots', '--merges', 'off')
            assert result.returncode == 0, result.stderr[-300:]
        elif transport == 'uri':
            result, answer = cli_json(uri(git_project, 'hotspots=true&merges=off'))
            assert result.returncode == 0, result.stderr[-300:]
        else:
            answer = query(uri(git_project, 'hotspots=true'), merges='off')
        assert_equal_answer(answer, expected)
        assert not warnings_of(answer, 'unknown_query_param')
        on = query(uri(git_project, 'hotspots=true&merges=on'))
        assert {h['file']: h['details']['commit_count'] for h in on['hotspots']}['pkg/e.py'] == 3

    def test_no_merges_names_merges_and_conflicts_reject(self, git_project):
        answer = query(uri(git_project, 'hotspots=true&no_merges=true'))
        assert _first_note_with(answer, 'no_merges', 'merges'), notes(answer)
        result, answer = cli_json(uri(git_project, 'hotspots=true&merges=on&no_merges=true'))
        assert_usage(result, answer, 'merges')

    # -- Decision 5: --detail normal|summary ---------------------------------------------------------------

    @pytest.mark.parametrize('transport', ['cli', 'uri', 'api'])
    def test_detail_summary_replaces_summary_only(self, project, transport):
        expected = query(uri(project, 'summary_only=true'))
        assert 'files' not in expected
        if transport == 'cli':
            result, answer = cli_json('metrics', str(project), '--detail', 'summary')
            assert result.returncode == 0, result.stderr[-300:]
        elif transport == 'uri':
            result, answer = cli_json(uri(project, 'detail=summary'))
            assert result.returncode == 0, result.stderr[-300:]
        else:
            answer = query(uri(project), detail='summary')
        assert_equal_answer(answer, expected)
        assert not notes(answer), notes(answer)

    def test_detail_normal_is_the_default_and_summary_only_names_detail(self, project):
        result, answer = cli_json(uri(project, 'detail=normal'))
        assert result.returncode == 0, result.stderr[-300:]
        assert_equal_answer(answer, query(uri(project)))
        result, answer = cli_json('metrics', str(project), '--summary-only')
        assert result.returncode == 0
        assert _first_note_with(answer, 'summary', 'detail'), notes(answer)

    @pytest.mark.parametrize('args', [('--detail', 'full'), ('URI', 'detail=full')])
    def test_detail_full_rejects_naming_the_levels(self, project, args):
        if args[0] == 'URI':
            result, answer = cli_json(uri(project, args[1]))
        else:
            result, answer = cli_json('metrics', str(project), *args)
        assert_usage(result, answer, 'summary')
        assert 'normal' in answer['error']

    # -- Decision 6 and B5: since validated; churn disclosure in meta and text -----------------------------

    @pytest.mark.parametrize('transport', ['cli', 'uri', 'api'])
    def test_invalid_since_rejects(self, git_project, transport):
        if transport == 'api':
            with pytest.raises(ValueError, match='since'):
                query(uri(git_project, 'hotspots=true&since=notadate'))
            return
        args = (('metrics', str(git_project), '--hotspots', '--since', 'notadate') if transport == 'cli'
                else (uri(git_project, 'hotspots=true&since=notadate'),))
        result, answer = cli_json(*args)
        assert_usage(result, answer, 'since')

    def test_churn_unavailable_is_disclosed_in_meta_and_text(self, git_project, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, 'pygit2', None)  # import fails: the churn signal is unavailable
        result, answer = cli_json('metrics', str(git_project), '--hotspots')
        assert result.returncode == 0
        disclosed = warnings_of(answer, 'churn_unavailable')
        assert len(disclosed) == 1, f"meta.warnings {[w['type'] for w in answer['meta']['warnings']]}"
        assert 'warnings' not in answer, 'the disclosure lives in the envelope only'
        text = run('metrics', str(git_project), '--hotspots')
        assert 'churn scoring unavailable' in text.stdout + text.stderr

    # -- Decision 7, B2-B4: typed API, direct construction, disclosure, unsupported controls ---------------

    @pytest.mark.parametrize('base,keywords,controls', [
        ('sort=file', {'limit': 2}, 'sort=file&limit=2'),
        ('sort=file&limit=1', {'limit': 2}, 'sort=file&limit=2'),
        ('sort=file', {'offset': 3}, 'sort=file&offset=3'),
        ('sort=file&limit=2', {'sort': '-lines'}, 'sort=-lines&limit=2'),
        ('', {'view': 'provenance'}, 'view=provenance'),
        ('hotspots=true', {'tests': 'exclude'}, 'hotspots=true&tests=exclude'),
        ('hotspots=true', {'top': 2}, 'hotspots=true&top=2'),
        ('min_lines=1&sort=file', {'min_lines': 15}, 'min_lines=15&sort=file'),
    ])
    def test_typed_api_keyword_answers_like_its_uri_spelling(self, project, base, keywords, controls):
        """B2: every declared keyword reaches the answer, and an explicit keyword beats the URI value."""
        expected = query(uri(project, controls))
        assert without_retirement(expected) != without_retirement(query(uri(project, base))), \
            'fixture must make the control observable'
        assert_equal_answer(query(uri(project, base), **keywords), expected)

    def test_retired_stats_spelling_binds_typed_keywords_too(self, project):
        """stats:// is metrics' retired spelling and answers the same, typed keywords included."""
        expected = query(uri(project, 'hotspots=true&top=2&sort=file&limit=3'))
        answer = query(f'stats://{project.as_posix()}', hotspots=True, top=2, sort='file', limit=3)
        assert hotspot_rows(answer) == HOTSPOTS[:2] and file_rows(answer) == file_rows(expected)
        assert_equal_answer(answer, expected)

    @pytest.mark.parametrize('keywords,name', [
        ({'limit': -1}, 'limit'), ({'offset': -1}, 'offset'), ({'min_lines': 'abc'}, 'min_lines'),
        ({'view': 'other'}, 'view'), ({'tests': 'only'}, 'tests'), ({'detail': 'full'}, 'detail'),
        ({'bogus': 1}, 'bogus'),
    ])
    def test_typed_api_invalid_or_unknown_keyword_rejects(self, project, keywords, name):
        with pytest.raises((TypeError, ValueError), match=name):
            query(uri(project), **keywords)

    @pytest.mark.parametrize('controls,name', [
        ('hotspots=true&top=-1', 'top'), ('hotspots=true&top=2.5', 'top'), ('hotspots=true&top=abc', 'top'),
        ('hotspots=maybe', 'hotspots'), ('summary_only=maybe', 'summary_only'), ('tests=bad', 'tests'),
        ('min_lines=abc', 'min_lines'),
    ])
    def test_api_uri_string_validates_like_the_cli(self, project, controls, name):
        """B3: the CLI exits 2 on each of these; the API URI string must reject, not answer."""
        result, _ = cli_json(uri(project, controls))
        assert result.returncode == 2
        with pytest.raises(ValueError, match=name):
            query(uri(project, controls))

    def test_direct_construction_binds_declared_controls(self, project):
        """The hotspots and review compositions construct the adapter directly: it binds the same declarations."""
        from reveal.adapters.stats import MetricsAdapter
        with pytest.raises(ValueError, match='top'):
            MetricsAdapter(str(project), 'hotspots=true&top=-1')
        assert hotspot_rows(MetricsAdapter(str(project), 'view=hotspots&limit=2').get_structure()) == HOTSPOTS[:2]
        with pytest.raises(TypeError):
            MetricsAdapter(str(project)).get_structure(hotspots=True)

    @pytest.mark.parametrize('flags,field', [(('--code-only',), '--code-only'), (('--min-lines', '5'), 'min-lines'),
                                             (('--detail', 'summary'), '--detail')])
    def test_subcommand_discloses_controls_the_provenance_view_does_not_read(self, project, flags, field):
        """B4: the URI form warns; the subcommand must too."""
        result, answer = cli_json('metrics', str(project), '--view', 'provenance', *flags)
        assert result.returncode == 0, result.stderr[-300:]
        fields = [f for warning in unread(answer) for f in warning.get('fields', [])]
        assert any(field in f for f in fields), f'{flags} unread but undisclosed: {unread(answer)}'

    @pytest.mark.parametrize('control', ['match', 'kind', 'depth', 'until'])
    def test_unsupported_shared_controls_reject(self, project, control):
        result, answer = cli_json(uri(project, f'{control}=1'))
        assert result.returncode == 2, f'{control} is not a Metrics control and must exit 2, got {result.returncode}'
        assert control in answer['error'] and 'where' in answer['error'], answer['error']
        result, answer = cli_json('metrics', str(project), f'--{control}', '1')
        assert_usage(result, answer, control)
        with pytest.raises((TypeError, ValueError), match=control):
            query(uri(project), **{control: '1'})

    # -- Decision 8, B7 and B8 ------------------------------------------------------------------------------

    @pytest.mark.parametrize('args', [('--limit', '-1'), ('--offset', '-1'), ('--hotspots', '--top', '-1')])
    def test_negative_values_say_at_least_zero(self, project, args):
        result, answer = cli_json('metrics', str(project), *args)
        assert result.returncode == 2
        assert '>= 0' in answer['error'], answer['error']

    @pytest.mark.parametrize('target', ['.', 'pkg/a.py'])
    def test_path_read_with_hotspots_teaches_the_view(self, project, target):
        result = run(str(project / target), '--hotspots')
        assert result.returncode == 2, f'usage error must exit 2, got {result.returncode}'
        assert 'reveal metrics' in result.stderr and '--view hotspots' in result.stderr, result.stderr
