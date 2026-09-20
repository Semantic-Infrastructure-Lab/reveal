"""Tests for reveal.conventions -- per-language convention profiles (BACK-1273)."""

from pathlib import PureWindowsPath  # handles '/' and '\\' separators alike
import pytest

from reveal.adapters.calls.index import _get_decorator_names, find_uncalled, rank_by_callers
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
        files = {PureWindowsPath(r['file']).name for e in result['entries'] for r in e.get('callers', [])
                 if e['name'].split('.')[-1] == 'sorted'}
        assert files == {'b.rb'}


class TestGoAndRustEntryPoints:
    """BACK-1274: Go tests/main/init and Rust #[test]/main are not dead code."""

    @pytest.fixture(autouse=True)
    def _no_disk_cache(self, monkeypatch):
        monkeypatch.setenv('REVEAL_DISK_CACHE', '0')

    def test_go_test_functions_only_in_test_files(self, tmp_path):
        _write(tmp_path, 'a_test.go', 'package p\nfunc TestRead(t int) {}\nfunc BenchmarkRead(b int) {}\n'
               'func ExampleRead() {}\nfunc FuzzRead(f int) {}\nfunc Testable() {}\nfunc helper() {}\n')
        _write(tmp_path, 'a.go', 'package p\nfunc TestNotATest() {}\nfunc main() {}\nfunc init() {}\nfunc dead() {}\n')
        result = find_uncalled(str(tmp_path))
        assert {e['name'] for e in result['entries']} == {'Testable', 'TestNotATest', 'dead', 'helper'}
        assert result['test_entrypoints_excluded'] == 4

    def test_rust_test_attributes_and_main(self, tmp_path):
        _write(tmp_path, 'a.rs', '#[test]\nfn it_works() {}\n\n#[tokio::test(flavor = "multi_thread")]\n'
               'async fn async_works() {}\n\n#[bench]\nfn bench_it() {}\n\nfn main() {}\n\n#[inline]\nfn dead() {}\n')
        result = find_uncalled(str(tmp_path))
        assert [e['name'] for e in result['entries']] == ['dead']
        assert result['test_entrypoints_excluded'] == 3

    def test_test_names_do_not_leak_across_languages(self, tmp_path):
        _write(tmp_path, 'a.rs', 'fn TestLooksLikeGo() {}\nfn init() {}\n')
        _write(tmp_path, 'b_test.py', 'def TestLooksLikeGo():\n    pass\n')
        names = {e['name'] for e in find_uncalled(str(tmp_path))['entries']}
        assert {'TestLooksLikeGo', 'init'} <= names

    def test_go_profile_is_file_scoped(self):
        go = conventions_for('go')
        assert go.is_test_name('TestX', 'pkg/x_test.go')
        assert not go.is_test_name('TestX', 'pkg/x.go')
        assert not go.is_test_name('Testable', 'pkg/x_test.go')
        assert go.is_test_name('Test', 'x_test.go')


class TestDecoratorBareNames:
    @pytest.mark.parametrize('raw, bare', [
        ('@property', 'property'),
        ("@app.route('/x')", 'route'),
        ('@pytest.fixture()', 'fixture'),
        ('#[test]', 'test'),
        ('#[tokio::test]', 'test'),
        ('#[tokio::test(flavor = "multi_thread")]', 'test'),
        ('#[cfg(test)]', 'cfg'),
        ('#![allow(dead_code)]', 'allow'),
    ])
    def test_bare_names(self, raw, bare):
        assert _get_decorator_names({'decorators': [raw]}) == {bare}


class TestStdlibKey:
    """BACK-1275: per-language stdlib classification via conventions.stdlib_key."""

    def _classify(self, module, family):
        from reveal.analyzers.imports.classify import classify_module
        return classify_module(module, family, frozenset())

    def test_go_stdlib_and_third_party(self):
        assert self._classify('net/http', 'go') == ('stdlib', 'net/http')
        assert self._classify('fmt', 'go') == ('stdlib', 'fmt')
        assert self._classify('k8s.io/client-go/kubernetes', 'go')[0] == 'external'
        # A dotless local module path is not stdlib.
        assert self._classify('myapp/pkg', 'go')[0] == 'external'

    def test_rust_std_core_alloc(self):
        for mod in ('std::io::Read', 'core::fmt', 'alloc::vec::Vec'):
            assert self._classify(mod, 'rust')[0] == 'stdlib'
        assert self._classify('serde::Serialize', 'rust')[0] == 'external'

    def test_jvm_namespaces(self):
        assert self._classify('java.util.List', 'java') == ('stdlib', 'java')
        assert self._classify('javax.swing.JFrame', 'java')[0] == 'stdlib'
        assert self._classify('org.junit.Test', 'java')[0] == 'external'
        assert self._classify('kotlin.collections.List', 'kotlin')[0] == 'stdlib'
        assert self._classify('kotlinx.coroutines.Flow', 'kotlin')[0] == 'external'

    def test_node_builtins(self):
        assert self._classify('fs', 'js') == ('stdlib', 'fs')
        assert self._classify('node:path', 'js') == ('stdlib', 'path')
        assert self._classify('fs/promises', 'js') == ('stdlib', 'fs')
        assert self._classify('react', 'js')[0] == 'external'

    def test_csharp_system(self):
        assert self._classify('System.Collections.Generic', 'csharp')[0] == 'stdlib'
        assert self._classify('Newtonsoft.Json', 'csharp')[0] == 'external'

    def test_python_stdlib_not_applied_to_other_languages(self):
        # BACK-1193: `json`/`socket` in Ruby must not read as Python stdlib.
        assert self._classify('json', 'ruby')[0] == 'external'
        assert self._classify('json', 'python') == ('stdlib', 'json')

    def test_unknown_family_claims_no_stdlib(self):
        assert self._classify('os', '')[0] == 'external'

    def test_dart_marker_is_family_independent(self):
        assert self._classify('dart:async', 'dart') == ('stdlib', 'dart:async')


class TestIsTestPath:
    """BACK-1277: one shared 'is this a test file?' answer."""

    def _t(self, p):
        from reveal.utils.path_utils import is_test_path
        return is_test_path(p)

    def test_language_conventions(self):
        for p in ('pkg/etcd_test.go', 'src/a.spec.ts', 'src/b.test.jsx', 'app/x_spec.rb',
                  'src/foo_tests.rs', 'src/tests.rs', 'pkg/conftest.py', 'lib/spec_helper.rb',
                  'a/foo_tests.cpp', 'src/FooTest.java'):
            assert self._t(p), p

    def test_test_directories(self):
        assert self._t('repo/tests/helpers.py')
        assert self._t('repo/__tests__/util.js')

    def test_non_tests(self):
        for p in ('src/etcd.go', 'src/testing_utils.py', 'src/contest.py', 'src/latest.ts'):
            assert not self._t(p), p

    def test_go_test_previously_missed_by_overview(self):
        from reveal.adapters.overview import _is_test_file
        assert _is_test_file('pkg/util/foo_test.go')
        assert not _is_test_file('pkg/testing/util.go')


def test_scanned_dir_named_like_stdlib_root_does_not_hide_stdlib():
    """Scanning `src/main/java` must not classify `java.util.List` as internal."""
    from reveal.analyzers.imports.classify import classify_module
    assert classify_module('java.util.List', 'java', frozenset({'java'})) == ('stdlib', 'java')
    assert classify_module('net/http', 'go', frozenset({'net'}))[0] == 'stdlib'
    # Python keeps local-first: a local package shadows a same-named stdlib module.
    assert classify_module('json', 'python', frozenset({'json'})) == ('internal', None)


class TestJUnit3TestPrefix:
    """BACK-1290: `testXxx` counts as a test only inside test files."""

    def test_java_prefix_scoped_to_test_files(self):
        from reveal.conventions import conventions_for
        java = conventions_for('java')
        assert java.is_test_name('testParse', 'src/test/java/FooTest.java')
        assert java.is_test_name('testParse', 'FooTests.java')
        assert not java.is_test_name('testParse', 'src/main/java/Foo.java')
        assert not java.is_test_name('parse', 'src/test/java/FooTest.java')

    def test_python_prefix_unscoped(self):
        from reveal.conventions import conventions_for
        assert conventions_for('python').is_test_name('test_x', 'anywhere.py')


def test_rust_trait_impl_methods_flagged(tmp_path):
    """BACK-1291: methods of `impl Trait for T` carry trait_impl; inherent ones don't."""
    from reveal.registry import get_analyzer
    src = tmp_path / 't.rs'
    src.write_text(
        'struct A;\n'
        'impl std::fmt::Display for A {\n'
        '    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result { Ok(()) }\n'
        '}\n'
        'impl A {\n'
        '    fn plain(&self) { fn nested() {} }\n'
        '}\n'
    )
    funcs = {f['name']: f for f in get_analyzer(str(src))(str(src)).get_structure()['functions']}
    assert funcs['fmt'].get('trait_impl') is True
    assert 'trait_impl' not in funcs['plain']
    assert 'trait_impl' not in funcs.get('nested', {})


class TestEntryPointDecorators:
    """BACK-1273: framework entry-point decorators are per-language, case-sensitive."""

    def test_nestjs_and_spring_are_entry_points(self):
        from reveal.conventions import conventions_for
        assert 'Get' in conventions_for('js').entry_point_decorators
        assert 'GetMapping' in conventions_for('java').entry_point_decorators
        assert 'Override' in conventions_for('java').entry_point_decorators

    def test_python_verbs_stay_python_and_rust(self):
        from reveal.conventions import conventions_for
        assert 'route' in conventions_for('python').entry_point_decorators
        assert 'get' in conventions_for('rust').entry_point_decorators
        assert 'route' not in conventions_for('java').entry_point_decorators
        assert conventions_for('go').entry_point_decorators == frozenset()

    def test_java_main_is_implicit(self):
        from reveal.conventions import conventions_for
        assert conventions_for('java').is_implicit_name('main')
        assert conventions_for('csharp').is_implicit_name('Main')


class TestEntryPointAndReexportFiles:
    """BACK-1287: entry-point / barrel-file conventions are per language."""

    def test_pack_entry_point_names_cover_more_languages(self):
        from reveal.adapters.pack import _is_entry_point_name, _is_entry_config_file
        for n in ('Program.cs', 'Application.java', 'main.swift', 'index.php', 'main.cpp', 'lib.rs', 'main.py'):
            assert _is_entry_point_name(n), n
        assert not _is_entry_point_name('helpers.py')
        for n in ('go.mod', 'pom.xml', 'build.gradle.kts', 'Gemfile', 'composer.json',
                  'CMakeLists.txt', 'Package.swift', 'App.csproj'):
            assert _is_entry_config_file(n), n

    def test_makefile_and_dockerfile_match_despite_case(self):
        # _compute_priority lowercases the name; the set used to hold 'Makefile'.
        from reveal.adapters.pack import _is_entry_config_file
        assert _is_entry_config_file('makefile') and _is_entry_config_file('Dockerfile')

    def test_makefile_earns_root_bonus(self, tmp_path):
        from reveal.adapters.pack import _compute_priority
        mk = tmp_path / 'Makefile'
        mk.write_text('all:\n\techo hi\n')
        assert _compute_priority(mk, mk.relative_to(tmp_path), None) >= 10.0

    def test_reexport_barrels_excluded_from_core_abstractions(self):
        from reveal.adapters.architecture import _is_reexport_file
        for f in ('pkg/__init__.py', 'src/index.ts', 'src/net/mod.rs', 'pkg/doc.go'):
            assert _is_reexport_file(f), f
        for f in ('pkg/core.py', 'src/lib.rs', 'src/main.ts'):
            assert not _is_reexport_file(f), f
