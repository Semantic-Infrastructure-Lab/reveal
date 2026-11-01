"""Empty code scans must not call documentation or data a source language."""
import json

import pytest

from conftest import _run_reveal_direct as run
from reveal.utils import path_utils
from reveal.utils.path_utils import detect_non_python_language


@pytest.mark.parametrize('suffix', ['.md', '.json', '.yaml', '.toml', '.xml', '.txt'])
def test_document_and_data_files_are_not_code_languages(tmp_path, suffix):
    path = tmp_path / f'notes{suffix}'
    path.write_text('', encoding='utf-8')
    assert detect_non_python_language(path) == ''
    assert detect_non_python_language(tmp_path) == ''


def test_docs_cannot_outvote_source_and_display_aliases_still_combine(tmp_path):
    for index in range(5):
        (tmp_path / f'notes{index}.json').write_text('{}', encoding='utf-8')
    for index, suffix in enumerate(('.ts', '.tsx', '.ts', '.tsx', '.go', '.go', '.go')):
        (tmp_path / f'source{index}{suffix}').write_text('', encoding='utf-8')
    assert detect_non_python_language(tmp_path) == 'TypeScript'


def test_empty_and_python_only_remain_without_non_python_language(tmp_path):
    assert detect_non_python_language(tmp_path) == ''
    path = tmp_path / 'sample.py'
    path.write_text('value = 1\n', encoding='utf-8')
    assert detect_non_python_language(path) == ''
    assert detect_non_python_language(tmp_path) == ''


def test_unsupported_code_language_remains_visible_among_documents(tmp_path):
    for index in range(3):
        (tmp_path / f'notes{index}.md').write_text('# Notes\n', encoding='utf-8')
    source = tmp_path / 'sample.ex'
    source.write_text('defmodule Example do\nend\n', encoding='utf-8')
    assert detect_non_python_language(source) == 'Elixir'
    assert detect_non_python_language(tmp_path) == 'Elixir'


def test_language_detection_does_not_swallow_discovery_failure(tmp_path, monkeypatch):
    def denied(path):
        raise PermissionError('source discovery denied')
    monkeypatch.setattr(path_utils, '_walk_code_files', denied)
    with pytest.raises(PermissionError, match='source discovery denied'):
        detect_non_python_language(tmp_path)


@pytest.mark.parametrize('adapter', ['contracts', 'ast'])
def test_actual_cli_docs_only_scan_agrees_with_no_code_disclosure(tmp_path, adapter):
    (tmp_path / 'notes.md').write_text('# Notes\n', encoding='utf-8')
    (tmp_path / 'config.json').write_text('{}\n', encoding='utf-8')
    query = '?show=dict-schemas' if adapter == 'ast' else ''
    result = run(f'{adapter}://{tmp_path}{query}', '--format', 'json')
    assert result.returncode == 0, result.stderr
    answer = json.loads(result.stdout)
    assert answer['unsupported_language'] == ''
    if adapter == 'contracts':
        assert answer['coverage']['total_code_files'] == 0
        assert answer['coverage']['dominant_language'] == ''
