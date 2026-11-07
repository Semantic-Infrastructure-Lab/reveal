"""imports:// text states both file counts with their rule (BACK-2534, rule 4: every number states its rule).

It printed only 'Total Files: N', where N is the files with at least one import; beside overview's
scanned count (443 files scanned, 'Total Files: 397' on one project) it read as a contradiction.
"""
from conftest import _run_reveal_direct


def test_summary_names_scanned_files_and_files_with_imports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pkg = tmp_path / 'pkg'
    pkg.mkdir()
    (pkg / 'a.py').write_text('X = 1\n', encoding='utf-8')  # scanned, no import
    (pkg / 'b.py').write_text('import os\n', encoding='utf-8')
    (pkg / 'c.py').write_text('from pkg import a\n', encoding='utf-8')
    result = _run_reveal_direct('imports://pkg', '--no-gitignore')
    assert result.returncode == 0, result.stderr
    assert 'Files:         3 scanned, 2 with imports' in result.stdout, result.stdout
    assert 'Total Files:' not in result.stdout
