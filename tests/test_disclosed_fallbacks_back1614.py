"""BACK-1614: fallbacks that used to be silent now say what they fell back from."""

import logging
import subprocess

from reveal import grep_handler, tree_view
from reveal.cli.commands import health, review


def test_review_names_why_the_structural_diff_fell_back(monkeypatch):
    import reveal.adapters.diff.adapter as diff_adapter

    def _boom(*args, **kwargs):
        raise ValueError('bad range')

    monkeypatch.setattr(diff_adapter, 'DiffAdapter', _boom)
    monkeypatch.setattr(review.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(
        a, 0, stdout='a.py\n', stderr=''))
    result = review._run_diff('main..HEAD')
    assert result['changed_files'] == ['a.py']
    assert result['structural_diff_error'] == 'ValueError: bad range'


def test_tree_json_entry_carries_the_error(tmp_path, monkeypatch):
    f = tmp_path / 'x.py'
    f.write_text('x = 1\n', encoding='utf-8')

    class _Broken:
        def __init__(self, path):
            raise RuntimeError('analyzer bug')

    monkeypatch.setattr(tree_view, 'get_analyzer', lambda path: _Broken)
    entry = tree_view._file_entry_json(f, fast=False)
    assert entry == {'name': 'x.py', 'type': 'file', 'error': 'RuntimeError: analyzer bug'}


def test_grep_names_a_file_whose_structure_failed(tmp_path, monkeypatch, caplog):
    import reveal.registry as registry
    f = tmp_path / 'x.py'
    f.write_text('x = 1\n', encoding='utf-8')

    class _Broken:
        def __init__(self, path):
            raise RuntimeError('analyzer bug')

    monkeypatch.setattr(registry, 'get_analyzer', lambda path: _Broken)
    with caplog.at_level(logging.WARNING, logger='reveal.grep_handler'):
        assert grep_handler._get_structural_elements(str(f)) == []
    assert 'hits shown without their enclosing element' in caplog.text


def test_health_targets_of_the_wrong_shape_are_named(tmp_path, monkeypatch, caplog):
    (tmp_path / '.reveal.yaml').write_text('health: [not, a, mapping]\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    with caplog.at_level(logging.WARNING, logger='reveal.cli.commands.health'):
        targets = health._detect_targets()
    assert targets == ['.']  # fell through to the default
    assert '.reveal.yaml health.targets ignored' in caplog.text
