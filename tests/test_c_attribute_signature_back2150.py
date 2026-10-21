"""A C/C++ function whose declaration starts with a GNU attribute shows its own parameter list as its
signature, not the attribute's text (BACK-2150).

`static __attribute__((noinline)) void publish(const char *a) {...}` used to print as
`publish((noinline)) void publish(const char *a)`: the clean-parse fallback cut the declaration text at its
FIRST `(`, which belongs to the attribute.
"""
import pytest

from reveal.analyzers.c import CAnalyzer
from reveal.analyzers.cpp import CppAnalyzer


def _functions(tmp_path, name, code, analyzer_class):
    path = tmp_path / name
    path.write_text(code, encoding='utf-8')
    structure = analyzer_class(str(path)).get_structure()
    return {f['name']: f for f in structure.get('functions', [])}


C_SOURCE = '''\
static __attribute__((noinline)) void publish(const char *a) {
    if (a == 0) return;
}

__attribute__((always_inline)) static inline int twice(int x) { return x * 2; }

static void __attribute__((unused)) tail_attr(int y) { (void)y; }

int plain(int x) { return x; }
'''


@pytest.mark.parametrize('name, signature', [
    ('publish', '(const char *a)'),
    ('twice', '(int x)'),
    ('tail_attr', '(int y)'),
    ('plain', '(int x)'),   # sibling without an attribute: unchanged
])
def test_c_function_signature_is_its_own_parameter_list(tmp_path, name, signature):
    functions = _functions(tmp_path, 'attrs.c', C_SOURCE, CAnalyzer)
    assert functions[name]['signature'] == signature


def test_cpp_function_signature_with_a_leading_attribute(tmp_path):
    code = '__attribute__((noinline)) static int mix(int a, int b) { return a + b; }\n'
    functions = _functions(tmp_path, 'attrs.cpp', code, CppAnalyzer)
    assert functions['mix']['signature'] == '(int a, int b)'


def test_the_outline_shows_one_name_and_one_parameter_list(tmp_path):
    """The text outline joins name and signature: no attribute text may leak between them."""
    functions = _functions(tmp_path, 'attrs.c', C_SOURCE, CAnalyzer)
    shown = functions['publish']['name'] + functions['publish']['signature']
    assert shown == 'publish(const char *a)'
