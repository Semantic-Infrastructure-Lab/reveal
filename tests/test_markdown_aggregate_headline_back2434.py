"""The aggregate headline says what each file count counts (BACK-2434).

It printed ``Files: 78 of 78 matched`` directly above ``Missing field: 67 files``, which reads as a
contradiction: "matched" counts files passing the filters, not files that have the field.
"""

from conftest import _run_reveal_direct


def _docs(tmp_path):
    (tmp_path / 'a.md').write_text('---\ntype: guide\n---\n# A\n', encoding='utf-8')
    (tmp_path / 'b.md').write_text('# B\nno front matter\n', encoding='utf-8')
    (tmp_path / 'c.md').write_text('---\ntitle: C\n---\n# C\n', encoding='utf-8')
    return tmp_path


def test_headline_separates_matched_from_has_field(tmp_path):
    response = _run_reveal_direct(f'markdown://{_docs(tmp_path).as_posix()}/?aggregate=type')
    assert response.returncode == 0
    assert "Files: 3 of 3 matched; 1 has 'type', 2 do not" in response.stdout
    assert 'Missing field:' not in response.stdout


def test_headline_with_every_file_having_the_field(tmp_path):
    (tmp_path / 'a.md').write_text('---\ntype: guide\n---\n# A\n', encoding='utf-8')
    response = _run_reveal_direct(f'markdown://{tmp_path.as_posix()}/?aggregate=type')
    assert "Files: 1 of 1 matched; 1 has 'type'" in response.stdout
    assert 'do not' not in response.stdout
