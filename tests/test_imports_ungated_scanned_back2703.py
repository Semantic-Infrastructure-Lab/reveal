"""BACK-2703: a language with scanned files but no resolved edges is still named as ungated.

``ungated_languages`` counted edges, so an ungated file that resolved none read as measured zeros. It now counts the
scan's files; ``ungated_edges`` keeps the edge count beside it.
"""
import pytest

from reveal import api


@pytest.fixture
def project(tmp_path):
    (tmp_path / 'lib').mkdir()
    (tmp_path / 'main.lua').write_text('local u = require("lib.util")\nreturn u\n', encoding='utf-8')
    (tmp_path / 'lib' / 'util.lua').write_text('return {}\n', encoding='utf-8')
    (tmp_path / 'B.cs').write_text('class B { }\n', encoding='utf-8')
    return tmp_path


def test_a_file_with_no_edges_still_names_its_ungated_language(project):
    rule = api.query(f'imports://{project}')['edge_rule']
    assert rule['ungated_languages'] == ['csharp', 'lua']
    assert rule['ungated_edges'] == 1  # the edge count stays beside it
    assert 'Not gated by default recall checks: csharp, lua, 1 edge(s)' in rule['text']


def test_a_gated_language_is_not_named(project):
    (project / 'a.py').write_text('import os\n', encoding='utf-8')
    assert 'python' not in api.query(f'imports://{project}')['edge_rule']['ungated_languages']
