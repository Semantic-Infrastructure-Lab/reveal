"""Post-source carrier and compatibility features; semantic reds remain separate."""
from pathlib import Path

import pytest

from reveal.cli import file_checker as fc
from reveal import mcp_server
from reveal.reveal_types import PathFailure
from test_check_collection_loss_back2040 import collection_fault, project, write

pytestmark = pytest.mark.component


@pytest.mark.parametrize('unknown', [False, True])
def test_collection_owns_full_immutable_event_sequence_and_formats_without_second_walk(
        tmp_path, collection_fault, monkeypatch, unknown):
    root = tmp_path / 'raw'
    visible = write(root / 'visible.py', 'VALUE=1\n')
    denied = {write(root / f'blocked{i}' / 'hidden.py', 'VALUE=1\n').parent for i in range(7)}
    collection_fault.update(denied=denied, unknown=unknown)
    walks = []
    real = fc._walk_code_files
    def walk(*args, **kwargs):
        walks.append((args, kwargs))
        return real(*args, **kwargs)
    monkeypatch.setattr(fc, '_walk_code_files', walk)
    result = fc.collect_files_to_check(root, False, [])
    assert result.files == [visible] and len(walks) == 1
    assert len(collection_fault['events']) == 7 and collection_fault['checked'] == []
    assert type(result.traversal_failures) is tuple and len(result.traversal_failures) == 7
    assert all(type(event) is PathFailure and len(event) == 2 for event in result.traversal_failures)
    assert all(cause.startswith('PermissionError:') for _, cause in result.traversal_failures)
    if unknown:
        assert all(path is None for path, _ in result.traversal_failures)
    else:
        assert {path for path, _ in result.traversal_failures} == {path.as_posix() for path in denied}
    assert result.skipped_dirs == result.skipped_gitignore == result.skipped_no_analyzer == 0
    scope = result.to_scope_census().to_scope_dict()
    assert scope['total_code_files'] == 1 and 'traversal_failures' not in scope
    expected = fc._collection_disclosures(result, root)
    assert len(expected) == 1
    assert fc._collection_disclosures(result, root) == expected and len(walks) == 1


def test_old_scan_and_mcp_note_helper_positional_calls_remain_compatible(tmp_path):
    assert fc._collect_files_to_check is fc.collect_files_to_check
    result = fc.FileCollectionResult([], 1, 2, 3, {})
    assert result.traversal_failures == ()
    assert fc._scan_disclosures([], ['E501'], None) == ([], False)
    assert mcp_server._check_notes([], ['E501'], None, []) == ([], False)
    assert fc._collection_disclosures(result, tmp_path) == []
