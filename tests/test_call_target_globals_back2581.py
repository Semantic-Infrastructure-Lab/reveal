"""BACK-2581: a JS/TS call through a language global, or a class field holding an object, is no call target.

On typescript/src, ``Math.max(a, b)`` resolved to ``OffsetPair``'s ``static readonly max = new
OffsetPair(...)`` (the project's one ``max``) and ``String(x)`` to ``static readonly String = new ...``:
graph_invariants' call_targets check was red with 4 target_defines. Two causes: a class field whose
initializer builds an object was a call target (it is only a call source, BACK-2230), and a call
qualified by a global nothing imports (``Math``) reached any project definition of its name.
"""

import json

import pytest

from conftest import _run_reveal_direct
from reveal.analyzers.imports.bindings import reaches

pytestmark = pytest.mark.component

PAIR = """\
export class OffsetPair {
    static readonly max = new OffsetPair(1, 2);
    public static readonly String = new OffsetPair(3, 4);
    handler = (x: number) => helper(x);
    save = debounce(() => helper(1));
    constructor(public a: number, public b: number) {}
}
export function helper(x: number) { return x; }
export function debounce(f: () => number) { return f; }
"""

USE = """\
import { OffsetPair } from './pair';
export function ratio(a: number, b: number) {
    const p = new OffsetPair(a, b);
    p.handler(a);
    p.save();
    return Math.max(a, b) + String(a).length;
}
"""

RANGE = """\
export class Range {
    static max(a: number, b: number) { return a > b ? a : b; }
}
export function useRange() { return Range.max(1, 2); }
"""


@pytest.fixture
def project(tmp_path):
    src = tmp_path / 'src'
    src.mkdir()
    (src / 'pair.ts').write_text(PAIR, encoding='utf-8')
    (src / 'use.ts').write_text(USE, encoding='utf-8')
    return src


def _callees(src, name):
    run = _run_reveal_direct(f'calls://{src.as_posix()}?callees={name}&depth=2&builtins=true', '--format', 'json')
    assert run.returncode == 0, run.stderr
    return {e['call_expr']: e for level in json.loads(run.stdout)['levels'] for e in level['callees']}


def test_global_and_object_field_calls_reach_no_project_definition(project):
    edges = _callees(project, 'ratio')
    assert edges['Math.max']['resolved'] is False
    assert edges['String']['resolved'] is False


def test_function_holding_fields_stay_call_targets(project):
    edges = _callees(project, 'ratio')
    assert edges['p.handler']['resolved'] is True and edges['p.handler']['callee_line'] == 4
    assert edges['p.save']['resolved'] is True and edges['p.save']['callee_line'] == 5


def test_callers_of_a_project_max_exclude_the_global_call(project):
    (project / 'range.ts').write_text(RANGE, encoding='utf-8')
    run = _run_reveal_direct(f'calls://{project.as_posix()}?callers=max', '--format', 'json')
    assert run.returncode == 0, run.stderr
    callers = [c['call_expr'] for level in json.loads(run.stdout)['levels'] for c in level['callers']]
    assert callers == ['Range.max']


def test_reaches_global_qualifier_rule():
    files = {'src/a.ts', 'src/b.ts'}
    assert reaches(None, 'Math.max', 'src/a.ts', files) == {'src/a.ts'}   # a class Math in the file itself
    assert reaches(None, 'Math.max', 'src/c.ts', files) == set()
    assert reaches(None, 'range.max', 'src/c.ts', files) == files          # not a global: unchanged
    assert reaches(None, 'Math.max', 'src/c.py', files) == files           # a JS fact only
