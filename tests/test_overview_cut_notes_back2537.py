"""overview's cut-list footer is one line in reader terms (BACK-2537).

On a tree with 13 unparseable files the text ended with three near-identical lines naming internal
JSON paths ('Truncated map.metadata.files_failed: showing 5 of 13 -- ... at most 50 details', then
map.metadata.extraction_diagnostics, then meta.warnings.0.files): one list of files, three cuts, and
'5' beside 'at most 50' contradicting its own cap. JSON keeps one truncation entry per field.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.display.formatting import print_result_control_notes


@pytest.fixture
def broken_tree(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pkg = tmp_path / 'pkg'
    pkg.mkdir()
    (tmp_path / 'pyproject.toml').write_text('[project]\nname = "p"\n', encoding='utf-8')
    (pkg / '__init__.py').write_text('', encoding='utf-8')
    for i in range(13):
        (pkg / f'bad{i}.py').write_text('import os\ndef f(:\n    pass\n', encoding='utf-8')
    (pkg / 'ok.py').write_text('from pkg import bad1\n', encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('top', ['5', '10'])
def test_text_footer_says_it_once_in_reader_terms(broken_tree, top):
    result = _run_reveal_direct('overview', '.', '--no-gitignore', '--top', top)
    assert result.returncode == 3, result.stderr  # files parsed with errors: incomplete
    cuts = [line for line in result.stdout.splitlines() if line.startswith('⚠ Truncated')]
    assert cuts == ['⚠ Truncated files named in diagnostics: showing 5 of 13 — '
                    'imports:// on the same path with --format json names every file'], result.stdout
    assert 'map.metadata' not in result.stdout and 'meta.warnings' not in result.stdout


def test_json_keeps_one_entry_per_cut_field(broken_tree):
    result = _run_reveal_direct('overview', '.', '--no-gitignore', '--format', 'json')
    fields = {w['field']: (w['shown'], w['total'], w['label']) for w in json.loads(result.stdout)['meta']['warnings']
              if w['type'] == 'truncated'}
    label = 'files named in diagnostics'
    assert fields == {'map.metadata.files_failed': (5, 13, label),
                      'map.metadata.extraction_diagnostics': (5, 13, label),
                      'meta.warnings.0.files': (5, 13, label)}


def test_the_hint_is_true_imports_json_names_every_file(broken_tree):
    result = _run_reveal_direct('imports://.', '--no-gitignore', '--format', 'json')
    assert len(json.loads(result.stdout)['metadata']['files_failed']) == 13


def test_unlabelled_cuts_of_different_lists_each_print(capsys):
    """Control: only notes for one labelled list collapse; two different cut lists both print."""
    result = {'meta': {'warnings': [
        {'type': 'truncated', 'field': 'a', 'shown': 1, 'total': 2, 'message': 'a: showing 1 of 2'},
        {'type': 'truncated', 'field': 'b', 'shown': 1, 'total': 2, 'message': 'b: showing 1 of 2'},
    ]}}
    print_result_control_notes(result, 'text')
    assert capsys.readouterr().out.split('\n')[1:3] == ['⚠ Truncated a: showing 1 of 2', '⚠ Truncated b: showing 1 of 2']
