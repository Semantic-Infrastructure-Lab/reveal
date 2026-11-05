"""Kotlin and Scala imports that reach a name THROUGH a declared top-level symbol (BACK-2512).

``import a.b.Outer.Inner``, ``import a.b.Outer.Companion.f``, ``import a.b.Obj.profile.Api._`` name a member
of ``Outer``/``Obj``, so the file declaring ``(a.b, Outer)`` is the dependency even when that file is not
named ``Outer``. The resolver peels trailing segments, longest DECLARED package first. Controls: a prefix
that is not a declared package is never peeled, a package wildcard stays a package, and an exact
``(package, symbol)`` hit is taken before any peel.
"""
import json
import os
import urllib.parse
from pathlib import Path

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component


def _scan(root: Path, files: dict, suffix: str) -> set:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    scan = root.resolve()
    quoted = urllib.parse.quote(scan.as_posix(), safe='/:')
    rows = set()
    for target in sorted(scan.rglob(f'*{suffix}')):
        response = _run_reveal_direct(f'imports://{target.as_posix()}?importers&root={quoted}', '--format', 'json')
        assert response.returncode == 0, response.stderr
        for row in json.loads(response.stdout)['importers']:
            importer = Path(os.path.normpath(target.parent / row['file']))
            rows.add((importer.relative_to(scan).as_posix(), target.relative_to(scan).as_posix()))
    return rows


def test_scala_import_through_a_symbol_declared_in_a_differently_named_file(tmp_path):
    files = {
        'src/Things.scala': 'package a.b\n\nobject Par {\n  type ParallelF = Int\n}\nobject profile {\n  object api\n}\n',
        'src/Other.scala': 'package a.b\n\nclass Other\n',
        'src/Use1.scala': 'package app\n\nimport a.b.Par.ParallelF\nclass Use1\n',
        'src/Use2.scala': 'package app\n\nimport a.b.profile.api._\nclass Use2\n',
        # control: not a declared package, so nothing is peeled onto a.b.Other
        'src/Use3.scala': 'package app\n\nimport x.y.Other.Missing\nclass Use3\n',
        # control: a package wildcard names no file
        'src/Use4.scala': 'package app\n\nimport a.b._\nclass Use4\n',
    }
    assert _scan(tmp_path, files, '.scala') == {('src/Use1.scala', 'src/Things.scala'),
                                                ('src/Use2.scala', 'src/Things.scala')}


def test_kotlin_import_through_a_companion_of_a_class_declared_in_another_file(tmp_path):
    files = {
        'src/Channel.kt': 'package k.ch\n\nclass ChannelResult {\n  companion object {\n    val closed = 1\n  }\n}\n',
        'src/Use1.kt': 'package app\n\nimport k.ch.ChannelResult.Companion.closed\n\nclass Use1\n',
        'src/Use2.kt': 'package app\n\nimport k.ch.ChannelResult.Companion.*\n\nclass Use2\n',
        'src/Use3.kt': 'package app\n\nimport nope.ch.ChannelResult.Companion.closed\n\nclass Use3\n',
    }
    assert _scan(tmp_path, files, '.kt') == {('src/Use1.kt', 'src/Channel.kt'), ('src/Use2.kt', 'src/Channel.kt')}
