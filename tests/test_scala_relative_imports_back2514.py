"""Scala imports relative to a package the file's own package clause opens (BACK-2514).

Inside ``package gitbucket.core.util``, ``import Directory._`` names the members of ``object Directory``
declared in that same package; Scala reads the first segment against the packages in scope before the
root. Reveal read every import as absolute, so these got no edge: 23 of the 27 misses left on the four
Kotlin/Scala gate rows (GitBucket ``Directory``/``ConfigUtil``/``StringUtil``/``Implicits``, cats-effect
``TracingConstants``, ``IOFiberConstants``, ``Outcome``, ``Sync.Type``, ...).

Which packages a file opens is the language rule, not every prefix of its package: a single clause
``package a.b.c`` opens ``a.b.c`` only, while chained clauses ``package a.b`` / ``package c`` open both
``a.b`` and ``a.b.c`` (innermost first). An absolute reading that resolves is kept as before; the relative
reading is tried only when it does not, so no existing edge moves.

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


def _edges(scan: Path, suffix: str = '.scala') -> set:
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


TARGETS = {
    # Declared in files not named after them, so only the declared-symbol index can find them.
    'src/a/b/Dirs.scala': 'package a.b\nobject Directory {\n  val Root = "/"\n}\n',
    'src/a/Outcomes.scala': 'package a\nsealed trait Outcome\nobject Outcome {\n  case class Done() extends Outcome\n}\n',
    'src/a/b/c/Thing.scala': 'package a.b.c\nclass Thing\n',
}


def _scan(tmp_path: Path, importers: dict) -> set:
    return _edges(_write(tmp_path, {**TARGETS, **importers}) / 'src')


def test_same_package_type_member_wildcard(tmp_path):
    rows = _scan(tmp_path, {'src/a/b/User.scala': 'package a.b\nimport Directory._\nclass User\n'})
    assert rows == {('a/b/User.scala', 'a/b/Dirs.scala', 2)}


def test_same_package_member_import(tmp_path):
    rows = _scan(tmp_path, {'src/a/b/User.scala': 'package a.b\nimport Directory.Root\nclass User\n'})
    assert rows == {('a/b/User.scala', 'a/b/Dirs.scala', 2)}


def test_chained_clauses_open_the_enclosing_package(tmp_path):
    # `package a` / `package b` opens a and a.b: Outcome (in a) and Directory (in a.b) are both in scope.
    rows = _scan(tmp_path, {'src/a/b/Spec.scala': (
        'package a\npackage b\nimport Outcome._\nimport Directory._\nclass Spec\n')})
    assert rows == {('a/b/Spec.scala', 'a/Outcomes.scala', 3), ('a/b/Spec.scala', 'a/b/Dirs.scala', 4)}


def test_single_clause_does_not_open_its_parent_package(tmp_path):
    # `package a.b` opens a.b only; `Outcome` (declared in a) is not in scope, so no edge.
    rows = _scan(tmp_path, {'src/a/b/User.scala': 'package a.b\nimport Outcome._\nclass User\n'})
    assert rows == set()


def test_relative_subpackage(tmp_path):
    # Inside package a.b, `c.Thing` is a.b.c.Thing.
    rows = _scan(tmp_path, {'src/a/b/User.scala': 'package a.b\nimport c.Thing\nclass User\n'})
    assert rows == {('a/b/User.scala', 'a/b/c/Thing.scala', 2)}


def test_absolute_import_is_unchanged(tmp_path):
    rows = _scan(tmp_path, {'src/x/User.scala': 'package x\nimport a.b.Directory._\nimport a.b.c.Thing\nclass User\n'})
    assert rows == {('x/User.scala', 'a/b/Dirs.scala', 2), ('x/User.scala', 'a/b/c/Thing.scala', 3)}


def test_unrelated_package_gets_no_relative_edge(tmp_path):
    # Directory is declared in a.b, not in x: a relative reading from x finds nothing.
    rows = _scan(tmp_path, {'src/x/User.scala': 'package x\nimport Directory._\nclass User\n'})
    assert rows == set()


def test_package_wildcard_through_a_relative_name_names_no_file(tmp_path):
    # `import c._` inside a.b is the package wildcard a.b.c._ (BACK-1711): still no file.
    rows = _scan(tmp_path, {'src/a/b/User.scala': 'package a.b\nimport c._\nclass User\n'})
    assert rows == set()


def test_kotlin_has_no_relative_imports(tmp_path):
    files = {
        'src/a/b/Dirs.kt': 'package a.b\nobject Directory\n',
        'src/a/b/User.kt': 'package a.b\nimport Directory\nclass User\n',
    }
    assert _edges(_write(tmp_path, files) / 'src', '.kt') == set()


@pytest.mark.xfail(strict=True, reason='BACK-2514 limit: Scala resolves a relative first segment before the root '
                   'package; Reveal (and the declaration oracle) keep the absolute reading when it resolves, so a '
                   'name that is both a root package and a subpackage of an opened package lands on the root one')
def test_relative_reading_shadows_a_root_package_of_the_same_name(tmp_path):
    files = {**TARGETS,
             'src/c/Thing.scala': 'package c\nclass Thing\n',
             'src/a/b/User.scala': 'package a.b\nimport c.Thing\nclass User\n'}
    assert _edges(_write(tmp_path, files) / 'src') == {('a/b/User.scala', 'a/b/c/Thing.scala', 2)}


def test_own_companion_import_in_each_platform_copy_is_no_edge(tmp_path):
    # cats-effect core/js and core/jvm-native both declare `object CallbackStack` in cats.effect, and each
    # runs `import CallbackStack.Handle` on its own: the name is the importer's own declaration.
    files = {
        'src/js/a/Stack.scala': 'package a\nimport Stack.Handle\nobject Stack {\n  class Handle\n}\n',
        'src/jvm/a/Stack.scala': 'package a\nimport Stack.Handle\nobject Stack {\n  class Handle\n}\n',
    }
    assert _edges(_write(tmp_path, files) / 'src') == set()
