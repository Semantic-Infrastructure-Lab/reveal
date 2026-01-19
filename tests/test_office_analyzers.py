"""Tests for office document analyzers (OpenXML and ODF)."""

import os
import tempfile
import zipfile
import pytest
from pathlib import Path

from reveal.analyzers.office import (
    DocxAnalyzer,
    XlsxAnalyzer,
    PptxAnalyzer,
    OdtAnalyzer,
    OdsAnalyzer,
    OdpAnalyzer,
)
from reveal.analyzers.office.base import ZipXMLAnalyzer


# =============================================================================
# Test Fixtures - Create minimal valid office documents
# =============================================================================

@pytest.fixture
def minimal_docx(tmp_path):
    """Create a minimal valid .docx file."""
    docx_path = tmp_path / "test.docx"

    with zipfile.ZipFile(docx_path, 'w') as zf:
        # [Content_Types].xml
        zf.writestr('[Content_Types].xml', '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="xml" ContentType="application/xml"/>
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>''')

        # _rels/.rels
        zf.writestr('_rels/.rels', '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>''')

        # word/document.xml with headings and paragraphs
        zf.writestr('word/document.xml', '''<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body>
        <w:p>
            <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
            <w:r><w:t>Introduction</w:t></w:r>
        </w:p>
        <w:p>
            <w:r><w:t>This is the first paragraph.</w:t></w:r>
        </w:p>
        <w:p>
            <w:r><w:t>This is the second paragraph.</w:t></w:r>
        </w:p>
        <w:p>
            <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
            <w:r><w:t>Conclusion</w:t></w:r>
        </w:p>
        <w:p>
            <w:r><w:t>Final thoughts here.</w:t></w:r>
        </w:p>
        <w:tbl>
            <w:tr>
                <w:tc><w:p><w:r><w:t>A1</w:t></w:r></w:p></w:tc>
                <w:tc><w:p><w:r><w:t>B1</w:t></w:r></w:p></w:tc>
            </w:tr>
            <w:tr>
                <w:tc><w:p><w:r><w:t>A2</w:t></w:r></w:p></w:tc>
                <w:tc><w:p><w:r><w:t>B2</w:t></w:r></w:p></w:tc>
            </w:tr>
        </w:tbl>
    </w:body>
</w:document>''')

        # docProps/core.xml (metadata)
        zf.writestr('docProps/core.xml', '''<?xml version="1.0" encoding="UTF-8"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/"
                   xmlns:dcterms="http://purl.org/dc/terms/">
    <dc:title>Test Document</dc:title>
    <dc:creator>Test Author</dc:creator>
</cp:coreProperties>''')

    return docx_path


@pytest.fixture
def minimal_xlsx(tmp_path):
    """Create a minimal valid .xlsx file."""
    xlsx_path = tmp_path / "test.xlsx"

    with zipfile.ZipFile(xlsx_path, 'w') as zf:
        # [Content_Types].xml
        zf.writestr('[Content_Types].xml', '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="xml" ContentType="application/xml"/>
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
    <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
    <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>''')

        # xl/workbook.xml
        zf.writestr('xl/workbook.xml', '''<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
    <sheets>
        <sheet name="Data" sheetId="1" r:id="rId1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>
    </sheets>
</workbook>''')

        # xl/worksheets/sheet1.xml
        zf.writestr('xl/worksheets/sheet1.xml', '''<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
    <dimension ref="A1:B3"/>
    <sheetData>
        <row r="1">
            <c r="A1" t="s"><v>0</v></c>
            <c r="B1" t="s"><v>1</v></c>
        </row>
        <row r="2">
            <c r="A2"><v>100</v></c>
            <c r="B2"><v>200</v></c>
        </row>
        <row r="3">
            <c r="A3"><v>300</v></c>
            <c r="B3"><f>A2+B2</f><v>300</v></c>
        </row>
    </sheetData>
</worksheet>''')

        # xl/sharedStrings.xml
        zf.writestr('xl/sharedStrings.xml', '''<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="2" uniqueCount="2">
    <si><t>Name</t></si>
    <si><t>Value</t></si>
</sst>''')

    return xlsx_path


@pytest.fixture
def minimal_pptx(tmp_path):
    """Create a minimal valid .pptx file."""
    pptx_path = tmp_path / "test.pptx"

    with zipfile.ZipFile(pptx_path, 'w') as zf:
        # [Content_Types].xml
        zf.writestr('[Content_Types].xml', '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
    <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
</Types>''')

        # ppt/presentation.xml
        zf.writestr('ppt/presentation.xml', '''<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
</p:presentation>''')

        # ppt/slides/slide1.xml
        zf.writestr('ppt/slides/slide1.xml', '''<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
    <p:cSld>
        <p:spTree>
            <p:sp>
                <p:nvSpPr>
                    <p:cNvPr id="1" name="Title"/>
                    <p:cNvSpPr/>
                    <p:nvPr><p:ph type="title"/></p:nvPr>
                </p:nvSpPr>
                <p:txBody>
                    <a:p><a:r><a:t>Welcome Slide</a:t></a:r></a:p>
                </p:txBody>
            </p:sp>
            <p:sp>
                <p:nvSpPr>
                    <p:cNvPr id="2" name="Body"/>
                    <p:cNvSpPr/>
                    <p:nvPr><p:ph type="body"/></p:nvPr>
                </p:nvSpPr>
                <p:txBody>
                    <a:p><a:r><a:t>Bullet point one</a:t></a:r></a:p>
                    <a:p><a:r><a:t>Bullet point two</a:t></a:r></a:p>
                </p:txBody>
            </p:sp>
        </p:spTree>
    </p:cSld>
</p:sld>''')

    return pptx_path


@pytest.fixture
def minimal_odt(tmp_path):
    """Create a minimal valid .odt file."""
    odt_path = tmp_path / "test.odt"

    with zipfile.ZipFile(odt_path, 'w') as zf:
        # mimetype (must be first, uncompressed)
        zf.writestr('mimetype', 'application/vnd.oasis.opendocument.text')

        # content.xml
        zf.writestr('content.xml', '''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
                         xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
                         xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0">
    <office:body>
        <office:text>
            <text:h text:outline-level="1">Chapter One</text:h>
            <text:p>First paragraph of chapter one.</text:p>
            <text:p>Second paragraph of chapter one.</text:p>
            <text:h text:outline-level="1">Chapter Two</text:h>
            <text:p>Content of chapter two.</text:p>
            <table:table table:name="Table1">
                <table:table-row>
                    <table:table-cell><text:p>Cell A1</text:p></table:table-cell>
                    <table:table-cell><text:p>Cell B1</text:p></table:table-cell>
                </table:table-row>
            </table:table>
        </office:text>
    </office:body>
</office:document-content>''')

        # meta.xml
        zf.writestr('meta.xml', '''<?xml version="1.0" encoding="UTF-8"?>
<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
                      xmlns:dc="http://purl.org/dc/elements/1.1/"
                      xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0">
    <office:meta>
        <dc:title>ODF Test Document</dc:title>
        <dc:creator>ODF Author</dc:creator>
    </office:meta>
</office:document-meta>''')

    return odt_path


@pytest.fixture
def minimal_ods(tmp_path):
    """Create a minimal valid .ods file."""
    ods_path = tmp_path / "test.ods"

    with zipfile.ZipFile(ods_path, 'w') as zf:
        zf.writestr('mimetype', 'application/vnd.oasis.opendocument.spreadsheet')

        zf.writestr('content.xml', '''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
                         xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
                         xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
    <office:body>
        <office:spreadsheet>
            <table:table table:name="Sheet1">
                <table:table-row>
                    <table:table-cell><text:p>Header1</text:p></table:table-cell>
                    <table:table-cell><text:p>Header2</text:p></table:table-cell>
                </table:table-row>
                <table:table-row>
                    <table:table-cell><text:p>Data1</text:p></table:table-cell>
                    <table:table-cell><text:p>Data2</text:p></table:table-cell>
                </table:table-row>
            </table:table>
        </office:spreadsheet>
    </office:body>
</office:document-content>''')

    return ods_path


@pytest.fixture
def minimal_odp(tmp_path):
    """Create a minimal valid .odp file."""
    odp_path = tmp_path / "test.odp"

    with zipfile.ZipFile(odp_path, 'w') as zf:
        zf.writestr('mimetype', 'application/vnd.oasis.opendocument.presentation')

        zf.writestr('content.xml', '''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
                         xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
                         xmlns:presentation="urn:oasis:names:tc:opendocument:xmlns:presentation:1.0"
                         xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
    <office:body>
        <office:presentation>
            <draw:page draw:name="Slide 1">
                <draw:frame presentation:class="title">
                    <draw:text-box><text:p>Welcome to ODP</text:p></draw:text-box>
                </draw:frame>
                <draw:frame presentation:class="outline">
                    <draw:text-box><text:p>First bullet</text:p></draw:text-box>
                </draw:frame>
            </draw:page>
            <draw:page draw:name="Slide 2">
                <draw:frame presentation:class="title">
                    <draw:text-box><text:p>Second Slide</text:p></draw:text-box>
                </draw:frame>
            </draw:page>
        </office:presentation>
    </office:body>
</office:document-content>''')

    return odp_path


# =============================================================================
# DOCX Tests
# =============================================================================

class TestDocxAnalyzer:
    """Tests for Word document (.docx) analyzer."""

    def test_basic_structure(self, minimal_docx):
        """Test basic docx structure extraction."""
        analyzer = DocxAnalyzer(str(minimal_docx))
        structure = analyzer.get_structure()

        assert 'sections' in structure
        assert 'tables' in structure
        assert 'overview' in structure

        # Should find 2 headings
        assert len(structure['sections']) == 2
        assert 'Introduction' in structure['sections'][0]['name']
        assert 'Conclusion' in structure['sections'][1]['name']

        # Should find 1 table
        assert len(structure['tables']) == 1
        assert '2×2' in structure['tables'][0]['name']

    def test_metadata(self, minimal_docx):
        """Test metadata extraction from docx."""
        analyzer = DocxAnalyzer(str(minimal_docx))

        assert analyzer.metadata.get('title') == 'Test Document'
        assert analyzer.metadata.get('creator') == 'Test Author'

    def test_extract_section(self, minimal_docx):
        """Test section extraction by heading name."""
        analyzer = DocxAnalyzer(str(minimal_docx))
        result = analyzer.extract_element('section', 'Introduction')

        assert result is not None
        assert 'Introduction' in result['name']
        assert 'source' in result
        assert 'first paragraph' in result['source']

    def test_extract_nonexistent_section(self, minimal_docx):
        """Test extraction of section that doesn't exist."""
        analyzer = DocxAnalyzer(str(minimal_docx))
        result = analyzer.extract_element('section', 'NonexistentSection')

        assert result is None

    def test_invalid_file(self, tmp_path):
        """Test handling of invalid/corrupt file."""
        bad_file = tmp_path / "bad.docx"
        bad_file.write_text("not a zip file")

        analyzer = DocxAnalyzer(str(bad_file))
        assert analyzer.parse_error is not None
        assert 'error' in analyzer.get_structure()


# =============================================================================
# XLSX Tests
# =============================================================================

class TestXlsxAnalyzer:
    """Tests for Excel spreadsheet (.xlsx) analyzer."""

    def test_basic_structure(self, minimal_xlsx):
        """Test basic xlsx structure extraction."""
        analyzer = XlsxAnalyzer(str(minimal_xlsx))
        structure = analyzer.get_structure()

        assert 'sheets' in structure
        assert len(structure['sheets']) == 1
        assert 'Data' in structure['sheets'][0]['name']
        assert '3 rows' in structure['sheets'][0]['name']

    def test_shared_strings(self, minimal_xlsx):
        """Test shared strings are loaded."""
        analyzer = XlsxAnalyzer(str(minimal_xlsx))

        assert len(analyzer.shared_strings) == 2
        assert 'Name' in analyzer.shared_strings
        assert 'Value' in analyzer.shared_strings

    def test_extract_sheet(self, minimal_xlsx):
        """Test sheet extraction by name."""
        analyzer = XlsxAnalyzer(str(minimal_xlsx))
        result = analyzer.extract_element('sheet', 'Data')

        assert result is not None
        assert 'Data' in result['name']
        assert 'source' in result
        assert 'Name' in result['source']  # Header from shared strings

    def test_formulas_detected(self, minimal_xlsx):
        """Test that formulas are detected in sheet analysis."""
        analyzer = XlsxAnalyzer(str(minimal_xlsx))
        result = analyzer.extract_element('sheet', 'Data')

        # Sheet has 1 formula
        assert 'Formulas: 1' in result['source']


# =============================================================================
# PPTX Tests
# =============================================================================

class TestPptxAnalyzer:
    """Tests for PowerPoint presentation (.pptx) analyzer."""

    def test_basic_structure(self, minimal_pptx):
        """Test basic pptx structure extraction."""
        analyzer = PptxAnalyzer(str(minimal_pptx))
        structure = analyzer.get_structure()

        assert 'slides' in structure
        assert len(structure['slides']) == 1
        assert 'Welcome Slide' in structure['slides'][0]['name']

    def test_extract_slide_by_number(self, minimal_pptx):
        """Test slide extraction by number."""
        analyzer = PptxAnalyzer(str(minimal_pptx))
        result = analyzer.extract_element('slide', '1')

        assert result is not None
        assert 'Slide 1' in result['name']
        assert 'source' in result
        assert 'Welcome Slide' in result['source']

    def test_extract_slide_by_title(self, minimal_pptx):
        """Test slide extraction by title match."""
        analyzer = PptxAnalyzer(str(minimal_pptx))
        result = analyzer.extract_element('slide', 'Welcome')

        assert result is not None
        assert 'Bullet point' in result['source']


# =============================================================================
# ODT Tests
# =============================================================================

class TestOdtAnalyzer:
    """Tests for Writer document (.odt) analyzer."""

    def test_basic_structure(self, minimal_odt):
        """Test basic odt structure extraction."""
        analyzer = OdtAnalyzer(str(minimal_odt))
        structure = analyzer.get_structure()

        assert 'sections' in structure
        assert 'tables' in structure
        assert 'overview' in structure

        # Should find 2 headings
        assert len(structure['sections']) == 2
        assert 'Chapter One' in structure['sections'][0]['name']
        assert 'Chapter Two' in structure['sections'][1]['name']

    def test_metadata(self, minimal_odt):
        """Test metadata extraction from odt."""
        analyzer = OdtAnalyzer(str(minimal_odt))

        assert analyzer.metadata.get('title') == 'ODF Test Document'
        assert analyzer.metadata.get('creator') == 'ODF Author'

    def test_extract_section(self, minimal_odt):
        """Test section extraction by heading name."""
        analyzer = OdtAnalyzer(str(minimal_odt))
        result = analyzer.extract_element('section', 'Chapter One')

        assert result is not None
        assert 'source' in result
        assert 'First paragraph' in result['source']


# =============================================================================
# ODS Tests
# =============================================================================

class TestOdsAnalyzer:
    """Tests for Calc spreadsheet (.ods) analyzer."""

    def test_basic_structure(self, minimal_ods):
        """Test basic ods structure extraction."""
        analyzer = OdsAnalyzer(str(minimal_ods))
        structure = analyzer.get_structure()

        assert 'sheets' in structure
        assert len(structure['sheets']) == 1
        assert 'Sheet1' in structure['sheets'][0]['name']

    def test_extract_sheet(self, minimal_ods):
        """Test sheet extraction."""
        analyzer = OdsAnalyzer(str(minimal_ods))
        result = analyzer.extract_element('sheet', 'Sheet1')

        assert result is not None
        assert 'source' in result
        assert 'Header1' in result['source']


# =============================================================================
# ODP Tests
# =============================================================================

class TestOdpAnalyzer:
    """Tests for Impress presentation (.odp) analyzer."""

    def test_basic_structure(self, minimal_odp):
        """Test basic odp structure extraction."""
        analyzer = OdpAnalyzer(str(minimal_odp))
        structure = analyzer.get_structure()

        assert 'slides' in structure
        assert len(structure['slides']) == 2

    def test_extract_slide(self, minimal_odp):
        """Test slide extraction."""
        analyzer = OdpAnalyzer(str(minimal_odp))
        result = analyzer.extract_element('slide', '1')

        assert result is not None
        assert 'source' in result
        assert 'Welcome to ODP' in result['source']


# =============================================================================
# Base Class Tests
# =============================================================================

class TestZipXMLAnalyzer:
    """Tests for the base ZipXMLAnalyzer class."""

    def test_embedded_media_detection(self, tmp_path):
        """Test detection of embedded media files."""
        doc_path = tmp_path / "with_media.docx"

        with zipfile.ZipFile(doc_path, 'w') as zf:
            zf.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types/>')
            zf.writestr('word/document.xml', '<?xml version="1.0"?><document/>')
            zf.writestr('word/media/image1.png', b'\x89PNG\r\n\x1a\n' + b'\x00' * 100)
            zf.writestr('word/media/image2.jpg', b'\xff\xd8\xff' + b'\x00' * 100)

        analyzer = DocxAnalyzer(str(doc_path))
        media = analyzer._get_embedded_media()

        assert len(media) == 2
        assert any('png' in m['name'].lower() for m in media)
        assert any('jpg' in m['name'].lower() for m in media)

    def test_format_size(self, minimal_docx):
        """Test file size formatting utility (now in reveal.utils)."""
        from reveal.utils import format_size

        assert format_size(500) == '500.0 B'
        assert format_size(1024) == '1.0 KB'
        assert format_size(1024 * 1024) == '1.0 MB'

    def test_get_metadata(self, minimal_docx):
        """Test base metadata retrieval."""
        analyzer = DocxAnalyzer(str(minimal_docx))
        meta = analyzer.get_metadata()

        assert 'path' in meta
        assert 'name' in meta
        assert 'size' in meta
        assert 'parts_count' in meta
        assert meta['parts_count'] > 0


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_document(self, tmp_path):
        """Test handling of document with no content."""
        doc_path = tmp_path / "empty.docx"

        with zipfile.ZipFile(doc_path, 'w') as zf:
            zf.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types/>')
            zf.writestr('word/document.xml', '''<?xml version="1.0"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body></w:body>
</w:document>''')

        analyzer = DocxAnalyzer(str(doc_path))
        structure = analyzer.get_structure()

        # Should handle gracefully with empty/minimal structure
        assert 'error' not in structure

    def test_missing_content_file(self, tmp_path):
        """Test handling of ZIP without expected content file."""
        doc_path = tmp_path / "incomplete.docx"

        with zipfile.ZipFile(doc_path, 'w') as zf:
            zf.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types/>')
            # Missing word/document.xml

        analyzer = DocxAnalyzer(str(doc_path))
        structure = analyzer.get_structure()

        # Should handle gracefully
        assert 'error' in structure

    def test_malformed_xml(self, tmp_path):
        """Test handling of malformed XML content."""
        doc_path = tmp_path / "malformed.docx"

        with zipfile.ZipFile(doc_path, 'w') as zf:
            zf.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types/>')
            zf.writestr('word/document.xml', 'not valid xml <<<<')

        analyzer = DocxAnalyzer(str(doc_path))
        assert analyzer.parse_error is not None

    def test_semantic_slice(self, minimal_docx):
        """Test head/tail/range slicing of structure."""
        analyzer = DocxAnalyzer(str(minimal_docx))

        # Test head
        structure = analyzer.get_structure(head=1)
        assert len(structure['sections']) == 1

        # Test tail
        structure = analyzer.get_structure(tail=1)
        assert len(structure['sections']) == 1
        assert 'Conclusion' in structure['sections'][0]['name']
