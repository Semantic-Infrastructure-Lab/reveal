"""Required dict sources retain read/parse evidence before usage filtering."""
import io
from pathlib import Path

import pytest

from reveal.adapters.ast.adapter import AstAdapter
from reveal.analyzers import _python_dict_usage as usage

pytestmark = pytest.mark.component
SOURCE = 'def read(cfg: dict):\n    return cfg["a"] + cfg["b"] + cfg["c"]\n'


@pytest.mark.parametrize('loss', ['parse', 'read'])
def test_real_source_loss_is_not_a_confident_empty_answer(tmp_path, monkeypatch, loss):
    source = tmp_path / 'source.py'
    source.write_text(SOURCE, encoding='utf-8')
    assert len(usage.collect_dict_analysis(str(source))[0]) == 1
    real_open = io.open
    denied = []

    def reader(file, *args, **kwargs):
        if Path(file).resolve() == source.resolve():
            denied.append(file)
            raise PermissionError(13, 'reader denied', str(file))
        return real_open(file, *args, **kwargs)

    if loss == 'parse':
        source.write_text(SOURCE + 'def broken(\n', encoding='utf-8')
    else:
        monkeypatch.setattr(io, 'open', reader)
    result = AstAdapter(str(source), 'show=dict-heatmap').get_structure()
    assert result['total_results'] == 0
    if loss == 'read':
        assert denied, 'the actual Path.read_text reader must execute'
    assert result['meta'].get('confidence') != 1.0, result['meta']
    assert any(w['code'] == usage.DICT_SOURCE_WARNING_CODE for w in result['meta']['warnings'])
