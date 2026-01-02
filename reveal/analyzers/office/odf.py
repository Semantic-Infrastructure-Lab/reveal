"""ODF analyzers for LibreOffice/OpenOffice formats.

Supports:
- .odt (Writer documents)
- .ods (Calc spreadsheets)
- .odp (Impress presentations)

All are ZIP archives containing XML files following the OASIS ODF standard.
"""

import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
from ...base import register
from .base import ZipXMLAnalyzer


# ODF namespaces
ODF_NS = {
    'office': 'urn:oasis:names:tc:opendocument:xmlns:office:1.0',
    'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
    'table': 'urn:oasis:names:tc:opendocument:xmlns:table:1.0',
    'style': 'urn:oasis:names:tc:opendocument:xmlns:style:1.0',
    'draw': 'urn:oasis:names:tc:opendocument:xmlns:drawing:1.0',
    'presentation': 'urn:oasis:names:tc:opendocument:xmlns:presentation:1.0',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'meta': 'urn:oasis:names:tc:opendocument:xmlns:meta:1.0',
    'fo': 'urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0',
}


class OdfAnalyzer(ZipXMLAnalyzer):
    """Base class for ODF document analyzers."""

    CONTENT_PATH = 'content.xml'
    NAMESPACES = ODF_NS

    def _parse_metadata(self) -> None:
        """Parse ODF metadata from meta.xml."""
        meta_tree = self._read_xml('meta.xml')
        if meta_tree is None:
            return

        ns = self.NAMESPACES

        def get_text(tag: str, prefix: str) -> Optional[str]:
            ns_uri = ns.get(prefix, '')
            elem = meta_tree.find(f'.//{{{ns_uri}}}{tag}')
            return elem.text if elem is not None and elem.text else None

        self.metadata = {
            'title': get_text('title', 'dc'),
            'creator': get_text('creator', 'dc'),
            'subject': get_text('subject', 'dc'),
            'creation-date': get_text('creation-date', 'meta'),
            'date': get_text('date', 'dc'),  # Last modified
        }
        # Remove None values
        self.metadata = {k: v for k, v in self.metadata.items() if v}

    def _get_mimetype(self) -> Optional[str]:
        """Get document mimetype."""
        content = self._read_part('mimetype')
        if content:
            return content.decode('utf-8').strip()
        return None


@register('.odt', name='Writer Document', icon='📝')
class OdtAnalyzer(OdfAnalyzer):
    """Analyzer for LibreOffice/OpenOffice Writer documents (.odt)."""

    # ODF heading outline levels
    HEADING_STYLES = {'Heading': True}  # ODF uses outline-level attribute

    def get_structure(self, head: int = None, tail: int = None,
                      range: tuple = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Extract document structure: headings, paragraphs, tables."""
        if self.parse_error:
            return {'error': [{'message': self.parse_error}]}

        if self.content_tree is None:
            return {'error': [{'message': 'No content found'}]}

        ns = self.NAMESPACES
        text_ns = ns['text']
        table_ns = ns['table']
        office_ns = ns['office']

        # Find body/text
        body = self.content_tree.find(f'.//{{{office_ns}}}body')
        if body is None:
            return {'error': [{'message': 'No document body found'}]}

        text_body = body.find(f'{{{office_ns}}}text')
        if text_body is None:
            # Try spreadsheet or presentation body
            text_body = body

        sections: List[Dict[str, Any]] = []
        tables: List[Dict[str, Any]] = []
        para_count = 0
        word_count = 0

        for idx, elem in enumerate(text_body):
            tag = elem.tag.split('}')[-1]

            if tag == 'p':  # Paragraph
                para_count += 1
                text = self._get_element_text(elem)
                word_count += len(text.split())

            elif tag == 'h':  # Heading
                text = self._get_element_text(elem)
                level = int(elem.get(f'{{{text_ns}}}outline-level', '1'))
                word_count += len(text.split())

                sections.append({
                    'name': text[:80] + ('...' if len(text) > 80 else '') if text else f'[Heading {level}]',
                    'level': level,
                    'line': idx + 1,
                })

            elif tag == 'table':  # Table
                rows, cols = self._get_table_dimensions(elem)
                name = elem.get(f'{{{table_ns}}}name', f'Table {len(tables) + 1}')
                tables.append({
                    'name': f'{name} ({rows}×{cols})',
                    'rows': rows,
                    'cols': cols,
                    'line': idx + 1,
                })

        # Build result
        result: Dict[str, List[Dict[str, Any]]] = {}

        if sections:
            sections = self._apply_semantic_slice(sections, head, tail, range)
            result['sections'] = sections

        if tables:
            result['tables'] = tables

        # Add overview as first item
        result['overview'] = [{
            'name': f'{para_count} paragraphs, {word_count} words',
            'line': 1,
        }]

        # Embedded media
        media = self._get_embedded_media()
        if media:
            result['media'] = [{
                'name': f"{m['name']} ({m['type']}, {self._format_size(m['size'])})",
                'line': idx + 1,
            } for idx, m in enumerate(media)]

        return result

    def _get_element_text(self, elem: ET.Element) -> str:
        """Extract all text from an element and its children."""
        texts = []
        if elem.text:
            texts.append(elem.text)
        for child in elem:
            texts.append(self._get_element_text(child))
            if child.tail:
                texts.append(child.tail)
        return ''.join(texts)

    def _get_table_dimensions(self, table: ET.Element) -> tuple:
        """Get table row and column counts."""
        table_ns = self.NAMESPACES['table']
        rows = list(table.iter(f'{{{table_ns}}}table-row'))
        if rows:
            first_row = rows[0]
            cols = list(first_row.iter(f'{{{table_ns}}}table-cell'))
            return len(rows), len(cols)
        return 0, 0

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a section by heading name."""
        if self.content_tree is None:
            return None

        ns = self.NAMESPACES
        office_ns = ns['office']
        text_ns = ns['text']

        body = self.content_tree.find(f'.//{{{office_ns}}}body')
        if body is None:
            return None

        text_body = body.find(f'{{{office_ns}}}text')
        if text_body is None:
            text_body = body

        # Find matching section
        in_section = False
        section_text: List[str] = []
        section_level = 0
        start_idx = 0

        for idx, elem in enumerate(text_body):
            tag = elem.tag.split('}')[-1]

            if tag == 'h':
                text = self._get_element_text(elem)
                level = int(elem.get(f'{{{text_ns}}}outline-level', '1'))

                if in_section:
                    if level <= section_level:
                        break  # End of section
                    section_text.append(f"{'#' * level} {text}")
                else:
                    if name.lower() in text.lower():
                        in_section = True
                        section_level = level
                        start_idx = idx + 1
                        section_text.append(f"{'#' * level} {text}")

            elif tag == 'p' and in_section:
                text = self._get_element_text(elem)
                section_text.append(text)

        if section_text:
            return {
                'name': name,
                'line_start': start_idx,
                'line_end': start_idx + len(section_text),
                'source': '\n\n'.join(section_text),
            }
        return None


@register('.ods', name='Calc Spreadsheet', icon='📈')
class OdsAnalyzer(OdfAnalyzer):
    """Analyzer for LibreOffice/OpenOffice Calc spreadsheets (.ods)."""

    def get_structure(self, head: int = None, tail: int = None,
                      range: tuple = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Extract spreadsheet structure: sheets, dimensions."""
        if self.parse_error:
            return {'error': [{'message': self.parse_error}]}

        if self.content_tree is None:
            return {'error': [{'message': 'No content found'}]}

        ns = self.NAMESPACES
        office_ns = ns['office']
        table_ns = ns['table']

        # Find spreadsheet body
        body = self.content_tree.find(f'.//{{{office_ns}}}body')
        if body is None:
            return {'error': [{'message': 'No document body found'}]}

        spreadsheet = body.find(f'{{{office_ns}}}spreadsheet')
        if spreadsheet is None:
            return {'error': [{'message': 'No spreadsheet found'}]}

        sheets: List[Dict[str, Any]] = []

        for idx, table in enumerate(spreadsheet.findall(f'{{{table_ns}}}table')):
            sheet_name = table.get(f'{{{table_ns}}}name', f'Sheet{idx + 1}')
            sheet_info = self._analyze_sheet(table, sheet_name)
            sheet_info['line'] = idx + 1
            sheets.append(sheet_info)

        result: Dict[str, List[Dict[str, Any]]] = {}

        if sheets:
            # Format sheets with details in name
            formatted_sheets = []
            for s in sheets:
                formatted_sheets.append({
                    'name': f"{s['name']} - {s['rows']} rows, {s['cols']} cols",
                    'line': s['line'],
                })
            formatted_sheets = self._apply_semantic_slice(formatted_sheets, head, tail, range)
            result['sheets'] = formatted_sheets

        return result

    def _analyze_sheet(self, table: ET.Element, sheet_name: str) -> Dict[str, Any]:
        """Analyze a single sheet."""
        table_ns = self.NAMESPACES['table']

        rows = list(table.findall(f'{{{table_ns}}}table-row'))
        col_count = 0

        # Get column count from first row
        if rows:
            first_row = rows[0]
            cols = list(first_row.findall(f'{{{table_ns}}}table-cell'))
            col_count = len(cols)

        # Count non-empty rows (ODF can have many empty rows)
        non_empty_rows = 0
        for row in rows:
            cells = row.findall(f'{{{table_ns}}}table-cell')
            for cell in cells:
                if self._get_element_text(cell).strip():
                    non_empty_rows += 1
                    break

        return {
            'name': sheet_name,
            'rows': non_empty_rows,
            'cols': col_count,
            'total_rows': len(rows),
        }

    def _get_element_text(self, elem: ET.Element) -> str:
        """Extract text from element."""
        texts = []
        if elem.text:
            texts.append(elem.text)
        for child in elem:
            texts.append(self._get_element_text(child))
            if child.tail:
                texts.append(child.tail)
        return ''.join(texts)

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a sheet by name."""
        if self.content_tree is None:
            return None

        ns = self.NAMESPACES
        office_ns = ns['office']
        table_ns = ns['table']

        body = self.content_tree.find(f'.//{{{office_ns}}}body')
        if body is None:
            return None

        spreadsheet = body.find(f'{{{office_ns}}}spreadsheet')
        if spreadsheet is None:
            return None

        for idx, table in enumerate(spreadsheet.findall(f'{{{table_ns}}}table')):
            sheet_name = table.get(f'{{{table_ns}}}name', '')
            if name.lower() in sheet_name.lower():
                preview = self._get_sheet_preview(table, max_rows=20)
                sheet_info = self._analyze_sheet(table, sheet_name)

                # Format as text
                lines = []
                for row in preview:
                    lines.append(' | '.join(str(cell) for cell in row))

                header = f"Sheet: {sheet_name}"
                header += f"\nRows: {sheet_info.get('rows', 0)}, Cols: {sheet_info.get('cols', 0)}"

                source = header + "\n\n" + '\n'.join(lines)

                return {
                    'name': sheet_name,
                    'line_start': idx + 1,
                    'line_end': idx + 1 + len(lines),
                    'source': source,
                }

        return None

    def _get_sheet_preview(self, table: ET.Element, max_rows: int = 10) -> List[List[str]]:
        """Get preview of sheet data."""
        table_ns = self.NAMESPACES['table']
        text_ns = self.NAMESPACES['text']
        preview = []

        rows = list(table.findall(f'{{{table_ns}}}table-row'))[:max_rows]

        for row in rows:
            row_data = []
            for cell in row.findall(f'{{{table_ns}}}table-cell'):
                # Get text from text:p elements
                text_parts = []
                for p in cell.findall(f'{{{text_ns}}}p'):
                    text_parts.append(self._get_element_text(p))
                row_data.append(''.join(text_parts))

            # Only add non-empty rows
            if any(cell.strip() for cell in row_data):
                preview.append(row_data)

        return preview


@register('.odp', name='Impress Presentation', icon='🎞️')
class OdpAnalyzer(OdfAnalyzer):
    """Analyzer for LibreOffice/OpenOffice Impress presentations (.odp)."""

    def get_structure(self, head: int = None, tail: int = None,
                      range: tuple = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Extract presentation structure: slides with titles."""
        if self.parse_error:
            return {'error': [{'message': self.parse_error}]}

        if self.content_tree is None:
            return {'error': [{'message': 'No content found'}]}

        ns = self.NAMESPACES
        office_ns = ns['office']
        draw_ns = ns['draw']
        presentation_ns = ns['presentation']

        # Find presentation body
        body = self.content_tree.find(f'.//{{{office_ns}}}body')
        if body is None:
            return {'error': [{'message': 'No document body found'}]}

        presentation = body.find(f'{{{office_ns}}}presentation')
        if presentation is None:
            return {'error': [{'message': 'No presentation found'}]}

        slides: List[Dict[str, Any]] = []

        for idx, page in enumerate(presentation.findall(f'{{{draw_ns}}}page')):
            slide_info = self._analyze_slide(page, idx + 1)
            slides.append(slide_info)

        result: Dict[str, List[Dict[str, Any]]] = {}

        if slides:
            # Format slides with details
            formatted_slides = []
            for s in slides:
                frames_info = f", {s['frames']} frames" if s.get('frames') else ''
                formatted_slides.append({
                    'name': f"[{s['slide_num']}] {s['name']}{frames_info}",
                    'line': s['line'],
                })
            formatted_slides = self._apply_semantic_slice(formatted_slides, head, tail, range)
            result['slides'] = formatted_slides

        # Media
        media = self._get_embedded_media()
        if media:
            result['media'] = [{
                'name': f"{m['name']} ({m['type']}, {self._format_size(m['size'])})",
                'line': idx + 1,
            } for idx, m in enumerate(media)]

        return result

    def _analyze_slide(self, page: ET.Element, slide_num: int) -> Dict[str, Any]:
        """Analyze a single slide."""
        ns = self.NAMESPACES
        draw_ns = ns['draw']
        presentation_ns = ns['presentation']

        # Get slide name
        slide_name = page.get(f'{{{draw_ns}}}name', f'Slide {slide_num}')

        # Count frames/shapes
        frames = list(page.findall(f'{{{draw_ns}}}frame'))

        # Try to find title
        title = slide_name
        for frame in frames:
            # Check for title frame
            frame_class = frame.get(f'{{{presentation_ns}}}class', '')
            if 'title' in frame_class.lower():
                text = self._get_element_text(frame)
                if text.strip():
                    title = text.strip()[:60]
                    if len(text.strip()) > 60:
                        title += '...'
                    break

        # Count text elements
        text_count = 0
        for elem in page.iter():
            if elem.text and elem.text.strip():
                text_count += 1

        return {
            'name': title,
            'slide_num': slide_num,
            'frames': len(frames),
            'text_elements': text_count,
            'line': slide_num,
        }

    def _get_element_text(self, elem: ET.Element) -> str:
        """Extract text from element."""
        texts = []
        if elem.text:
            texts.append(elem.text)
        for child in elem:
            texts.append(self._get_element_text(child))
            if child.tail:
                texts.append(child.tail)
        return ''.join(texts)

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a slide by number or title match."""
        if self.content_tree is None:
            return None

        ns = self.NAMESPACES
        office_ns = ns['office']
        draw_ns = ns['draw']

        body = self.content_tree.find(f'.//{{{office_ns}}}body')
        if body is None:
            return None

        presentation = body.find(f'{{{office_ns}}}presentation')
        if presentation is None:
            return None

        pages = presentation.findall(f'{{{draw_ns}}}page')

        # Try as slide number
        try:
            slide_num = int(name)
            if 1 <= slide_num <= len(pages):
                return self._extract_slide_content(pages[slide_num - 1], slide_num)
        except ValueError:
            pass

        # Search by title
        for idx, page in enumerate(pages):
            slide_info = self._analyze_slide(page, idx + 1)
            if name.lower() in slide_info['name'].lower():
                return self._extract_slide_content(page, idx + 1)

        return None

    def _extract_slide_content(self, page: ET.Element, slide_num: int) -> Dict[str, Any]:
        """Extract full content from a slide."""
        text = self._get_element_text(page).strip()
        lines = text.split('\n') if text else []

        return {
            'name': f'Slide {slide_num}',
            'line_start': slide_num,
            'line_end': slide_num + len(lines),
            'source': f"Slide {slide_num}\n{'=' * 40}\n\n{text}",
        }
