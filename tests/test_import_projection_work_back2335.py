"""Projection context construction stays bounded as a result gains rows."""
import pytest

from reveal.adapters.imports import ImportsAdapter

pytestmark = pytest.mark.component


@pytest.mark.parametrize('query', ['', 'unused', 'external', 'importers', 'rank=fan-in'])
def test_projection_context_is_not_recreated_for_every_source(tmp_path, monkeypatch, query):
    for number in range(401):
        content = f'import m{number + 1}\n' if number < 400 else 'def leaf():\n    return 1\n'
        (tmp_path / f'm{number}.py').write_text(content, encoding='utf-8')
    calls = []
    original = ImportsAdapter._analysis_view

    def view(self, **kwargs):
        calls.append(kwargs)
        return original(self, **kwargs)

    monkeypatch.setattr(ImportsAdapter, '_analysis_view', view)
    adapter = ImportsAdapter(str(tmp_path), query)
    answer = adapter.get_structure()
    assert len(adapter.analysis.scanned_files) == 401
    assert adapter.analysis.graph.get_import_count() == 400
    assert answer['metadata']['scanned_files'] == 401
    assert len(calls) <= 4, f'{len(calls)} contexts for 401 sources in {query!r}'
