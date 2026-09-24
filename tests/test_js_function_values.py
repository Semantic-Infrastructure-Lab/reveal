"""JSFunctionValueMixin (reveal/analyzers/_js_function_values.py, BACK-1280): arrow / function-
expression / call-wrapped / class-field function values in the JS family.

Not a registered analyzer, so this file exists mainly to keep it covered directly (rule V004)."""
import pytest

from reveal.registry import get_analyzer

pytestmark = pytest.mark.component


def _analyzer(tmp_path, suffix, src):
    f = tmp_path / f't{suffix}'
    f.write_text(src)
    return get_analyzer(str(f))(str(f))


def _names(analyzer):
    return {fn['name'] for fn in analyzer.get_structure().get('functions', [])}


@pytest.mark.parametrize('suffix,src,expected', [
    ('.js', 'const add = (a, b) => a + b;\n', {'add'}),
    ('.js', 'const mul = function(a, b) { return a * b; };\n', {'mul'}),
    ('.js', 'const wrapped = memo(() => 1);\n', {'wrapped'}),
    ('.js', 'class K { handler = () => { return 2; }; method() {} }\n', {'handler', 'method'}),
    ('.ts', 'const f = (x: number): number => x + 1;\n', {'f'}),
    ('.ts', 'class C { go = (): void => {}; }\n', {'go'}),
])
def test_function_values_are_extracted(tmp_path, suffix, src, expected):
    assert expected <= _names(_analyzer(tmp_path, suffix, src))


def test_plain_value_declarations_are_not_functions(tmp_path):
    names = _names(_analyzer(tmp_path, '.js', 'const n = 1;\nconst s = "x";\nconst o = { a: 1 };\n'))
    assert not names & {'n', 's', 'o'}


def test_named_function_value_resolves_to_its_function_node(tmp_path):
    a = _analyzer(tmp_path, '.js', 'const add = (a, b) => a + b;\nconst n = 1;\n')
    assert a._find_named_function_value('add') is not None
    assert a._find_named_function_value('n') is None
    assert a._find_named_function_value('missing') is None


def test_arrow_function_complexity_counts_its_own_branches(tmp_path):
    a = _analyzer(tmp_path, '.js', 'const f = (a, b) => a && b ? 1 : 2;\n')
    (fn,) = [x for x in a.get_structure()['functions'] if x['name'] == 'f']
    assert fn['complexity'] == 3


# --- BACK-1410: JS/TS outline gaps -------------------------------------------

def _extract(analyzer, element):
    from reveal.display.element import _extract_by_syntax, _parse_element_syntax
    return _extract_by_syntax(analyzer, element, _parse_element_syntax(element))


@pytest.mark.parametrize('suffix,src,expected', [
    # ES private methods had no name (private_property_identifier) and vanished.
    ('.js', 'class S { #norm(x) { return x; } }\n', {'#norm'}),
    ('.ts', 'class S { #norm(x: string) { return x; } }\n', {'#norm'}),
    # Object-literal methods of a named object.
    ('.ts', 'const api = {\n  fetchAll: async () => [],\n  remove: function (id: number) { return id; },\n};\n',
     {'fetchAll', 'remove'}),
    ('.js', 'module.exports = { load: () => 1 };\n', {'load'}),
    ('.js', 'export default { mount: () => 1 };\n', {'mount'}),
    # CommonJS and prototype assignments.
    ('.js', 'module.exports = function main() { return 1; };\n', {'main'}),
    ('.js', 'module.exports.helper = function () { return 2; };\nexports.other = (x) => x;\n', {'helper', 'other'}),
    ('.js', 'function A() {}\nA.prototype.greet = function () { return 1; };\n', {'greet'}),
    ('.js', 'var legacy = function () { return 1; };\n', {'legacy'}),
])
def test_back1410_shapes_are_listed(tmp_path, suffix, src, expected):
    assert expected <= _names(_analyzer(tmp_path, suffix, src))


def test_inline_argument_objects_and_plain_assignments_are_not_listed(tmp_path):
    names = _names(_analyzer(tmp_path, '.js', (
        'fetch(url, { onDone: () => 1 });\n'
        'window.onload = () => 1;\n'
        'module.exports = function () { return 1; };\n'
    )))
    assert not names & {'onDone', 'onload'}


@pytest.mark.parametrize('suffix,src,element,line', [
    ('.ts', 'class Svc {\n  handler = (e: Event) => { return e; };\n}\n', 'Svc.handler', 2),
    ('.ts', 'class Svc {\n  #norm(x: string) { return x; }\n}\n', 'Svc.#norm', 2),
    ('.ts', 'const api = {\n  fetchAll: async () => [],\n};\n', 'api.fetchAll', 2),
    ('.js', 'function A() {}\nA.prototype.greet = function () { return 1; };\n', 'A.greet', 2),
    ('.js', 'module.exports.helper = function () { return 2; };\n', 'exports.helper', 1),
    ('.js', 'module.exports.helper = function () { return 2; };\n', 'module.exports.helper', 1),
    ('.ts', 'namespace Outer {\n  export function inner() { return 1; }\n}\n', 'Outer.inner', 2),
])
def test_back1410_member_paths_resolve(tmp_path, suffix, src, element, line):
    result = _extract(_analyzer(tmp_path, suffix, src), element)
    assert result is not None and result['line_start'] == line, element


def test_same_named_object_methods_are_disclosed_by_owner(tmp_path):
    a = _analyzer(tmp_path, '.js', 'const api = { save: (x) => x };\nconst other = { save: (y) => y };\n')
    result = _extract(a, 'save')
    # Named by where they are bound, not by their first parameter (x / y).
    assert [c['address'] for c in result['candidates']] == ['api.save', 'other.save']


def test_ts_namespace_is_listed(tmp_path):
    a = _analyzer(tmp_path, '.ts', 'namespace Outer {\n  export function inner() { return 1; }\n}\n')
    assert [n['name'] for n in a.get_structure()['namespaces']] == ['Outer']
