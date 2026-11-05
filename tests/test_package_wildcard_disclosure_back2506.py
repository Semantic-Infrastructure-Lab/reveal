"""imports:// discloses in-tree package wildcards instead of printing a clean zero (BACK-2506).

``import a.b.*`` (Kotlin, Java) or ``import a.b._`` (Scala) depends on package ``a.b``, not on one file,
and Reveal records no edge for it (BACK-1711: wildcards are excluded, never expanded). A file of ``a.b``
imported only that way printed "No importers found" and fan-in 0 with nothing said. Every imports://
answer's counting rule now states how many in-tree package wildcards it left out, under which packages,
and, for a requested file, whether its own package is one of them. The edge counts do not move.

"In-tree" is exact: the prefix is a package some scanned file declares. External wildcards
(``java.util.*``) and type-member wildcards (``a.b.Obj._``, an edge since BACK-1237) are not counted.
"""
import json
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


def _answer(scan: Path, target: str, query: str, fmt: str = 'json'):
    quoted_root = urllib.parse.quote(scan.as_posix(), safe='/:')
    response = _run_reveal_direct(f'imports://{(scan / target).as_posix()}?{query}&root={quoted_root}',
                                  '--format', fmt)
    assert response.returncode == 0, response.stderr
    return json.loads(response.stdout) if fmt == 'json' else response.stdout


KOTLIN = {
    'src/a/b/Foo.kt': 'package a.b\nclass Foo\n',
    'src/a/b/Bar.kt': 'package a.b\nclass Bar\n',
    'src/a/c/Baz.kt': 'package a.c\nclass Baz\n',
    'src/u/U.kt': 'package u\nimport a.b.*\nclass U\n',
    'src/u/V.kt': 'package u\nimport a.b.*\nimport java.util.*\nimport a.c.Baz\nclass V\n',
}


def test_importers_of_a_wildcard_only_file_say_what_was_left_out(tmp_path):
    scan = _write(tmp_path, KOTLIN)
    answer = _answer(scan, 'src/a/b/Foo.kt', 'importers')
    assert answer['importers'] == []  # no edge is invented
    disclosed = answer['edge_rule']['package_wildcards']
    assert disclosed == {'statements': 2, 'importers': 2, 'packages': {'a.b': 2}, 'requested_file': {'a.b': 2},
                         'rule': disclosed['rule']}
    assert 'declares' in disclosed['rule']
    text = answer['edge_rule']['text']
    assert '2 in-tree package wildcard import(s) in 2 file(s)' in text and 'a.b (2)' in text
    assert "package a.b is wildcard-imported by 2 file(s)" in text


def test_text_output_carries_the_same_sentence(tmp_path):
    scan = _write(tmp_path, KOTLIN)
    text = _answer(scan, 'src/a/b/Foo.kt', 'importers', fmt='text')
    assert 'No importers found' in text
    assert "package a.b is wildcard-imported by 2 file(s)" in ' '.join(text.split())


def test_a_file_outside_the_wildcarded_packages_gets_the_tree_note_only(tmp_path):
    scan = _write(tmp_path, KOTLIN)
    answer = _answer(scan, 'src/a/c/Baz.kt', 'importers')
    assert [row['file'] for row in answer['importers']] == ['../../u/V.kt']
    disclosed = answer['edge_rule']['package_wildcards']
    assert disclosed['packages'] == {'a.b': 2} and disclosed['requested_file'] == {}
    assert 'is wildcard-imported by' not in answer['edge_rule']['text']


def test_directory_views_carry_the_disclosure(tmp_path):
    scan = _write(tmp_path, KOTLIN)
    for query in ('rank=fan-in', 'circular', 'entrypoints'):
        answer = _answer(scan, 'src', query)
        assert answer['edge_rule']['package_wildcards']['statements'] == 2, query


def test_a_file_wildcard_importing_two_packages_is_one_file(tmp_path):
    scan = _write(tmp_path, {**KOTLIN, 'src/u/W.kt': 'package u\nimport a.b.*\nimport a.c.*\nclass W\n'})
    disclosed = _answer(scan, 'src/a/b/Foo.kt', 'importers')['edge_rule']['package_wildcards']
    assert disclosed['statements'] == 4 and disclosed['importers'] == 3
    assert disclosed['packages'] == {'a.b': 3, 'a.c': 1}


def test_external_and_type_member_wildcards_are_not_counted(tmp_path):
    scan = _write(tmp_path, {
        'src/a/b/Obj.kt': 'package a.b\nobject Obj {\n    val x = 1\n}\n',
        'src/u/U.kt': 'package u\nimport java.util.*\nimport kotlinx.coroutines.*\nimport a.b.Obj.*\nclass U\n',
    })
    answer = _answer(scan, 'src/a/b/Obj.kt', 'importers')
    assert [row['file'] for row in answer['importers']] == ['../../u/U.kt']  # the type-member wildcard is an edge
    assert 'package_wildcards' not in answer['edge_rule']
    assert 'wildcard' not in answer['edge_rule']['text']


def test_scala_and_java_package_wildcards_are_counted_alike(tmp_path):
    scan = _write(tmp_path, {
        'src/a/b/X.scala': 'package a.b\nclass X\n',
        'src/u/S.scala': 'package u\nimport a.b._\nclass S\n',
        'src/u/T.scala': 'package u\nimport a.b.{X => _, _}\nclass T\n',
        'src/j/a/b/J.java': 'package a.b;\npublic class J {}\n',
        'src/j/u/K.java': 'package u;\nimport a.b.*;\npublic class K {}\n',
    })
    disclosed = _answer(scan, 'src/a/b/X.scala', 'importers')['edge_rule']['package_wildcards']
    assert disclosed['statements'] == 3 and disclosed['packages'] == {'a.b': 3}


def test_tests_exclude_drops_wildcard_importers_under_tests(tmp_path):
    scan = _write(tmp_path, {**KOTLIN, 'src/test/u/T.kt': 'package u\nimport a.b.*\nclass T\n'})
    assert _answer(scan, 'src/a/b/Foo.kt', 'importers')['edge_rule']['package_wildcards']['importers'] == 3
    excluded = _answer(scan, 'src/a/b/Foo.kt', 'importers&tests=exclude')['edge_rule']['package_wildcards']
    assert excluded['importers'] == 2 and excluded['statements'] == 2


@pytest.mark.parametrize('files,target', [
    ({'go.mod': 'module ex\n', 'a/a.go': 'package a\n\nfunc A() {}\n',
      'main.go': 'package main\n\nimport "ex/a"\n\nfunc main() { a.A() }\n'}, 'a/a.go'),
    ({'Cargo.toml': '[package]\nname = "ex"\nversion = "0.1.0"\n', 'src/a.rs': 'pub fn f() {}\n',
      'src/main.rs': 'mod a;\nuse a::*;\nfn main() { f(); }\n'}, 'src/a.rs'),
    ({'pkg/__init__.py': '', 'pkg/m.py': 'X = 1\n', 'main.py': 'from pkg.m import *\n'}, 'pkg/m.py'),
])
def test_languages_without_package_wildcards_get_no_disclosure(tmp_path, files, target):
    """Control: Go, Rust (a glob is an edge to the module) and Python (``from m import *`` is an edge)."""
    answer = _answer(_write(tmp_path, files), target, 'importers')
    assert 'package_wildcards' not in answer['edge_rule']
    assert 'wildcard' not in answer['edge_rule']['text']
