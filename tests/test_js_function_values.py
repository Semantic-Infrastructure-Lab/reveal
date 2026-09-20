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
