"""A zero-result decorator= query says when the scan held languages that never extract decorators (BACK-2265).

JavaScript `@dec class X`, C++ `[[nodiscard]]`, Dart `@override` and GDScript annotations are not in
those analyzers' `decorators` field, so `decorator=` found nothing and printed a plain `Results: 0`,
the same answer a language that has none gets. The zero now carries a warning naming those languages.
"""

import pytest

from reveal.adapters.ast.adapter import AstAdapter

FILES = {
    'k.py': '@property\ndef prop(): pass\n',
    'a.js': '@dec\nclass A { @m() foo() {} }\n',
    'a.cpp': '[[nodiscard]] int f() { return 1; }\n',
    'a.dart': 'class A { @override void g() {} }\n',
    'a.go': 'func F() {}\n',
}


@pytest.fixture(scope='module')
def root(tmp_path_factory):
    directory = tmp_path_factory.mktemp('back2265')
    for name, text in FILES.items():
        (directory / name).write_text(text, encoding='utf-8')
    return directory


def _result(path, query):
    return AstAdapter(str(path), query).get_structure()


def _decorator_warnings(result):
    return [w for w in result['meta']['warnings'] if w.get('type') == 'decorator_not_extracted']


def test_zero_over_languages_without_extraction_names_them(root):
    result = _result(root, 'decorator=nonexistent')
    assert result['total_results'] == 0
    (warning,) = _decorator_warnings(result)
    for language in ('javascript', 'cpp', 'dart'):
        assert language in warning['message']
    assert 'python' not in warning['message']
    assert 'go' not in warning['message'].replace('gdscript', '')


def test_the_regex_form_warns_too(root):
    assert _decorator_warnings(_result(root, 'decorator~=^nothing$'))


def test_a_scan_with_only_extracting_languages_is_a_genuine_zero(root):
    # Control: python extracts decorators, so a miss there is a real zero.
    assert _decorator_warnings(_result(root / 'k.py', 'decorator=nonexistent')) == []


def test_a_hit_carries_no_warning(root):
    result = _result(root, 'decorator=property')
    assert result['total_results'] == 1
    assert _decorator_warnings(result) == []


def test_other_filters_carry_no_decorator_warning(root):
    assert _decorator_warnings(_result(root, 'name=nonexistent')) == []
