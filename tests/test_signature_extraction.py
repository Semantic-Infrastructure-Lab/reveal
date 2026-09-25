"""BACK-1415: an outline signature is the parameter list (and return type) --
never the same-line body, an initializer list, or a first line cut mid-list."""

import pytest

from reveal.registry import get_analyzer

pytestmark = pytest.mark.component


def _signatures(tmp_path, filename, code):
    path = tmp_path / filename
    path.write_text(code, encoding='utf-8')
    functions = get_analyzer(str(path))(str(path)).get_structure()['functions']
    return {f['name']: f['signature'] for f in functions}


def test_c_signature_has_no_trailing_brace(tmp_path):
    sigs = _signatures(tmp_path, 'd.c', 'int dictGetCmpFunc(dict *d) {\n    return 1;\n}\n')
    assert sigs['dictGetCmpFunc'] == '(dict *d)'


def test_c_multiline_declaration_is_not_empty(tmp_path):
    code = 'static int\nother(int a,\n      int b)\n{\n    return a + b;\n}\n'
    assert _signatures(tmp_path, 'd.c', code)['other'] == '(int a, int b)'


def test_c_header_inline_body_is_not_in_signature(tmp_path):
    code = 'static inline int flags(mstr s) { return s[-1] & 3; }\n'
    assert _signatures(tmp_path, 'h.c', code)['flags'] == '(mstr s)'


def test_cpp_constructor_initializer_list_is_not_in_signature(tmp_path):
    code = 'struct P {\n  P(int a, int b) : x(a), y(b) { }\n  int x, y;\n};\n'
    assert _signatures(tmp_path, 'p.cpp', code)['P'] == '(int a, int b)'


def test_kotlin_expression_and_block_bodies_are_not_in_signature(tmp_path):
    code = (
        'suspend fun String.fetch(x: Int): Int = x + 1\n'
        'fun plain(a: Int) = a * 2\n'
        'fun blockBody(a: Int): Int {\n    return a\n}\n'
    )
    sigs = _signatures(tmp_path, 'k.kt', code)
    assert sigs == {'fetch': '(x: Int): Int', 'plain': '(a: Int)', 'blockBody': '(a: Int): Int'}


def test_swift_inline_body_and_multiline_parameters(tmp_path):
    code = (
        'func expr(a: Int) -> Int { a * 2 }\n'
        'func multi(a: Int,\n           b: Int) -> Int {\n    return a + b\n}\n'
    )
    sigs = _signatures(tmp_path, 's.swift', code)
    assert sigs == {'expr': '(a: Int) -> Int', 'multi': '(a: Int, b: Int) -> Int'}
