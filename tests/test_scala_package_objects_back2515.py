"""Scala package-object members are declarations (BACK-2515).

``package object testkit { type TestContext = kernel.testkit.TestContext }`` declares ``TestContext`` in the
package ``cats.effect.testkit``. Reveal indexed none of a package object's members, so an import of such a
name kept only the path guess: ``import cats.effect.testkit.TestContext`` landed on the aliased class
``kernel/testkit/TestContext.scala`` (another package), ``import cats.effect.kernel.ParallelF`` on
``ParallelF.scala`` (same package, but it declares ``object Par``, not ``ParallelF``), and
``import Resource.ExitCase`` inside ``package cats.effect`` on ``kernel/Resource.scala``. The file that
declares the name is the dependency (the package object's file); the aliased class is a further hop.

A package wildcard (``import a.ex._``) and a package rename (``import a.{kernel => k}``) name no declaration
and stay without an edge (BACK-2506 policy); the controls below pin that.

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


def _scan(tmp_path: Path, files: dict) -> set:
    return _edges(_write(tmp_path, files) / 'src')


KERNEL_TESTKIT = {
    # The aliased class, in another package than the alias.
    'src/kernel/testkit/Ctx.scala': 'package a.kernel.testkit\nclass Ctx\n',
    # Another file of the package the alias lives in, so it is a declared package.
    'src/testkit/Other.scala': 'package a.testkit\nclass Other\n',
}


def test_alias_import_resolves_to_the_package_object_not_the_aliased_class(tmp_path):
    files = {
        **KERNEL_TESTKIT,
        'src/testkit/package.scala': 'package a\npackage object testkit {\n  type Ctx = a.kernel.testkit.Ctx\n}\n',
        'src/use/Use.scala': 'package a.use\nimport a.testkit.Ctx\nclass Use\n',
    }
    assert _scan(tmp_path, files) == {('use/Use.scala', 'testkit/package.scala', 2)}


def test_same_package_file_that_declares_another_name_is_not_the_target(tmp_path):
    # ParallelF.scala declares `object Par`; `ParallelF` is the package object's alias.
    files = {
        'src/kernel/ParallelF.scala': 'package a.kernel\nobject Par {\n  type ParallelF[A] = A\n}\n',
        'src/kernel/package.scala': ('package a\npackage object kernel {\n'
                                     '  type ParallelF[A] = Par.ParallelF[A]\n  val ParallelF = Par.ParallelF\n}\n'),
        'src/instances/Inst.scala': 'package a.instances\nimport a.kernel.ParallelF\nclass Inst\n',
    }
    assert _scan(tmp_path, files) == {('instances/Inst.scala', 'kernel/package.scala', 2)}


def test_relative_import_of_a_package_object_alias(tmp_path):
    # `import Resource.ExitCase` inside `package cats.effect`: `Resource` is the package object's `val`.
    files = {
        'src/effect/package.scala': 'package cats\npackage object effect {\n  val Resource = kernel.Resource\n}\n',
        'src/kernel/Resource.scala': 'package cats.effect.kernel\nobject Resource {\n  object ExitCase\n}\n',
        'src/spec/ResourceSpec.scala': ('package cats.effect\nclass Spec {\n  def f = {\n'
                                        '    import Resource.ExitCase\n    ExitCase\n  }\n}\n'),
    }
    assert _scan(tmp_path, files) == {('spec/ResourceSpec.scala', 'effect/package.scala', 4)}


def test_every_kind_of_package_object_member_is_a_declaration(tmp_path):
    files = {
        'src/util/package.scala': ('package a\npackage object util {\n  class Box\n  object Tool\n'
                                   '  trait Shape\n  def go = 1\n  val K = 2\n  type T = Int\n}\n'),
        'src/use/Use.scala': ('package a.use\nimport a.util.Box\nimport a.util.Tool\nimport a.util.Shape\n'
                              'import a.util.go\nimport a.util.K\nimport a.util.T\nclass Use\n'),
    }
    assert _scan(tmp_path, files) == {('use/Use.scala', 'util/package.scala', line) for line in range(2, 8)}


def test_package_that_is_only_a_package_object_is_a_declared_package(tmp_path):
    # No file says `package a.only`; the package object does. A member reached through a class in it peels.
    files = {
        'src/only/package.scala': 'package a\npackage object only {\n  object Holder {\n    class Inner\n  }\n}\n',
        'src/use/Use.scala': 'package a.use\nimport a.only.Holder.Inner\nclass Use\n',
    }
    assert _scan(tmp_path, files) == {('use/Use.scala', 'only/package.scala', 2)}


def test_path_match_that_declares_the_name_stands(tmp_path):
    # Positive control for the name check: the file named for the class declares it (among other things).
    files = {
        'src/kernel/Ref.scala': 'package a.kernel\ntrait Ref\nobject Ref {\n  def of = 1\n}\nclass Helper\n',
        'src/kernel/package.scala': 'package a\npackage object kernel {\n  val Other = 1\n}\n',
        'src/use/Use.scala': 'package a.use\nimport a.kernel.Ref\nclass Use\n',
    }
    assert _scan(tmp_path, files) == {('use/Use.scala', 'kernel/Ref.scala', 2)}


def test_package_wildcard_of_a_package_with_a_package_object_names_no_file(tmp_path):
    files = {
        'src/ex/package.scala': 'package a\npackage object ex {\n  def shared = 1\n}\npackage ex {\n  object Run\n}\n',
        'src/use/Use.scala': 'package a.use\nimport a.ex._\nclass Use\n',
    }
    assert _scan(tmp_path, files) == set()


def test_package_rename_selector_names_no_file(tmp_path):
    files = {
        'src/kernel/package.scala': 'package a\npackage object kernel {\n  val X = 1\n}\n',
        'src/kernel/Thing.scala': 'package a.kernel\nclass Thing\n',
        'src/use/Use.scala': 'package a.use\nimport a.{kernel => k}\nclass Use\n',
    }
    assert _scan(tmp_path, files) == set()
