"""Compact overview keeps independent facts, paths and invocation-local diagnostics."""
from unittest.mock import patch

from reveal.adapters.overview import OverviewAdapter
from reveal.analyzers.imports import service
from reveal.analyzers.imports.views import ImportView


def test_reused_adapter_clears_failed_invocation_evidence(tmp_path):
    (tmp_path / 'a.py').write_text('VALUE=1\n', encoding='utf-8')
    adapter = OverviewAdapter(str(tmp_path))
    with patch.object(service, 'analyze', side_effect=OSError('controlled graph failure')):
        failed = adapter.get_structure()
    assert failed['map_status'] == 'failed' and failed['meta']['errors']
    repaired = adapter.get_structure()
    assert repaired['map_status'] == 'complete'
    assert not repaired.get('meta', {}).get('errors')
    assert repaired['scope']['total_code_files'] == 1


def test_metadata_is_read_once_and_paths_share_target_relative_display(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    root.mkdir()
    (root / 'a.py').write_text('from b import value\n', encoding='utf-8')
    (root / 'b.py').write_text('value=1\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    original = ImportView.get_metadata
    with patch.object(ImportView, 'get_metadata', autospec=True, side_effect=original) as metadata:
        result = OverviewAdapter('project').get_structure()
    assert metadata.call_count == 1
    assert result['path'] == result['source'] == 'project'
    assert result['map']['fan_in']['rows'] == [{'file': 'b.py', 'fan_in': 1, 'fan_out': 0}]
