"""The retired ``stats://`` refuses a positional element as ``metrics://`` and ``api.query`` do (BACK-2694).

A declared noun reads no positional element (BACK-2522, BACK-2687): ``reveal metrics://P a.py`` and
``api.query('stats://P', 'a.py')`` give the one refusal naming the URI form. The CLI's ``stats://P a.py`` took the
generic element route instead: an existing file answered a ``stats_element`` document (exit 0) and any other name said
"Element 'x' not found". It now refuses with the shared message on the CLI too (the class already binds its query as a
declared noun does: ``uses_bound_query_call``); a file's metrics are ``reveal metrics P/a.py``.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.base import get_adapter_class, unread_element_message
from reveal.errors import RequestValidationError


@pytest.fixture
def proj(tmp_path, monkeypatch):
    (tmp_path / 'a.py').write_text('def f(x):\n    return x\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _refusal(scheme, element):
    return unread_element_message(get_adapter_class(scheme), scheme, element)


@pytest.mark.parametrize('element', ['a.py', 'missing.py'])
def test_the_cli_refuses_the_element_with_the_shared_message(proj, element):
    run = _run_reveal_direct('stats://.', element)
    assert run.returncode == 2, (run.returncode, run.stdout[:300], run.stderr)
    assert _refusal('stats', element) in run.stderr, run.stderr
    assert 'not found' not in run.stderr


@pytest.mark.parametrize('element', ['a.py', 'missing.py'])
def test_the_json_envelope_is_an_invalid_request_as_on_metrics(proj, element):
    docs = {}
    for scheme in ('stats', 'metrics'):
        run = _run_reveal_direct(f'{scheme}://.', element, '--format', 'json')
        assert run.returncode == 2, (scheme, run.stdout[:300], run.stderr)
        docs[scheme] = json.loads(run.stdout)
    assert docs['stats']['error'] == _refusal('stats', element)
    assert [e['code'] for e in docs['stats']['meta']['errors']] == ['invalid_request']
    assert [e['code'] for e in docs['metrics']['meta']['errors']] == ['invalid_request']


def test_the_cli_and_the_api_say_the_same(proj):
    from reveal import api
    with pytest.raises(RequestValidationError) as raised:
        api.query('stats://.', 'a.py')
    assert str(raised.value) == _refusal('stats', 'a.py')
    run = _run_reveal_direct('stats://.', 'a.py')
    assert str(raised.value) in run.stderr


def test_stats_without_an_element_still_answers_with_its_note(proj):
    run = _run_reveal_direct('stats://.', '--format', 'json')
    assert run.returncode == 0, run.stderr
    doc = json.loads(run.stdout)
    assert doc['type'] == 'stats_summary'
    assert any(w.get('code') == 'retired_spelling' and 'stats://' in w['message'] for w in doc['meta']['warnings'])
