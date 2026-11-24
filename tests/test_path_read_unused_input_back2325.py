"""A path read's JSON carries the flag ledger's unused-input facts in ``meta.warnings``; it prints no note on stderr
(BACK-2325, ruling STOP 2 (a)).

``reveal ok.py --links --format json`` printed ``Note: --links has no effect on the file view ...`` on stderr and an empty
``meta.warnings``, and ``api.analyze('ok.py', links=True)`` printed that CLI note on the caller's stderr. A declared noun's
JSON carries the fact as a structured warning (``unused_flag``, the flag in ``fields``) and says nothing on stderr; the
path read now does the same, on the CLI and through the API (whose document equals the CLI's). Text output keeps its
stderr note.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api

OK_PY = 'import os\n\n\ndef foo():\n    return 1\n'

# argv, the view the text note names
READS = [
    (['ok.py', '--links'], 'the file view'),
    (['ok.py', '--since', 'HEAD'], 'the file view'),
    (['ok.py', '--typed', '--links'], 'the file view'),
    (['d', '--links'], 'a directory listing'),
    (['d', '--files', '--links'], 'a directory listing'),
    (['ok.py', '--grep', 'foo', '--links'], 'the file view'),
    (['d', '--grep', 'foo', '--links'], 'a directory listing'),
    (['ok.py', 'foo', '--links'], 'the file view'),
]
API = [('ok.py', {'links': True}), ('ok.py', {'since': 'HEAD'}), ('d', {'links': True}),
       ('d', {'files': True, 'links': True}), ('ok.py', {'grep': 'foo', 'links': True}),
       ('ok.py', {'name': 'foo', 'links': True})]


@pytest.fixture
def fx(tmp_path, monkeypatch):
    (tmp_path / 'ok.py').write_text(OK_PY, encoding='utf-8')
    (tmp_path / 'd').mkdir()
    (tmp_path / 'd' / 'a.py').write_text(OK_PY, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _flag(argv):
    return [word for word in argv if word in ('--links', '--since')]


def _unused(document):
    return [w for w in document['meta']['warnings'] if w.get('code') == 'unused_flag']


@pytest.mark.parametrize('argv, view', READS, ids=[' '.join(r[0]) for r in READS])
def test_the_json_carries_the_fact_and_stderr_says_nothing(fx, argv, view):
    run = _run_reveal_direct(*argv, '--format', 'json')
    assert run.returncode == 0, run.stderr
    assert 'has no effect' not in run.stderr
    fields = _flag(argv)
    assert _unused(json.loads(run.stdout)) == [{
        'type': 'unused_flag', 'code': 'unused_flag', 'fields': fields,
        'message': f"Input {', '.join(fields)} has no effect for this operation."}]


@pytest.mark.parametrize('argv, view', READS, ids=[' '.join(r[0]) for r in READS])
def test_sibling_text_keeps_its_note(fx, argv, view):
    run = _run_reveal_direct(*argv)
    assert run.returncode == 0
    assert f"Note: {', '.join(_flag(argv))} has no effect on {view} -- this view does not use it." in run.stderr


@pytest.mark.parametrize('path, keywords', API, ids=[f'{p} {sorted(k)}' for p, k in API])
def test_the_api_returns_the_fact_and_prints_nothing(fx, capsys, path, keywords):
    document = api.analyze(path, **keywords)
    assert capsys.readouterr().err == ''
    assert [w['fields'] for w in _unused(document)] == [['--links' if 'links' in keywords else '--since']]
    argv = [path]
    for key, value in keywords.items():
        argv += [f"--{key}"] + ([] if value is True else [value])
    assert document == json.loads(_run_reveal_direct(*argv, '--format', 'json').stdout)


def test_control_a_read_flag_draws_no_fact(fx, capsys):
    run = _run_reveal_direct('ok.py', '--head', '1', '--format', 'json')
    assert _unused(json.loads(run.stdout)) == [] and 'has no effect' not in run.stderr
    assert _unused(api.analyze('ok.py', head=1)) == [] and capsys.readouterr().err == ''
