"""Every imports view that exits 3 on lost input says what was lost, once, in text and JSON (BACK-2524).

A file parsed with errors made ``?components``, ``?entrypoints``, ``?rank=fan-in`` and ``?importers``
exit 3 with nothing in the text and nothing in ``meta.warnings``: only ``metadata.files_failed_count``
carried the loss. The base view, ``?circular``, ``?unused`` and ``?external`` printed it from three
different text helpers, and no view put it in ``meta.warnings``. The disclosure is now the answer's
meta warning (``partial_parse``, ``analysis_failed``, ``worker_lost``), shown once by the shared
warning renderer, and scoped like the answer's own failure counts: a ``?external``/``?unused``/base
answer lists only the files under the path, so a failure outside it is counted apart (BACK-2438) and
is not a warning.
"""
import json
import os
import sys

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component

BROKEN = 'import os\ndef f(:\n    return (\n'

VIEWS = ['', '?components', '?entrypoints', '?rank=fan-in', '?importers', '?importers=pkg/b.py',
         '?circular', '?unused', '?external', '?violations']
WHOLE_GRAPH_VIEWS = ['?components', '?entrypoints', '?rank=fan-in', '?importers', '?circular']
TARGET_VIEWS = ['', '?unused', '?external']


def _project(root, *, broken: bool):
    (root / '.git').mkdir()
    pkg = root / 'pkg'
    pkg.mkdir()
    (pkg / '__init__.py').write_text('', encoding='utf-8')
    (pkg / 'a.py').write_text('from pkg import b\n', encoding='utf-8')
    (pkg / 'b.py').write_text('X = 1\n', encoding='utf-8')
    if broken:
        (pkg / 'broken.py').write_text(BROKEN, encoding='utf-8')
    return root


@pytest.fixture
def broken_project(tmp_path):
    return _project(tmp_path, broken=True)


@pytest.fixture
def clean_project(tmp_path):
    return _project(tmp_path, broken=False)


def _json(uri):
    response = _run_reveal_direct(uri, '--format', 'json')
    return response.returncode, json.loads(response.stdout)


def _warnings(result, kind):
    return [w for w in (result.get('meta') or {}).get('warnings', []) if w.get('type') == kind]


@pytest.mark.parametrize('view', VIEWS)
def test_json_names_the_partial_parse_once_in_meta_warnings(broken_project, view):
    code, result = _json(f'imports://{broken_project}{view}')
    assert code == 3, result.get('metadata')
    partial = _warnings(result, 'partial_parse')
    assert len(partial) == 1, result.get('meta')
    assert partial[0]['count'] == result['metadata']['files_failed_count'] == 1
    assert [f.rsplit('/', 1)[-1] for f in partial[0]['files']] == ['broken.py']


@pytest.mark.parametrize('view', VIEWS)
def test_text_names_the_partial_parse_exactly_once(broken_project, view):
    response = _run_reveal_direct(f'imports://{broken_project}{view}')
    assert response.returncode == 3
    assert response.stdout.count('parsed with errors') == 1, response.stdout
    assert 'broken.py' in response.stdout


def test_dot_names_the_partial_parse_on_stderr_and_keeps_stdout_graphviz(broken_project):
    response = _run_reveal_direct(f'imports://{broken_project}?importers&format=dot')
    assert response.returncode == 3
    assert response.stdout.startswith('digraph')
    assert 'parsed with errors' not in response.stdout
    assert response.stderr.count('parsed with errors') == 1, response.stderr


@pytest.mark.parametrize('view', VIEWS)
def test_clean_input_has_no_loss_warning_and_exits_0(clean_project, view):
    """Control: passes before and after the fix."""
    code, result = _json(f'imports://{clean_project}{view}')
    assert code == 0, result.get('meta')
    assert not _warnings(result, 'partial_parse')
    response = _run_reveal_direct(f'imports://{clean_project}{view}')
    assert 'parsed with errors' not in response.stdout


@pytest.fixture
def outside_failure(tmp_path):
    """A broken file at the project root, outside the queried pkg/ directory."""
    _project(tmp_path, broken=False)
    (tmp_path / 'broken.py').write_text(BROKEN, encoding='utf-8')
    return tmp_path / 'pkg'


@pytest.mark.parametrize('view', TARGET_VIEWS)
def test_a_failure_outside_the_path_is_no_warning_where_it_cannot_change_the_answer(outside_failure, view):
    """Control for scoping (BACK-2438): passes before and after the fix."""
    code, result = _json(f'imports://{outside_failure}{view}&scope=root' if view
                         else f'imports://{outside_failure}?scope=root')
    assert code == 0, result.get('metadata')
    assert result['metadata']['files_failed_count'] == 0
    assert result['metadata']['files_failed_outside_target_count'] == 1
    assert not _warnings(result, 'partial_parse')


@pytest.mark.parametrize('view', WHOLE_GRAPH_VIEWS)
def test_a_failure_outside_the_path_is_named_where_it_can_hide_an_importer(outside_failure, view):
    code, result = _json(f'imports://{outside_failure}{view}&scope=root')
    assert code == 3, result.get('metadata')
    assert result['metadata']['files_failed_count'] == 1
    assert len(_warnings(result, 'partial_parse')) == 1, result.get('meta')


@pytest.mark.skipif(sys.platform == 'win32' or (hasattr(os, 'geteuid') and os.geteuid() == 0),
                    reason='POSIX permissions; root reads a mode-000 file')
def test_an_unreadable_file_is_named_under_its_own_cause(broken_project):
    unreadable = broken_project / 'pkg' / 'secret.py'
    unreadable.write_text('import os\n', encoding='utf-8')
    unreadable.chmod(0)
    try:
        code, result = _json(f'imports://{broken_project}?components')
    finally:
        unreadable.chmod(0o644)
    assert code == 3
    failed = _warnings(result, 'analysis_failed')
    assert len(failed) == 1 and [f.rsplit('/', 1)[-1] for f in failed[0]['files']] == ['secret.py']
    assert len(_warnings(result, 'partial_parse')) == 1


def test_calls_modules_carries_one_partial_parse_not_two(broken_project):
    """calls ?modules composes the imports answer: the warning must not arrive twice."""
    code, result = _json(f'calls://{broken_project}?modules')
    assert code == 0, result.get('meta')
    assert len(_warnings(result, 'partial_parse')) == 1, result.get('meta')


def test_deps_carries_one_partial_parse_from_its_three_views(broken_project):
    """deps:// composes three views of one imports build; one loss is one warning."""
    code, result = _json(f'deps://{broken_project}')
    assert code == 3
    assert len(_warnings(result, 'partial_parse')) == 1, result.get('meta')
