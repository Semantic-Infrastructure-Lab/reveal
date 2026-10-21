"""BACK-2131: the callee walk looked up every candidate's language family on every call site.

``CallResolver.resolve`` filtered a name's candidate definitions by the caller's language family
with ``family_for_path`` (a ``Path(...).suffix`` and two dict lookups) once per candidate per call
site, so a high-fan-out name cost ``call sites x candidates`` path parses on every query: 1,273,325
lookups for 4,826 resolves on the java corpus's ``server/src/main`` ``writeTo`` depth 2, 68% of a
warm profiled query. A definition's family is a property of its file; it is computed once, when the
definitions are collected, and stored on the ``CallSource`` the callee cache keeps per root.

Counts here are deterministic: calls to the family lookup, not seconds.
"""
import json
import os
import time

import pytest

from reveal import api
from reveal.adapters.calls import index, resolve
from reveal.utils import request_cache

pytestmark = pytest.mark.component

FILES = 6
NAMES = ('run', 'helper', 'leaf')


def write(path, source, *, age=60):
    """Files modified at or after a request start are never stamped as current."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding='utf-8')
    stamp = time.time_ns() - age * 1_000_000_000
    os.utime(path, ns=(stamp, stamp))


def make_tree(root):
    """FILES python files each defining run/helper/leaf (so every call has FILES candidates and
    resolves ambiguously), plus a JS file defining the same names: the family filter must drop it."""
    for number in range(FILES):
        write(root / f'mod{number}.py',
              'def run():\n    helper()\n    helper()\n    leaf()\n    run()\n\n'
              'def helper():\n    leaf()\n    leaf()\n\ndef leaf():\n    pass\n')
    write(root / 'other.js', 'function run() { helper(); }\nfunction helper() { leaf(); }\nfunction leaf() {}\n')
    return root


@pytest.fixture(autouse=True)
def memo_only(monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    request_cache._STAMPS.clear()
    yield
    request_cache._STAMPS.clear()


@pytest.fixture
def family_lookups(monkeypatch):
    """Every call to the language-family lookup the calls package holds (index and resolve each
    bind it at import, so patch both names)."""
    seen = []
    real = index._lang_family

    def counting(file_path):
        seen.append(file_path)
        return real(file_path)

    monkeypatch.setattr(index, '_lang_family', counting)
    monkeypatch.setattr(resolve, '_lang_family', counting)
    return seen


def query(root, suffix):
    return api.query(f'calls://{root.as_posix()}?{suffix}')


def dump(result):
    return json.dumps(result, sort_keys=True, default=str)


def test_family_lookups_do_not_scale_with_calls_times_candidates(tmp_path, family_lookups):
    """A depth-3 walk resolves dozens of call sites against FILES candidates each. Old code: one
    lookup per candidate per call site (236 on a warm repeat of this tree). The family is a property of the file:
    at most one lookup per file, whatever the number of call sites or candidates."""
    root = make_tree(tmp_path / 'fan')
    files = FILES + 1
    answer = query(root, 'callees=run&depth=3')
    assert answer['total_edges'] >= 20, 'the tree must make many call sites'
    assert len(family_lookups) <= 2 * files, len(family_lookups)


def test_a_repeated_query_asks_for_families_of_callers_only(tmp_path, family_lookups):
    """The second query reads the stored source: candidate families are already on it. Old code
    paid the whole call-sites x candidates cost again on every repeat."""
    root = make_tree(tmp_path / 'again')
    query(root, 'callees=run&depth=3')
    family_lookups.clear()
    query(root, 'callees=run&depth=3')
    assert len(family_lookups) <= FILES + 1, len(family_lookups)


def test_family_filter_still_drops_other_languages(tmp_path, family_lookups):
    """Negative control: counting must not have removed the filter. run() in mod0.py reaches
    helper in a python file, never other.js's helper, and a JS caller never reaches python."""
    root = make_tree(tmp_path / 'filter')
    walked = query(root, 'callees=run&depth=2')
    edges = [e for level in walked['levels'] for e in level['callees']]
    py_edges = [e for e in edges if e['caller_file'].endswith('.py') and e['callee'] == 'leaf'
                and e.get('callee_file')]
    assert all(e['callee_file'].endswith('.py') for e in py_edges)
    js_edges = [e for e in edges if e['caller_file'].endswith('.js')]
    assert js_edges, 'other.js run() is a root and must be walked'
    for e in js_edges:
        assert not e.get('resolved') or e['callee_file'].endswith('.js')
        assert not any(c['file'].endswith('.py') for c in e.get('candidates', []))
    assert any(e['caller_file'].endswith('.js') and e['resolved'] and e['callee_file'].endswith('.js')
               for e in edges)


def test_answers_equal_the_cache_off_answer(tmp_path, monkeypatch):
    """Positive control for any change to what the stored source carries: cache-off (no host
    request, so always collected), cold and warm answers are byte-equal, for every query shape."""
    root = make_tree(tmp_path / 'eq')
    shapes = ('callees=run', 'callees=run&depth=2', 'callees=run&depth=3&detail', 'callees=leaf&depth=2',
              'callees=run&builtins=true&depth=2')
    with monkeypatch.context() as patch:
        patch.setattr(index, 'in_host_request', lambda: False)
        off = [dump(query(root, shape)) for shape in shapes]
    cold = [dump(query(root, shape)) for shape in shapes]
    warm = [dump(query(root, shape)) for shape in shapes]
    assert cold == off and warm == off
