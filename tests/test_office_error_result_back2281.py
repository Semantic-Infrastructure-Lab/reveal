"""BACK-2281: a corrupt office file is a failed result with an error string.

``reveal bad.xlsx`` printed ``Error (bad.xlsx): [{'message': 'Invalid ZIP archive: ...'}]`` and an
empty ``Error (1):`` section: the office analyzers put a list of dicts in ``error``, which the
Output Contract defines as a string (``ResultBuilder.create_error``).
"""
import json
import zipfile

import pytest

from conftest import _run_reveal_direct
from reveal.analyzers.office import DocxAnalyzer, XlsxAnalyzer


@pytest.mark.parametrize('suffix', ['xlsx', 'docx', 'pptx', 'odt', 'ods', 'odp'])
def test_corrupt_office_file_reports_the_message(tmp_path, suffix):
    path = tmp_path / f'bad.{suffix}'
    path.write_text('not a zip', encoding='utf-8')
    r = _run_reveal_direct(str(path))
    assert r.returncode == 1
    assert 'Invalid ZIP archive: File is not a zip file' in r.stderr
    assert "[{'message'" not in r.stderr
    assert 'Error (1)' not in r.stdout


def test_corrupt_office_file_json_error_is_a_string(tmp_path):
    path = tmp_path / 'bad.xlsx'
    path.write_text('not a zip', encoding='utf-8')
    r = _run_reveal_direct(str(path), '--format', 'json')
    assert r.returncode == 1
    data = json.loads(r.stdout)
    assert data['structure']['error'] == 'Invalid ZIP archive: File is not a zip file'


def test_missing_part_is_still_a_failed_result_with_a_string(tmp_path):
    """A zip without the workbook part keeps failing; its own message is a string too."""
    path = tmp_path / 'empty.xlsx'
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types/>')
    structure = XlsxAnalyzer(str(path)).get_structure()
    assert structure['error'] == 'No workbook found'


def test_valid_document_has_no_error(tmp_path):
    """Negative control: a readable document is not a failed result."""
    path = tmp_path / 'ok.docx'
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types/>')
        zf.writestr('word/document.xml', '<?xml version="1.0"?>'
                    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    '<w:body></w:body></w:document>')
    assert 'error' not in DocxAnalyzer(str(path)).get_structure()
