"""File structures classify producer causes through D6, before presentation."""
import csv
import json
import zipfile

import pytest

from conftest import _run_reveal_direct
from reveal.analyzers.xml_analyzer import XmlAnalyzer
from reveal.utils.results import ResultBuilder


@pytest.fixture
def cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    return tmp_path


@pytest.mark.parametrize('name,content,code', [
    ('bad.xml', '<root></bad>', 3),
    ('bad.csv', 'column\n' + 'x' * (csv.field_size_limit() + 1), 3),
    ('bad.ipynb', '{"cells": [}', 3),
    ('shape.ipynb', '[]', 2),
    ('cells.ipynb', '{"cells": 5}', 2),
    ('cell.ipynb', '{"cells": [9]}', 2),
    ('metadata.ipynb', '{"metadata": 5}', 2),
    ('bad.docx', 'not zip', 2),
    ('bad.xlsx', 'not zip', 2),
])
@pytest.mark.parametrize('format', ['text', 'json'])
def test_failed_file_exits_by_cause(cwd, name, content, code, format):
    (cwd / name).write_text(content, encoding='utf-8')
    result = _run_reveal_direct(name, '--format', format)
    assert result.returncode == code, result.stderr
    assert result.stderr.count(f'Error ({name}):') == 1
    assert 'Traceback' not in result.stderr and 'Parse recovered' not in result.stdout
    if format == 'json':
        assert json.loads(result.stdout)['error']


@pytest.mark.parametrize('name,part', [('bad.xlsx', 'xl/workbook.xml'), ('bad.docx', 'word/document.xml')])
@pytest.mark.parametrize('content,code', [(None, 2), ('<broken>', 3)])
def test_office_missing_content_and_corrupt_content_are_distinct(cwd, name, part, content, code):
    with zipfile.ZipFile(cwd / name, 'w') as archive:
        if content is not None:
            archive.writestr(part, content)
    result = _run_reveal_direct(name, '--format', 'json')
    assert result.returncode == code, result.stderr
    assert json.loads(result.stdout)['error']
    if name.endswith('.xlsx'):
        uri = _run_reveal_direct('xlsx://' + name, '--format', 'json')
        assert uri.returncode == result.returncode, uri.stderr


@pytest.mark.parametrize('name,content', [
    ('empty.xml', '<root/>'), ('empty.csv', ''), ('empty.ipynb', '{"cells": []}'),
    ('recovered.json', '{"a": 1,,}'),
])
def test_empty_and_recovered_file_answers_stay_successful(cwd, name, content):
    (cwd / name).write_text(content, encoding='utf-8')
    assert _run_reveal_direct(name).returncode == 0


def test_display_cut_does_not_make_analysis_incomplete(cwd):
    (cwd / 'good.xml').write_text('<root><a/><b/><c/></root>', encoding='utf-8')
    run = _run_reveal_direct('good.xml', '--head', '1', '--format', 'json')
    assert run.returncode == 0
    result = json.loads(run.stdout)
    assert len(result['structure']['children']) == 1
    assert result['meta']['warnings']


def test_optional_errors_are_not_a_completeness_verdict(cwd, monkeypatch):
    (cwd / 'good.xml').write_text('<root/>', encoding='utf-8')
    result = ResultBuilder.create('xml_structure', 'good.xml', data={'children': []},
                                  errors=[{'code': 'optional_enrichment', 'message': 'not required'}])
    monkeypatch.setattr(XmlAnalyzer, 'get_structure', lambda *a, **kw: result)
    assert _run_reveal_direct('good.xml').returncode == 0


def test_required_output_failure_uses_d6(cwd, monkeypatch):
    (cwd / 'good.xml').write_text('<root/>', encoding='utf-8')
    from reveal.display import structure
    def broken(*args, **kwargs):
        raise RuntimeError('planted renderer failure')
    monkeypatch.setattr(structure, '_render_structure_view', broken)
    run = _run_reveal_direct('good.xml')
    assert run.returncode == 3
    assert 'Requested output failed' in run.stderr and 'planted renderer failure' in run.stderr
    assert 'Traceback' not in run.stderr


def test_unsupported_findings_suppression_remains_a_usage_error(cwd):
    (cwd / 'bad.xml').write_text('<broken>', encoding='utf-8')
    assert _run_reveal_direct('bad.xml', '--exit-zero').returncode == 2


def test_file_sink_rejection_stays_explicit(cwd):
    (cwd / 'good.xml').write_text('<root/>', encoding='utf-8')
    run = _run_reveal_direct('good.xml', '--output', 'json=report.json')
    assert run.returncode == 2 and not (cwd / 'report.json').exists()


def test_repeated_fail_repair_and_fail_do_not_share_facts(cwd):
    path = cwd / 'changing.xml'
    for content, code in [('<broken>', 3), ('<root/>', 0), ('<broken>', 3)]:
        path.write_text(content, encoding='utf-8')
        run = _run_reveal_direct('changing.xml', '--format', 'json')
        assert run.returncode == code
        assert bool(json.loads(run.stdout).get('error')) == bool(code)


def test_office_io_failure_is_analysis_not_wrong_format(cwd, monkeypatch):
    (cwd / 'bad.docx').write_bytes(b'placeholder')
    from reveal.analyzers.office import base
    def denied(*args, **kwargs):
        raise PermissionError('planted denied read')
    monkeypatch.setattr(base.zipfile, 'ZipFile', denied)
    run = _run_reveal_direct('bad.docx', '--format', 'json')
    assert run.returncode == 3
    assert 'planted denied read' in json.loads(run.stdout)['error']


@pytest.mark.parametrize('sheet,code', [('<broken>', 3), ('<worksheet/>', 0), ('x' * 1000, 3)])
def test_workbook_required_sheet_loss_is_not_an_empty_success(cwd, monkeypatch, sheet, code):
    from reveal.analyzers.office import base
    monkeypatch.setattr(base, 'MAX_XML_PART_SIZE', 500)
    with zipfile.ZipFile(cwd / 'book.xlsx', 'w') as archive:
        archive.writestr('xl/workbook.xml',
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheets><sheet name="S" sheetId="1"/></sheets></workbook>')
        archive.writestr('xl/worksheets/sheet1.xml', sheet)
    for target in ['book.xlsx', 'xlsx://book.xlsx']:
        run = _run_reveal_direct(target, '--format', 'json')
        assert run.returncode == code, run.stderr
        if code:
            # Useful observations survive with required-loss warnings.
            assert 'sheet_' in run.stdout


def test_optional_office_metadata_failure_does_not_make_content_incomplete(cwd):
    with zipfile.ZipFile(cwd / 'ok.docx', 'w') as archive:
        archive.writestr('word/document.xml',
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body/></w:document>')
        archive.writestr('docProps/core.xml', '<broken>')
    assert _run_reveal_direct('ok.docx', '--format', 'json').returncode == 0


def test_recorded_decline_stays_successful(cwd, monkeypatch):
    (cwd / 'good.xml').write_text('<root/>', encoding='utf-8')
    result = ResultBuilder.create('xml_structure', 'good.xml', applicable=False, reason='not applicable')
    monkeypatch.setattr(XmlAnalyzer, 'get_structure', lambda *a, **kw: result)
    assert _run_reveal_direct('good.xml', '--format', 'json').returncode == 0


def test_required_sheet_loss_survives_display_cut(cwd, monkeypatch):
    path = cwd / 'book.xlsx'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('xl/workbook.xml',
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheets><sheet name="S" sheetId="1"/></sheets></workbook>')
        archive.writestr('xl/worksheets/sheet1.xml', '<broken>')
    run = _run_reveal_direct('book.xlsx', '--head', '0', '--format', 'json')
    assert run.returncode == 3 and json.loads(run.stdout)['structure']['meta']['warnings']


def test_corrupt_member_of_an_open_archive_is_analysis_failure(cwd, monkeypatch):
    from reveal.analyzers.office.base import ZipXMLAnalyzer
    with zipfile.ZipFile(cwd / 'bad.docx', 'w') as archive:
        archive.writestr('word/document.xml', '<document/>')
    def corrupt_member(*args):
        raise zipfile.BadZipFile('planted member CRC error')
    monkeypatch.setattr(ZipXMLAnalyzer, '_safe_read', corrupt_member)
    run = _run_reveal_direct('bad.docx', '--format', 'json')
    assert run.returncode == 3
    assert 'planted member CRC error' in json.loads(run.stdout)['error']
