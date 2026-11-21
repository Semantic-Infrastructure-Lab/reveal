"""BACK-2622: overview's vocabulary under D20 (Scott 2026-11-20 decisions A, B, C).

--limit caps each map section and 0 is uncapped; the legacy top keeps its own zero (no graph rows) with a note until the
cut, and top/limit with different meanings exit 2. --imports on|off is the switch, --no-imports its legacy word. The
comparison's population is four times the limit, the whole population at 0. --all stays the shared uncapping word.
"""
import json
import shlex

import pytest
from conftest import _run_reveal_direct as run
from test_architecture_alias_back2377 import project  # noqa: F401  (the fixture: seven components)

from reveal import api
from reveal.errors import RequestValidationError

ROWS = 7  # components the fixture observes


def _components(answer):
    return answer['map']['components']['returned']


def _noted(answer, key):
    return [w for w in answer['meta']['warnings'] if w.get('field') == key]


def _cli(*argv):
    response = run(*argv, '--format', 'json')
    return response.returncode, json.loads(response.stdout), response.stderr


def test_limit_caps_each_section_and_zero_is_uncapped(project):  # noqa: F811
    assert _components(api.query('overview', str(project))) == 5
    assert _components(api.query('overview', str(project), limit=2)) == 2
    assert _components(api.query('overview', str(project), limit=0)) == ROWS
    assert _components(api.query('overview', str(project), all=True)) == ROWS  # decision A: --all stays


def test_legacy_top_keeps_its_zero_with_a_note(project):  # noqa: F811
    code, answer, _ = _cli('overview', str(project), '--top', '0')
    assert code == 0 and _components(answer) == 0  # no graph rows, as before
    assert [w['replacement'] for w in _noted(answer, 'param:overview.top')] == [
        '--limit N, which caps each map section; 0 is uncapped']
    code, answer, _ = _cli('overview', str(project), '--top', '2')
    assert code == 0 and _components(answer) == 2


@pytest.mark.parametrize('top,limit,refused', [('2', '2', False), ('2', '3', True), ('0', '0', True)])
def test_top_and_limit_together_are_one_request_only_when_they_mean_the_same(project, top, limit,  # noqa: F811
                                                                              refused):
    response = run('overview', str(project), '--top', top, '--limit', limit, '--format', 'json')
    assert response.returncode == (2 if refused else 0), response.stderr
    if refused:
        assert f'top={top} conflicts with limit={limit}' in response.stderr
        with pytest.raises(RequestValidationError, match='conflicts with limit'):
            api.query('overview', str(project), top=int(top), limit=int(limit))


def test_imports_is_a_switch_and_no_imports_its_legacy_word(project):  # noqa: F811
    _, off, _ = _cli('overview', str(project), '--imports', 'off')
    code, legacy, _ = _cli('overview', str(project), '--no-imports')
    assert code == 0 and off['map_status'] == legacy['map_status'] == 'not_requested'
    assert [w['replacement'] for w in _noted(legacy, 'param:overview.no_imports')] == ['--imports off']
    assert _noted(off, 'param:overview.no_imports') == []
    assert api.query('overview', str(project), imports='on')['map_status'] == 'complete'


def test_the_request_note_spells_the_switch_on_or_off(project):  # noqa: F811
    _, answer, _ = _cli(f'overview://{project.as_posix()}?no_imports=true')
    notes = [w['replacement'] for w in answer['meta']['warnings'] if w.get('field') == 'request:overview']
    assert notes == [f'reveal overview {shlex.quote(project.as_posix())} --imports off'], notes


def test_api_verbose_answers_as_the_flag_does(project):  # noqa: F811
    """The global --verbose is overview's legacy word of --all; the API keyword raised 'unsupported control'."""
    answer = api.query('overview', str(project), verbose=True)
    assert _components(answer) == ROWS
    assert [w['field'] for w in answer['meta']['warnings'] if w.get('type') == 'retired_spelling'] == [
        'param:overview.verbose']


def test_the_comparison_population_follows_the_limit():
    """Decision C: population 4 x limit (every current answer unchanged), the whole population at --limit 0, and the
    legacy top=0 keeps population 4."""
    from reveal.adapters.overview import _section_rows
    from reveal.defaults import UNLIMITED_TOP
    populations = [_section_rows(params)[1] for params in ({}, {'limit': 3}, {'limit': 0}, {'top': 0}, {'top': 2})]
    assert populations == [20, 12, UNLIMITED_TOP, 4, 8]
