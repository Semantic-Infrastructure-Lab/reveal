"""Kotlin and Scala imports of a top-level type declared in a differently named file (BACK-2510).

Kotlin and Scala let any file hold any top-level declaration. ``import app.screens.DiscoverScreen`` is
resolved by path (``DiscoverScreen.kt``), so an ``object DiscoverScreen`` declared in ``Screens.kt``
was never an edge: ``imports://Screens.kt?importers`` printed "No importers found" while 42 files
imported from it (tivi). The declared-symbol index C# already uses (``namespaced_type_fallback``)
now carries top-level types for both languages.

Each answer is read through ``imports://<file>?importers`` and compared as the full set of
(importer, target, line) rows, so a lost right edge fails as loudly as a kept wrong one.
"""
import json
import os
import urllib.parse
from pathlib import Path

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component


def _write(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root.resolve()


def _edges(scan: Path, suffix: str) -> set:
    """Every (importer, target, line) row the public importers view reports under ``scan``."""
    rows = set()
    quoted_root = urllib.parse.quote(scan.as_posix(), safe='/:')
    for target in sorted(scan.rglob(f'*{suffix}')):
        response = _run_reveal_direct(f'imports://{target.as_posix()}?importers&root={quoted_root}',
                                      '--format', 'json')
        assert response.returncode == 0, response.stderr
        for row in json.loads(response.stdout)['importers']:
            importer = Path(os.path.normpath(target.parent / row['file']))
            rows.add((importer.relative_to(scan).as_posix(), target.relative_to(scan).as_posix(), row['line']))
    return rows


KOTLIN = {
    # The declaring file is not named after any of its types.
    'src/app/screens/Screens.kt': (
        'package app.screens\n'
        'object DiscoverScreen\n'
        'class AccountScreen\n'
        'interface Navigator\n'
        'typealias Route = String\n'
        'class Outer {\n    class Inner\n}\n'),
    'src/app/ui/UsesObject.kt': 'package app.ui\nimport app.screens.DiscoverScreen\nclass UsesObject\n',
    'src/app/ui/UsesClass.kt': 'package app.ui\nimport app.screens.AccountScreen\nclass UsesClass\n',
    'src/app/ui/UsesInterface.kt': 'package app.ui\nimport app.screens.Navigator\nclass UsesInterface\n',
    'src/app/ui/UsesAlias.kt': 'package app.ui\nimport app.screens.Route\nclass UsesAlias\n',
    # Controls: a nested type is not a top-level declaration; nothing to guess.
    'src/app/ui/UsesNested.kt': 'package app.ui\nimport app.screens.Inner\nclass UsesNested\n',
    'src/app/ui/UsesNestedQualified.kt': 'package app.ui\nimport app.screens.Outer.Inner\nclass UsesNestedQualified\n',
    # Control: the right simple name in the wrong package is external, never matched.
    'src/app/ui/UsesOtherPackage.kt': 'package app.ui\nimport lib.other.DiscoverScreen\nclass UsesOtherPackage\n',
    # Control: a file named for its type keeps resolving by path.
    'src/app/data/Repo.kt': 'package app.data\nclass Repo\n',
    'src/app/ui/UsesRepo.kt': 'package app.ui\nimport app.data.Repo\nclass UsesRepo\n',
}

KOTLIN_EDGES = {
    ('app/ui/UsesObject.kt', 'app/screens/Screens.kt', 2),
    ('app/ui/UsesClass.kt', 'app/screens/Screens.kt', 2),
    ('app/ui/UsesInterface.kt', 'app/screens/Screens.kt', 2),
    ('app/ui/UsesAlias.kt', 'app/screens/Screens.kt', 2),
    # `Outer.Inner` is reached through Outer, declared in Screens.kt (BACK-2512; it had no edge before)
    ('app/ui/UsesNestedQualified.kt', 'app/screens/Screens.kt', 2),
    ('app/ui/UsesRepo.kt', 'app/data/Repo.kt', 2),
}


def test_kotlin_import_of_a_top_level_type_in_a_differently_named_file_is_an_edge(tmp_path):
    root = _write(tmp_path, KOTLIN)
    assert _edges(root / 'src', '.kt') == KOTLIN_EDGES


def test_kotlin_same_name_in_two_packages_is_never_guessed(tmp_path):
    root = _write(tmp_path, {
        'src/a/Models.kt': 'package a\nclass Dup\n',
        'src/b/Other.kt': 'package b\nclass Dup\n',
        'src/c/Uses.kt': 'package c\nimport a.Dup\nclass Uses\n',
    })
    assert _edges(root / 'src', '.kt') == {('c/Uses.kt', 'a/Models.kt', 2)}


def test_kotlin_same_name_declared_in_two_files_of_one_package_fans_out(tmp_path):
    # The existing member-index policy: without type inference there is no principled pick (KMP source sets).
    root = _write(tmp_path, {
        'src/common/Platform.kt': 'package app.p\nexpect class Clock\n',
        'src/android/Impl.kt': 'package app.p\nclass Clock\n',
        'src/app/Uses.kt': 'package app.u\nimport app.p.Clock\nclass Uses\n',
    })
    assert _edges(root / 'src', '.kt') == {
        ('app/Uses.kt', 'common/Platform.kt', 2),
        ('app/Uses.kt', 'android/Impl.kt', 2),
    }


SCALA = {
    'src/gb/core/ControllerBase.scala': (
        'package gb.core\n'
        'case class Context(name: String)\n'
        'trait Helper\n'
        'object Registry\n'
        'class Outer {\n    class Inner\n}\n'),
    'src/gb/web/UsesCase.scala': 'package gb.web\nimport gb.core.Context\nclass UsesCase\n',
    'src/gb/web/UsesTrait.scala': 'package gb.web\nimport gb.core.Helper\nclass UsesTrait\n',
    'src/gb/web/UsesObject.scala': 'package gb.web\nimport gb.core.Registry\nclass UsesObject\n',
    # Chained package clauses declare cats.effect.std, in a file named for none of its types.
    'src/cats/effect/std/Misc.scala': 'package cats\npackage effect\npackage std\n\nclass Semaphore\n',
    'src/gb/web/UsesChained.scala': 'package gb.web\nimport cats.effect.std.Semaphore\nclass UsesChained\n',
    # Controls.
    'src/gb/web/UsesNested.scala': 'package gb.web\nimport gb.core.Inner\nclass UsesNested\n',
    'src/gb/web/UsesBareChainPrefix.scala': 'package gb.web\nimport cats.Semaphore\nclass UsesBareChainPrefix\n',
    'src/gb/web/UsesOtherPackage.scala': 'package gb.web\nimport lib.other.Context\nclass UsesOtherPackage\n',
    'src/gb/data/Repo.scala': 'package gb.data\nclass Repo\n',
    'src/gb/web/UsesRepo.scala': 'package gb.web\nimport gb.data.Repo\nclass UsesRepo\n',
}

SCALA_EDGES = {
    ('gb/web/UsesCase.scala', 'gb/core/ControllerBase.scala', 2),
    ('gb/web/UsesTrait.scala', 'gb/core/ControllerBase.scala', 2),
    ('gb/web/UsesObject.scala', 'gb/core/ControllerBase.scala', 2),
    ('gb/web/UsesChained.scala', 'cats/effect/std/Misc.scala', 2),
    ('gb/web/UsesRepo.scala', 'gb/data/Repo.scala', 2),
}


def test_scala_import_of_a_top_level_type_in_a_differently_named_file_is_an_edge(tmp_path):
    root = _write(tmp_path, SCALA)
    assert _edges(root / 'src', '.scala') == SCALA_EDGES
