"""`const NAME = callee(fn)` is a function only when the file calls NAME (BACK-2174).

BACK-2169 stopped member calls (`xs.map(fn)`) from adopting their function argument. A plain call
(`setTimeout(fn)`, `derived(fn)`, `useMemo(fn)`) still did, so the value it returns (a timer id, a store,
a memoised number) was listed as a function named after the variable: in outlines, in `callers` and in
`?uncalled`. A plain-call declarator is now a function only when this file calls or constructs the name
and the call refers to this very declaration (not an inner binding of the same spelling), or when the
callee is one of the declared wrappers (`memo`, `forwardRef`, `useCallback`). Precision over recall (Scott,
2026-10-23): a function-returning callee whose result is only passed around is no longer listed.
"""
import json

import pytest

from conftest import _run_reveal_direct

SOURCE = '''\
function helper(x: number) { return x; }

const onClick = debounce((e: number) => helper(e), 10);
onClick(1);

const Widget = styled((p: number) => helper(p));
const widget = new Widget(1);

const timer = setTimeout(() => helper(1), 10);
const store = derived((a: number) => helper(a));
const memoValue = useMemo(() => helper(2), []);
export const stopper = autorun(() => helper(3));
const passed = wrap((q: number) => helper(q));
register(passed);

const cb = useCallback((q: number) => helper(q), []);
const Memo = React.memo((q: number) => helper(q));

export function nestedCalled() {
  const local = once(() => helper(4));
  local();
}
export function nestedNotCalled() {
  const local2 = once(() => helper(5));
  return 1;
}
export function paramShadows(shadowed: () => void) { shadowed(); }
const shadowed = wrap((q: number) => helper(q));
export function blockShadows() {
  const blocked = wrap((q: number) => helper(q));
  { const blocked = 1 as any; blocked(); }
  return blocked;
}
const viaMember = wrap((q: number) => helper(q));
export const holder: any = { viaMember: 1 };
holder.viaMember();
'''
JSX = '''\
declare function withTheme(fn: (p: number) => any): any;
const Card = withTheme((p: number) => null);
const Unused = withTheme((p: number) => null);
const lower = withTheme((p: number) => null);
export const Page = () => <div><Card /><lower /></div>;
'''
FUNCTIONS = {'onClick', 'Widget', 'cb', 'Memo', 'local', 'helper'}
VALUES = {'timer', 'store', 'memoValue', 'stopper', 'passed', 'local2', 'shadowed', 'blocked', 'viaMember'}


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'a.ts').write_text(SOURCE, encoding='utf-8')
    (root / 'b.tsx').write_text(JSX, encoding='utf-8')
    return root


def run(*argv):
    out = _run_reveal_direct(*argv, '--no-gitignore', '--format', 'json')
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_outline_lists_a_plain_call_declarator_only_when_the_file_calls_it(project):
    names = {f['name'] for f in run(str(project / 'a.ts'))['structure']['functions']}
    assert FUNCTIONS <= names
    assert not VALUES & names


def test_uncalled_does_not_report_a_plain_call_value(project):
    names = {e['name'] for e in run(f'calls://{project}?uncalled=true')['entries']}
    assert not VALUES & names


def test_callers_do_not_name_a_plain_call_value(project):
    callers = {c['caller'] for level in run(f'calls://{project}?callers=helper')['levels'] for c in level['callers']}
    assert {'onClick', 'cb'} <= callers
    assert not VALUES & callers


def test_a_component_used_as_a_jsx_tag_is_a_function_and_an_unused_one_is_not(project):
    names = {f['name'] for f in run(str(project / 'b.tsx'))['structure']['functions']}
    assert {'Card', 'Page'} <= names
    assert not {'Unused', 'lower'} & names
