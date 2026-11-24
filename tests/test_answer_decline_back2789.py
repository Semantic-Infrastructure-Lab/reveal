"""``typed.answer_decline`` builds the declined answer the CLI's declared route gives a ``NotApplicableError`` (exit 0,
BACK-1210): the router's not-applicable result (``applicable: false``, the reason, a ``not_applicable`` warning and the
declared controls the adapter never read), typed as the route predicts the request's answer, ``source`` the path the
resource names (BACK-2789)."""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.patches.adapter import PatchesAdapter
from reveal.cli.routing.typed import answer_decline
from reveal.errors import NotApplicableError
from reveal.utils.query_binding import bind_declared_params, prepare_declared_params
from reveal.utils.query_parser import collect_query_keys
from reveal.utils.results import execution_failed


@pytest.fixture
def notests(tmp_path, monkeypatch):
    (tmp_path / 'notests').mkdir()
    (tmp_path / 'notests' / 'app.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return 'notests'


def _declined(path, query=''):
    params = bind_declared_params(PatchesAdapter.PARAM_SPECS, query, transport='uri')
    adapter = PatchesAdapter(path, params=params)
    with pytest.raises(NotApplicableError) as raised:
        adapter.get_structure()
    return answer_decline(adapter, 'patches', path, prepare_declared_params(PatchesAdapter.PARAM_SPECS, query, 'uri'),
                          raised.value), raised.value


def test_the_decline_is_the_routes_not_applicable_answer(notests):
    declined, error = _declined(notests)
    assert declined['applicable'] is False
    assert declined['reason'] == error.reason
    assert declined['type'] == 'patches_scan'  # the predicted type, not the scheme
    assert declined['source'] == 'notests' and declined['source_type'] == 'directory'
    assert [w['type'] for w in declined['meta']['warnings']] == ['not_applicable']


def test_it_equals_the_clis_document(notests):
    run = _run_reveal_direct('patches', notests, '--format', 'json')
    assert run.returncode == 0
    declined, _error = _declined(notests)
    assert declined == json.loads(run.stdout)


def test_a_control_the_answer_never_read_is_named_inside_a_dispatch_that_records_reads(notests):
    """The CLI's dispatch records the keys the adapter reads (its ledger); a decline names the given ones it never read."""
    with collect_query_keys(warnings_to_stderr=False):
        declined, _error = _declined(notests, 'limit=3')
    unread = [w for w in declined['meta']['warnings'] if w['type'] != 'not_applicable']
    assert [(w['type'], w['fields']) for w in unread] == [('control_unread_by_data', ['limit'])]


def test_control_outside_a_dispatch_that_records_reads_nothing_is_named(notests):
    declined, _error = _declined(notests, 'limit=3')
    assert [w['type'] for w in declined['meta']['warnings']] == ['not_applicable']


def test_the_decline_is_no_failure(notests):
    declined, _error = _declined(notests)
    facts = PatchesAdapter.execution_facts(declined)
    assert facts is None or not execution_failed(facts)


def test_without_params_the_type_is_the_routers_own(notests):
    params = bind_declared_params(PatchesAdapter.PARAM_SPECS, '', transport='uri')
    adapter = PatchesAdapter(notests, params=params)
    declined = answer_decline(adapter, 'patches', notests, None, NotApplicableError('no tests'))
    assert declined['type'] == 'patches' and declined['reason'] == 'no tests' and declined['applicable'] is False
