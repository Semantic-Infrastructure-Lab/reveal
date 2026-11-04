"""A Java import resolves by its fully qualified name, never by a shorter path suffix (BACK-1712).

``import org.apache.lucene.geo.GeoUtils;`` names a class outside the tree. The dotted-name resolver
matched the longest path suffix that was unique in the tree and accepted a match of two components,
so the import landed on an in-tree ``org/es/common/geo/GeoUtils.java`` (package ``org.es.common.geo``):
same simple name, same last package segment, different package. On the pinned Elasticsearch gate
population all 25 extra edges (32615 against the oracle's 32590) were this one shape.

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

JAVA = {
    'src/main/java/org/es/common/geo/GeoUtils.java': (
        'package org.es.common.geo;\npublic class GeoUtils { public static final int CONST = 1; }\n'),
    'src/main/java/org/es/search/Helper.java': 'package org.es.search;\npublic class Helper {}\n',
    # The bug: an external class whose last package segment and simple name match an in-tree file.
    'src/main/java/org/es/search/ExternalLucene.java': (
        'package org.es.search;\nimport org.apache.lucene.geo.GeoUtils;\npublic class ExternalLucene {}\n'),
    # The same shape under the project's own root package: a class in a module outside the scan root.
    'src/main/java/org/es/search/ExternalSplit.java': (
        'package org.es.search;\nimport org.es.plugin.geo.GeoUtils;\npublic class ExternalSplit {}\n'),
    # Controls that must keep resolving (or keep not resolving) exactly as before.
    'src/main/java/org/es/search/CrossPackage.java': (
        'package org.es.search;\nimport org.es.common.geo.GeoUtils;\npublic class CrossPackage {}\n'),
    'src/main/java/org/es/search/SamePackage.java': (
        'package org.es.search;\nimport org.es.search.Helper;\npublic class SamePackage {}\n'),
    'src/main/java/org/es/search/StaticMember.java': (
        'package org.es.search;\nimport static org.es.common.geo.GeoUtils.CONST;\npublic class StaticMember {}\n'),
    # BACK-1711: a wildcard resolves to no file today (a strict xfail in test_recall_gate.py); unchanged.
    'src/main/java/org/es/search/Wildcard.java': (
        'package org.es.search;\nimport org.es.common.geo.*;\npublic class Wildcard {}\n'),
}

JAVA_EDGES = {
    ('org/es/search/CrossPackage.java', 'org/es/common/geo/GeoUtils.java', 2),
    ('org/es/search/SamePackage.java', 'org/es/search/Helper.java', 2),
    ('org/es/search/StaticMember.java', 'org/es/common/geo/GeoUtils.java', 2),
}


def _write(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root.resolve()


def _edges(root: Path, scan: Path, suffix: str) -> set:
    """Every (importer, target, line) row the public importers view reports under ``scan``."""
    rows = set()
    quoted_root = urllib.parse.quote(scan.as_posix(), safe='/:')
    for target in sorted(scan.rglob(f'*{suffix}')):
        response = _run_reveal_direct(f'imports://{target.as_posix()}?importers&root={quoted_root}',
                                      '--format', 'json')
        assert response.returncode == 0, response.stderr
        answer = json.loads(response.stdout)
        for row in answer['importers']:
            importer = Path(os.path.normpath(target.parent / row['file']))
            rows.add((importer.relative_to(scan).as_posix(), target.relative_to(scan).as_posix(), row['line']))
    return rows


def test_java_external_import_does_not_resolve_to_a_same_named_class_in_another_package(tmp_path):
    root = _write(tmp_path, JAVA)
    assert _edges(root, root / 'src/main/java', '.java') == JAVA_EDGES


def test_java_import_resolves_through_a_scan_root_inside_the_package_path(tmp_path):
    # A scan rooted below the package path still matches the whole name: the file's full path spells it.
    root = _write(tmp_path, JAVA)
    scan = root / 'src/main/java/org/es'
    prefix = len('org/es/')
    assert _edges(root, scan, '.java') == {(a[prefix:], b[prefix:], line) for a, b, line in JAVA_EDGES}


# Kotlin and Scala share the resolver and the bug, but not Java's layout rule: Kotlin's own convention
# drops the common root package from the directory path, and the Scala corpora declare packages that
# are not their directory tail (cats-effect: 142 of 404 files). The Java fix leaves them unchanged.
KOTLIN = {
    'src/org/es/common/geo/GeoUtils.kt': 'package org.es.common.geo\nclass GeoUtils\n',
    'src/org/es/search/Helper.kt': 'package org.es.search\nclass Helper\n',
    'src/org/es/search/ExternalLucene.kt': 'package org.es.search\nimport org.apache.lucene.geo.GeoUtils\nclass ExternalLucene\n',
    'src/org/es/search/CrossPackage.kt': 'package org.es.search\nimport org.es.common.geo.GeoUtils\nclass CrossPackage\n',
    'src/org/es/search/SamePackage.kt': 'package org.es.search\nimport org.es.search.Helper\nclass SamePackage\n',
    # Kotlin's recommended layout: root package org.example omitted from the directory path.
    'src/network/Socket.kt': 'package org.example.network\nclass Socket\n',
    'src/network/Client.kt': 'package org.example.network\nimport org.example.network.Socket\nclass Client\n',
}

KOTLIN_RIGHT = {
    ('org/es/search/CrossPackage.kt', 'org/es/common/geo/GeoUtils.kt', 2),
    ('org/es/search/SamePackage.kt', 'org/es/search/Helper.kt', 2),
    ('network/Client.kt', 'network/Socket.kt', 2),
}
KOTLIN_WRONG = ('org/es/search/ExternalLucene.kt', 'org/es/common/geo/GeoUtils.kt', 2)


def test_kotlin_resolution_is_unchanged_by_the_java_rule(tmp_path):
    # Negative control: the same shape in Kotlin keeps today's answer, the false edge included, and the
    # root-omitted layout keeps resolving (a whole-name rule would lose it).
    root = _write(tmp_path, KOTLIN)
    assert _edges(root, root / 'src', '.kt') == KOTLIN_RIGHT | {KOTLIN_WRONG}


@pytest.mark.xfail(strict=True, reason='BACK-1712 follow-up: Kotlin and Scala resolve an external import onto '
                   'an in-tree class with the same last package segment and simple name; their layouts do not '
                   'spell the package, so the fix needs the declared package, not the Java path rule')
@pytest.mark.parametrize('suffix', ['.kt', '.scala'])
def test_kotlin_and_scala_external_import_is_not_an_edge(tmp_path, suffix):
    files = {
        f'src/org/es/common/geo/GeoUtils{suffix}': 'package org.es.common.geo\nclass GeoUtils\n',
        f'src/org/es/search/ExternalLucene{suffix}': (
            'package org.es.search\nimport org.apache.lucene.geo.GeoUtils\nclass ExternalLucene\n'),
    }
    root = _write(tmp_path, files)
    assert _edges(root, root / 'src', suffix) == set()
