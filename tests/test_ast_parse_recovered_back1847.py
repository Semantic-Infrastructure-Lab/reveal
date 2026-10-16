"""ast:// discloses a file tree-sitter could only partly parse (BACK-1847).

analyze_file dropped the structure's ``_has_errors`` flag, so a directory query listed what
survived the recovery with confidence 1.0 and no warning, while the file view of the same
file said its outline "may be incomplete or wrong".
"""
import json

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component

BROKEN = 'def ok():\n    return 1\n\ndef broken(:\n    x = = 2\n'
CLEAN = 'def fine():\n    return 2\n'


def _query(tmp_path, *extra):
    return _run_reveal_direct(f'ast://{tmp_path}', '--format', 'json', *extra)


def test_directory_query_warns_about_the_recovered_file(tmp_path):
    (tmp_path / 'bad.py').write_text(BROKEN, encoding='utf-8')
    (tmp_path / 'good.py').write_text(CLEAN, encoding='utf-8')
    warnings = json.loads(_query(tmp_path).stdout)['meta']['warnings']
    (warning,) = [w for w in warnings if w['type'] == 'parse_recovered']
    assert warning['count'] == 1
    assert warning['files'][0].endswith('bad.py')


def test_text_output_shows_the_warning(tmp_path):
    (tmp_path / 'bad.py').write_text(BROKEN, encoding='utf-8')
    out = _run_reveal_direct(f'ast://{tmp_path}').stdout
    assert 'could not read' in out and 'bad.py' in out


def test_clean_tree_has_no_parse_recovered_warning(tmp_path):
    (tmp_path / 'good.py').write_text(CLEAN, encoding='utf-8')
    warnings = json.loads(_query(tmp_path).stdout)['meta']['warnings']
    assert not [w for w in warnings if w['type'] == 'parse_recovered']
