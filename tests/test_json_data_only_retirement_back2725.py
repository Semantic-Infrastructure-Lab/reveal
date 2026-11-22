"""JSON ``?gron&data-only`` (``?flatten&data-only``) is a standalone legacy spelling with its own note (BACK-2725).

It answers the flatten lines as a bare JSON array, which ``--view flatten --detail raw`` does not (the lines inside the
JSON envelope), so it translates to nothing (COMMAND_MODEL "Legacy operations": a legacy spelling is translated only
when its answer is identical). It was a ``where`` term the adapter took back after binding, so the generic json://
request note recommended a different answer: ``reveal json://F --view flatten`` on the CLI and
``api.query("json://F", view='flatten', where=['data-only'])`` in Python. It is now its own declared control with no
flag and a standalone ``param:json.data-only`` RETIREMENTS row: the request has no canonical form, so the one note is
the row's, on every transport, and the answer is unchanged.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.cli.invocation import RETIREMENTS, request_note_covers

ROW = RETIREMENTS.get('param:json.data-only')


@pytest.fixture
def data(tmp_path, monkeypatch):
    (tmp_path / 'd.json').write_text('{"a": {"b": [1, 2]}, "c": "x"}', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


LINES = ['json = {}', 'json.a = {}', 'json.a.b = []', 'json.a.b[0] = 1', 'json.a.b[1] = 2', 'json.c = "x"']


def test_the_row_is_a_standalone_note_naming_the_enveloped_replacement():
    assert ROW is not None and ROW.stage == 'note' and ROW.standalone and not ROW.removed
    assert '--view flatten --detail raw' in ROW.replacement
    assert not request_note_covers('param:json.data-only')


@pytest.mark.parametrize('selector', ['gron', 'flatten', 'view=flatten'])
def test_the_cli_notes_the_row_and_no_request_note(data, selector):
    for argv in (('json://d.json?%s&data-only' % selector,), ('json://d.json?%s&data-only' % selector, '--format', 'json')):
        run = _run_reveal_direct(*argv)
        assert run.returncode == 0, run.stderr
        assert f'note: {ROW.text}' in run.stderr.splitlines(), run.stderr
        assert 'a json:// request' not in run.stderr, run.stderr
        if '--format' in argv:
            assert json.loads(run.stdout) == LINES  # the bare legacy array, unchanged
        else:
            assert run.stdout.splitlines() == LINES


def test_the_api_notes_the_row_and_never_teaches_a_where_term(data):
    from reveal import api
    result = api.query('json://d.json?gron&data-only')
    assert result['lines'] == LINES and result.get('data_only') is True
    warnings = result['meta']['warnings']
    assert [w['field'] for w in warnings if w.get('code') == 'retired_spelling'] == ['param:json.data-only']
    assert 'data-only' not in json.dumps([w for w in warnings if w['field'] != 'param:json.data-only'])


@pytest.mark.parametrize('uri,replacement', [
    ('json://d.json?gron', 'reveal json://d.json --view flatten'),
    ('json://d.json?gron&detail=raw', 'reveal json://d.json --view flatten --detail raw'),
])
def test_a_translatable_flatten_request_keeps_its_request_note(data, uri, replacement):
    run = _run_reveal_direct(uri)
    assert run.returncode == 0, run.stderr
    assert f'use {replacement}.' in run.stderr, run.stderr
    assert 'data-only' not in run.stderr


def test_data_only_outside_the_flatten_answer_is_refused(data):
    run = _run_reveal_direct('json://d.json?keys&data-only')
    assert run.returncode == 2
    assert "control 'data-only' is not read by this answer" in run.stderr, run.stderr
