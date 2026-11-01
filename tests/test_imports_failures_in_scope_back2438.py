"""A file outside the queried path that fails to parse cannot change what that path imports (BACK-2438).

``imports DIR?external`` lists the imports OF the files under DIR, so a broken file elsewhere in the
project does not make it incomplete; the answer still says how many outside files failed. Views that
read the whole graph (fan-in, cycles, importers) can miss an outside importer, so they keep exit 3.
"""
import json

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component


BROKEN = 'import { x ;\n const = ;;; }{\n'


@pytest.fixture
def project(tmp_path):
    (tmp_path / '.git').mkdir()
    (tmp_path / 'package.json').write_text('{"name": "proj"}\n', encoding='utf-8')
    (tmp_path / 'broken.ts').write_text(BROKEN, encoding='utf-8')
    sub = tmp_path / 'sub'
    sub.mkdir()
    (sub / 'a.ts').write_text('import * as fs from "fs";\nimport r from "react";\nexport const a = 1;\n', encoding='utf-8')
    (sub / 'b.ts').write_text('import { a } from "./a";\nexport const b = a;\n', encoding='utf-8')
    return sub


def _query(sub, view):
    response = _run_reveal_direct(f'imports://{sub}{view}', '--format', 'json')
    return response.returncode, json.loads(response.stdout)


def test_external_table_ignores_failures_outside_the_path(project):
    code, result = _query(project, '?external')
    assert code == 0, result.get('metadata')
    assert [p['package'] for p in result['external_packages']] == ['react']
    metadata = result['metadata']
    assert metadata['files_failed_count'] == 0 and metadata['files_failed'] == []
    assert metadata['files_failed_outside_target_count'] == 1


def test_external_table_still_reports_a_failure_inside_the_path(project):
    (project / 'c.ts').write_text(BROKEN, encoding='utf-8')
    code, result = _query(project, '?external')
    assert code == 3
    assert result['metadata']['files_failed_count'] == 1
    assert result['metadata']['files_failed_outside_target_count'] == 1


@pytest.mark.parametrize('view', ['?importers', '?circular'])
def test_whole_graph_views_keep_outside_failures_as_incomplete(project, view):
    code, result = _query(project, view)
    assert code == 3, result['metadata']
    assert result['metadata']['files_failed_count'] == 1
    assert 'files_failed_outside_target_count' not in result['metadata']


def test_external_text_names_the_failed_file_under_the_path_and_counts_the_outside_one(project):
    (project / 'c.ts').write_text(BROKEN, encoding='utf-8')
    response = _run_reveal_direct(f'imports://{project}?external')
    assert response.returncode == 3
    assert '1 file(s) under this path parsed with errors' in response.stdout
    assert 'c.ts' in response.stdout
    assert '1 file(s) outside this path failed to parse' in response.stdout


def test_external_text_says_outside_failures_do_not_make_it_incomplete(project):
    response = _run_reveal_direct(f'imports://{project}?external')
    assert response.returncode == 0
    assert '1 file(s) outside this path failed to parse' in response.stdout
    assert 'parsed with errors' not in response.stdout
