"""BACK-1830: a component wrapped by memo / forwardRef keeps its name as the JSX owner.

The wrapper may carry a comparator (``memo(fn, areEqual)``), be namespaced (``React.memo``) or
sit inside ``Object.assign(forwardRef(fn), {...})``.  A callback passed to an array method
(``xs.map(x => <B/>)``) is not a component: its JSX belongs to the function that runs the map.
"""
from pathlib import Path

import pytest

from reveal.adapters.calls.index import find_callers

pytestmark = pytest.mark.component


def _owners(tmp_path, source, target='B'):
    (tmp_path / 'a.tsx').write_text(source, encoding='utf-8')
    result = find_callers(str(tmp_path), target)
    return sorted({c['caller'] for level in result['levels'] for c in level['callers']})


@pytest.mark.parametrize('source, owner', [
    ('const A = memo(() => <B/>);\n', 'A'),
    ('const A = memo(() => <B/>, (a, b) => a === b);\n', 'A'),
    ('const A = React.memo(() => <B/>);\n', 'A'),
    ('const A = React.memo(function () { return <B/>; }, (a, b) => a === b);\n', 'A'),
    ('const A = forwardRef((p, ref) => <B/>);\n', 'A'),
    ('const A = React.forwardRef((p, ref) => <B/>);\n', 'A'),
    ('const A = Object.assign(forwardRef((p, ref) => <B/>), { Item: 1 });\n', 'A'),
    ('const A = Object.assign(React.memo(() => <B/>, same), { Item: 1 });\n', 'A'),
    ('export const A = memo(forwardRef((p, ref) => <B/>));\n', 'A'),
    ('const A = Object.assign((p) => <B/>, { defaultItems: 1 });\n', 'A'),
], ids=['memo', 'memo-comparator', 'react-memo', 'react-memo-comparator', 'forwardRef',
        'react-forwardRef', 'assign-forwardRef', 'assign-memo-comparator', 'memo-of-forwardRef', 'assign-arrow-statics'])
def test_wrapped_component_owns_its_jsx(tmp_path, source, owner):
    assert _owners(tmp_path, source) == [owner]


@pytest.mark.parametrize('source, owner', [
    ('function Outer(xs) { const items = xs.map(x => <B/>); return items; }\n', 'Outer'),
    ('function Outer(xs) { const rows = xs.filter(Boolean).map(function (x) { return <B/>; }); return rows; }\n',
     'Outer'),
    ('function Outer(xs) { const first = xs.find(x => <B/>); return first; }\n', 'Outer'),
], ids=['map', 'filter-map', 'find'])
def test_array_callback_is_not_a_component(tmp_path, source, owner):
    assert _owners(tmp_path, source) == [owner]


def test_unrelated_call_with_two_callbacks_is_not_a_wrapper(tmp_path):
    source = 'function Outer() { const x = combine(() => <B/>, () => 1); return x; }\n'
    assert _owners(tmp_path, source) == ['Outer']


def test_plain_arrow_component_still_owns_its_jsx(tmp_path):
    assert _owners(tmp_path, 'const A = () => <B/>;\n') == ['A']


def test_comparator_is_not_adopted_as_the_component(tmp_path):
    source = ('const A = memo(Inner, (a, b) => { helper(); return a === b; });\n'
              'function Other() { return <B/>; }\n')
    (tmp_path / 'a.tsx').write_text(source, encoding='utf-8')
    result = find_callers(str(tmp_path), 'helper')
    owners = {c['caller'] for level in result['levels'] for c in level['callers']}
    assert 'A' not in owners
