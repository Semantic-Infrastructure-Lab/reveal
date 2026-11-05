"""Scala imports that name several targets in one statement (BACK-1237).

``import a.b.{X, Y}`` names X and Y, each a file of its own; ``import a.Implicits._`` names the one file
that declares ``object Implicits``. Reveal used to resolve none of them: about half of all Scala import
edges on GitBucket and cats-effect (53.25% and 47.14% recall with selector lists scored). Each name now
resolves through the same cascade as an explicit ``import a.b.X``. A package wildcard (``a.b._``, or
``_``/``*`` inside braces) still names no file: that is the wildcard question (BACK-1711/2506), not this.

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
    'src/a/b/X.scala': 'package a.b\nclass X\n',
    # Y and Z are declared in a file not named after either (the BACK-2510 index finds them).
    'src/a/b/Things.scala': 'package a.b\nclass Y\nobject Z\n',
    'src/a/b/W.scala': 'package a.b\nobject W\n',
    'src/a/b/Implicits.scala': 'package a.b\nobject Implicits {\n  def f: Int = 1\n}\n',
    # Reachable only through a package wildcard: must stay without an edge.
    'src/a/b/OnlyByWildcard.scala': 'package a.b\nclass OnlyByWildcard\n',
}


def _scan(tmp_path: Path, importers: dict) -> set:
    return _edges(_write(tmp_path, {**TARGETS, **importers}))


def test_selector_list_names_each_target(tmp_path):
    rows = _scan(tmp_path, {'src/c/Sel.scala': 'package c\nimport a.b.{X, Y}\nclass Sel\n'})
    assert rows == {('src/c/Sel.scala', 'src/a/b/X.scala', 2), ('src/c/Sel.scala', 'src/a/b/Things.scala', 2)}


def test_rename_binds_the_original_name_and_hide_names_nothing(tmp_path):
    rows = _scan(tmp_path, {'src/c/Ren.scala': 'package c\nimport a.b.{X => Ex, W => _, Z}\nclass Ren\n'})
    assert rows == {('src/c/Ren.scala', 'src/a/b/X.scala', 2), ('src/c/Ren.scala', 'src/a/b/Things.scala', 2)}


def test_multiline_selector_list(tmp_path):
    rows = _scan(tmp_path, {'src/c/Multi.scala': 'package c\nimport a.b.{\n  X,\n  W\n}\nclass Multi\n'})
    assert rows == {('src/c/Multi.scala', 'src/a/b/X.scala', 2), ('src/c/Multi.scala', 'src/a/b/W.scala', 2)}


def test_comment_inside_a_selector_list_names_nothing(tmp_path):
    rows = _scan(tmp_path, {'src/c/Cmt.scala': 'package c\nimport a.b.{X /*, W*/, Y} // and Z\nclass Cmt\n'})
    assert rows == {('src/c/Cmt.scala', 'src/a/b/X.scala', 2), ('src/c/Cmt.scala', 'src/a/b/Things.scala', 2)}


def test_comma_separated_import_expressions(tmp_path):
    rows = _scan(tmp_path, {'src/c/Comma.scala': 'package c\nimport a.b.X, a.b.W\nclass Comma\n'})
    assert rows == {('src/c/Comma.scala', 'src/a/b/X.scala', 2), ('src/c/Comma.scala', 'src/a/b/W.scala', 2)}


def test_type_member_wildcard_names_the_declaring_file(tmp_path):
    rows = _scan(tmp_path, {
        'src/c/Mem.scala': 'package c\nimport a.b.Implicits._\nclass Mem\n',
        'src/c/Mem3.scala': 'package c\nimport a.b.Implicits.*\nclass Mem3\n',
    })
    assert rows == {('src/c/Mem.scala', 'src/a/b/Implicits.scala', 2),
                    ('src/c/Mem3.scala', 'src/a/b/Implicits.scala', 2)}


def test_package_wildcards_still_name_no_file(tmp_path):
    """Control: a package wildcard, bare or inside braces, depends on a package, not one file, even when
    the enclosing package also declares a symbol of the same name (``object b`` in ``a``)."""
    rows = _scan(tmp_path, {
        'src/a/BObject.scala': 'package a\nobject b\n',
        'src/c/Wild.scala': 'package c\nimport a.b._\nclass Wild\n',
        'src/c/Wild3.scala': 'package c\nimport a.b.*\nclass Wild3\n',
        'src/c/BraceWild.scala': 'package c\nimport a.b.{X => _, _}\nclass BraceWild\n',
    })
    assert rows == set()


def test_external_selector_list_is_no_edge(tmp_path):
    """Control: names of a package the tree does not declare resolve to nothing."""
    rows = _scan(tmp_path, {'src/c/Ext.scala': 'package c\nimport scala.collection.{Seq, Map}\nclass Ext\n'})
    assert rows == set()


def test_kotlin_type_member_wildcard_names_the_declaring_file(tmp_path):
    """Kotlin shares the member lookup: ``import s.Result.*`` imports an enum's entries (kotlinx.coroutines
    ``TrySelectDetailedResult.*``), while ``import s.*`` stays a package wildcard."""
    scan = _write(tmp_path, {
        'src/s/Select.kt': 'package s\nenum class Result { A, B }\n',
        'src/s/Other.kt': 'package s\nclass Other\n',
        'src/u/U.kt': 'package u\nimport s.*\nimport s.Result.*\nclass U\n',
    })
    rows = _edges(scan, '.kt')
    assert rows == {('src/u/U.kt', 'src/s/Select.kt', 3)}
