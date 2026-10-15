"""Calls and JSX share source scope without sharing effect classification."""
import json
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
    assert 'calls and JSX reference to' in callers.stdout and '[lines 4]' in callers.stdout
    callees = _run_reveal_direct('calls://' + str(tmp_path) + '?callees=App')
    assert 'Button (includes JSX reference)' in callees.stdout


def test_private_reference_fields_do_not_leak_into_ast_or_uncalled(tmp_path):
    from conftest import _run_reveal_direct
    from reveal.adapters.calls.index import find_uncalled
    (tmp_path / 'App.tsx').write_text('function Button(){return null;}\nfunction App(){return <Button/>;}\n', encoding='utf-8')
    ast_result = _run_reveal_direct('ast://' + str(tmp_path), '--format', 'json')
    for result in (json.loads(ast_result.stdout), find_uncalled(str(tmp_path))):
        assert all(not ({'jsx_references', 'module_call_sites'} & set(row)) for row in records(result))
