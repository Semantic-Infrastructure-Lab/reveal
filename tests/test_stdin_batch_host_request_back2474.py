"""BACK-2474: a --stdin batch is one host request, so its lines share the request-owned caches.

Outside a host request the calls callers index is never read or stored (a direct library call
always builds). A batch therefore wraps itself in host_request(): two calls:// lines over the
same tree build the index once and both answer, where an unwrapped batch would build per line.
"""
import io
import json
import sys

import pytest

from reveal.adapters.calls import index as calls_index
from reveal.main import main


@pytest.fixture
def project(tmp_path, monkeypatch):
    pkg = tmp_path / 'pkg'
    pkg.mkdir()
    (pkg / 'b.py').write_text('def helper(x):\n    return x\n', encoding='utf-8')
    (pkg / 'a.py').write_text('from pkg.b import helper\n\n\ndef run():\n    return helper(1)\n',
                              encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    calls_index._INDEX_CACHE.clear()
    yield tmp_path
    calls_index._INDEX_CACHE.clear()


def _run_batch(monkeypatch, capsys, lines):
    builds = []
    collect = calls_index._structures_or_collect

    def counting(structures, directory):
        builds.append(str(directory))
        return collect(structures, directory)

    monkeypatch.setattr(calls_index, '_structures_or_collect', counting)
    monkeypatch.setattr(sys, 'stdin', io.StringIO(''.join(f'{line}\n' for line in lines)))
    with pytest.raises(SystemExit):
        main(['reveal', '--stdin', '--format', 'json'])
    return builds, capsys.readouterr().out


def test_a_batch_builds_the_callers_index_once_for_two_lines(project, monkeypatch, capsys):
    builds, out = _run_batch(monkeypatch, capsys, ['calls://pkg/?callers=helper', 'calls://pkg/?rank=callers'])
    assert builds == ['pkg'], builds
    assert '"run"' in out  # both lines answered; the first names run as helper's caller


def test_the_shared_index_still_answers_each_line(project, monkeypatch, capsys):
    builds, out = _run_batch(monkeypatch, capsys, ['calls://pkg/?callers=helper', 'calls://pkg/?callers=run'])
    # run has no callers, so find_callers also indexes the parent for its widening hint: another root.
    assert builds.count('pkg') == 1, builds
    answers = _json_objects(out)
    callers = [sorted(c['caller'] for level in a.get('levels', []) for c in level['callers']) for a in answers]
    assert callers == [['run'], []], callers


def _json_objects(text):
    decoder, position, objects = json.JSONDecoder(), 0, []
    while position < len(text):
        while position < len(text) and text[position].isspace():
            position += 1
        if position >= len(text):
            break
        obj, position = decoder.raw_decode(text, position)
        objects.append(obj)
    return objects
