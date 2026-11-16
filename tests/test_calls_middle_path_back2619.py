"""BACK-2619 preservation pins and canonical Calls vocabulary regressions.

Class grouping preserves the reviewed Step 2 inventory and migration controls.
"""
import copy
import json
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.api import query
from reveal.adapters.calls.adapter import CallsAdapter, _TOP
from reveal.utils.query_binding import bind_declared_params
from reveal.utils.request_cache import host_request


@pytest.fixture
def project(tmp_path, monkeypatch):
    # A subdirectory, so an empty ?callers answer's parent hint scans only this
    # test's tmp_path, not pytest's shared basetemp with sibling tests' files.
    root = tmp_path / 'proj'
    root.mkdir()
    monkeypatch.chdir(root)
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')
    source = ''.join(f'def n{i}(): return {i}\n' for i in range(12))
    source += 'def sink(): return 1\ndef middle(): return sink()\ndef top(): return middle()\n'
    source += 'def entry(): return (' + ','.join(f'n{i}()' for i in range(12)) + ',len([]))\n'
    source += 'def orphan(): return 0\nclass Box:\n    def unused(self): return 0\n'
    (root / 'app.py').write_text(source, encoding='utf-8')
    return root


def uri(project, controls):
    return f'calls://{project.as_posix()}?{controls}'


def cli_json(*args):
    result = run(*args, '--format', 'json')
    return result, json.loads(result.stdout) if result.stdout.strip() else None


def without_retirement(answer):
    """Only spelling-specific retirement warnings may differ across aliases."""
    result = copy.deepcopy(answer)
    result['meta']['warnings'] = [w for w in result['meta']['warnings']
                                  if w.get('type') != 'retired_spelling']
    return result


def assert_equal_answer(actual, expected):
    assert without_retirement(actual) == without_retirement(expected), 'canonical answer differs'


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
    # Provenance is explicitly requested only because this tool has no JSON-format argument.
    answer.pop('execution', None)
    return answer


class TestPreservation:
    @pytest.mark.parametrize('limit', [0, 1, 3])
    def test_legacy_limit_converter_and_cli_alias_preserve_population(self, project, limit):
        expected = query(uri(project, f'rank=callers&top={limit}'))
        full = query(uri(project, 'rank=callers&top=0'))
        assert len(full['entries']) == 14
        assert {e['name']: e['caller_count'] for e in full['entries']} == {
            **{f'n{i}': 1 for i in range(12)}, 'sink': 1, 'middle': 1}
        for entry in full['entries']:
            expected_caller = {'sink': 'middle', 'middle': 'top'}.get(entry['name'], 'entry')
            assert [c['caller'] for c in entry['callers']] == [expected_caller]
        assert _TOP.zero_policy == 'all' and _TOP.validate(limit) == limit
        assert len(expected['entries']) == (14 if limit == 0 else limit)
        assert expected['total_unique_callees'] == full['total_unique_callees'] == 14
        for spelling in ('--top', '--limit'):
            result, answer = cli_json('calls', str(project), '--rank', 'callers', spelling, str(limit))
            assert result.returncode == 0, result.stderr
            assert_equal_answer(answer, expected)

    def test_output_limit_does_not_become_required_input_budget(self, project):
        full = query(uri(project, 'rank=callers&top=0'))
        result, cut = cli_json('calls', str(project), '--rank', 'callers', '--top', '1')
        assert result.returncode == 0
        assert cut['total_unique_callees'] == full['total_unique_callees'] == 14
        assert cut['entries'] == full['entries'][:1]
        assert cut['meta']['errors'] == []
        assert not any(w['type'] in ('analysis_failed', 'analysis_incomplete') for w in cut['meta']['warnings'])
        cuts = [w for w in cut['meta']['warnings'] if w['type'] == 'truncated']
        assert len(cuts) == 1
        assert {k: cuts[0][k] for k in ('field', 'shown', 'total', 'exact', 'cause')} == {
            'field': 'entries', 'shown': 1, 'total': 14, 'exact': True, 'cause': 'limit'}

    def test_top_is_ignored_with_warning_on_walks_today(self, project):
        full = query(uri(project, 'callers=sink&depth=2'))
        result, cut = cli_json('calls', str(project), '--callers', 'sink', '--depth', '2', '--limit', '1')
        assert result.returncode == 0
        assert_equal_answer(cut, full)
        assert cut['total_callers'] == 2
        assert "only caps ?rank=callers" in result.stderr and 'ignored' in result.stderr

    def test_max_items_zero_is_an_empty_output_page_not_native_uncapped(self, project):
        full = query(uri(project, 'rank=callers&top=0'))
        for cap in (0, 1):
            result, cut = cli_json('calls', str(project), '--rank', 'callers', '--top', '0',
                                   '--max-items', str(cap))
            assert result.returncode == 0
            assert cut['entries'] == full['entries'][:cap]
            assert cut['total_unique_callees'] == 14
            cuts = [w for w in cut['meta']['warnings'] if w['type'] == 'truncated']
            assert len(cuts) == 1 and cuts[0]['shown'] == cap and cuts[0]['total'] == 14

    @pytest.mark.parametrize('controls,typed', [
        ('rank=callers&top=0', {'rank': 'callers', 'top': 0}),
        ('callees=top&detail=false', {'callees': 'top', 'detail': False}),
        ('callees=top&detail=false', {'callees': 'top', 'detail': None}),
        ('callers=sink&depth=1', {'callers': 'sink', 'depth': None}),
        ('callers=sink&depth=1', {'callers': 'sink', 'depth': 0}),
    ])
    def test_api_false_zero_none_are_real_overrides(self, project, controls, typed):
        assert query(uri(project, controls)) == query(uri(project, ''), **typed)

    def test_same_key_repetition_and_same_cli_alias_values(self, project):
        expected = query(uri(project, 'rank=callers&top=2'))
        assert query(uri(project, 'rank=callers&top=2&top=2')) == expected
        # BACK-2654 rule 1: one setting, two values is an invalid request (it was last-wins).
        with pytest.raises(ValueError, match='top is given twice with different values'):
            query(uri(project, 'rank=callers&top=1&top=2'))
        result, _answer = cli_json('calls', str(project), '--rank', 'callers', '--top', '1', '--top', '2')
        assert result.returncode == 2 and '--top 1 and --top 2' in result.stderr
        result, answer = cli_json('calls', str(project), '--rank', 'callers', '--top', '2', '--limit', '2')
        assert result.returncode == 0
        assert_equal_answer(answer, expected)

    def test_declared_boolean_dest_differs_from_api_keyword(self, project):
        expected = query(uri(project, 'rank=callers&test-framework=true'))
        assert query(uri(project, 'rank=callers'), **{'test-framework': True}) == expected
        with pytest.raises(TypeError, match='test_framework'):
            query(uri(project, 'rank=callers'), test_framework=True)

    def test_cli_conflicting_cap_aliases_reject_and_positive_control_answers(self, project):
        good, answer = cli_json('calls', str(project), '--rank', 'callers', '--top', '2', '--limit', '2')
        assert good.returncode == 0 and len(answer['entries']) == 2
        bad = run('calls', str(project), '--rank', 'callers', '--top', '1', '--limit', '2')
        assert bad.returncode == 2
        assert 'conflicting spellings' in bad.stderr and '--top' in bad.stderr and '--limit' in bad.stderr

    def test_exact_answer_guard_detects_wrong_population(self, project):
        expected = query(uri(project, 'rank=callers&top=0'))
        wrong = copy.deepcopy(expected)
        wrong['entries'] = wrong['entries'][:1]
        assert_equal_answer(expected, expected)
        with pytest.raises(AssertionError, match='canonical answer differs'):
            assert_equal_answer(wrong, expected)

    def test_rejection_guard_detects_clean_success_and_wrong_suggestion(self, project):
        bad, answer = cli_json('calls', str(project), '--callers', 'sink', '--detail')
        assert_usage(bad, answer, 'callees')
        good, successful = cli_json('calls', str(project), '--callees', 'top')
        assert good.returncode == 0 and successful['matches']
        with pytest.raises(AssertionError, match='expected usage exit 2'):
            assert_usage(good, successful, 'callees')
        with pytest.raises(AssertionError, match='error must name'):
            assert_usage(bad, answer, 'nonexistent-replacement')

    def test_mcp_json_matches_current_answer_and_guard_detects_mutation(self, project):
        expected = query(uri(project, 'rank=callers&top=1'))
        actual = mcp_json(uri(project, 'rank=callers&top=1'))
        assert_equal_answer(actual, expected)
        wrong = copy.deepcopy(actual)
        wrong['total_unique_callees'] = -1
        with pytest.raises(AssertionError, match='canonical answer differs'):
            assert_equal_answer(wrong, expected)

    def test_required_output_failure_beats_success_and_recovers(self, project):
        good, full = cli_json('calls', str(project), '--rank', 'callers', '--top', '1')
        assert good.returncode == 0 and len(full['entries']) == 1
        failed, kept = cli_json('calls', str(project), '--rank', 'callers', '--top', '1',
                                '--output', f'json={project.as_posix()}')
        assert failed.returncode == 3, failed.stderr
        assert kept['entries'] == full['entries']
        assert 'output' in failed.stderr.lower()
        recovered, answer = cli_json('calls', str(project), '--rank', 'callers', '--top', '1')
        assert recovered.returncode == 0
        assert_equal_answer(answer, full)

    def test_global_gitignore_and_cli_exclusion_are_not_adapter_typed_inputs(self, project):
        subprocess.run(['git', 'init', '-q', str(project)], check=True, capture_output=True)
        (project / '.gitignore').write_text('hidden.py\n', encoding='utf-8')
        (project / 'hidden.py').write_text('def hidden(): return sink()\n', encoding='utf-8')
        base = query(uri(project, 'callers=sink'))
        included = query(uri(project, 'callers=sink&respect_gitignore=false'))
        assert base['total_callers'] == 1 and included['total_callers'] == 2
        result, cli = cli_json('calls', str(project), '--callers', 'sink', '--no-gitignore')
        assert result.returncode == 0
        assert_equal_answer(cli, included)
        result, excluded = cli_json('calls', str(project), '--callers', 'sink', '--no-gitignore',
                                     '--exclude', 'hidden.py')
        assert result.returncode == 0 and excluded['total_callers'] == 1
        with pytest.raises(TypeError, match='respect_gitignore'):
            query(uri(project, 'callers=sink'), respect_gitignore=False)

    def test_current_mcp_absence_compatibility_differs_from_invalid_request(self, project):
        from reveal.mcp_server import _ToolFailure, reveal_query
        cli, absent = cli_json(uri(project, 'callers=not_present'))
        assert cli.returncode == 2 and absent['total_callers'] == 0
        mcp = reveal_query(uri(project, 'callers=not_present'), provenance=True)
        assert not isinstance(mcp, _ToolFailure)
        assert json.loads(mcp)['error'] == absent['error']
        usage = reveal_query(uri(project, 'callers=sink&detail=true'))
        assert isinstance(usage, _ToolFailure) and 'callees' in str(usage)

    def test_registered_stdio_tool_preserves_answer_and_usage_outcomes(self, project):
        from test_mcp_expected_errors_back1992 import _run, _text
        expected = query(uri(project, 'rank=callers&top=1'))

        async def scenario(session):
            good = await session.call_tool('reveal_query', {
                'uri': uri(project, 'rank=callers&top=1'), 'provenance': True})
            assert not good.is_error
            answer = json.loads(_text(good))
            answer.pop('execution', None)
            assert_equal_answer(answer, expected)
            bad = await session.call_tool('reveal_query', {'uri': uri(project, 'callers=sink&detail=true')})
            assert bad.is_error and 'callees' in _text(bad)
            absent = await session.call_tool('reveal_query', {'uri': uri(project, 'callers=not_present')})
            assert not absent.is_error and 'not found' in _text(absent)
        _run(project, scenario)

    def test_host_request_reentrant_lock_serializes_distinct_threads(self):
        entered = threading.Event()
        attempting = threading.Event()
        second_entered = threading.Event()
        release = threading.Event()

        def first():
            with host_request(), host_request():
                entered.set()
                assert release.wait(5)

        def second():
            assert entered.wait(5)
            attempting.set()
            with host_request():
                second_entered.set()

        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(first)
            b = pool.submit(second)
            try:
                assert attempting.wait(5)
                assert not second_entered.wait(0.1), 'another thread entered the held host request'
            finally:
                release.set()
            a.result(timeout=5)
            b.result(timeout=5)
        assert second_entered.is_set()


    def test_uri_dot_is_retained_without_widening_global_formats(self, project):
        old = run(uri(project, 'callers=sink&format=dot'))
        assert old.returncode == 0 and old.stdout.startswith('digraph')
        current = run('calls', str(project), '--callers', 'sink', '--format', 'dot')
        assert current.returncode == 2
        assert 'invalid choice' in current.stderr and 'dot' in current.stderr


class TestProposedChanges:
    @pytest.mark.parametrize('control', ['where', 'match', 'offset', 'since', 'until'])
    def test_api_unsupported_controls_name_supported_lookup(self, project, control):
        baseline = query(uri(project, 'callers=sink'))
        assert baseline['total_callers'] == 1
        with pytest.raises(TypeError) as error:
            query(uri(project, 'callers=sink'), **{control: 'unsupported'})
        assert control in str(error.value)
        assert 'callers=NAME' in str(error.value) and 'no equivalent filter' in str(error.value)

    def test_canonical_requests_have_no_retirement_notes(self, project):
        result, answer = cli_json('calls', str(project), '--sort=-callers', '--limit', '1')
        assert result.returncode == 0 and len(answer['entries']) == 1
        assert not [w for w in answer['meta']['warnings'] if w.get('type') == 'retired_spelling']
        assert 'deprecated' not in result.stderr
        result, answer = cli_json('calls', str(project), '--callees', 'top', '--detail', 'full')
        assert result.returncode == 0 and answer['levels']
        assert not [w for w in answer['meta']['warnings'] if w.get('type') == 'retired_spelling']

    def test_equal_numeric_cap_aliases_coalesce_and_api_notes_match_cli(self, project):
        expected = query(uri(project, 'sort=-callers&limit=1'))
        actual = query(uri(project, ''), sort='-callers', limit=1, top='1.0')
        assert_equal_answer(actual, expected)
        assert len(actual['entries']) == 1
        result, answer = cli_json('calls', str(project), '--sort=-callers', '--limit', '1', '--top', '1.0')
        assert result.returncode == 0
        assert answer == actual

    def test_uri_global_zero_cap_is_uncapped_not_a_million_row_approximation(self, project):
        from reveal.cli.defaults import _default_args
        from reveal.cli.routing.flag_specs import inject_query_flags
        for submitted in (1, 0):
            fragment = inject_query_flags('', 'calls', _default_args(limit=submitted))
            bound = bind_declared_params(CallsAdapter.PARAM_SPECS, fragment.lstrip('?'), transport='uri')
            cap = next((s.read(bound) for s in CallsAdapter.PARAM_SPECS
                        if s.name in ('top', 'limit') and s.name in bound), None)
            assert cap == submitted, f'global --limit {submitted} must bind exactly, got {cap}; finite sentinels are not uncapped'

    @pytest.mark.parametrize('controls', ['sort=-callers&top=1', 'rank=callers&limit=1',
                                          'uncalled&kind=function&top=0', 'callees=top&detail=full'])
    def test_registered_stdio_tool_canonical_answer(self, project, controls):
        from test_mcp_expected_errors_back1992 import _run, _text
        legacy = {'sort=-callers&top=1': 'rank=callers&top=1',
                  'rank=callers&limit=1': 'rank=callers&top=1',
                  'uncalled&kind=function&top=0': 'uncalled&type=function&top=0',
                  'callees=top&detail=full': 'callees=top&detail=true'}[controls]
        expected = query(uri(project, legacy))
        assert expected['type'].startswith('calls_') and not expected.get('error')

        async def scenario(session):
            answer = await session.call_tool('reveal_query', {'uri': uri(project, controls), 'provenance': True})
            assert not answer.is_error, f'registered canonical request failed: {_text(answer)}'
            actual = json.loads(_text(answer))
            actual.pop('execution', None)
            assert_equal_answer(actual, expected)
        _run(project, scenario)


    @pytest.mark.parametrize('transport', ['cli', 'uri', 'api', 'mcp'])
    @pytest.mark.parametrize('level', ['normal', 'full'])
    def test_detail_scale_preserves_boolean_answer(self, project, transport, level):
        expected = query(uri(project, 'callees=top&detail=' + ('true' if level == 'full' else 'false')))
        assert bool(expected.get('levels')) == (level == 'full')
        if transport == 'api':
            actual = query(uri(project, 'callees=top'), detail=level)
        elif transport == 'mcp':
            actual = mcp_json(uri(project, f'callees=top&detail={level}'))
        else:
            result, actual = (cli_json('calls', str(project), '--callees', 'top', '--detail', level)
                              if transport == 'cli' else cli_json(uri(project, f'callees=top&detail={level}')))
            assert result.returncode == 0, result.stderr
        assert_equal_answer(actual, expected)

    @pytest.mark.parametrize('transport', ['cli', 'uri', 'api', 'mcp'])
    def test_canonical_sort_selects_same_rank_answer(self, project, transport):
        expected = query(uri(project, 'rank=callers&top=1'))
        assert len(expected['entries']) == 1 and expected['total_unique_callees'] == 14
        if transport == 'api':
            actual = query(uri(project, ''), sort='-callers', top=1)
        elif transport == 'mcp':
            actual = mcp_json(uri(project, 'sort=-callers&top=1'))
        else:
            result, actual = (cli_json('calls', str(project), '--sort=-callers', '--top', '1')
                              if transport == 'cli' else cli_json(uri(project, 'sort=-callers&top=1')))
            assert result.returncode == 0, result.stderr
        assert_equal_answer(actual, expected)

    @pytest.mark.parametrize('transport', ['uri', 'api', 'mcp'])
    @pytest.mark.parametrize('limit', [0, 1])
    def test_canonical_limit_preserves_full_population(self, project, transport, limit):
        expected = query(uri(project, f'rank=callers&top={limit}'))
        assert len(expected['entries']) == (14 if limit == 0 else 1)
        if transport == 'api':
            actual = query(uri(project, 'rank=callers'), limit=limit)
        elif transport == 'mcp':
            actual = mcp_json(uri(project, f'rank=callers&limit={limit}'))
        else:
            result, actual = cli_json(uri(project, f'rank=callers&limit={limit}'))
            assert result.returncode == 0, result.stderr
        assert_equal_answer(actual, expected)

    @pytest.mark.parametrize('transport', ['cli', 'uri', 'api', 'mcp'])
    def test_kind_function_keeps_existing_uncalled_selection(self, project, transport):
        expected = query(uri(project, 'uncalled&type=function&top=0'))
        assert 'orphan' in {e['name'] for e in expected['entries']}
        assert 'unused' not in {e['name'] for e in expected['entries']}
        if transport == 'api':
            actual = query(uri(project, 'uncalled&top=0'), kind='function')
        elif transport == 'mcp':
            actual = mcp_json(uri(project, 'uncalled&kind=function&top=0'))
        else:
            result, actual = (cli_json('calls', str(project), '--uncalled', '--kind', 'function', '--top', '0')
                              if transport == 'cli' else cli_json(uri(project, 'uncalled&kind=function&top=0')))
            assert result.returncode == 0, result.stderr
        assert_equal_answer(actual, expected)

    @pytest.mark.parametrize('legacy,canonical', [('top=1', 'limit=1'), ('rank=callers', 'sort=-callers')])
    def test_legacy_vocabulary_keeps_answer_and_names_replacement(self, project, legacy, canonical):
        controls = 'rank=callers&top=1' if legacy.startswith('top') else legacy + '&top=1'
        result, answer = cli_json(uri(project, controls))
        assert result.returncode == 0
        assert len(answer['entries']) == 1
        assert_equal_answer(answer, query(uri(project, controls)))
        old = legacy.partition('=')[0]
        new = canonical.partition('=')[0]
        notes = [w for w in answer['meta']['warnings'] if w.get('type') == 'retired_spelling']
        assert any(old in w.get('message', '') and new in w.get('message', '') for w in notes), \
            f'legacy {old} must keep working with a retirement note naming {new}'

    @pytest.mark.parametrize('controls,replacement', [
        ('rank=callers&top=1&limit=2', 'limit'),
        ('rank=callers&sort=name', '-callers'),
        ('rank=callers&where=caller_count>1', '--callers'),
    ])
    def test_conflicts_and_unsupported_controls_reject_with_guidance(self, project, controls, replacement):
        good, baseline = cli_json(uri(project, 'rank=callers&top=1'))
        assert good.returncode == 0 and len(baseline['entries']) == 1
        result, answer = cli_json(uri(project, controls))
        assert_usage(result, answer, replacement)

    def test_equal_cap_aliases_are_accepted_once_not_ignored(self, project):
        expected = query(uri(project, 'rank=callers&top=2'))
        result, answer = cli_json(uri(project, 'rank=callers&top=2&limit=2'))
        assert result.returncode == 0
        assert_equal_answer(answer, expected)
        assert 'ignored' not in result.stderr
        assert 'limit' in {s.name for s in CallsAdapter.PARAM_SPECS}, 'limit needs a declared value owner'

    def test_canonical_query_after_failure_sees_edit_and_recovers(self, project):
        bad = run('calls', str(project), '--rank', 'callers', '--top', '1', '--output', f'json={project}')
        assert bad.returncode == 3
        (project / 'app.py').write_text('def only(): return 1\ndef use(): return only()\n', encoding='utf-8')
        expected = query(uri(project, 'rank=callers&top=0'))
        assert [e['name'] for e in expected['entries']] == ['only']
        actual = query(uri(project, ''), sort='-callers', limit=0)
        assert_equal_answer(actual, expected)

    def test_canonical_limit_keeps_output_failure_exit_three(self, project):
        baseline = run('calls', str(project), '--rank', 'callers', '--top', '1', '--output', f'json={project}')
        assert baseline.returncode == 3
        result, answer = cli_json('calls', str(project), '--sort=-callers', '--limit', '1',
                                  '--output', f'json={project}')
        assert result.returncode == 3, f'required output failure must win, got {result.returncode}: {result.stderr}'
        assert len(answer['entries']) == 1
