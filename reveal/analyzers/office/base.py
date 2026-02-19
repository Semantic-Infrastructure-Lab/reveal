"""Base class for ZIP-based office documents (OpenXML and ODF).

Both formats share the same fundamental structure:
- ZIP archive containing XML files
- Metadata in dedicated files
- Content in main XML file(s)
- Embedded media (images, etc.)

This base class provides shared infrastructure for both format families.
"""

import zipfile
import xml.etree.ElementTree as ET
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from ...base import FileAnalyzer
from ...utils import format_size


MAX_XML_PART_SIZE = 50 * 1024 * 1024  # 50 MB per XML part
MAX_COMPRESSION_RATIO = 1000  # Flag suspicious compression ratios


class ZipXMLAnalyzer(FileAnalyzer):
    """Base analyzer for ZIP archives containing XML documents.

    Subclasses define:
    - CONTENT_PATH: Path to main content XML within archive
    - NAMESPACES: XML namespaces used in the format
    - _parse_content(): Format-specific content parsing
    """

    CONTENT_PATH: str = ''  # Override in subclass
    NAMESPACES: Dict[str, str] = {}  # Override in subclass

    def __init__(self, path: str):
        # Don't call super().__init__ - we handle file reading differently
        self.path = Path(path)
        self.parse_error: Optional[str] = None
        self.archive: Optional[zipfile.ZipFile] = None
        self.parts: List[str] = []
        self.metadata: Dict[str, Any] = {}
        self.content_tree: Optional[ET.Element] = None

        # For compatibility with base class
        self.lines: List[str] = []
        self.content: str = ''

        self._open_archive()

    def _safe_read(self, part_path: str) -> bytes:
        """Read a part from the archive with decompressed-size guard."""
        info = self.archive.getinfo(part_path)  # type: ignore[union-attr]
        if info.file_size > MAX_XML_PART_SIZE:
            raise ValueError(
                f"Part {part_path} too large: {info.file_size} bytes (limit {MAX_XML_PART_SIZE})"
            )
        if info.compress_size > 0 and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
            raise ValueError(
                f"Part {part_path} has suspicious compression ratio "
                f"({info.file_size}/{info.compress_size}), possible zip bomb"
            )
        return self.archive.read(part_path)  # type: ignore[union-attr]

    def _open_archive(self) -> None:
        """Open ZIP archive and parse structure."""
        try:
            self.archive = zipfile.ZipFile(self.path, 'r')
            self.parts = self.archive.namelist()

            # Parse main content if available
            if self.CONTENT_PATH and self.CONTENT_PATH in self.parts:
                xml_content = self._safe_read(self.CONTENT_PATH)
                self.content_tree = ET.fromstring(xml_content)

            # Parse metadata
            self._parse_metadata()

        except zipfile.BadZipFile as e:
            self.parse_error = f"Invalid ZIP archive: {e}"
        except ET.ParseError as e:
            self.parse_error = f"Invalid XML content: {e}"
        except Exception as e:
            self.parse_error = f"Error opening document: {e}"

    @staticmethod
    def _get_xml_text(xml_tree: ET.Element, tag: str, prefix: str,
                      namespaces: Dict[str, str]) -> Optional[str]:
        """Extract text from an XML element by tag and namespace prefix."""
        ns_uri = namespaces.get(prefix, '')
        elem = xml_tree.find(f'.//{{{ns_uri}}}{tag}')
        return elem.text if elem is not None and elem.text else None

    def _parse_metadata(self) -> None:
        """Parse document metadata from core.xml (title, creator, dates)."""
        core = self._read_xml('docProps/core.xml')
        if core is None:
            return

        ns = self.NAMESPACES

        def get(tag, pfx):
            return self._get_xml_text(core, tag, pfx, ns)
        self.metadata = {k: v for k, v in {
            'title': get('title', 'dc'),
            'creator': get('creator', 'dc'),
            'created': get('created', 'dcterms'),
            'modified': get('modified', 'dcterms'),
        }.items() if v}

    def _read_xml(self, part_path: str) -> Optional[ET.Element]:
        """Read and parse an XML part from the archive."""
        if not self.archive or part_path not in self.parts:
            return None
        try:
            xml_content = self._safe_read(part_path)
            return ET.fromstring(xml_content)
        except Exception as e:
            logging.debug(f"Failed to read/parse XML part {part_path}: {e}")
            return None

    def _read_part(self, part_path: str) -> Optional[bytes]:
        """Read raw bytes from a part in the archive."""
        if not self.archive or part_path not in self.parts:
            return None
        try:
            return self._safe_read(part_path)
        except Exception as e:
            logging.debug(f"Failed to read part {part_path}: {e}")
            return None

    def _extract_text(self, element: ET.Element, text_tag: str, ns_prefix: str = '') -> str:
        """Extract all text from elements matching tag.

        Args:
            element: Root element to search
            text_tag: Tag name to find (e.g., 't' for text runs)
            ns_prefix: Namespace prefix (e.g., 'w' for Word)

        Returns:
            Concatenated text content
        """
        ns = self.NAMESPACES.get(ns_prefix, '')
        full_tag = f'{{{ns}}}{text_tag}' if ns else text_tag

        texts = []
        for text_elem in element.iter(full_tag):
            if text_elem.text:
                texts.append(text_elem.text)
        return ''.join(texts)

    def _find_elements(self, element: ET.Element, tag: str, ns_prefix: str = '') -> List[ET.Element]:
        """Find all elements matching tag with namespace.

        Args:
            element: Root element to search
            tag: Tag name to find
            ns_prefix: Namespace prefix

        Returns:
            List of matching elements
        """
        ns = self.NAMESPACES.get(ns_prefix, '')
        full_tag = f'{{{ns}}}{tag}' if ns else tag
        return list(element.iter(full_tag))

    def _get_embedded_media(self) -> List[Dict[str, Any]]:
        """Get list of embedded media files (images, etc.)."""
        if not self.archive:
            return []

        media = []
        media_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.svg', '.emf', '.wmf'}

        for part in self.parts:
            ext = Path(part).suffix.lower()
            if ext in media_extensions:
                try:
                    info = self.archive.getinfo(part)
                    media.append({
                        'path': part,
                        'name': Path(part).name,
                        'size': info.file_size,
                        'type': ext[1:].upper(),
                    })
                except Exception as e:
                    logging.debug(f"Failed to extract media info for {part}: {e}")
                    pass
        return media

    def get_metadata(self) -> Dict[str, Any]:
        """Return file metadata including document-specific info."""
        import os
        stat = os.stat(self.path)

        base_meta = {
            'path': str(self.path),
            'name': self.path.name,
            'size': stat.st_size,
            'size_human': format_size(stat.st_size),
            'parts_count': len(self.parts),
        }

        # Add document-specific metadata
        base_meta.update(self.metadata)

        return base_meta

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Return document structure. Override in subclass."""
        if self.parse_error:
            return {'error': [{'message': self.parse_error}]}
        return {}

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a specific element by name. Override in subclass for semantic extraction."""
        return None

    def __del__(self):
        """Clean up ZIP archive handle."""
        if self.archive:
            try:
                self.archive.close()
            except Exception as e:
                logging.debug(f"Failed to close archive {self.path}: {e}")
                pass
