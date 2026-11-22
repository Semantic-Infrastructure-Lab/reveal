"""A control that requires another control's value (Scott 2026-11-18, COMMAND_MODEL "Applicability", BACK-2656).

Metrics ``since`` and ``merges`` bound the churn walk, so they require ``churn`` on: given with ``churn off`` (or the
legacy ``--no-churn``) the request conflicts with itself and exits 2 before analysis, naming both. One generic
declaration on the control (``ParamSpec.requires``), checked by the shared applicability seam on every transport; no
metrics-only code path. Before, the request answered and the ledger noted since/merges unused, exit 0.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.errors import RequestValidationError


@pytest.fixture
def proj(tmp_path, monkeypatch):
    (tmp_path / 'app.py').write_text('def serve(x):\n    if x:\n        return 1\n    return 2\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _run(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run, (json.loads(run.stdout) if run.stdout.strip().startswith('{') else {})


@pytest.mark.parametrize('argv,control,given', [
    (('metrics://.?view=hotspots&churn=off&since=2020-01-01',), 'since', 'churn=off'),
    (('metrics://.?view=hotspots&churn=off&merges=off',), 'merges', 'churn=off'),
    (('metrics://.?hotspots&no_churn=true&since=2020-01-01',), 'since', 'churn=off'),   # the legacy spelling
    (('metrics', '.', '--view', 'hotspots', '--churn', 'off', '--since', '2020-01-01'), 'since', 'churn=off'),
    (('metrics', '.', '--view', 'hotspots', '--no-churn', '--merges', 'on'), 'merges', 'churn=off'),
    (('metrics://.?view=hotspots&churn=off', '--since', '2020-01-01'), 'since', 'churn=off'),
])
def test_since_and_merges_with_churn_off_conflict(proj, argv, control, given):
    run, _doc = _run(*argv)
    assert run.returncode == 2, (run.returncode, run.stdout[:300], run.stderr)
    assert f"control '{control}' requires churn=on" in run.stderr and given in run.stderr, run.stderr


def test_the_api_refuses_the_same_request(proj):
    from reveal import api
    with pytest.raises(RequestValidationError, match=r"control 'since' requires churn=on"):
        api.query('metrics://.?view=hotspots&churn=off&since=2020-01-01')
    with pytest.raises(RequestValidationError, match=r"control 'merges' requires churn=on"):
        api.query('metrics://.?view=hotspots', churn=False, merges=False)


@pytest.mark.parametrize('uri', ['metrics://.?view=hotspots&since=2020-01-01',           # churn on by default
                                 'metrics://.?view=hotspots&churn=on&since=2020-01-01&merges=off',
                                 'metrics://.?view=hotspots&churn=off',                    # churn off alone
                                 'metrics://.?hotspots&no_churn=true'])
def test_churn_on_with_its_bounds_and_churn_off_alone_answer(proj, uri):
    run, doc = _run(uri)
    assert run.returncode == 0, run.stderr
    assert doc['type'] == 'stats_summary'


# --- the shared declaration (unit) ---------------------------------------------------------------------------------

from reveal.utils.query_binding import (bind_prepared_params, prepare_declared_params,  # noqa: E402
                                        reject_unread_controls, switch_value)
from reveal.utils.query_parser import ParamSpec  # noqa: E402

SWITCH = ParamSpec('walk', 'boolean', 'a switch, on by default', True, switch_value)
BOUND = ParamSpec('bound', 'string', 'needs the walk', None, str, requires=('walk=on',))
FREE = ParamSpec('free', 'string', 'needs nothing', None, str)
PICK = ParamSpec('pick', 'string', 'one way to narrow', None, str)
FIND = ParamSpec('find', 'string', 'another way to narrow', None, str)
NARROWED = ParamSpec('narrowed', 'string', 'bounds a narrowed request', None, str, requires=('pick|find',))
SPECS = (SWITCH, BOUND, FREE, PICK, FIND, NARROWED)


def _check(query=None, **typed):
    if query is not None:
        params = bind_prepared_params(SPECS, prepare_declared_params(SPECS, query, 'uri'), transport='uri')
    else:
        params = bind_prepared_params(SPECS, prepare_declared_params(SPECS, typed, 'typed'), transport='typed')
    reject_unread_controls(SPECS, params, lambda: 'fixture')


@pytest.mark.parametrize('query', ['bound=x', 'walk=on&bound=x', 'walk=off', 'walk=off&free=y', ''])
def test_a_requirement_met_or_not_asked_answers(query):
    _check(query)


@pytest.mark.parametrize('request_', [{'query': 'walk=off&bound=x'}, {'walk': False, 'bound': 'x'},
                                      {'walk': 'off', 'bound': 'x'}])
def test_a_requirement_the_request_contradicts_is_an_invalid_request_naming_both(request_):
    with pytest.raises(RequestValidationError, match=r"control 'bound' requires walk=on; this request gives walk=off"):
        _check(**request_)


@pytest.mark.parametrize('query', ['narrowed=x&pick=a', 'narrowed=x&find=b', 'narrowed=x&pick=a&find=b', 'pick=a'])
def test_a_presence_requirement_met_by_any_alternative_answers(query):
    _check(query)


@pytest.mark.parametrize('request_', [{'query': 'narrowed=x'}, {'query': 'narrowed=x&free=y'}, {'narrowed': 'x'}])
def test_a_presence_requirement_with_no_alternative_given_is_an_invalid_request_naming_them(request_):
    with pytest.raises(RequestValidationError, match=r"control 'narrowed' requires pick or find; this request gives "
                                                     r"none of them: give one, or drop narrowed"):
        _check(**request_)


def test_the_requirement_is_published_in_the_schema():
    assert BOUND.schema()['requires'] == ['walk=on'] and 'requires' not in FREE.schema()


def test_every_declared_requirement_names_a_sibling_control_and_a_value_it_accepts():
    from test_vocabulary_conformance_back2654 import NOUNS, _adapter
    requirements = [(noun, spec, requirement) for noun in NOUNS for spec in _adapter(noun).PARAM_SPECS
                    for requirement in spec.requires]
    for noun, spec, requirement in requirements:
        for alternative in requirement.split('|'):
            other, sep, value = alternative.removeprefix('!').partition('=')  # '!name': name not given (BACK-2623)
            [sibling] = [s for s in _adapter(noun).PARAM_SPECS if s.name == other]
            assert other != spec.name, (noun, spec.name, requirement)
            if sep:
                sibling.validate(value)  # a value the required control accepts (raises otherwise)
