"""BACK-2620 preservation pins and canonical Imports vocabulary regressions.

TestPreservation pins the Step 1 inventory: answers, diagnostics and exits that the
vocabulary migration must not change. Comparisons drop only spelling-specific
diagnostics: ``retired_spelling`` notes (as BACK-2619 does) and, where an input is
deliberately unread, the one unread-input warning, which names the spelling the
caller typed (``unused_flag`` ['--top'] on the subcommand, ``unused_query_param``
['top'] on the URI); each test asserts that warning separately.
"""
import copy
import json
import subprocess

import pytest

from conftest import _run_reveal_direct as run
from reveal.api import query


FILES = {
    '.reveal.yaml': 'root: true\n',
    'pkg/__init__.py': '',
    'pkg/a.py': 'from pkg import b\nfrom pkg import c\nimport os\n\n\ndef fa():\n    return b.fb()\n',
    'pkg/b.py': 'from pkg import a\nimport json\n\n\ndef fb():\n    return 1\n',
    'pkg/c.py': 'import requests\n\n\ndef fc():\n    from pkg import a\n    return a\n',
    'pkg/d.py': 'def fd():\n    return 2\n',
    'tests/test_a.py': 'from pkg import a\n',
    'main.py': 'from pkg import a\nfrom pkg import d\n',
}
# The full fan-in ranking of FILES: (file, fan_in), most imported first.
RANKING = [('pkg/__init__.py', 5), ('pkg/a.py', 4), ('pkg/b.py', 1), ('pkg/c.py', 1), ('pkg/d.py', 1),
           ('main.py', 0), ('tests/test_a.py', 0)]
SPELLING_WARNINGS = ('retired_spelling',)
UNREAD_WARNINGS = ('unused_flag', 'unused_query_param')


@pytest.fixture
def project(tmp_path, monkeypatch):
    # A subdirectory with its own root marker: nothing from pytest's shared basetemp is scanned.
    root = tmp_path / 'proj'
    for rel, text in FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    monkeypatch.chdir(root)
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')
    return root


def uri(project, controls='', sub=''):
    base = f'imports://{(project / sub if sub else project).as_posix()}'
    return f'{base}?{controls}' if controls else base


def cli_json(*args):
    result = run(*args, '--format', 'json')
    return result, json.loads(result.stdout) if result.stdout.strip() else None


def _without(answer, types):
    result = copy.deepcopy(answer)
    # Imports keeps the additive-stage `metadata` alias of `meta`; JSON makes it a second copy.
    for key in ('meta', 'metadata'):
        if isinstance(result.get(key), dict) and 'warnings' in result[key]:
            result[key]['warnings'] = [w for w in result[key]['warnings'] if w.get('type') not in types]
    return result


def without_retirement(answer):
    """Only spelling-specific retirement warnings may differ across aliases."""
    return _without(answer, SPELLING_WARNINGS)


def assert_equal_answer(actual, expected):
    assert without_retirement(actual) == without_retirement(expected), 'canonical answer differs'


def unread(answer):
    return [w for w in answer['meta']['warnings'] if w.get('type') in UNREAD_WARNINGS]


def ranking(answer):
    return [(e['file'], e['fan_in']) for e in answer['entries']]


def assert_usage(result, answer, replacement):
    assert result.returncode == 2, f'expected usage exit 2, got {result.returncode}'
    assert isinstance(answer, dict), 'usage rejection must retain parsed JSON'
    assert replacement in answer['error'], f'error must name {replacement}: {answer["error"]}'
    assert replacement in result.stderr, f'stderr must name {replacement}: {result.stderr}'


def mcp_json(address):
    from reveal.mcp_server import _ToolFailure, reveal_query
    result = reveal_query(address, provenance=True)
    assert not isinstance(result, _ToolFailure), f'MCP unexpectedly failed: {result}'
    answer = json.loads(result)
    # Provenance is requested only because this tool has no JSON-format argument.
    answer.pop('execution', None)
    return answer


class TestPreservation:
    @pytest.mark.parametrize('cap', [0, 1, 3])
    def test_rank_population_and_legacy_cap(self, project, cap):
        full = query(uri(project, 'rank=fan-in'))
        assert full['type'] == 'fan_in_ranking' and ranking(full) == RANKING and full['total'] == 7
        expected = query(uri(project, f'rank=fan-in&top={cap}'))
        assert expected['entries'] == (full['entries'] if cap == 0 else full['entries'][:cap])
        assert expected['total'] == 7
        cuts = [w for w in expected['meta']['warnings'] if w['type'] == 'truncated']
        if cap == 0:
            assert cuts == []
        else:
            assert len(cuts) == 1
            assert {k: cuts[0][k] for k in ('field', 'shown', 'total', 'exact', 'cause')} == {
                'field': 'entries', 'shown': cap, 'total': 7, 'exact': True, 'cause': 'limit'}
        for spelling in ('--top', '--limit'):
            result, answer = cli_json('imports', str(project), '--rank', 'fan-in', spelling, str(cap))
            assert result.returncode == 0, result.stderr
            assert_equal_answer(answer, expected)
        result, answer = cli_json(uri(project, f'rank=fan-in&top={cap}'))
        assert result.returncode == 0, result.stderr
        assert_equal_answer(answer, expected)

    def test_row_cap_is_not_an_input_budget(self, project):
        result, cut = cli_json('imports', str(project), '--rank', 'fan-in', '--top', '1')
        assert result.returncode == 0
        assert cut['total'] == 7 and cut['meta']['errors'] == []
        assert cut['meta']['scan_budget']['capped'] is False
        assert not [w for w in cut['meta']['warnings'] if w['type'] in ('scan_capped', 'analysis_incomplete')]

    @pytest.mark.parametrize('value,needle', [('-1', '>= 0'), ('abc', 'whole number'), ('2.5', 'whole number')])
    def test_invalid_row_cap_rejects_with_json(self, project, value, needle):
        for result, answer in (cli_json('imports', str(project), '--rank', 'fan-in', '--top', value),
                               cli_json(uri(project, f'rank=fan-in&top={value}'))):
            assert result.returncode == 2, result.stderr
            assert needle in answer['error']

    @pytest.mark.parametrize('view', ['entrypoints', 'importers', 'components'])
    def test_row_cap_on_unranked_views_is_unread_with_one_diagnostic(self, project, view):
        base = query(uri(project, view))
        result, typed = cli_json('imports', str(project), f'--{view}', '--top', '1')
        assert result.returncode == 0
        assert [w['fields'] for w in unread(typed)] in (
            [['--top']], [['--limit']]), f'one unread warning naming the typed flag: {unread(typed)}'
        assert _without(typed, SPELLING_WARNINGS + UNREAD_WARNINGS) == _without(base, SPELLING_WARNINGS)
        result, spelled = cli_json(uri(project, f'{view}&top=1'))
        assert result.returncode == 0
        assert [w['fields'] for w in unread(spelled)] in ([['top']], [['limit']]), unread(spelled)
        assert _without(spelled, SPELLING_WARNINGS + UNREAD_WARNINGS) == _without(base, SPELLING_WARNINGS)

    def test_scan_budget_cut_is_incomplete_exit_three(self, project):
        typed_result, typed = cli_json('imports', str(project), '--rank', 'fan-in', '--max-files', '3')
        uri_result, spelled = cli_json(uri(project, 'rank=fan-in&max_files=3'))
        for result, answer in ((typed_result, typed), (uri_result, spelled)):
            assert result.returncode == 3, result.stderr
            assert answer['meta']['scan_budget'] == {
                'scope': 'scan', 'limit': 3, 'total': 4, 'returned': 3, 'exact': False, 'capped': True}
            capped = [w for w in answer['meta']['warnings'] if w['type'] == 'scan_capped']
            assert len(capped) == 1 and capped[0]['limit'] == 3
            assert len(answer['entries']) == 6
        assert_equal_answer(typed, spelled)

    @pytest.mark.parametrize('value', ['0', '-1'])
    def test_scan_budget_zero_and_negative_reject(self, project, value):
        for result, answer in (cli_json('imports', str(project), '--rank', 'fan-in', '--max-files', value),
                               cli_json(uri(project, f'rank=fan-in&max_files={value}'))):
            assert result.returncode == 2, result.stderr
            assert '>= 1' in answer['error']

    def test_scan_budget_requests_do_not_share_answers(self, project):
        counts = [len(query(uri(project, 'rank=fan-in' + q))['entries'])
                  for q in ('&max_files=3', '', '&max_files=3', '')]
        assert counts == [6, 7, 6, 7]

    @pytest.mark.parametrize('view', ['circular', 'unused', 'external', 'importers', 'violations'])
    def test_verbose_marks_json_and_changes_nothing_else(self, project, view):
        plain = query(uri(project, view))
        expanded = query(uri(project, f'{view}&verbose'))
        assert 'verbose' not in plain and expanded.pop('verbose') is True
        assert_equal_answer(expanded, plain)
        expected = query(uri(project, f'{view}&verbose'))
        for args in (('imports', str(project), f'--{view}', '--verbose'), (uri(project, view), '--verbose')):
            result, answer = cli_json(*args)
            assert result.returncode == 0, result.stderr
            assert_equal_answer(answer, expected)
        result, answer = cli_json(uri(project, f'{view}&verbose=false'))
        assert result.returncode == 0 and 'verbose' not in answer

    def test_verbose_expands_text_and_is_unread_on_rank(self, project):
        plain = run(uri(project, 'circular'))
        expanded = run(uri(project, 'circular&verbose'))
        assert plain.returncode == expanded.returncode == 0
        # Cycle members print relative to the group's directory.
        assert 'cycle: a.py → b.py → a.py' not in plain.stdout
        assert 'cycle: a.py → b.py → a.py' in expanded.stdout
        result, answer = cli_json(uri(project, 'rank=fan-in&verbose'))
        assert result.returncode == 0 and 'verbose' not in answer
        assert [w['fields'] for w in unread(answer)] == [['verbose']]

    def test_lazy_tests_scope_and_root_keep_their_answers(self, project):
        assert query(uri(project, 'circular'))['cycles'] == [['pkg/a.py', 'pkg/b.py']]
        assert query(uri(project, 'circular&lazy=include'))['cycles'] == [['pkg/a.py', 'pkg/b.py', 'pkg/c.py']]
        assert dict(ranking(query(uri(project, 'rank=fan-in&tests=exclude'))))['pkg/a.py'] == 3
        rooted = query(uri(project, 'rank=fan-in', sub='pkg'))
        scoped = query(uri(project, 'rank=fan-in&scope=path', sub='pkg'))
        assert dict(ranking(rooted))['a.py'] == 4 and dict(ranking(scoped))['a.py'] == 0
        result, refused = cli_json(uri(project, 'rank=fan-in&root=/'))
        assert result.returncode == 0
        # Decision 7 (D5): the legacy rank spelling keeps its answer and adds its one retirement note.
        assert [w['type'] for w in without_retirement(refused)['meta']['warnings']] == ['root_rejected']
        assert [w['field'] for w in refused['meta']['warnings'] if w['type'] in SPELLING_WARNINGS] in (
            [], ['param:imports.rank'])
        assert ranking(refused) == RANKING

    @pytest.mark.parametrize('controls,needle', [
        ('lazy=bogus', "('include', 'exclude', 'only')"), ('lazy', 'valid string'),
        ('tests=only', "('include', 'exclude')"), ('scope=bogus', "('root', 'path')"), ('scope', 'valid string'),
        ('root', 'valid string'), ('rank=callers', "('fan-in',)"), ('rank', 'valid string'),
        ('unused=banana', 'valid boolean'), ('format=yaml', "('text', 'json', 'dot')"),
    ])
    def test_invalid_request_values_reject_with_json(self, project, controls, needle):
        result, answer = cli_json(uri(project, f'rank=fan-in&{controls}' if 'rank' not in controls else controls))
        assert result.returncode == 2, result.stderr
        assert needle in answer['error']

    def test_importers_targets_and_no_match_exit_two(self, project):
        named = query(uri(project, 'importers=pkg/b.py'))
        assert named['type'] == 'module_importers'
        assert [(r['file'], r['line']) for r in named['importers']] == [('pkg/a.py', 1)]
        # A file target spells its importers relative to the requested file's directory.
        on_file = query(uri(project, 'importers', sub='pkg/b.py'))
        assert [(r['file'], r['line']) for r in on_file['importers']] == [('a.py', 1)]
        for result, answer in (cli_json(uri(project, 'importers=nope.py')),
                               cli_json('imports', str(project), '--importers', 'nope.py')):
            assert result.returncode == 2
            assert 'importers=nope.py matched no file under requested directory' in answer['error']
        result, answer = cli_json(uri(project, 'importers', sub='pkg/nope.py'))
        assert result.returncode == 2 and 'Path not found' in answer['error']
        result, answer = cli_json(uri(project, 'importers='))
        assert result.returncode == 2 and 'importers' in answer['error']

    def test_uri_dot_is_retained_and_text_json_follow_global_format(self, project):
        dot = run(uri(project, 'importers&format=dot'))
        assert dot.returncode == 0 and dot.stdout.startswith('digraph modules')
        assert '"pkg/a.py" -> "pkg/b.py";' in dot.stdout
        _, plain = cli_json(uri(project, 'importers'))
        for value in ('text', 'json'):
            result, answer = cli_json(uri(project, f'importers&format={value}'))
            assert result.returncode == 0 and answer == plain
        subcommand = run('imports', str(project), '--importers', '--format', 'dot')
        assert subcommand.returncode == 2 and 'invalid choice' in subcommand.stderr
        result, answer = cli_json(uri(project, 'rank=fan-in&format=dot'))
        assert result.returncode == 0 and ranking(answer) == RANKING
        assert [w['fields'] for w in unread(answer)] == [['format']]

    def test_findings_gate_only_on_findings_views(self, project):
        result, answer = cli_json('imports', str(project), '--entrypoints', '--fail-on', 'findings')
        assert result.returncode == 2 and 'imports gates --circular, --unused and --violations' in answer['error']
        result, answer = cli_json('imports', str(project), '--circular', '--fail-on', 'findings')
        assert result.returncode == 1 and answer['count'] == 1

    def test_cli_equal_cap_aliases_accepted_conflicts_rejected(self, project):
        result, answer = cli_json('imports', str(project), '--rank', 'fan-in', '--top', '2', '--limit', '2')
        assert result.returncode == 0 and len(answer['entries']) == 2
        bad = run('imports', str(project), '--rank', 'fan-in', '--top', '1', '--limit', '2')
        assert bad.returncode == 2
        assert 'conflicting spellings' in bad.stderr and '--top' in bad.stderr and '--limit' in bad.stderr

    def test_same_key_repetition_last_value_wins(self, project):
        expected = query(uri(project, 'rank=fan-in&top=3'))
        assert query(uri(project, 'rank=fan-in&top=2&top=3')) == expected
        result, answer = cli_json('imports', str(project), '--rank', 'fan-in', '--top', '2', '--top', '3')
        assert result.returncode == 0
        assert_equal_answer(answer, expected)

    def test_max_items_zero_is_an_empty_output_page_not_a_row_cap(self, project):
        full = query(uri(project, 'rank=fan-in'))
        for cap in (0, 2):
            result, cut = cli_json('imports', str(project), '--rank', 'fan-in', '--max-items', str(cap))
            assert result.returncode == 0
            assert cut['entries'] == full['entries'][:cap] and cut['total'] == 7
            cuts = [w for w in cut['meta']['warnings'] if w['type'] == 'truncated']
            assert len(cuts) == 1 and cuts[0]['shown'] == cap and cuts[0]['total'] == 7

    def test_required_output_failure_beats_success_and_recovers(self, project):
        good, full = cli_json('imports', str(project), '--rank', 'fan-in', '--top', '1')
        assert good.returncode == 0 and len(full['entries']) == 1
        failed, kept = cli_json('imports', str(project), '--rank', 'fan-in', '--top', '1',
                                '--output', f'json={project.as_posix()}')
        assert failed.returncode == 3, failed.stderr
        assert kept['entries'] == full['entries']
        assert 'artifact failed' in failed.stderr
        recovered, answer = cli_json('imports', str(project), '--rank', 'fan-in', '--top', '1')
        assert recovered.returncode == 0
        assert_equal_answer(answer, full)

    def test_api_honours_current_mode_keywords(self, project):
        for keywords, controls in (({'unused': True}, 'unused'), ({'circular': True}, 'circular'),
                                   ({'violations': True}, 'violations'),
                                   ({'circular': True, 'verbose': True}, 'circular&verbose')):
            assert_equal_answer(query(uri(project), **keywords), query(uri(project, controls)))

    def test_mcp_answers_and_rejections_match_the_api(self, project):
        from reveal.mcp_server import _ToolFailure, reveal_query
        expected = query(uri(project, 'rank=fan-in&top=2'))
        assert_equal_answer(mcp_json(uri(project, 'rank=fan-in&top=2')), expected)
        # MCP has no exit code: an incomplete answer (CLI exit 3) carries one analysis_incomplete warning.
        result, cli_capped = cli_json(uri(project, 'rank=fan-in&max_files=3'))
        assert result.returncode == 3
        mcp_capped = mcp_json(uri(project, 'rank=fan-in&max_files=3'))
        outcome = [w for w in mcp_capped['meta']['warnings'] if w['type'] == 'analysis_incomplete']
        assert len(outcome) == 1
        assert_equal_answer(_without(mcp_capped, ('analysis_incomplete',)), cli_capped)
        missing = reveal_query(uri(project, 'importers=nope.py'))
        assert isinstance(missing, _ToolFailure) and 'matched no file' in str(missing)

    def test_global_gitignore_and_exclusion_reach_the_walk(self, project):
        subprocess.run(['git', 'init', '-q', str(project)], check=True, capture_output=True, timeout=60)
        (project / '.gitignore').write_text('gen/\n', encoding='utf-8')
        (project / 'gen').mkdir()
        (project / 'gen' / 'g.py').write_text('from pkg import d\n', encoding='utf-8')
        base = query(uri(project, 'rank=fan-in'))
        included = query(uri(project, 'rank=fan-in&respect_gitignore=false'))
        assert base['total'] == 7 and included['total'] == 8
        for args in (('imports', str(project), '--rank', 'fan-in', '--no-gitignore'),
                     (uri(project, 'rank=fan-in'), '--no-gitignore')):
            result, answer = cli_json(*args)
            assert result.returncode == 0
            assert_equal_answer(answer, included)
        for args in (('imports', str(project), '--rank', 'fan-in', '--exclude', 'tests'),
                     (uri(project, 'rank=fan-in'), '--exclude', 'tests')):
            result, answer = cli_json(*args)
            assert result.returncode == 0 and answer['total'] == 6

    def test_answer_and_usage_guards_detect_wrong_results(self, project):
        expected = query(uri(project, 'rank=fan-in'))
        wrong = copy.deepcopy(expected)
        wrong['entries'] = wrong['entries'][:1]
        assert_equal_answer(expected, expected)
        with pytest.raises(AssertionError, match='canonical answer differs'):
            assert_equal_answer(wrong, expected)
        noted = copy.deepcopy(expected)
        noted['meta']['warnings'].append({'type': 'retired_spelling', 'message': 'x is deprecated; use y.'})
        assert_equal_answer(noted, expected)
        bad, answer = cli_json(uri(project, 'rank=callers'))
        assert_usage(bad, answer, 'fan-in')
        good, successful = cli_json(uri(project, 'rank=fan-in'))
        with pytest.raises(AssertionError, match='expected usage exit 2'):
            assert_usage(good, successful, 'fan-in')
        with pytest.raises(AssertionError, match='error must name'):
            assert_usage(bad, answer, 'nonexistent-replacement')

    def test_edit_between_api_requests_is_seen(self, project):
        before = dict(ranking(query(uri(project, 'rank=fan-in'))))
        (project / 'pkg' / 'd.py').write_text('from pkg import b\n\n\ndef fd():\n    return 2\n', encoding='utf-8')
        after = dict(ranking(query(uri(project, 'rank=fan-in'))))
        assert before['pkg/b.py'] == 1 and after['pkg/b.py'] == 2


MODES = ('unused', 'circular', 'violations', 'entrypoints', 'components', 'external')


class TestProposedChanges:
    @pytest.mark.parametrize('mode', MODES)
    @pytest.mark.parametrize('value', ['false', '0'])
    def test_false_mode_is_not_selected_on_every_transport(self, project, mode, value):
        """B1: ?MODE=false means the mode is not selected: the default view, exit 0, on every transport."""
        from reveal.mcp_server import _ToolFailure, reveal_query
        expected = query(uri(project))
        assert expected['type'] == 'imports'
        result, cli = cli_json(uri(project, f'{mode}={value}'))
        mcp = reveal_query(uri(project, f'{mode}={value}'), provenance=True)
        answers = {
            'cli-uri': cli,
            'api-uri': query(uri(project, f'{mode}={value}')),
            'api-keyword': query(uri(project), **{mode: False}),
            'mcp': None if isinstance(mcp, _ToolFailure) else {k: v for k, v in json.loads(mcp).items()
                                                              if k != 'execution'},
        }
        problems = [] if result.returncode == 0 else [f'cli-uri exit {result.returncode}: {result.stderr.strip()}']
        if isinstance(mcp, _ToolFailure):
            problems.append(f'mcp failed: {mcp}')
        problems += [f'{name} answered {answer.get("type")}' for name, answer in answers.items()
                     if answer is not None and without_retirement(answer) != without_retirement(expected)]
        assert not problems, f'{mode}={value} must answer the default view everywhere: {problems}'

    @pytest.mark.parametrize('transport', ['uri', 'uri-global', 'api', 'mcp'])
    def test_canonical_limit_cuts_rank_rows_and_zero_is_uncapped(self, project, transport):
        for cap in (1, 0):
            expected = query(uri(project, f'rank=fan-in&top={cap}'))
            assert len(expected['entries']) == (7 if cap == 0 else 1)
            if transport == 'api':
                actual = query(uri(project, 'rank=fan-in'), limit=cap)
            elif transport == 'mcp':
                actual = mcp_json(uri(project, f'rank=fan-in&limit={cap}'))
            else:
                result, actual = (cli_json(uri(project, f'rank=fan-in&limit={cap}')) if transport == 'uri'
                                  else cli_json(uri(project, 'rank=fan-in'), '--limit', str(cap)))
                assert result.returncode == 0, result.stderr
            assert not [w for w in actual['meta']['warnings'] if w['type'] == 'unknown_query_param'], \
                f'limit={cap} must be a declared Imports control'
            assert_equal_answer(actual, expected)

    def test_uri_global_zero_limit_binds_exactly_not_a_sentinel(self, project):
        from reveal.adapters.imports import ImportsAdapter
        from reveal.cli.defaults import _default_args
        from reveal.cli.routing.flag_specs import inject_query_flags
        from reveal.utils.query_binding import bind_declared_params
        for submitted in (1, 0):
            fragment = inject_query_flags('', 'imports', _default_args(limit=submitted))
            bound = bind_declared_params(ImportsAdapter.PARAM_SPECS, fragment.lstrip('?'), transport='uri')
            cap = next((s.read(bound) for s in ImportsAdapter.PARAM_SPECS
                        if s.name == 'limit' and s.name in bound), None)
            assert cap == submitted, f'global --limit {submitted} must bind limit exactly, got {cap} from {fragment!r}'

    @pytest.mark.parametrize('transport', ['cli', 'uri', 'uri-global', 'api', 'mcp'])
    def test_canonical_sort_selects_the_fan_in_ranking(self, project, transport):
        expected = query(uri(project, 'rank=fan-in&top=2'))
        assert expected['type'] == 'fan_in_ranking' and len(expected['entries']) == 2
        if transport == 'api':
            actual = query(uri(project, 'top=2'), sort='-fan-in')
        elif transport == 'mcp':
            actual = mcp_json(uri(project, 'sort=-fan-in&top=2'))
        else:
            result, actual = {
                'cli': lambda: cli_json('imports', str(project), '--sort=-fan-in', '--top', '2'),
                'uri': lambda: cli_json(uri(project, 'sort=-fan-in&top=2')),
                'uri-global': lambda: cli_json(uri(project, 'top=2'), '--sort=-fan-in'),
            }[transport]()
            assert result.returncode == 0, result.stderr
        assert_equal_answer(actual, expected)

    @pytest.mark.parametrize('transport', ['cli', 'uri', 'api', 'mcp'])
    def test_canonical_detail_levels_equal_verbose_and_plain(self, project, transport):
        for level, legacy in (('full', 'circular&verbose'), ('normal', 'circular')):
            expected = query(uri(project, legacy))
            assert ('verbose' in expected) == (level == 'full')
            if transport == 'api':
                actual = query(uri(project, 'circular'), detail=level)
            elif transport == 'mcp':
                actual = mcp_json(uri(project, f'circular&detail={level}'))
            else:
                result, actual = (cli_json('imports', str(project), '--circular', '--detail', level)
                                  if transport == 'cli' else cli_json(uri(project, f'circular&detail={level}')))
                assert result.returncode == 0, result.stderr
            assert_equal_answer(actual, expected)

    def test_canonical_detail_full_expands_text_like_verbose(self, project):
        expected = run(uri(project, 'circular&verbose'))
        actual = run(uri(project, 'circular&detail=full'))
        assert actual.returncode == expected.returncode == 0
        assert actual.stdout == expected.stdout

    @pytest.mark.parametrize('transport', ['cli', 'uri', 'uri-alias', 'api', 'mcp'])
    def test_canonical_scan_limit_is_the_incomplete_input_budget(self, project, transport):
        if transport == 'api':
            expected = query(uri(project, 'rank=fan-in&max_files=3'))
            actual = query(uri(project, 'rank=fan-in'), **{'scan-limit': 3})
        else:
            legacy_result, expected = cli_json(uri(project, 'rank=fan-in&max_files=3'))
            assert legacy_result.returncode == 3
            if transport == 'mcp':
                actual = _without(mcp_json(uri(project, 'rank=fan-in&scan-limit=3')), ('analysis_incomplete',))
            else:
                result, actual = {
                    'cli': lambda: cli_json('imports', str(project), '--rank', 'fan-in', '--scan-limit', '3'),
                    'uri': lambda: cli_json(uri(project, 'rank=fan-in&scan-limit=3')),
                    'uri-alias': lambda: cli_json(uri(project, 'rank=fan-in&scan_limit=3')),
                }[transport]()
                assert result.returncode == 3, f'a cut input budget is incomplete (exit 3), got {result.returncode}'
        assert actual['meta']['scan_budget']['capped'] is True, 'scan-limit=3 must cut the walk'
        assert_equal_answer(actual, expected)

    @pytest.mark.parametrize('value', ['0', '-1'])
    def test_canonical_scan_limit_zero_and_negative_reject(self, project, value):
        for result, answer in (cli_json('imports', str(project), '--rank', 'fan-in', '--scan-limit', value),
                               cli_json(uri(project, f'rank=fan-in&scan-limit={value}'))):
            assert result.returncode == 2, f'scan-limit={value} must reject, got {result.returncode}'
            assert answer is not None, f'scan-limit must be declared, not an unknown flag: {result.stderr[-120:]}'
            assert '>= 1' in answer['error']

    def test_canonical_requests_have_no_retirement_notes(self, project):
        result, answer = cli_json('imports', str(project), '--sort=-fan-in', '--limit', '1', '--scan-limit', '100')
        assert result.returncode == 0, result.stderr
        assert len(answer['entries']) == 1
        assert not [w for w in answer['meta']['warnings'] if w.get('type') == 'retired_spelling']
        assert 'deprecated' not in result.stderr
        result, answer = cli_json('imports', str(project), '--circular', '--detail', 'full')
        assert result.returncode == 0 and answer.get('verbose') is True
        assert not [w for w in answer['meta']['warnings'] if w.get('type') == 'retired_spelling']

    @pytest.mark.parametrize('transport', ['cli', 'uri', 'api-uri', 'api-keyword'])
    @pytest.mark.parametrize('old,new,controls,flags,keywords', [
        ('rank', 'sort', 'rank=fan-in', ('--rank', 'fan-in'), {'rank': 'fan-in'}),
        ('top', 'limit', 'rank=fan-in&top=2', ('--rank', 'fan-in', '--top', '2'), {'rank': 'fan-in', 'top': 2}),
        ('verbose', 'detail', 'circular&verbose', ('--circular', '--verbose'), {'circular': True, 'verbose': True}),
        ('max_files', 'scan-limit', 'rank=fan-in&max_files=100', ('--rank', 'fan-in', '--max-files', '100'),
         {'rank': 'fan-in', 'max_files': 100}),
    ])
    def test_legacy_vocabulary_keeps_answer_and_names_replacement(self, project, transport, old, new,
                                                                  controls, flags, keywords):
        expected = query(uri(project, controls))
        if transport == 'cli':
            result, answer = cli_json('imports', str(project), *flags)
        elif transport == 'uri':
            result, answer = cli_json(uri(project, controls))
        else:
            result, answer = None, (query(uri(project, controls)) if transport == 'api-uri'
                                    else query(uri(project), **keywords))
        if result is not None:
            assert result.returncode == 0, result.stderr
        assert_equal_answer(answer, expected)
        notes = [w for w in answer['meta']['warnings'] if w.get('type') == 'retired_spelling']
        assert any(old in w.get('message', '') and new in w.get('message', '') for w in notes), \
            f'legacy {old} must keep working with a retirement note naming {new}: {notes}'

    @pytest.mark.parametrize('controls,replacement', [
        ('rank=fan-in&top=1&limit=2', 'limit'),
        ('rank=fan-in&max_files=3&scan-limit=4', 'scan-limit'),
        ('circular&verbose&detail=normal', 'detail'),
        ('sort=fan-in', '-fan-in'),
        ('rank=fan-in&sort=-fan-out', '-fan-in'),
        ('circular&detail=summary', 'full'),
    ])
    def test_conflicts_and_unsupported_values_reject_with_guidance(self, project, controls, replacement):
        result, answer = cli_json(uri(project, controls))
        assert_usage(result, answer, replacement)

    def test_equal_old_and_new_spellings_are_accepted_once(self, project):
        expected = query(uri(project, 'rank=fan-in&top=2'))
        result, answer = cli_json(uri(project, 'rank=fan-in&sort=-fan-in&top=2&limit=2'))
        assert result.returncode == 0, result.stderr
        assert not [w for w in answer['meta']['warnings'] if w['type'] in ('unknown_query_param',) + UNREAD_WARNINGS]
        assert_equal_answer(answer, expected)
        assert 'ignored' not in result.stderr

    @pytest.mark.parametrize('control', ['offset', 'where', 'match', 'kind', 'depth'])
    def test_unsupported_shared_controls_reject(self, project, control):
        result, answer = cli_json(uri(project, f'rank=fan-in&{control}=1'))
        assert result.returncode == 2, f'{control} is not an Imports control and must exit 2, got {result.returncode}'
        assert control in answer['error']
        with pytest.raises((TypeError, ValueError), match=control):
            query(uri(project, 'rank=fan-in'), **{control: '1'})

    @pytest.mark.parametrize('base,keywords,controls,sub', [
        ('', {'rank': 'fan-in'}, 'rank=fan-in', ''),
        ('rank=fan-in', {'top': 2}, 'rank=fan-in&top=2', ''),
        ('rank=fan-in', {'max_files': 3}, 'rank=fan-in&max_files=3', ''),
        ('', {'importers': True}, 'importers', ''),
        ('', {'importers': 'pkg/b.py'}, 'importers=pkg/b.py', ''),
        ('circular', {'lazy': 'include'}, 'circular&lazy=include', ''),
        ('rank=fan-in', {'tests': 'exclude'}, 'rank=fan-in&tests=exclude', ''),
        ('rank=fan-in', {'scope': 'path'}, 'rank=fan-in&scope=path', 'pkg'),
        ('rank=fan-in', {'root': '/'}, 'rank=fan-in&root=/', ''),
        ('importers', {'format': 'dot'}, 'importers&format=dot', ''),
        ('', {'entrypoints': True}, 'entrypoints', ''),
        ('', {'components': True}, 'components', ''),
        ('', {'external': True}, 'external', ''),
    ])
    def test_typed_api_keyword_answers_like_its_uri_spelling(self, project, base, keywords, controls, sub):
        """B2: every declared typed keyword reaches the answer, as its URI spelling does."""
        expected = query(uri(project, controls, sub=sub))
        assert expected != query(uri(project, base, sub=sub)), 'fixture must make the control observable'
        assert_equal_answer(query(uri(project, base, sub=sub), **keywords), expected)

    def test_typed_api_none_importers_is_the_default_view(self, project):
        """None selects the declared default for importers as for every typed keyword (no view); a bare
        --importers on the subcommand still asks for the importer summary of the directory."""
        default = query(uri(project))
        assert_equal_answer(query(uri(project), importers=None), default)
        assert_equal_answer(query(uri(project, 'importers'), importers=None), default)
        result, answer = cli_json('imports', str(project), '--importers')
        assert result.returncode == 0, result.stderr
        assert answer['type'] == 'importer_summary'
        assert_equal_answer(answer, query(uri(project, 'importers')))

    @pytest.mark.parametrize('keywords', [
        {'rank': 'callers'}, {'rank': 'fan-in', 'top': -1}, {'rank': 'fan-in', 'max_files': 0},
        {'circular': True, 'lazy': 'bogus'}, {'tests': 'only'}, {'bogus': 1},
    ])
    def test_typed_api_invalid_or_unknown_keyword_rejects(self, project, keywords):
        with pytest.raises((TypeError, ValueError)):
            query(uri(project), **keywords)

    @pytest.mark.parametrize('first,second', [
        ('importers', 'circular'), ('unused', 'circular'), ('circular', 'violations'),
        ('rank=fan-in', 'entrypoints'), ('components', 'external'),
    ])
    def test_two_view_modes_reject_naming_both(self, project, first, second):
        """D18 (Scott 2026-11-14): two view modes in one request exit 2 naming both, as Calls does;
        today the first in precedence answers and the other is only warned unread."""
        from reveal.mcp_server import _ToolFailure, reveal_query
        names = [mode.partition('=')[0] for mode in (first, second)]

        def names_both(text):
            # rank's canonical spelling is sort; either names the ranking mode.
            return all(n in text or (n == 'rank' and 'sort' in text) for n in names)

        flags = [arg for mode in (first, second) for arg in (
            ('--rank', 'fan-in') if mode.startswith('rank') else (f'--{mode}',))]
        keywords = {n: ('fan-in' if n == 'rank' else True) for n in names}
        for result, answer in (cli_json(uri(project, f'{first}&{second}')),
                               cli_json('imports', str(project), *flags)):
            assert result.returncode == 2, f'{first}&{second} must exit 2, got {result.returncode}'
            assert names_both(answer['error']), f'the error must name both modes: {answer["error"]}'
        mcp = reveal_query(uri(project, f'{first}&{second}'))
        assert isinstance(mcp, _ToolFailure) and names_both(str(mcp)), f'MCP must reject: {str(mcp)[:200]}'
        for request in (lambda: query(uri(project, f'{first}&{second}')), lambda: query(uri(project), **keywords)):
            with pytest.raises(ValueError) as rejected:
                request()
            assert names_both(str(rejected.value)), str(rejected.value)

    @pytest.mark.parametrize('controls', ['circular=false', 'entrypoints&unused=0', 'violations=no&components'])
    def test_a_false_findings_mode_does_not_satisfy_the_gate(self, project, controls):
        """B1 at the gate: --fail-on findings needs a selected findings view; a false one is not selected."""
        result, answer = cli_json(uri(project, controls), '--fail-on', 'findings')
        assert result.returncode == 2, f'{controls} has no findings verdict: exit 2, got {result.returncode}'
        assert 'imports gates --circular, --unused and --violations' in answer['error']
        # Positive control: the same false modes beside one selected findings view (no second view).
        false_only = '&'.join(part for part in controls.split('&') if '=' in part)
        control, gated = cli_json(uri(project, f'{false_only}&circular'), '--fail-on', 'findings')
        assert control.returncode == 1 and gated['type'] == 'circular_dependencies', control.stderr

    @pytest.mark.parametrize('mode', MODES)
    def test_direct_construction_reads_a_false_mode_as_not_selected(self, project, mode):
        """B1 at the owner: the raw-query constructor (deps, calls ?modules, library callers) reads the
        bound value, not key presence; verbose=false does not expand either."""
        from reveal.adapters.imports import ImportsAdapter
        expected = ImportsAdapter(str(project)).get_structure()
        for value in ('false', '0', 'no'):
            assert ImportsAdapter(str(project), f'{mode}={value}').get_structure() == expected
        assert 'verbose' not in ImportsAdapter(str(project), 'circular&verbose=false').get_structure()
        assert ImportsAdapter(str(project), 'circular&verbose').get_structure()['verbose'] is True

    def test_direct_construction_and_get_view_bind_the_canonical_controls(self, project):
        """The raw-query constructor (deps, calls ?modules, library callers) and get_view bind through
        the same declarations as the URI: canonical names answer, legacy names still do, and a value
        the URI rejects is rejected at construction."""
        from reveal.adapters.imports import ImportsAdapter
        expected = ranking(query(uri(project, 'rank=fan-in&top=2')))
        for controls in ('sort=-fan-in&limit=2', 'rank=fan-in&top=2', 'sort=-fan-in&top=2&scan-limit=100'):
            got = ImportsAdapter(str(project), controls).get_structure()
            assert (ranking(got), got['total']) == (expected, 7), controls
        adapter = ImportsAdapter(str(project))
        adapter.get_structure()
        assert ranking(adapter.get_view('sort=-fan-in&limit=2')) == expected
        assert adapter.get_view('circular&detail=full')['verbose'] is True
        with pytest.raises(ValueError, match='unused'):
            ImportsAdapter(str(project), 'unused=banana')

    @pytest.mark.parametrize('controls', ['circular&unused=false', 'unused=0&circular'])
    def test_a_false_mode_is_not_a_second_mode(self, project, controls):
        """Negative control for the two-mode rule: a mode bound False is not selected (B1)."""
        expected = query(uri(project, 'circular'))
        result, answer = cli_json(uri(project, controls))
        assert result.returncode == 0, result.stderr
        assert answer['type'] == 'circular_dependencies'
        assert_equal_answer(_without(answer, UNREAD_WARNINGS), _without(expected, UNREAD_WARNINGS))
        api = query(uri(project, controls))
        assert_equal_answer(_without(api, UNREAD_WARNINGS), _without(expected, UNREAD_WARNINGS))
