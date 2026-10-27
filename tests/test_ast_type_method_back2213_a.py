"""ast:// ?type=method (BACK-2213 lane A, F1).

``type=method`` mapped to a ``methods`` category no analyzer emits: every method is a
``functions`` element, so ``?type=method`` returned nothing
in every language. A method is a function with an owner; ``type=method`` now selects those.
``type=function`` keeps matching every function, methods included.
"""

import pytest

from reveal.adapters.ast.adapter import AstAdapter

SOURCES = {
    'm.py': 'class Foo:\n    def bar(self):\n        return 1\n\n\ndef helper():\n    return 2\n',
    'a.go': 'package main\n\ntype T struct{}\n\nfunc (t T) M() int { return 1 }\n\nfunc F() int { return 2 }\n',
    'c.js': 'class A {\n  m() { return 1; }\n}\nfunction f() { return 2; }\n',
    'B.java': 'class B {\n  int m() { return 1; }\n}\n',
}
METHODS = {'bar', 'M', 'm'}


@pytest.fixture
def tree(tmp_path):
    for name, text in SOURCES.items():
        (tmp_path / name).write_text(text, encoding='utf-8')
    return tmp_path


def _names(tree, query):
    result = AstAdapter(str(tree), query).get_structure()
    return sorted({r['name'] for r in result['results']}), result['results']


def test_type_method_selects_methods_in_every_language(tree):
    names, results = _names(tree, 'type=method')
    assert set(names) == METHODS
    assert {r['file'].rsplit('/', 1)[-1] for r in results} == set(SOURCES)
    assert all(r['category'] == 'functions' and r['owner'] for r in results)


def test_type_function_still_includes_methods(tree):
    names, _ = _names(tree, 'type=function')
    assert set(names) == METHODS | {'helper', 'F', 'f'}


def test_type_not_method_excludes_methods(tree):
    names, results = _names(tree, 'type!=method')
    assert not set(names) & METHODS
    assert 'helper' in names


def test_type_function_or_method(tree):
    assert set(_names(tree, 'type=function|method')[0]) == METHODS | {'helper', 'F', 'f'}


def test_type_method_with_name_takes_the_outline_path_and_agrees(tree):
    assert _names(tree, 'type=method&name=m')[0] == ['m']
    assert _names(tree, 'type=method&name=helper')[0] == []


def test_type_not_function_excludes_functions(tree):
    """type!= was not normalized to the plural category, so type!=function matched everything."""
    names, results = _names(tree, 'type!=function')
    assert not set(names) & (METHODS | {'helper', 'F', 'f'})
    assert {r['category'] for r in results} >= {'classes'}
