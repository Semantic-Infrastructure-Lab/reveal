"""Answer assertions for the exact README cross-file Calls examples (BACK-2448)."""
import copy
import json
import shlex

import pytest

from doc_command_fixture import build_calls_cohort_tree
import test_example_recipes_run as recipes
from test_output_contract_compliance import _Harness

pytestmark = pytest.mark.contract

SOURCE = '../../README.md'
CALLERS = "reveal 'calls://src/?callers=validate_token'"
IMPACT = "reveal 'calls://src/?callers=fn&depth=3'"
RANK = "reveal 'calls://src/?rank=callers&top=20'"
CALLEES = 'reveal calls src/ --callees main --depth 2 --detail'
COMMANDS = (CALLERS, IMPACT, RANK, CALLEES)


def _assert_inventory(docs=None):
    identities = {(source, shlex.join(tokens))
                  for source, _, tokens, _ in recipes._documented_commands(docs)}
    assert {(SOURCE, query) for query in COMMANDS} <= identities, (
        'README Calls examples disappeared or changed; requalify their answers')


@pytest.mark.parametrize('query', COMMANDS)
def test_advertised_calls_command_is_eligible(query):
    _assert_inventory()
    assert recipes._source_cohort_reason(SOURCE, shlex.split(query)) is None


def test_previous_navigation_cohort_remains_eligible():
    assert recipes._source_cohort_reason(SOURCE, shlex.split('reveal overview .')) is None


def test_unrelated_readme_examples_keep_their_explicit_exclusion():
    command = 'reveal pack src/ --focus auth --budget 6000'
    identities = {(source, shlex.join(tokens))
                  for source, _, tokens, _ in recipes._documented_commands()}
    assert (SOURCE, command) in identities
    assert 'not yet qualified' in recipes._source_cohort_reason(SOURCE, shlex.split(command))


def test_changed_advertised_example_fails_presence_guard(tmp_path):
    docs = tmp_path / 'reveal' / 'docs'
    docs.mkdir(parents=True)
    readme = tmp_path / 'README.md'
    readme.write_text('```bash\n' + '\n'.join(COMMANDS) + '\n```\n', encoding='utf-8')
    _assert_inventory(docs)
    readme.write_text(readme.read_text(encoding='utf-8').replace('depth=3', 'depth=2'), encoding='utf-8')
    with pytest.raises(AssertionError, match='disappeared or changed'):
        _assert_inventory(docs)


@pytest.fixture
def calls_harness(tmp_path):
    return _Harness(build_calls_cohort_tree(tmp_path))


def _answer(harness, query):
    output = recipes._assert_text_as_written(harness, query + ' --format json', literal=True)
    return json.loads(output)


def _assert_callers(query, answer):
    assert answer['type'] == 'calls_query'
    if query == CALLERS:
        assert answer['target'] == 'validate_token' and answer['depth'] == 1
        expected = {1: {('src/auth.py', 'fn', 'validate_token'),
                        ('src/service.py', 'authenticate', 'validate_token')}}
    else:
        assert answer['target'] == 'fn' and answer['depth'] == 3
        expected = {1: {('src/service.py', 'invoke_fn', 'fn')},
                    2: {('src/main.py', 'main', 'invoke_fn')},
                    3: {('src/cli.py', 'cli', 'main')}}
    assert answer['total_callers'] == sum(map(len, expected.values()))
    assert {level['level']: {(row['file'], row['caller'], row['callee']) for row in level['callers']}
            for level in answer['levels']} == expected


def _assert_rank(answer):
    assert answer['type'] == 'calls_ranking' and answer['top'] == 20
    assert answer['total_unique_callees'] == 30 and len(answer['entries']) == 20
    counts = {'validate_token': 2, 'fn': 1, 'authenticate': 1, 'invoke_fn': 1, 'main': 1,
              **{f'ranked_{n:02}': 1 for n in range(25)}}
    assert len({row['name'] for row in answer['entries']}) == 20
    assert all(row['name'] in counts and row['caller_count'] == counts[row['name']]
               for row in answer['entries'])
    assert answer['entries'][0]['name'] == 'validate_token'
    assert answer['undefined_callees'] > 0 and 'defined under the path' in answer['rule']


def _assert_callees(answer):
    assert answer['type'] == 'calls_callees' and answer['target'] == 'main' and answer['depth'] == 2
    resolved = {(level['level'], row['caller'], row['callee'], row['caller_file'], row['callee_file'])
                for level in answer['levels'] for row in level['callees'] if row['resolved']}
    assert resolved == {
        (1, 'main', 'authenticate', 'src/main.py', 'src/service.py'),
        (1, 'main', 'invoke_fn', 'src/main.py', 'src/service.py'),
        (2, 'authenticate', 'validate_token', 'src/service.py', 'src/auth.py'),
        (2, 'invoke_fn', 'fn', 'src/service.py', 'src/auth.py')}
    assert answer['total_resolved'] == 4 and answer['total_ambiguous'] == 0
    assert answer['total_unresolved'] == 2 and answer['total_edges'] == 6
    definitions = {row['name']: row for row in answer['definitions']}
    assert set(definitions) == {'main', 'authenticate', 'invoke_fn', 'fn', 'validate_token'}
    assert definitions['main']['level'] == 0 and definitions['main']['expanded']
    assert definitions['authenticate']['level'] == 1 and definitions['authenticate']['expanded']
    assert definitions['validate_token']['level'] == 2 and not definitions['validate_token']['expanded']
    assert definitions['main']['params'] == definitions['authenticate']['params'] == ['value']
    assert definitions['validate_token']['params'] == ['token']
    assert definitions['authenticate']['effects'] == ['file:copy']
    # This fixture qualifies the example, not a corpus measurement of deep walks/detail.
    assert answer['walk_rule']['measured'] == {'depth_1': True, 'beyond_depth_1': False, 'detail': False}


def _assert_answer(query, answer):
    if query in (CALLERS, IMPACT):
        _assert_callers(query, answer)
    elif query == RANK:
        _assert_rank(answer)
    else:
        assert query == CALLEES
        _assert_callees(answer)


@pytest.mark.parametrize('query', COMMANDS)
def test_exact_readme_calls_command_answers(calls_harness, query):
    _assert_inventory()
    text = recipes._assert_text_as_written(calls_harness, query, literal=True)
    _assert_answer(query, _answer(calls_harness, query))
    if query == CALLEES:
        assert 'params: value' in text and 'effects: file:copy' in text
        assert 'not measured' in text


@pytest.mark.parametrize('query,defect', [
    (CALLERS, 'wrong_file'), (IMPACT, 'lost_depth'), (RANK, 'ranked_builtin'), (RANK, 'ignored_top'),
    (CALLEES, 'lost_effect'), (CALLEES, 'lost_params'), (CALLEES, 'claimed_measurement'),
])
def test_successful_but_wrong_answers_fail_semantic_guards(calls_harness, query, defect):
    answer = _answer(calls_harness, query)
    _assert_answer(query, answer)
    wrong = copy.deepcopy(answer)
    if defect == 'wrong_file':
        wrong['levels'][0]['callers'][0]['file'] = 'src/not_the_caller.py'
    elif defect == 'lost_depth':
        wrong['levels'] = wrong['levels'][:2]
    elif defect == 'ranked_builtin':
        wrong['entries'][0]['name'] = 'append'
    elif defect == 'ignored_top':
        wrong['entries'] = wrong['entries'][:10]
    elif defect == 'lost_effect':
        next(row for row in wrong['definitions'] if row['name'] == 'authenticate')['effects'] = []
    elif defect == 'lost_params':
        next(row for row in wrong['definitions'] if row['name'] == 'main')['params'] = []
    else:
        wrong['walk_rule']['measured']['detail'] = True
    with pytest.raises(AssertionError):
        _assert_answer(query, wrong)
