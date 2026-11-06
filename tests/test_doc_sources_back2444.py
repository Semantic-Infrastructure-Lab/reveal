"""Canonical source inventory and answer controls for the bounded docs cohort."""

import copy
import json
import shlex
import shutil
from pathlib import Path

import pytest

from doc_command_fixture import build_navigation_cohort_tree
from test_example_recipes_run import (
    DOC_SOURCE_COHORT, DOC_NAMED_SOURCE_COHORT, RUN_SOURCES,
    _documented_commands, _documented_sources, _source_cohort_reason,
    _assert_text_as_written,
)
from test_output_contract_compliance import _Harness

pytestmark = pytest.mark.contract


def test_collector_includes_canonical_sources_with_distinct_provenance(tmp_path):
    docs = tmp_path / 'reveal' / 'docs'
    examples = {
        tmp_path / 'README.md': 'reveal overview .',
        docs / 'AGENT_HELP.md': 'reveal help://quick',
        docs / 'guides' / 'SAME.md': 'reveal env://',
        docs / 'adapters' / 'SAME.md': 'reveal imports .',
        docs / 'QUICK_START.md': 'reveal src/',
        docs / 'WHY_REVEAL.md': 'reveal app.py',
        docs / 'INDEX.md': 'reveal help://adapters',
    }
    for source, command in examples.items():
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f'```bash\n{command}\n```\n', encoding='utf-8')
    rows = list(_documented_commands(docs))
    assert {row[0] for row in rows} == {
        '../../README.md', 'AGENT_HELP.md', 'guides/SAME.md', 'adapters/SAME.md',
        'QUICK_START.md', 'WHY_REVEAL.md', 'INDEX.md',
    }
    assert {row[1] for row in rows} == set(examples.values())


def test_legacy_guide_remains_collected(tmp_path):
    (tmp_path / 'guides').mkdir()
    (tmp_path / 'AGENT_HELP.md').write_text('```bash\nreveal help://quick\n```', encoding='utf-8')
    (tmp_path / 'guides' / 'EXAMPLE.md').write_text('```bash\nreveal app.py\n```', encoding='utf-8')
    assert {row[1] for row in _documented_commands(tmp_path)} == {'reveal help://quick', 'reveal app.py'}


@pytest.fixture
def navigation_harness(tmp_path):
    if not shutil.which('git'):
        pytest.skip('navigation cohort requires git history')
    pytest.importorskip('pygit2')
    return _Harness(build_navigation_cohort_tree(tmp_path))


def _assert_navigation_answer(query, answer):
    """Check claims against the independent, tiny on-disk fixture, not just exit 0."""
    if '--against' in query:
        assert answer['type'] == 'overview_diff'
        assert answer['analysis']['complete'] is True
        delta = answer['deltas']
        assert delta['fan_in'] == delta['fan_out'] == delta['component_coupling'] == []
        assert delta['circular_groups'] == {'introduced': [], 'resolved': []}
        assert delta['entry_points'] == {'added': [], 'removed': []}
        assert delta['complexity_centroid']['change'] == 0
    elif query.startswith('reveal overview'):
        assert answer['type'] == 'overview' and answer['map_status'] == 'complete'
        assert answer['scope']['total_code_files'] == 3
        assert {row['language']: row['files'] for row in answer['scope']['languages']} == {'Go': 2, 'Python': 1}
        assert answer['map']['fan_in']['total'] == 1
        if '--top 0' in query:
            assert answer['map']['fan_in']['rows'] == []
            assert answer['map']['fan_in']['omitted'] == 1
        else:
            assert answer['map']['fan_in']['rows'] == [{'file': 'src/helper', 'fan_in': 1, 'fan_out': 0}]
    elif '--external' in query:
        assert answer['type'] == 'external_packages'
        assert answer['stdlib_packages'] == [{'package': 'os', 'uses': 1}]
        assert answer['external_packages'] == [] and answer['internal_imports'] == 1
    elif query == 'reveal imports://src':
        assert answer['type'] == 'imports'
        assert answer['files']['main.go'][0]['resolved'] == 'helper'
        assert answer['files']['app.py'][0]['classification'] == 'stdlib'
    elif '?aggregate=' in query:
        assert answer['type'] == 'markdown_aggregate'
        assert answer['matched_files'] == answer['total_files'] == 3
        assert answer['files_missing_field'] == 1
        assert {row['value']: row['count'] for row in answer['aggregate']} == {'guide': 1, 'procedure': 1}
    else:
        assert answer['type'] == 'markdown_query'
        assert answer['matched_files'] == 1
        assert [row['path'] for row in answer['results']] == ['docs/retry.md']


@pytest.mark.parametrize('source,query', sorted(DOC_SOURCE_COHORT))
def test_qualified_source_command_answers(navigation_harness, source, query):
    inventory = {(name, shlex.join(tokens)) for name, _, tokens, _ in _documented_commands()}
    assert (source, query) in inventory, 'qualified command disappeared or changed; requalify its answer'
    assert _source_cohort_reason(source, shlex.split(query)) is None
    _assert_text_as_written(navigation_harness, query, literal=True)
    argv = shlex.split(query)[1:]
    code, out, _, _ = navigation_harness.run_subcommand(*argv, '--format', 'json')
    assert code == 0
    _assert_navigation_answer(query, json.loads(out))


def test_new_source_exclusions_are_explicit_and_legacy_sources_still_run():
    rows = list(_documented_commands())
    identities = {(source, shlex.join(tokens)) for source, _, tokens, _ in rows}
    assert DOC_NAMED_SOURCE_COHORT <= identities
    reasons = [_source_cohort_reason(source, tokens) for source, _, tokens, _ in rows]
    # Every inventoried source now runs whole, its embedded Markdown included (BACK-1365).
    assert [(source, reason) for (source, _, _, _), reason in zip(rows, reasons) if reason] == []
    assert any(source == '../../README.md#embedded-md' for source, _, _, _ in rows)
    sources ={name for name, _ in _documented_sources(Path(__file__).parents[1] / 'reveal' / 'docs')}
    assert {'../../README.md', 'QUICK_START.md', 'WHY_REVEAL.md', 'INDEX.md',
            'adapters/IMPORTS_ADAPTER_GUIDE.md', 'adapters/OVERVIEW_ADAPTER_GUIDE.md',
            'adapters/MARKDOWN_GUIDE.md'} <= sources


def test_first_contact_sources_run_their_own_commands():
    """QUICK_START, WHY_REVEAL and the README (its embedded table too) are executed, not only
    inventoried (BACK-1365): a collector or cohort change that skips them again fails here."""
    from test_example_recipes_run import _named_fixture_commands
    floors = {'QUICK_START.md': 10, 'WHY_REVEAL.md': 10, '../../README.md': 4,
              '../../README.md#embedded-md': 5}
    for source, floor in floors.items():
        params = [p for p in _named_fixture_commands() if p.id.startswith(source + ':')]
        run = [p for p in params if not any(m.name == 'skip' for m in p.marks)]
        assert len(run) >= floor, (source, len(params), len(run))
        assert not any('not yet qualified' in m.kwargs.get('reason', '')
                       for p in params for m in p.marks), source


def test_neutral_go_edit_preserves_advertised_comparison(navigation_harness):
    root = navigation_harness.root
    source = root / 'src' / 'main.go'
    source.write_text(source.read_text(encoding='utf-8') + '// comment only\n', encoding='utf-8')
    query = 'reveal overview . --against HEAD'
    code, out, _, _ = navigation_harness.run_subcommand('overview', '.', '--against', 'HEAD', '--format', 'json')
    assert code == 0
    answer = json.loads(out)
    assert answer['analysis']['basis'] != 'identical_tree'
    _assert_navigation_answer(query, answer)
    altered = copy.deepcopy(answer)
    altered['deltas']['fan_in'] = [{'file': 'src/helper', 'change': -1}]
    with pytest.raises(AssertionError):
        _assert_navigation_answer(query, altered)


def test_answer_guard_rejects_successful_but_wrong_aggregate(navigation_harness):
    query = "reveal 'markdown://docs/?aggregate=type'"
    code, out, _, _ = navigation_harness.run_subcommand('markdown://docs/?aggregate=type', '--format', 'json')
    assert code == 0
    answer = json.loads(out)
    _assert_navigation_answer(query, answer)
    answer['files_missing_field'] = 0
    with pytest.raises(AssertionError):
        _assert_navigation_answer(query, answer)


def test_incomplete_markdown_keeps_partial_answer_and_failure(navigation_harness, monkeypatch):
    read_text = Path.read_text
    lost = (navigation_harness.root / 'docs' / 'retry.md').resolve()

    def denied(path, *args, **kwargs):
        if path.resolve() == lost:
            raise PermissionError('fixture read denied')
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', denied)
    code, out, _, _ = navigation_harness.run_subcommand('markdown://docs/?aggregate=type', '--format', 'json')
    answer = json.loads(out)
    assert code == 3
    assert answer['analysis']['failed_files'] == 1
    assert answer['matched_files'] == 2
    assert answer['aggregate'] == [{'value': 'guide', 'count': 1}]
    assert any(w['type'] == 'unreadable_files' for w in answer['meta']['warnings'])
    sibling_code, sibling_out, _, _ = navigation_harness.run_subcommand('imports', '.', '--external', '--format', 'json')
    assert sibling_code == 0
    _assert_navigation_answer('reveal imports . --external', json.loads(sibling_out))


def test_adapter_guides_run_their_own_commands():
    """Every adapter guide is a run source (BACK-2518): none of its commands is excluded as
    unqualified, and the guides that have runnable examples run them."""
    from test_example_recipes_run import _named_fixture_commands
    params = _named_fixture_commands()
    by_source = {}
    for p in params:
        source = p.id.split(':', 1)[0]
        if source.startswith('adapters/'):
            by_source.setdefault(source, []).append(p)
    assert len(by_source) >= 12, sorted(by_source)
    for source, group in by_source.items():
        assert not any('not yet qualified' in m.kwargs.get('reason', '')
                       for p in group for m in p.marks), source
    for source, floor in (('AST', 10), ('CALLS', 10), ('JSON', 10), ('CLAUDE', 10), ('CODEX', 4), ('GIT', 10)):
        group = by_source[f'adapters/{source}_ADAPTER_GUIDE.md']
        run = [p for p in group if not any(m.name == 'skip' for m in p.marks)]
        assert len(run) >= floor, (source, len(group), len(run))


def test_harness_reads_the_guides_ast_type_spellings():
    """?type=a,b and a|b are OR and `method` is a function row with an owner: the AST guide's own
    examples must not be read as contradicting their query (BACK-2518)."""
    from test_example_recipes_run import _row_matches, _findings_exits, _DOCUMENTED_FAILURE
    function = {'category': 'functions', 'name': 'f', 'owner': None}
    method = {'category': 'functions', 'name': 'm', 'owner': 'C'}
    klass = {'category': 'classes', 'name': 'C'}
    for spelling in ('class,function', 'class|function'):
        assert all(_row_matches('ast_query', 'type', '=', spelling, r, None) for r in (function, method, klass))
        assert not _row_matches('ast_query', 'type', '=', 'class|method', function, None)
    assert _row_matches('ast_query', 'type', '=', 'method', method, None)
    assert not _row_matches('ast_query', 'type', '=', 'method', function, None)
    assert _findings_exits(['imports://src?circular', '--fail-on', 'findings']) == {0, 1}
    assert _DOCUMENTED_FAILURE.search('reveal env://MY_VAR=value  # Error')
    assert not _DOCUMENTED_FAILURE.search('reveal env://MY_VAR')
