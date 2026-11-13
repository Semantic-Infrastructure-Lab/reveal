"""Source receipts share the output path boundary on every host."""
import json
from pathlib import PureWindowsPath

import pytest


@pytest.mark.parametrize('kind', ['document', 'transcript', 'codex_catalog', 'codex_lookup',
                                   'claude_catalog', 'claude_discovery', 'workspace', 'inventory'])
def test_source_receipts_publish_portable_paths(kind):
    path = PureWindowsPath('C:/home/fixture')
    expected = path.as_posix()
    if kind == 'document':
        from reveal.utils.document_read import DocumentRead
        value = DocumentRead(path).attach({})['meta']['installation_analysis']['source']
    elif kind == 'transcript':
        from reveal.utils.jsonl_records import TranscriptRecords
        value = TranscriptRecords(path).receipt()['source']
    elif kind == 'codex_catalog':
        from reveal.adapters.codex.catalog import CatalogRead
        value = CatalogRead(path, None).proof['source']
    elif kind == 'codex_lookup':
        from reveal.adapters.codex.lookup import SessionLookup
        value = SessionLookup(path, 'id').receipt()['source']
    elif kind == 'claude_catalog':
        from reveal.adapters.claude.catalog import SessionEntries
        entries = SessionEntries()
        entries.discovery_failures.append((path, PermissionError('denied')))
        value = entries.receipt()['failures'][0]['source']
    elif kind == 'claude_discovery':
        from reveal.adapters.claude.discovery import _diagnostics
        value = _diagnostics([(path, PermissionError('denied'))])[0]['source']
    elif kind == 'workspace':
        from reveal.adapters.claude.workspace_scan import WorkspaceScan
        scan = WorkspaceScan()
        scan.discovery_errors.append((path, PermissionError('denied')))
        value = scan.attach({})['meta']['workspace_analysis']['failures'][0]['source']
    else:
        from reveal.utils.path_inventory import path_info
        class MissingPath(PureWindowsPath):
            def stat(self): raise FileNotFoundError('missing')
        value = path_info(MissingPath(path))['path']
    assert value == expected


def test_element_view_metadata_uses_the_same_path_as_its_source(capsys):
    from reveal.nav_handlers import _nav_json
    _nav_json('boundary', r'C:\project\file.py', 'main', 1, 2, [])
    answer = json.loads(capsys.readouterr().out)
    assert answer['source'] == 'C:/project/file.py'
    assert answer['meta']['file'] == answer['source']
