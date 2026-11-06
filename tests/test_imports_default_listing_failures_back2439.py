"""The default ``imports DIR`` listing does not exit 3 for files that failed outside DIR (BACK-2439).

The listing prints the imports of the files under DIR and a cycles verdict. A broken file elsewhere in
the project cannot change those imports, but it can hide a cycle, so with outside failures and no cycle
seen the verdict is unknown (``has_cycles`` null) instead of "No". A cycle that was found is still a
cycle. Views that read the whole graph (importers, circular) keep exit 3.
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
    (sub / 'a.ts').write_text('import r from "react";\nexport const a = 1;\n', encoding='utf-8')
    (sub / 'b.ts').write_text('import { a } from "./a";\nexport const b = a;\n', encoding='utf-8')
    return sub


def _query(sub, view=''):
    response = _run_reveal_direct(f'imports://{sub}{view}', '--format', 'json')
    return response.returncode, json.loads(response.stdout)


def test_listing_ignores_failures_outside_the_path(project):
    code, result = _query(project)
    assert code == 0, result['metadata']
    metadata = result['metadata']
    assert metadata['files_failed_count'] == 0
    assert metadata['files_failed_outside_target_count'] == 1


def test_cycles_are_unknown_when_an_outside_file_failed_and_none_was_seen(project):
    _, result = _query(project)
    assert result['metadata']['has_cycles'] is None


def test_a_cycle_that_was_found_stays_true_despite_outside_failures(project):
    (project / 'a.ts').write_text('import { b } from "./b";\nexport const a = 1;\n', encoding='utf-8')
    (project / 'b.ts').write_text('import { a } from "./a";\nexport const b = 2;\n', encoding='utf-8')
    code, result = _query(project)
    assert result['metadata']['has_cycles'] is True


def test_cycles_stay_boolean_when_nothing_failed(project):
    (project.parent / 'broken.ts').unlink()
    code, result = _query(project)
    assert code == 0
    assert result['metadata']['has_cycles'] is False
    assert 'files_failed_outside_target_count' in result['metadata']
    assert result['metadata']['files_failed_outside_target_count'] == 0


def test_listing_still_exits_3_for_a_failure_inside_the_path(project):
    (project / 'c.ts').write_text(BROKEN, encoding='utf-8')
    code, result = _query(project)
    assert code == 3
    assert result['metadata']['files_failed_count'] == 1
    assert result['metadata']['has_cycles'] is None


@pytest.mark.parametrize('view', ['?importers', '?circular'])
def test_whole_graph_views_keep_outside_failures_as_incomplete(project, view):
    code, result = _query(project, view)
    assert code == 3, result['metadata']
    assert 'files_failed_outside_target_count' not in result['metadata']


def test_external_view_cycles_claim_is_unknown_too(project):
    _, result = _query(project, '?external')
    assert result['metadata']['has_cycles'] is None


def test_text_says_cycles_are_not_determined_and_why(project):
    response = _run_reveal_direct(f'imports://{project}')
    assert response.returncode == 0
    assert 'Cycles Found:  Unknown' in response.stdout
    assert '1 file(s) outside this path could not be fully analyzed' in response.stdout
    assert 'parsed with errors' not in response.stdout  # outside loss is no warning here (BACK-2524)
    assert 'No' not in [line.split(':')[-1].strip() for line in response.stdout.splitlines() if 'Cycles Found' in line]


def test_text_for_a_cycle_free_clean_project_still_says_no(project):
    (project.parent / 'broken.ts').unlink()
    response = _run_reveal_direct(f'imports://{project}')
    assert 'Cycles Found:  ✅ No' in response.stdout
