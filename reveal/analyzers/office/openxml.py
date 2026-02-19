"""OpenXML analyzers for Microsoft Office formats.

Supports:
- .docx (Word documents)
- .xlsx (Excel spreadsheets)
- .pptx (PowerPoint presentations)

All are ZIP archives containing XML files following the ECMA-376 standard.
"""

import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
from ...registry import register
from ...utils import format_size
from .base import ZipXMLAnalyzer


# Common OpenXML namespaces
OPENXML_NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'cp': 'http://schemas.openxmlformats.org/package/2006/metadata/core-properties',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'dcterms': 'http://purl.org/dc/terms/',
    'xl': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
}


@register('.docx', name='Word Document', icon='📄')
class DocxAnalyzer(ZipXMLAnalyzer):
    """Analyzer for Microsoft Word documents (.docx)."""

    CONTENT_PATH = 'word/document.xml'
    NAMESPACES = OPENXML_NS

    # Mapping of Word style IDs to heading levels
    HEADING_STYLES = {
        'Heading1': 1, 'Heading2': 2, 'Heading3': 3,
        'Heading4': 4, 'Heading5': 5, 'Heading6': 6,
        'Title': 0,
    }

    def _parse_metadata(self) -> None:
        """Parse Word document metadata from core.xml (adds 'subject' field)."""
        super()._parse_metadata()
        core = self._read_xml('docProps/core.xml')
        if core is None:
            return
        subject = self._get_xml_text(core, 'subject', 'dc', self.NAMESPACES)
        if subject:
            self.metadata['subject'] = subject

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Extract document structure: headings, paragraphs, tables."""
        if self.parse_error:
            return {'error': [{'message': self.parse_error}]}

        if self.content_tree is None:
            return {'error': [{'message': 'No content found'}]}

        ns = self.NAMESPACES
        w = ns['w']

        # Find body
        body = self.content_tree.find(f'.//{{{w}}}body')
        if body is None:
            return {'error': [{'message': 'No document body found'}]}

        sections, tables, para_count, word_count = self._collect_body_stats(body)

        # Build result
        result: Dict[str, List[Dict[str, Any]]] = {
            'contract_version': '1.0',
            'type': 'docx_structure',
            'source': str(self.path),
            'source_type': 'file',
        }

        if sections:
            sections = self._apply_semantic_slice(sections, head, tail, range)
            result['sections'] = sections

        if tables:
            result['tables'] = tables

        # Add overview as first item (formatted for standard renderer)
        result['overview'] = [{
            'name': f'{para_count} paragraphs, {word_count} words',
            'line_start': 1,
        }]

        # Add embedded media
        media = self._get_embedded_media()
        if media:
            result['media'] = [{
                'name': f"{m['name']} ({m['type']}, {format_size(m['size'])})",
                'line_start': idx + 1,
            } for idx, m in enumerate(media)]

        return result

    def _collect_body_stats(self, body):
        """Extract sections, tables, paragraph count, and word count from document body."""
        sections: List[Dict[str, Any]] = []
        tables: List[Dict[str, Any]] = []
        para_count = 0
        word_count = 0
        for idx, elem in enumerate(body):
            tag = elem.tag.split('}')[-1]
            if tag == 'p':
                para_count += 1
                style = self._get_paragraph_style(elem)
                text = self._get_paragraph_text(elem)
                word_count += len(text.split())
                if style in self.HEADING_STYLES:
                    level = self.HEADING_STYLES[style]
                    heading_name = (text[:80] + '...' if len(text) > 80 else text) if text else f'[{style}]'
                    sections.append({
                        'name': heading_name,
                        'level': level,
                        'style': style,
                        'line_start': idx + 1,
                    })
            elif tag == 'tbl':
                rows, cols = self._get_table_dimensions(elem)
                tables.append({
                    'name': f'Table ({rows}×{cols})',
                    'rows': rows,
                    'cols': cols,
                    'line_start': idx + 1,
                })
        return sections, tables, para_count, word_count

    def _get_paragraph_style(self, para: ET.Element) -> Optional[str]:
        """Get paragraph style name."""
        w = self.NAMESPACES['w']
        pPr = para.find(f'{{{w}}}pPr')
        if pPr is not None:
            pStyle = pPr.find(f'{{{w}}}pStyle')
            if pStyle is not None:
                return pStyle.get(f'{{{w}}}val')
        return None

    def _get_paragraph_text(self, para: ET.Element) -> str:
        """Extract text from paragraph element."""
        w = self.NAMESPACES['w']
        texts = []
        for t in para.iter(f'{{{w}}}t'):
            if t.text:
                texts.append(t.text)
        return ''.join(texts)

    def _get_table_dimensions(self, table: ET.Element) -> tuple:
        """Get table row and column counts."""
        w = self.NAMESPACES['w']
        rows = list(table.iter(f'{{{w}}}tr'))
        if rows:
            first_row = rows[0]
            cols = list(first_row.iter(f'{{{w}}}tc'))
            return len(rows), len(cols)
        return 0, 0

    def _process_docx_paragraph(self, style, text, target_name, in_section,
                                 section_level, start_idx, end_idx, idx, section_text):
        """Process a single paragraph element during section extraction.

        Returns (in_section, section_level, start_idx, end_idx, stop).
        stop=True means the for loop should break.
        """
        if in_section:
            if style in self.HEADING_STYLES and self.HEADING_STYLES[style] <= section_level:
                return in_section, section_level, start_idx, end_idx, True
            section_text.append(text)
            end_idx = idx + 1
        elif style in self.HEADING_STYLES and target_name.lower() in text.lower():
            in_section = True
            section_level = self.HEADING_STYLES[style]
            start_idx = idx + 1
            end_idx = idx + 1
            section_text.append(f"# {text}")
        return in_section, section_level, start_idx, end_idx, False

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a section by heading name."""
        if self.content_tree is None:
            return None

        ns = self.NAMESPACES
        w = ns['w']
        body = self.content_tree.find(f'.//{{{w}}}body')
        if body is None:
            return None

        # Find the section with matching name
        in_section = False
        section_text: List[str] = []
        section_level = 0
        start_idx = 0
        end_idx = 0

        for idx, elem in enumerate(body):
            tag = elem.tag.split('}')[-1]
            if tag != 'p':
                continue
            style = self._get_paragraph_style(elem)
            text = self._get_paragraph_text(elem)
            in_section, section_level, start_idx, end_idx, stop = self._process_docx_paragraph(
                style, text, name, in_section, section_level, start_idx, end_idx, idx, section_text
            )
            if stop:
                break

        if section_text:
            return {
                'name': name,
                'line_start': start_idx,
                'line_end': end_idx,
                'source': '\n\n'.join(section_text),
            }
        return None


@register('.xlsx', name='Excel Spreadsheet', icon='📊')
class XlsxAnalyzer(ZipXMLAnalyzer):
    """Analyzer for Microsoft Excel spreadsheets (.xlsx)."""

    CONTENT_PATH = 'xl/workbook.xml'
    NAMESPACES = OPENXML_NS

    def __init__(self, path: str):
        super().__init__(path)
        self.shared_strings: List[str] = []
        self._load_shared_strings()

    def _load_shared_strings(self) -> None:
        """Load shared strings table."""
        ss_tree = self._read_xml('xl/sharedStrings.xml')
        if ss_tree is None:
            return

        xl = self.NAMESPACES['xl']
        for si in ss_tree.iter(f'{{{xl}}}si'):
            text_parts = []
            for t in si.iter(f'{{{xl}}}t'):
                if t.text:
                    text_parts.append(t.text)
            self.shared_strings.append(''.join(text_parts))

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Extract spreadsheet structure: sheets, dimensions, formulas."""
        if self.parse_error:
            return {'error': [{'message': self.parse_error}]}

        if self.content_tree is None:
            return {'error': [{'message': 'No workbook found'}]}

        xl = self.NAMESPACES['xl']

        # Get sheet names from workbook
        sheets_elem = self.content_tree.find(f'{{{xl}}}sheets')
        if sheets_elem is None:
            return {'error': [{'message': 'No sheets found'}]}

        sheets: List[Dict[str, Any]] = []

        for idx, sheet in enumerate(sheets_elem.findall(f'{{{xl}}}sheet')):
            sheet_name = sheet.get('name', f'Sheet{idx + 1}')
            sheet_id = idx + 1

            # Try to get sheet details
            sheet_path = f'xl/worksheets/sheet{sheet_id}.xml'
            sheet_info = self._analyze_sheet(sheet_path, sheet_name)
            sheet_info['line_start'] = idx + 1
            sheets.append(sheet_info)

        result: Dict[str, List[Dict[str, Any]]] = {
            'contract_version': '1.0',
            'type': 'xlsx_structure',
            'source': str(self.path),
            'source_type': 'file',
        }

        if sheets:
            # Format sheets with details in name
            formatted_sheets = []
            for s in sheets:
                dim = f" ({s['dimension']})" if s.get('dimension') else ''
                formulas = f", {s['formulas']} formulas" if s.get('formulas') else ''
                formatted_sheets.append({
                    'name': f"{s['name']}{dim} - {s['rows']} rows, {s['cols']} cols{formulas}",
                    'line_start': s['line_start'],
                })
            formatted_sheets = self._apply_semantic_slice(formatted_sheets, head, tail, range)
            result['sheets'] = formatted_sheets

        return result

    def _analyze_sheet(self, sheet_path: str, sheet_name: str) -> Dict[str, Any]:
        """Analyze a single worksheet."""
        sheet_tree = self._read_xml(sheet_path)
        if sheet_tree is None:
            return {'name': sheet_name, 'rows': 0, 'cols': 0}

        xl = self.NAMESPACES['xl']

        # Get dimension
        dimension = sheet_tree.find(f'{{{xl}}}dimension')
        dim_ref = dimension.get('ref', '') if dimension is not None else ''

        # Count rows and formulas
        rows = list(sheet_tree.iter(f'{{{xl}}}row'))
        formula_count = len(list(sheet_tree.iter(f'{{{xl}}}f')))

        # Estimate columns from first row
        col_count = 0
        if rows:
            first_row = rows[0]
            col_count = len(list(first_row.iter(f'{{{xl}}}c')))

        return {
            'name': sheet_name,
            'dimension': dim_ref,
            'rows': len(rows),
            'cols': col_count,
            'formulas': formula_count,
        }

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a sheet by name."""
        if self.content_tree is None:
            return None

        xl = self.NAMESPACES['xl']
        sheets_elem = self.content_tree.find(f'{{{xl}}}sheets')
        if sheets_elem is None:
            return None

        # Find matching sheet
        for idx, sheet in enumerate(sheets_elem.findall(f'{{{xl}}}sheet')):
            sheet_name = sheet.get('name', '')
            if name.lower() in sheet_name.lower():
                sheet_path = f'xl/worksheets/sheet{idx + 1}.xml'
                sheet_info = self._analyze_sheet(sheet_path, sheet_name)

                # Get preview of data and format as text
                preview = self._get_sheet_preview(sheet_path, max_rows=20)
                lines = []
                for row in preview:
                    lines.append(' | '.join(str(cell) for cell in row))

                dim = sheet_info.get('dimension', '')
                header = f"Sheet: {sheet_name}"
                if dim:
                    header += f" ({dim})"
                header += f"\nRows: {sheet_info.get('rows', 0)}, Cols: {sheet_info.get('cols', 0)}"
                if sheet_info.get('formulas'):
                    header += f", Formulas: {sheet_info['formulas']}"

                source = header + "\n\n" + '\n'.join(lines)

                return {
                    'name': sheet_name,
                    'line_start': idx + 1,
                    'line_end': idx + 1 + len(lines),
                    'source': source,
                }

        return None

    def _get_sheet_preview(self, sheet_path: str, max_rows: int = 10) -> List[List[str]]:
        """Get preview of sheet data."""
        sheet_tree = self._read_xml(sheet_path)
        if sheet_tree is None:
            return []

        xl = self.NAMESPACES['xl']
        preview = []

        for row in list(sheet_tree.iter(f'{{{xl}}}row'))[:max_rows]:
            row_data = []
            for cell in row.iter(f'{{{xl}}}c'):
                value = self._get_cell_value(cell)
                row_data.append(value)
            if row_data:
                preview.append(row_data)

        return preview

    def _get_cell_value(self, cell: ET.Element) -> str:
        """Get cell value, handling shared strings."""
        xl = self.NAMESPACES['xl']
        cell_type = cell.get('t', '')
        value_elem = cell.find(f'{{{xl}}}v')

        if value_elem is None or value_elem.text is None:
            return ''

        if cell_type == 's':  # Shared string
            try:
                idx = int(value_elem.text)
                if 0 <= idx < len(self.shared_strings):
                    return self.shared_strings[idx]
            except ValueError:
                pass
        return value_elem.text


@register('.pptx', name='PowerPoint Presentation', icon='📽️')
class PptxAnalyzer(ZipXMLAnalyzer):
    """Analyzer for Microsoft PowerPoint presentations (.pptx)."""

    CONTENT_PATH = 'ppt/presentation.xml'
    NAMESPACES = OPENXML_NS

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Extract presentation structure: slides with titles."""
        if self.parse_error:
            return {'error': [{'message': self.parse_error}]}

        # Find all slide files
        slide_paths = sorted([p for p in self.parts if p.startswith('ppt/slides/slide') and p.endswith('.xml')])

        slides: List[Dict[str, Any]] = []

        for idx, slide_path in enumerate(slide_paths):
            slide_info = self._analyze_slide(slide_path, idx + 1)
            slides.append(slide_info)

        result: Dict[str, List[Dict[str, Any]]] = {
            'contract_version': '1.0',
            'type': 'pptx_structure',
            'source': str(self.path),
            'source_type': 'file',
        }

        if slides:
            # Format slides with details
            formatted_slides = []
            for s in slides:
                shapes_info = f", {s['shapes']} shapes" if s.get('shapes') else ''
                formatted_slides.append({
                    'name': f"[{s['slide_num']}] {s['name']}{shapes_info}",
                    'line_start': s['line_start'],
                })
            formatted_slides = self._apply_semantic_slice(formatted_slides, head, tail, range)
            result['slides'] = formatted_slides

        # Media
        media = self._get_embedded_media()
        if media:
            result['media'] = [{
                'name': f"{m['name']} ({m['type']}, {format_size(m['size'])})",
                'line_start': idx + 1,
            } for idx, m in enumerate(media)]

        return result

    def _extract_shape_title(self, shape, ns_a: str, ns_p: str) -> Optional[str]:
        """Return the title text from a title/ctrTitle placeholder shape, or None."""
        nvSpPr = shape.find(f'.//{{{ns_p}}}nvSpPr')
        if nvSpPr is None:
            return None
        nvPr = nvSpPr.find(f'{{{ns_p}}}nvPr')
        if nvPr is None:
            return None
        ph = nvPr.find(f'{{{ns_p}}}ph')
        if ph is None or ph.get('type') not in ('title', 'ctrTitle'):
            return None
        texts = [t.text for t in shape.iter(f'{{{ns_a}}}t') if t.text]
        if not texts:
            return None
        full = ''.join(texts)
        return full[:60] + ('...' if len(full) > 60 else '')

    def _analyze_slide(self, slide_path: str, slide_num: int) -> Dict[str, Any]:
        """Analyze a single slide."""
        slide_tree = self._read_xml(slide_path)

        title = f'Slide {slide_num}'
        text_count = 0
        shapes_count = 0

        if slide_tree is not None:
            a = self.NAMESPACES['a']
            p = self.NAMESPACES['p']

            shapes = list(slide_tree.iter(f'{{{p}}}sp'))
            shapes_count = len(shapes)

            for shape in shapes:
                shape_title = self._extract_shape_title(shape, a, p)
                if shape_title:
                    title = shape_title
                    break

            text_count = len(list(slide_tree.iter(f'{{{a}}}t')))

        return {
            'name': title,
            'slide_num': slide_num,
            'shapes': shapes_count,
            'text_elements': text_count,
            'line_start': slide_num,
        }

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a slide by number or title match."""
        # Try to parse as slide number
        try:
            slide_num = int(name)
            slide_path = f'ppt/slides/slide{slide_num}.xml'
            if slide_path in self.parts:
                return self._extract_slide_content(slide_path, slide_num)
        except ValueError:
            pass

        # Search by title
        slide_paths = sorted([p for p in self.parts if p.startswith('ppt/slides/slide') and p.endswith('.xml')])

        for idx, slide_path in enumerate(slide_paths):
            slide_info = self._analyze_slide(slide_path, idx + 1)
            if name.lower() in slide_info['name'].lower():
                return self._extract_slide_content(slide_path, idx + 1)

        return None

    def _extract_slide_content(self, slide_path: str, slide_num: int) -> Dict[str, Any]:
        """Extract full content from a slide."""
        slide_tree = self._read_xml(slide_path)
        if slide_tree is None:
            return {'name': f'Slide {slide_num}', 'source': '', 'line_start': slide_num, 'line_end': slide_num}

        a = self.NAMESPACES['a']

        # Extract all text
        texts = []
        for t in slide_tree.iter(f'{{{a}}}t'):
            if t.text:
                texts.append(t.text)

        content = '\n'.join(texts)

        return {
            'name': f'Slide {slide_num}',
            'line_start': slide_num,
            'line_end': slide_num + len(texts),
            'source': f"Slide {slide_num}\n{'=' * 40}\n\n{content}",
        }
