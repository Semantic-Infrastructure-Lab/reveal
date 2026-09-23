"""BACK-1391: names used without a direct call are not dead code, in every language.

Each fixture holds a genuinely dead function next to the referenced ones; it
must still be reported, or the pass has become "hide everything".
"""

import pytest

from reveal.adapters.calls.confidence import build_meta
from reveal.adapters.calls.index import find_uncalled


@pytest.fixture(autouse=True)
def _no_disk_cache(monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')


def _uncalled(tmp_path, files):
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding='utf-8')
    return sorted(e['name'] for e in find_uncalled(str(tmp_path))['entries'])


def test_c_function_pointers_callbacks_and_prototypes(tmp_path):
    files = {
        'util.h': 'int dead(void);\nint handler(int);\n',
        'm.c': ('#include <stdlib.h>\n#include "util.h"\n'
                'static int cmp(const void *a, const void *b) { return 0; }\n'
                'int handler(int x) { return x; }\n'
                'int dead(void) { return 1; }\n'
                'static int (*hooks[])(int) = { handler };\n'
                'int main(void) { int a[1]; qsort(a, 1, sizeof(int), cmp); return hooks[0](1); }\n'),
    }
    assert _uncalled(tmp_path, files) == ['dead']


def test_cpp_member_function_pointer(tmp_path):
    files = {
        'node.h': 'class Node {\npublic:\n    void bound();\n    void dead();\n};\n',
        'node.cpp': ('#include "node.h"\n'
                     'void Node::bound() {}\n'
                     'void Node::dead() {}\n'
                     'void register_all() { bind_method("bound", &Node::bound); }\n'),
    }
    assert _uncalled(tmp_path, files) == ['Node::dead', 'register_all']


def test_go_method_values_and_composite_literals(tmp_path):
    files = {'a.go': ('package p\n'
                      'type L struct{}\n'
                      'func (l *L) run() {}\n'
                      'func indexFunc(x int) int { return x }\n'
                      'func dead() {}\n'
                      'var table = map[string]func(int) int{"k": indexFunc}\n'
                      'func Start(l *L, wg interface{ Go(func()) }) { wg.Go(l.run) }\n')}
    assert _uncalled(tmp_path, files) == ['Start', 'dead']


def test_java_method_references(tmp_path):
    files = {'A.java': ('class A {\n'
                        '    static int describe(Object o) { return 1; }\n'
                        '    static int dead() { return 2; }\n'
                        '    Object f = (java.util.function.Function<Object, Integer>) A::describe;\n'
                        '}\n')}
    assert _uncalled(tmp_path, files) == ['dead']


def test_js_callbacks_module_calls_exports_and_jsx(tmp_path):
    files = {
        'a.js': ('function onFrame(t) { return t; }\n'
                 'function helper() { return 2; }\n'
                 'function init() { return 3; }\n'
                 'function listed() { return 4; }\n'
                 'function dead() { return 5; }\n'
                 'requestAnimationFrame(onFrame);\n'
                 'const table = { h: helper };\n'
                 'init();\n'
                 'export { listed };\n'
                 'export function published() {}\n'),
        'c.jsx': ('function Button() { return <button/>; }\n'
                  'export default function App() { return <Button/>; }\n'),
    }
    assert _uncalled(tmp_path, files) == ['dead']


def test_php_hook_strings_and_callable_arrays(tmp_path):
    files = {'a.php': ("<?php\n"
                       "function my_init() {}\n"
                       "function dead() {}\n"
                       "add_action('init', 'my_init');\n"
                       "class C {\n"
                       "    function register() { add_filter('x', [$this, 'filter_cb']); }\n"
                       "    function filter_cb($v) { return $v; }\n"
                       "}\n")}
    assert _uncalled(tmp_path, files) == ['dead', 'register']


def test_ruby_symbol_references(tmp_path):
    files = {'c.rb': ('class C\n'
                      '  before_action :authenticate\n'
                      '  def authenticate; end\n'
                      '  def dead; end\n'
                      'end\n')}
    assert _uncalled(tmp_path, files) == ['dead']


def test_kotlin_calls_outside_function_bodies(tmp_path):
    files = {'A.kt': ('class A {\n'
                      '    val x = compute()\n'
                      '    init { setup() }\n'
                      '    fun compute(): Int = 1\n'
                      '    fun setup() {}\n'
                      '    fun dead() {}\n'
                      '}\n')}
    assert _uncalled(tmp_path, files) == ['dead']


def test_a_reference_in_another_language_does_not_count(tmp_path):
    files = {'a.go': 'package p\nfunc handler() {}\n',
             'b.js': 'setTimeout(handler, 0);\n'}
    assert _uncalled(tmp_path, files) == ['handler']


def test_python_only_warnings_are_not_printed_for_other_languages(tmp_path):
    (tmp_path / 'm.c').write_text('int main(void) { return 0; }\n', encoding='utf-8')
    codes = {w['code'] for w in build_meta(str(tmp_path), uncalled=True)['warnings']}
    assert 'W-CALLS-1' in codes and not codes & {'W-CALLS-2', 'W-CALLS-3', 'W-CALLS-4'}
    (tmp_path / 'm.c').unlink()
    (tmp_path / 'm.py').write_text('def f():\n    pass\n', encoding='utf-8')
    codes = {w['code'] for w in build_meta(str(tmp_path), uncalled=True)['warnings']}
    assert {'W-CALLS-2', 'W-CALLS-3', 'W-CALLS-4'} <= codes


def test_a_same_named_variable_is_not_a_reference(tmp_path):
    files = {'a.js': 'function result() { return 1; }\n',
             'b.js': 'const result = compute();\nconsole.log(result);\nfunction compute() { return 2; }\n'}
    assert _uncalled(tmp_path, files) == ['result']


def test_a_rust_field_does_not_hide_its_dead_accessor(tmp_path):
    files = {'lib.rs': ('pub struct S { size: usize }\n'
                        'impl S {\n'
                        '    fn size(&self) -> usize { self.size }\n'
                        '}\n')}
    assert _uncalled(tmp_path, files) == ['size']


def test_a_function_bound_to_a_variable_is_still_referenced(tmp_path):
    files = {'a.js': 'const onTick = () => 1;\nconst unused = () => 2;\nsetInterval(onTick, 10);\n'}
    assert _uncalled(tmp_path, files) == ['unused']


def test_a_variable_that_is_the_definition_still_counts_its_uses(tmp_path):
    """three.js: `export const decrementBefore = Fn(([a]) => ...)` is listed as a
    function; its same-file use must not be discarded as a variable's read."""
    files = {'a.js': ('export const decrementBefore = Fn(([a]) => a);\n'
                      'export const unusedOp = Fn(([a]) => a);\n'
                      'addMethodChaining("decrementBefore", decrementBefore);\n')}
    names = _uncalled(tmp_path, files)
    assert 'decrementBefore' not in names
