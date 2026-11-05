"""Independent Kotlin and Scala import truth: a type is declared in its package, whatever the file is named (BACK-2507).

The oracle must not share a bug with Reveal's resolver, so it is exercised on its own here, including the
shapes that fool a line scan: declarations and imports that only appear in comments or string literals,
nested types, chained Scala package clauses, selector lists read name by name, type-member wildcards scored
through the symbol they name, and package wildcards that are counted, never scored (BACK-1237).
"""
import pytest

from test_recall_gate import _repo, gate, oracles

pytestmark = pytest.mark.component


def _edges(tmp_path, name, files, importers=None, **config):
    root, entry = _repo(tmp_path, files, {'oracle': name, 'importer_dirs': ['.'], **config})
    oracle = oracles.ORACLES[name]
    scan = root
    population = [root / p for p in (importers or files)]
    return oracle.build(oracles.Scope(root, scan, population, entry['recall']))


def test_both_oracles_are_registered_with_their_own_suffix():
    assert oracles.ORACLES['kotlin-declared'].suffixes == frozenset({'.kt'})
    assert oracles.ORACLES['scala-declared'].suffixes == frozenset({'.scala'})


KOTLIN = {
    'src/Screens.kt': (
        'package app.screens\n'
        'object DiscoverScreen\n'
        'data class AccountScreen(val id: Int)\n'
        'sealed interface Navigator\n'
        'fun interface Handler { fun go() }\n'
        'typealias Route = String\n'
        'fun String.shout(): String = this\n'
        'val <T> List<T>.second: T get() = this[1]\n'
        'class Outer { class Inner }\n'),
    'src/UsesObject.kt': 'package app.ui\nimport app.screens.DiscoverScreen\n',
    'src/UsesData.kt': 'package app.ui\nimport app.screens.AccountScreen\n',
    'src/UsesSealed.kt': 'package app.ui\nimport app.screens.Navigator\n',
    'src/UsesFun.kt': 'package app.ui\nimport app.screens.Handler\n',
    'src/UsesAlias.kt': 'package app.ui\nimport app.screens.Route as R\n',
    'src/UsesExtension.kt': 'package app.ui\nimport app.screens.shout\n',
    'src/UsesProperty.kt': 'package app.ui\nimport app.screens.second\n',
    'src/UsesNested.kt': 'package app.ui\nimport app.screens.Outer.Inner\n',
}


def test_kotlin_every_top_level_declaration_kind_is_a_target(tmp_path):
    edges, coverage = _edges(tmp_path, 'kotlin-declared', KOTLIN, [p for p in KOTLIN if 'Uses' in p])
    assert edges == {'src/Screens.kt': sorted(p for p in KOTLIN if 'Uses' in p)}
    assert coverage['import_statements'] == coverage['resolved_statements'] == 8


def test_kotlin_text_in_comments_and_strings_declares_and_imports_nothing(tmp_path):
    files = {
        'src/Decoy.kt': ('package lib\n'
                         '// class Ghost\n'
                         '/* object Phantom /* nested */ class Wraith */\n'
                         'val note = """\nclass Spirit\nimport lib.Real\n"""\n'
                         'val tpl = "a ${"b"} class Banshee"\n'
                         "val quote = '\"'\n"
                         'class Real\n'),
        'src/Use.kt': ('package app\n'
                       'import lib.Ghost\nimport lib.Phantom\nimport lib.Spirit\nimport lib.Banshee\n'
                       'import lib.Real\n'
                       'val s = """\nimport lib.Phantom\n"""\n'),
    }
    edges, coverage = _edges(tmp_path, 'kotlin-declared', files, ['src/Use.kt'])
    assert edges == {'src/Decoy.kt': ['src/Use.kt']}
    assert coverage['import_statements'] == 5 and coverage['resolved_statements'] == 1


def test_kotlin_nested_declaration_is_not_top_level_and_same_name_in_two_packages_is_not_mixed(tmp_path):
    files = {
        'src/A.kt': 'package a\nclass Holder {\n    class Hidden\n    fun inner() {}\n}\nclass Dup\n',
        'src/B.kt': 'package b\nclass Dup\n',
        'src/U.kt': 'package c\nimport a.Hidden\nimport a.Dup\nimport a.inner\n',
    }
    edges, coverage = _edges(tmp_path, 'kotlin-declared', files, ['src/U.kt'])
    assert edges == {'src/A.kt': ['src/U.kt']}  # Dup resolves to package a only
    assert coverage['import_statements'] == 3 and coverage['resolved_statements'] == 1


def test_kotlin_same_name_in_two_files_of_one_package_is_an_edge_to_each(tmp_path):
    files = {
        'common/P.kt': 'package p\nexpect class Clock\n',
        'android/P.kt': 'package p\nactual class Clock\n',
        'src/U.kt': 'package u\nimport p.Clock\n',
    }
    edges, _ = _edges(tmp_path, 'kotlin-declared', files, ['src/U.kt'])
    assert edges == {'android/P.kt': ['src/U.kt'], 'common/P.kt': ['src/U.kt']}


def test_kotlin_wildcards_are_counted_never_scored(tmp_path):
    files = {'src/A.kt': 'package a\nclass X\n', 'src/U.kt': 'package u\nimport a.*\n'}
    edges, coverage = _edges(tmp_path, 'kotlin-declared', files, ['src/U.kt'])
    assert edges == {}
    assert coverage['wildcard_statements'] == 1 and coverage['import_statements'] == 0
    assert coverage['in_tree_package_wildcards'] == 1 and coverage['type_member_wildcards'] == 0


def test_kotlin_type_member_wildcard_depends_on_the_declaring_file(tmp_path):
    files = {'src/Select.kt': 'package s\nenum class Result { A, B }\n', 'src/U.kt': 'package u\nimport s.Result.*\n'}
    edges, coverage = _edges(tmp_path, 'kotlin-declared', files, ['src/U.kt'])
    assert edges == {'src/Select.kt': ['src/U.kt']}
    assert coverage['type_member_wildcards'] == 1 and coverage['in_tree_package_wildcards'] == 0


SCALA = {
    'src/ControllerBase.scala': (
        'package gb.core\n'
        'case class Context(name: String)\n'
        'sealed trait Helper\n'
        'abstract class Base\n'
        'object registry { def find(): Int = 1 }\n'
        'implicit class Rich(s: String)\n'
        'class Outer { class Inner }\n'),
    'src/Misc.scala': 'package cats\npackage effect\npackage std\n\nfinal class Semaphore\n',
    'src/UsesCase.scala': 'package gb.web\nimport gb.core.Context\n',
    'src/UsesTrait.scala': 'package gb.web\nimport gb.core.Helper\n',
    'src/UsesAbstract.scala': 'package gb.web\nimport gb.core.Base\n',
    'src/UsesMember.scala': 'package gb.web\nimport gb.core.registry.find\n',
    'src/UsesImplicit.scala': 'package gb.web\nimport gb.core.Rich\n',
    'src/UsesChained.scala': 'package gb.web\nimport cats.effect.std.Semaphore\n',
    'src/UsesNested.scala': 'package gb.web\nclass A {\n  import gb.core.Outer.Inner\n}\n',
}


def test_scala_declarations_chained_packages_and_scoped_imports(tmp_path):
    users = [p for p in SCALA if 'Uses' in p]
    edges, coverage = _edges(tmp_path, 'scala-declared', SCALA, users)
    assert edges == {
        'src/ControllerBase.scala': sorted(p for p in users if p != 'src/UsesChained.scala'),
        'src/Misc.scala': ['src/UsesChained.scala'],
    }
    assert coverage['import_statements'] == coverage['resolved_statements'] == 7


def test_scala_wrong_chain_prefix_does_not_resolve(tmp_path):
    files = {
        'src/Misc.scala': 'package cats\npackage effect\n\nclass Thing\n',
        'src/U.scala': 'package gb\nimport cats.Thing\n',
    }
    edges, coverage = _edges(tmp_path, 'scala-declared', files, ['src/U.scala'])
    assert edges == {} and coverage['resolved_statements'] == 0
    assert coverage['import_statements'] == 1


def test_scala_selector_lists_are_read_name_by_name_and_package_wildcards_are_counted(tmp_path):
    files = {
        'src/A.scala': 'package a\nclass X\nclass Y\nclass Z\n',
        'src/B.scala': 'package a\nclass W\n',
        'src/U.scala': 'package u\nimport a.{X, W => Why, Z => _, _}\nimport a._\nimport a.X, a.Y\n',
    }
    edges, coverage = _edges(tmp_path, 'scala-declared', files, ['src/U.scala'])
    assert edges == {'src/A.scala': ['src/U.scala'], 'src/B.scala': ['src/U.scala']}  # Z is hidden
    assert coverage['selector_lists'] == 1 and coverage['wildcard_statements'] == 2
    assert coverage['in_tree_package_wildcards'] == 2 and coverage['type_member_wildcards'] == 0
    assert coverage['import_statements'] == 4  # X, W from the selector list; X, Y comma-separated


def test_scala_selector_list_over_several_lines(tmp_path):
    files = {
        'src/A.scala': 'package a\nclass X\nclass Y\n',
        'src/U.scala': 'package u\nimport a.{\n  X,\n  Y\n}\nimport a.X\n',
    }
    edges, coverage = _edges(tmp_path, 'scala-declared', files, ['src/U.scala'])
    assert edges == {'src/A.scala': ['src/U.scala']}
    assert coverage['selector_lists'] == 1 and coverage['import_statements'] == 3


def test_scala_type_member_wildcard_and_package_named_like_a_symbol(tmp_path):
    """``a.Implicits._`` depends on the file declaring ``object Implicits``. ``a.b._`` is a package wildcard
    when the tree declares package ``a.b``, even though package ``a`` also declares ``object b``."""
    files = {
        'src/Implicits.scala': 'package a\nobject Implicits { def f: Int = 1 }\n',
        'src/BObject.scala': 'package a\nobject b\n',
        'src/Q.scala': 'package a.b\nclass Q\n',
        'src/U.scala': 'package u\nimport a.Implicits._\nimport a.b._\nimport scala.collection._\n',
    }
    edges, coverage = _edges(tmp_path, 'scala-declared', files, ['src/U.scala'])
    assert edges == {'src/Implicits.scala': ['src/U.scala']}
    assert coverage['wildcard_statements'] == 3 and coverage['type_member_wildcards'] == 1
    assert coverage['in_tree_package_wildcards'] == 1 and coverage['import_statements'] == 0


def test_scala_import_relative_to_an_enclosing_package(tmp_path):
    files = {
        'src/T.scala': 'package cats.effect.std\nclass Queue\n',
        'src/U.scala': 'package cats\npackage effect\nimport std.Queue\n',
    }
    edges, _ = _edges(tmp_path, 'scala-declared', files, ['src/U.scala'])
    assert edges == {'src/T.scala': ['src/U.scala']}


def test_scala_text_in_comments_and_interpolated_strings_declares_nothing(tmp_path):
    files = {
        'src/D.scala': ('package lib\n// class Ghost\n/* trait Phantom */\n'
                        'object Strings { val s = s"""class Spirit ${1 + 1}"""; val t = "class Wraith" }\n'
                        'class Real\n'),
        'src/U.scala': 'package app\nimport lib.Ghost\nimport lib.Phantom\nimport lib.Spirit\nimport lib.Real\n',
    }
    edges, coverage = _edges(tmp_path, 'scala-declared', files, ['src/U.scala'])
    assert edges == {'src/D.scala': ['src/U.scala']}
    assert coverage['import_statements'] == 4 and coverage['resolved_statements'] == 1


def test_scala_import_does_not_peel_past_a_package_onto_a_package_object(tmp_path):
    # `cats.effect.unsafe.implicits.global`: `effect` is a package object of `cats` AND the package `cats.effect`.
    # The longest package prefix wins; a name that package does not declare resolves to nothing. A member of the
    # package object IS a declaration in `cats.effect` (BACK-2515): `cats.effect.x` is a dependency on its file.
    files = {
        'src/effect.scala': 'package cats\npackage object effect {\n  val x = 1\n}\n',
        'src/Unsafe.scala': 'package cats.effect.unsafe\nobject Other\n',
        'src/U.scala': 'package app\nimport cats.effect.unsafe.implicits.global\nimport cats.effect.x\n',
    }
    edges, coverage = _edges(tmp_path, 'scala-declared', files, ['src/U.scala'])
    assert edges == {'src/effect.scala': ['src/U.scala']}
    assert coverage['import_statements'] == 2 and coverage['resolved_statements'] == 1


def test_scala_package_object_is_a_package_not_a_symbol(tmp_path):
    # BACK-2515: `import a.ex._` (a package wildcard, `ex` is also a package object) and `import a.{ex => e}`
    # name no declaration; neither is an edge to the package object's file.
    files = {
        'src/ex.scala': 'package a\npackage object ex {\n  def shared = 1\n}\n',
        'src/U.scala': 'package app\nimport a.ex._\nimport a.{ex => e}\nimport a.ex.shared\n',
    }
    edges, coverage = _edges(tmp_path, 'scala-declared', files, ['src/U.scala'])
    assert edges == {'src/ex.scala': ['src/U.scala']}  # only the member import, `a.ex.shared`
    assert coverage['in_tree_package_wildcards'] == 1 and coverage['resolved_statements'] == 1  # the rename is unresolved

def test_kotlin_names_are_read_past_type_parameters_arrows_and_receivers(tmp_path):
    # `-> Unit` closes no type-parameter list, and a receiver's type is not a declared name.
    files = {
        'src/Builders.kt': ('package k.flow\n'
                            'public fun <T> flow(block: suspend FlowCollector<T>.() -> Unit): Flow<T> = TODO()\n'
                            'fun <T> Flow<T>.observeOn(x: Int): Flow<T> = this\n'
                            'val <T : Comparable<T>> List<T>.best: T get() = first()\n'
                            'class Box<T : Any>(val v: T)\n'),
        'src/U.kt': ('package u\nimport k.flow.flow as safeFlow\nimport k.flow.observeOn\nimport k.flow.best\n'
                     'import k.flow.Box\nimport k.flow.Flow\nimport k.flow.Unit\nimport k.flow.T\n'),
    }
    edges, coverage = _edges(tmp_path, 'kotlin-declared', files, ['src/U.kt'])
    assert edges == {'src/Builders.kt': ['src/U.kt']}
    assert coverage['import_statements'] == 7 and coverage['resolved_statements'] == 4  # Flow, Unit, T: not declared


def test_a_file_that_declares_a_name_does_not_import_another_copy_of_it(tmp_path):
    # Platform copies of one type: `import CallbackStack.Handle` in either is the file's own declaration.
    files = {
        'js/CallbackStack.scala': 'package cats.effect\nobject CallbackStack { class Handle }\n',
        'jvm/CallbackStack.scala': 'package cats.effect\nimport CallbackStack.Handle\nobject CallbackStack { class Handle }\n',
        'src/Use.scala': 'package app\nimport cats.effect.CallbackStack\n',
    }
    edges, _ = _edges(tmp_path, 'scala-declared', files, ['jvm/CallbackStack.scala', 'src/Use.scala'])
    assert edges == {'jvm/CallbackStack.scala': ['src/Use.scala'], 'js/CallbackStack.scala': ['src/Use.scala']}


def test_a_member_import_depends_on_the_file_declaring_the_symbol_it_goes_through(tmp_path):
    # `object helpers extends Service` inherits `getApiMilestone`, yet the import cannot be resolved without
    # helpers.scala. The oracle does not claim Service.scala: it cannot follow inheritance.
    files = {
        'src/helpers.scala': 'package view\nobject helpers extends Service { def own(): Int = 1; type Alias = Int }\n',
        'src/Service.scala': 'package view\ntrait Service { def getApiMilestone(): Int = 1 }\n',
        'src/U.scala': ('package app\nimport view.helpers.own\nimport view.helpers.Alias\n'
                        'import view.helpers.getApiMilestone\n'),
    }
    edges, coverage = _edges(tmp_path, 'scala-declared', files, ['src/U.scala'])
    assert edges == {'src/helpers.scala': ['src/U.scala']}
    assert coverage['import_statements'] == coverage['resolved_statements'] == 3


def test_kotlin_nested_and_companion_imports_depend_on_the_outer_declaration(tmp_path):
    files = {
        'src/Channel.kt': 'package ch\nclass ChannelResult<out T> {\n    companion object { fun closed() {} }\n}\n',
        'src/Prefs.kt': 'package ch\ninterface Prefs {\n    enum class Theme { LIGHT }\n}\n',
        'src/U.kt': 'package u\nimport ch.ChannelResult.Companion.closed\nimport ch.Prefs.Theme\n',
    }
    edges, coverage = _edges(tmp_path, 'kotlin-declared', files, ['src/U.kt'])
    assert edges == {'src/Channel.kt': ['src/U.kt'], 'src/Prefs.kt': ['src/U.kt']}
    assert coverage['resolved_statements'] == 2
