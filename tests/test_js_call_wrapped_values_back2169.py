"""`const NAME = xs.map(arrow)` is a value, not a function named NAME (BACK-2169).

The JS-family extractor adopts the sole function-literal argument of a call as the declarator's function
(BACK-726: `const C = memo(fn)`). A member call such as `xs.map(fn)` returns a value, so the declarator was
listed as a function: in outlines, in `callers` (the phantom shared the call with the real caller) and in
`?uncalled`. Member calls no longer adopt; the component wrappers and plain calls are unchanged.
"""
import json

import pytest

from conftest import _run_reveal_direct

SOURCE = '''\
function helper(x: number) { return x; }
export function outer(xs: number[]) {
  const mapped = xs.map((x) => helper(x));
  const kept = xs.filter(function (x) { return helper(x) > 0; });
  const found = xs.find((x) => helper(x) > 1);
  const unused = xs.some((x) => helper(x) > 2);
  return [mapped, kept, found];
}
const Memoed = React.memo((p: number) => helper(p));
const Bare = memo((p: number) => helper(p));
const Fwd = forwardRef((p: number) => helper(p));
const Assigned = Object.assign((p: number) => helper(p), { tag: 1 });
const cb = useCallback((q: number) => helper(q), []);
const plain = (z: number) => helper(z);
'''
PHANTOMS = {'mapped', 'kept', 'found', 'unused'}
FUNCTION_VALUES = {'Memoed', 'Bare', 'Fwd', 'Assigned', 'cb', 'plain'}


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'a.ts').write_text(SOURCE, encoding='utf-8')
    return root


def run(*argv):
    out = _run_reveal_direct(*argv, '--no-gitignore', '--format', 'json')
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_outline_lists_function_values_and_not_member_call_results(project):
    names = {f['name'] for f in run(str(project / 'a.ts'))['structure']['functions']}
    assert FUNCTION_VALUES <= names
    assert not PHANTOMS & names


def test_callers_name_the_real_function_and_not_the_value_it_assigns(project):
    callers = {c['caller'] for level in run(f'calls://{project}?callers=helper')['levels'] for c in level['callers']}
    assert 'outer' in callers
    assert not PHANTOMS & callers


def test_uncalled_does_not_report_a_member_call_result(project):
    names = {e['name'] for e in run(f'calls://{project}?uncalled=true')['entries']}
    assert not PHANTOMS & names
