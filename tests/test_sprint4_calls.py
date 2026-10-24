"""Calls and JSX share source scope without sharing effect classification."""
import json
import re
from pathlib import Path
import pytest
from reveal.adapters.ast.analysis import analyze_file
from reveal.adapters.calls.index import find_callers
from reveal.adapters.trace import _build_trace

pytestmark = pytest.mark.component


def effect_file(tmp_path):
    path = tmp_path / 'App.tsx'
    path.write_text('export function App(items, url) {\n for (const item of items) {\n'
                    '  fetch(url); cache.set("key", item);\n'
                    '  const view = <div><Query/><Fetch/><Console.Log/><Redirect/><Sleep/><Cache.Set/></div>;\n'
                    ' }\n}\n', encoding='utf-8')
    return path


def records(value):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from records(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from records(nested)


@pytest.mark.parametrize('flags', [['--sideeffects'], ['--boundary'], ['--fanout'],
                                   ['--statewrites'], ['--sideeffects', '--transitive']])
def test_jsx_effect_consumers_keep_real_effects(tmp_path, flags):
    from conftest import _run_reveal_direct
    path = effect_file(tmp_path)
    result = _run_reveal_direct(str(path), 'App', *flags, '--format', 'json')
    assert result.returncode == 0
    effects = [r for r in records(json.loads(result.stdout))
               if r.get('kind') in ('http', 'log', 'sleep', 'cache', 'db')]
    assert effects
    assert not any((r.get('callee') or r.get('target')) in
                   {'Query', 'Fetch', 'Console.Log', 'Redirect', 'Sleep', 'Cache.Set'} for r in effects)
    assert any((r.get('callee') or r.get('target')) == 'cache.set' for r in effects)
    if flags != ['--statewrites']:
        assert any(r.get('callee') == 'fetch' for r in effects)


def test_mcp_navigation_uses_the_same_effect_policy(tmp_path):
    from reveal.mcp_server import reveal_nav
    path = effect_file(tmp_path)
    answer = reveal_nav(str(path), 'App', 'sideeffects')
    assert 'Fetch()' not in answer and 'Cache.Set()' not in answer
    assert 'fetch(' in answer and 'cache.set(' in answer


def test_methods_and_abstract_classes_do_not_create_module_helper_calls(tmp_path):
    path = tmp_path / 'a.ts'
    path.write_text('function helper() { return 1; }\n'
                    'abstract class A { x = helper(); abstract m(): void; }\n'
                    'class B { y = helper(); get g() { return helper(); } }\n'
                    'const api = { get() { return helper(); }, set: () => helper() };\n'
                    'export default { methods: { load() { helper(); } } };\n', encoding='utf-8')
    rows = find_callers(str(tmp_path), 'helper')['levels'][0]['callers']
    assert {r['caller'] for r in rows} == {'g', 'get', 'set', 'load'}
    assert not any(s['callee'] == 'helper' for s in analyze_file(str(path))['module_call_sites'])


def test_unnamed_and_wrapped_jsx_preserve_owners(tmp_path):
    path = tmp_path / 'a.jsx'
    path.write_text('function Button() { return null; }\n'
                    'export default function () { return <Button/>; }\n'
                    'items.forEach(() => <Button/>);\n'
                    '(function () { return <Button/>; })();\n'
                    'const obj = { render() { return <Button/>; } };\n'
                    'class K { field = <Button/>; }\n'
                    'ReactDOM.render(<Button/>, el);\n'
                    'const Row = memo(function RowImpl() { return <Button/>; });\n'
                    'const Input = forwardRef(function InputImpl() { return <Button/>; });\n', encoding='utf-8')
    refs = analyze_file(str(path))['jsx_references']
    assert [r['line'] for r in refs if r['owner'] == '<module>'] == [7]
    assert next(r for r in refs if r['line'] == 8)['owner'] == 'Row'
    assert next(r for r in refs if r['line'] == 9)['owner'] == 'Input'
    assert next(r for r in refs if r['line'] == 6)['owner'] == 'K'
    callers = find_callers(str(tmp_path), 'Button')['levels'][0]['callers']
    assert {r['caller'] for r in callers} == {'render', '<module>', 'Row', 'Input'}
    assert next(r for r in callers if r['caller'] == '<module>')['reference_lines'] == [7]


def test_alias_does_not_rewrite_member_call_but_bare_alias_still_resolves(tmp_path):
    (tmp_path / 'm.py').write_text('def helper(): return 1\n', encoding='utf-8')
    (tmp_path / 'app.py').write_text('from m import helper as h\nclass Obj:\n def h(self): return 2\n'
                                   'def run(o): return o.h()\ndef direct(): return h()\n', encoding='utf-8')
    member = _build_trace(str(tmp_path), 'run', 2)['frames']
    assert any(Path(r.get('file', '')).name == 'app.py' and r['line'] == 3 for r in member)
    assert not any(Path(r.get('file', '')).name == 'm.py' for r in member)
    bare = _build_trace(str(tmp_path), 'direct', 2)['frames']
    assert any(Path(r.get('file', '')).name == 'm.py' for r in bare)


def test_text_preserves_mixed_relationship_and_reference_locations(tmp_path):
    from conftest import _run_reveal_direct
    (tmp_path / 'App.tsx').write_text('function Button(){return null;}\n'
                                    'function App(){\n Button();\n return <Button/>;\n}\n', encoding='utf-8')
    callers = _run_reveal_direct('calls://' + str(tmp_path) + '?target=Button')
    assert 'calls and JSX reference to' in callers.stdout and '[call line 3, JSX line 4]' in callers.stdout
    callees = _run_reveal_direct('calls://' + str(tmp_path) + '?callees=App')
    assert 'Button (includes JSX reference)' in callees.stdout


# Every key call_sources/jsx_component_references use to carry JSX and module-call data between
# the structure and the calls index (BACK-1834 F12; jsx_call_sites and call_lines added with F7).
INTERNAL_CALL_KEYS = ('references', 'reference_only_calls', 'call_sites', 'owner', 'owner_line',
                      'reference_lines', 'relationship', 'jsx_references', 'module_call_sites',
                      'jsx_call_sites', 'call_lines')


def leaked_keys(result):
    return {key for row in records(result) for key in INTERNAL_CALL_KEYS if key in row}


def test_private_reference_fields_do_not_leak_into_ast_or_uncalled(tmp_path):
    from conftest import _run_reveal_direct
    from reveal.adapters.calls.index import find_uncalled
    (tmp_path / 'App.tsx').write_text('function Button(){return null;}\nfunction App(){Button(); return <Button/>;}\n'
                                    'function Lone(){return <Button/>;}\nButton();\n<Button/>;\n', encoding='utf-8')
    ast_result = _run_reveal_direct('ast://' + str(tmp_path), '--format', 'json')
    assert ast_result.returncode == 0
    assert leaked_keys(json.loads(ast_result.stdout)) == set()
    assert leaked_keys(find_uncalled(str(tmp_path))) == set()
    text = _run_reveal_direct('ast://' + str(tmp_path)).stdout
    assert 'App' in text and not any(re.search(rf'\b{key}\b', text) for key in INTERNAL_CALL_KEYS)


def test_leak_check_detects_a_leaked_key(tmp_path):
    """Negative control: the check fails on a result that carries one of the keys."""
    assert leaked_keys({'results': [{'name': 'App', 'jsx_call_sites': []}]}) == {'jsx_call_sites'}
    assert leaked_keys({'results': [{'name': 'App', 'owner_line': 3}]}) == {'owner_line'}


def test_jsx_in_test_and_hook_callbacks_belongs_to_the_enclosing_element(tmp_path):
    """BACK-1829: unnamed callbacks (describe/it/beforeEach, hooks) own their JSX, as for calls."""
    (tmp_path / 'w.test.tsx').write_text(
        'function Widget() { return null }\n'
        'function mount(x) { return x }\n'
        'describe("w", () => {\n'
        '  beforeEach(() => { mount(<Widget />); });\n'
        '  it("renders", () => {\n'
        '    mount(<Widget />);\n'
        '  });\n'
        '});\n'
        'function Panel() {\n'
        '  useEffect(() => { mount(<Widget />); }, []);\n'
        '  return null;\n'
        '}\n'
        'register({ perform: () => <Widget /> });\n', encoding='utf-8')
    refs = {r['line']: r['owner'] for r in analyze_file(str(tmp_path / 'w.test.tsx'))['jsx_references']}
    assert refs[4] == 'beforeEach' and refs[6] == 'it(renders)'     # the smallest element, not describe(w)
    assert refs[10] == 'Panel'                                       # a named function still wins
    assert refs[13] == '<anonymous>'                                 # no enclosing element: disclosed, not guessed
    callers = {r['caller'] for r in find_callers(str(tmp_path), 'Widget')['levels'][0]['callers']}
    assert {'beforeEach', 'it(renders)', 'Panel'} <= callers
    # Positive control: an ordinary call on the same lines is credited to the same elements.
    mounts = {r['caller'] for r in find_callers(str(tmp_path), 'mount')['levels'][0]['callers']}
    assert {'beforeEach', 'it(renders)', 'Panel'} <= mounts


def test_callback_that_computes_a_value_does_not_make_the_value_the_owner(tmp_path):
    """BACK-1832: the framework matrix's compiler oracle disagreed on Excalidraw HelpDialog: a JSX use
    inside `const keys = list.map(cb)` was credited to `keys`, a computed value, not to the component."""
    (tmp_path / 'k.tsx').write_text(
        'function Key() { return null }\n'
        'const Shortcut = ({ list }) => {\n'
        '  const keys = list.map((k) => (\n'
        '    <Key />\n'
        '  ));\n'
        '  const onPick = useCallback(() => <Key />, []);\n'
        '  return keys;\n'
        '};\n'
        'const Wrapped = React.memo(() => <Key />);\n'
        'const Forwarded = forwardRef((p, ref) => <Key />);\n', encoding='utf-8')
    refs = {r['line']: r['owner'] for r in analyze_file(str(tmp_path / 'k.tsx'))['jsx_references']}
    assert refs[4] == 'Shortcut' and refs[6] == 'Shortcut'    # unnamed callbacks inherit the component
    assert refs[9] == 'Wrapped' and refs[10] == 'Forwarded'    # component wrappers still name their function
    callers = {r['caller'] for r in find_callers(str(tmp_path), 'Key')['levels'][0]['callers']}
    assert 'keys' not in callers and 'onPick' not in callers and 'Shortcut' in callers


def test_module_graph_keeps_jsx_dependency_with_no_tracked_owner(tmp_path):
    # BACK-1831: <Button/> sits in a deferred body passed to register(), with no enclosing
    # element, so the use is <anonymous>. The file-to-file edge must not depend on that. Since
    # ?modules answers from imports ?importers (BACK-1054 slice S5, Q4) an edge is an import edge,
    # whichever scope uses the name, and an import used by nothing is an edge too.
    from reveal.adapters.calls import CallsAdapter
    (tmp_path / 'ui.tsx').write_text('export function Button() { return null; }\n'
                                     'export function Label() { return null; }\n', encoding='utf-8')
    (tmp_path / 'actions.tsx').write_text("import { Button } from './ui';\n"
                                          'register({ perform: () => <Button/> });\n', encoding='utf-8')
    (tmp_path / 'unused.tsx').write_text("import { Label } from './ui';\n"
                                         'export const x = 1;\n', encoding='utf-8')
    refs = analyze_file(str(tmp_path / 'actions.tsx'))['jsx_references']
    assert [r['owner'] for r in refs] == ['<anonymous>']
    edges = {(Path(e['from']).name, Path(e['to']).name)
             for e in CallsAdapter(str(tmp_path), 'modules').get_structure()['edges']}
    assert ('actions.tsx', 'ui.tsx') in edges
    assert ('unused.tsx', 'ui.tsx') in edges


def test_same_named_functions_on_one_line_share_an_owner_known_limit(tmp_path):
    """BACK-1830 F8, a documented limit: an owner is (name, line), so two functions both
    named f on one line cannot be told apart and each is credited with both uses. Remove
    this test when owner identity carries more than the line."""
    src = tmp_path / 'a.jsx'
    src.write_text('function f(){return <X/>}; function f(){return <Y/>};\n', encoding='utf-8')
    refs = analyze_file(str(src))['jsx_references']
    assert [(r['callee'], r['owner'], r['owner_line']) for r in refs] == [('X', 'f', 1), ('Y', 'f', 1)]
