"""Tests for reveal.conventions -- per-language convention profiles (BACK-1273)."""

import pytest

from reveal.adapters.calls.index import find_uncalled, rank_by_callers
from reveal.conventions import (
    EMPTY, PYTHON_BUILTINS, conventions_for, family_for_path, is_builtin_anywhere,
)

# BACK-1149: component-layer test -- no subprocess/CLI/MCP
pytestmark = pytest.mark.component


class TestProfiles:
    def test_unknown_family_is_empty_not_python(self):
        conv = conventions_for('no-such-language')
        assert conv is EMPTY
        assert not conv.builtins and not conv.is_implicit_name('__init__')
        assert not conv.is_test_name('test_x')

    def test_python_profile(self):
        py = conventions_for('python')
        assert py.builtins is PYTHON_BUILTINS
        assert py.is_implicit_name('__init__') and not py.is_implicit_name('constructor')
        assert py.is_test_name('test_it') and py.is_test_name('setUp')
        assert 'property' in py.implicit_decorators

    def test_other_languages_do_not_inherit_python_rules(self):
        for fam in ('go', 'rust', 'js', 'ruby', 'java'):
            conv = conventions_for(fam)
            assert not conv.builtins
            assert not conv.is_implicit_name('__init__')
            assert not conv.is_test_name('test_it')
            assert not conv.implicit_decorators

    def test_js_constructor_and_ruby_hooks_are_scoped(self):
        assert conventions_for('js').is_implicit_name('constructor')
        assert not conventions_for('go').is_implicit_name('constructor')
        assert conventions_for('ruby').is_implicit_name('initialize')
        assert not conventions_for('js').is_implicit_name('initialize')

    def test_jvm_and_csharp_markers(self):
        assert '@Test' in conventions_for('java').test_annotation_markers
        assert '@Test' in conventions_for('kotlin').test_annotation_markers
        assert '[Fact' in conventions_for('csharp').test_annotation_markers
        assert not conventions_for('python').test_annotation_markers

    def test_family_for_path(self):
        assert family_for_path('a/b.tsx') == 'js'
        assert family_for_path('x.cpp') == family_for_path('x.c') == 'c'
        assert family_for_path('x.unknownext') == ''

    def test_is_builtin_anywhere(self):
        assert is_builtin_anywhere('len') and not is_builtin_anywhere('fmt_println')


def _write(tmp_path, name, body):
    (tmp_path / name).write_text(body, encoding='utf-8')


class TestScopedInUncalled:
    """Conventions must not leak across languages (the BACK-1272 P1 bug class)."""

    @pytest.fixture(autouse=True)
    def _no_disk_cache(self, monkeypatch):
        monkeypatch.setenv('REVEAL_DISK_CACHE', '0')

    def test_go_constructor_and_dunder_are_still_reported(self, tmp_path):
        _write(tmp_path, 'a.go', 'package p\nfunc constructor() {}\nfunc __x__() {}\n')
        names = {e['name'] for e in find_uncalled(str(tmp_path))['entries']}
        assert {'constructor', '__x__'} <= names

    def test_python_dunder_and_test_prefix_excluded(self, tmp_path):
        _write(tmp_path, 'a.py', 'class C:\n    def __repr__(self):\n        return ""\n\ndef test_it():\n    pass\n\ndef dead():\n    pass\n')
        result = find_uncalled(str(tmp_path))
        assert [e['name'] for e in result['entries']] == ['dead']
        assert result['test_entrypoints_excluded'] == 1

    def test_kotlin_junit_annotation_excluded(self, tmp_path):
        _write(tmp_path, 'T.kt', 'class T {\n    @Test\n    fun works() {}\n    fun dead() {}\n}\n')
        result = find_uncalled(str(tmp_path))
        assert [e['name'] for e in result['entries']] == ['dead']
        assert result['test_entrypoints_excluded'] == 1

    def test_java_name_not_treated_as_python_test(self, tmp_path):
        _write(tmp_path, 'A.java', 'class A {\n    void test_helper() {}\n}\n')
        names = [e['name'] for e in find_uncalled(str(tmp_path))['entries']]
        assert 'test_helper' in names


class TestScopedBuiltins:
    @pytest.fixture(autouse=True)
    def _no_disk_cache(self, monkeypatch):
        monkeypatch.setenv('REVEAL_DISK_CACHE', '0')

    def test_rank_by_callers_hides_python_builtin_keeps_ruby_method(self, tmp_path):
        _write(tmp_path, 'a.py', 'def f(xs):\n    return sorted(xs)\n')
        _write(tmp_path, 'b.rb', 'def g(xs)\n  xs.sorted\nend\n')
        result = rank_by_callers(str(tmp_path), top=50)
        files = {r['file'].rsplit('/', 1)[-1] for e in result['entries'] for r in e.get('callers', [])
                 if e['name'].split('.')[-1] == 'sorted'}
        assert files == {'b.rb'}
