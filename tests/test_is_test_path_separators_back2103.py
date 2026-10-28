"""One answer to "is this a test path?" for a path spelled with backslashes (BACK-2103).

``is_test_path`` split a string on the host's separator only, so on POSIX
``'tests\\test_a.py'`` was one file name with a backslash in it, and not a test. The
architecture, overview and diff entry-point filters hid that behind a wrapper that
replaced backslashes first, while the imports entry-point list and the M102 rule called
``is_test_path`` bare: the same string was a test for one consumer and not for the next.
No tool writes such a string on POSIX today; the strings come from a recorded Windows
result read on POSIX (the equivalence table of BACK-1891).
"""
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

import pytest

from reveal.analyzers.imports.views import ImportView
from reveal.rules.maintainability.M102 import M102
from reveal.utils.entry_points import is_active_entry_point
from reveal.utils.path_utils import is_test_path

TEST_SPELLINGS = ['tests\\test_a.py', 'proj\\tests\\a.py', 'C:\\proj\\tests\\test_a.py', 'src\\test_a.py']
SOURCE_SPELLINGS = ['src\\a.py', 'C:\\proj\\src\\a.py', 'src\\latest.py']


def _imports_view(path: str) -> bool:
    """What ``ImportView.entrypoints`` records as ``is_test`` for *path*."""
    file = Path(path)
    graph = SimpleNamespace(reverse_deps={}, dependencies={}, files={file: None})
    adapter = SimpleNamespace(
        analysis=SimpleNamespace(graph=graph, scanned_files={file}),
        _edges=lambda default: graph,
        _row_files=lambda view: {file},
        _edge_rule=lambda *args, **kwargs: {},
        _build_response=lambda response_type, **fields: fields,
    )
    (entry,) = ImportView.entrypoints(adapter)['entries']
    return entry['is_test']


def _entry_point_filter_view(path: str) -> bool:
    """Whether the architecture, overview and diff entry-point filter drops *path* as a test."""
    return not is_active_entry_point({'file': path, 'fan_out': 1})


def _m102_view(path: str) -> bool:
    return M102()._is_test_file(Path(path))


VIEWS = [is_test_path, _imports_view, _entry_point_filter_view, _m102_view]
VIEW_IDS = ['is_test_path', 'imports', 'entry_point_filter', 'M102']


@pytest.mark.parametrize('view', VIEWS, ids=VIEW_IDS)
@pytest.mark.parametrize('spelling', TEST_SPELLINGS)
def test_backslash_spelled_test_path_is_a_test_for_every_consumer(view, spelling):
    assert view(spelling) is True


@pytest.mark.parametrize('view', VIEWS, ids=VIEW_IDS)
@pytest.mark.parametrize('spelling', SOURCE_SPELLINGS)
def test_backslash_spelled_source_path_is_not_a_test_for_any_consumer(view, spelling):
    """Negative control: normalising must not turn source paths into tests."""
    assert view(spelling) is False


@pytest.mark.parametrize('view', VIEWS, ids=VIEW_IDS)
@pytest.mark.parametrize('spelling,expected', [
    ('tests/test_a.py', True), ('proj/tests/a.py', True), ('src/a.py', False), ('src/latest.py', False),
])
def test_forward_slash_answers_are_unchanged(view, spelling, expected):
    """Negative control: the answers for the spelling every producer writes today."""
    assert view(spelling) is expected


def test_a_windows_flavoured_path_object_is_classified_like_its_string():
    assert is_test_path(PureWindowsPath('tests\\test_a.py')) is True
    assert is_test_path(PureWindowsPath('C:\\proj\\src\\a.py')) is False
