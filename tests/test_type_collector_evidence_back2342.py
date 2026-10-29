"""Required Python type sources disclose omissions and recovered uncertainty."""
import builtins
from pathlib import Path

import pytest

from reveal.adapters.ast.adapter import AstAdapter
from reveal.adapters.ast import nav_reveal_type as nav
from reveal.analyzers.python import PythonAnalyzer
from reveal.core.treesitter_compat import error_node_spans, tree_has_recovery_artifacts, tree_root

pytestmark = pytest.mark.component
SOURCE = 'def consume(target: dict):\n    return target\n'


@pytest.mark.parametrize('loss', ['recovery', 'read'])
def test_real_type_source_loss_has_no_unjustified_confidence(tmp_path, monkeypatch, loss):
    path = tmp_path / 'source.py'
    path.write_text(SOURCE, encoding='utf-8')
    assert len(nav.collect_type_evidence(str(path), 'target')) == 1
    real_open = builtins.open
    denied = []

    def reader(file, *args, **kwargs):
        if Path(file).resolve() == path.resolve():
            denied.append(file)
            raise PermissionError(13, 'reader denied', str(file))
        return real_open(file, *args, **kwargs)

    if loss == 'recovery':
        path.write_text(SOURCE + 'def broken(\n', encoding='utf-8')
        tree = PythonAnalyzer(str(path)).tree
        assert tree_has_recovery_artifacts(tree) and error_node_spans(tree_root(tree))
    else:
        monkeypatch.setattr(builtins, 'open', reader)
    result = AstAdapter(str(path), 'reveal_type=target').get_structure()
    assert result['total_results'] == (1 if loss == 'recovery' else 0)
    if loss == 'read':
        assert denied
        monkeypatch.setattr(builtins, 'open', real_open)
        assert len(nav.collect_type_evidence(str(path), 'target')) == 1
    assert result['meta'].get('confidence') != 1.0, result['meta']
    assert any(w['code'] == nav.TYPE_SOURCE_WARNING_CODE for w in result['meta']['warnings'])
