"""XML file analyzer.

Handles XML configuration and data files.
Common uses: Maven pom.xml, Spring configs, Android manifests, SOAP APIs.
"""

import xml.etree.ElementTree as ET
import xml.parsers.expat
import logging
from typing import Dict, Any, List, Optional, Tuple
from ..base import FileAnalyzer
from ..registry import register
from ..utils.results import ResultBuilder
from reveal.reveal_types import CONTRACT_VERSION

logger = logging.getLogger(__name__)


def _filter_xml_children(
    children: List[Any],
    head: Optional[int],
    tail: Optional[int],
    range: Optional[Tuple[int, int]],
    child_count: int,
) -> List[Any]:
    """Apply head/tail/range filtering to a list of XML children."""
    if head is not None:
        return children[:head]
    if tail is not None:
        return children[-tail:]
    if range is not None:
        start, end = range
        return children[start-1:end]
    if child_count > 10:
        return children[:10]
    return children


@register('.xml', name='XML', icon='📄', category='data')
class XmlAnalyzer(FileAnalyzer):
    """XML file analyzer.

    Analyzes XML configuration and data files with hierarchical structure.
    Common uses: Maven pom.xml, Spring configs, Android manifests, SOAP APIs, SVG images.

    Structure view shows:
    - Root element with namespace
    - Document statistics (element count, max depth, namespaces)
    - Top-level child elements with attributes and text preview
    - Filtering options (head, tail, range)

    Extract by element name or path to view specific elements.
    """

    def _strip_namespace(self, tag: str) -> str:
        """Remove namespace prefix from tag name.

        Args:
            tag: Element tag (may include namespace like {http://...}tag)

        Returns:
            Tag name without namespace
        """
        if '}' in tag:
            return tag.split('}', 1)[1]
        return tag

    def _get_namespace(self, tag: str) -> Optional[str]:
        """Extract namespace URI from tag.

        Args:
            tag: Element tag

        Returns:
            Namespace URI or None
        """
        if tag.startswith('{') and '}' in tag:
            return tag[1:tag.index('}')]
        return None

    def _infer_type(self, value: str) -> str:
        """Infer value type from string representation.

        Args:
            value: String value

        Returns:
            Type name: 'integer', 'float', 'boolean', 'string', 'empty'
        """
        if not value or not value.strip():
            return 'empty'

        value = value.strip()

        # Try boolean
        if value.lower() in ('true', 'false', 'yes', 'no', '1', '0'):
            return 'boolean'

        # Try integer
        try:
            int(value)
            return 'integer'
        except ValueError:
            pass

        # Try float
        try:
            float(value)
            return 'float'
        except ValueError:
            pass

        return 'string'

    def _count_elements(self, element: ET.Element) -> int:
        """Count total elements in tree recursively.

        Args:
            element: Root element

        Returns:
            Total element count including root
        """
        return 1 + sum(self._count_elements(child) for child in element)

    def _max_depth(self, element: ET.Element, current_depth: int = 0) -> int:
        """Calculate maximum depth of XML tree.

        Args:
            element: Root element
            current_depth: Current depth level

        Returns:
            Maximum depth
        """
        if not list(element):
            return current_depth

        return max(self._max_depth(child, current_depth + 1) for child in element)

    def _collect_namespaces(self, element: ET.Element) -> Dict[str, int]:
        """Collect all unique namespaces in document.

        Args:
            element: Root element

        Returns:
            Dict mapping namespace URI to usage count
        """
        namespaces: Dict[str, int] = {}

        def visit(elem: ET.Element):
            ns = self._get_namespace(elem.tag)
            if ns:
                namespaces[ns] = namespaces.get(ns, 0) + 1

            for child in elem:
                visit(child)

        visit(element)
        return namespaces

    def _element_to_dict(self, element: ET.Element, include_children: bool = True) -> Dict[str, Any]:
        """Convert XML element to dictionary representation.

        Args:
            element: XML element
            include_children: Whether to include child elements

        Returns:
            Dict with element data
        """
        result: Dict[str, Any] = {
            'tag': self._strip_namespace(element.tag),
            'namespace': self._get_namespace(element.tag),
        }

        # Add attributes
        if element.attrib:
            result['attributes'] = dict(element.attrib)

        # Add text content
        text = (element.text or '').strip()
        if text:
            result['text'] = text
            result['text_type'] = self._infer_type(text)

        # Add child elements
        if include_children:
            children = list(element)
            if children:
                result['child_count'] = len(children)
                result['children'] = [
                    self._element_to_dict(child, include_children=False)
                    for child in children
                ]

        return result

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, Any]:
        """Extract XML document structure.

        Args:
            head: Show first N top-level children
            tail: Show last N top-level children
            range: Show children in range (start, end) - 1-indexed
            **kwargs: Additional parameters (unused)

        Returns:
            Dict with document structure and statistics
        """
        try:
            # Parse XML
            root = ET.fromstring(self.content)

            # Collect statistics
            total_elements = self._count_elements(root)
            max_depth = self._max_depth(root)
            namespaces = self._collect_namespaces(root)

            # Get top-level children
            children = list(root)
            child_count = len(children)

            # Apply filtering if requested
            filtered_children = _filter_xml_children(children, head, tail, range, child_count)

            # Convert root and children to dict
            root_data: Dict[str, Any] = {
                'tag': self._strip_namespace(root.tag),
                'namespace': self._get_namespace(root.tag),
            }

            if root.attrib:
                root_data['attributes'] = dict(root.attrib)

            result = ResultBuilder.create(
                result_type='xml_structure',
                source=self.path,
                data={
                    'root': root_data,
                    'statistics': {
                        'total_elements': total_elements,
                        'max_depth': max_depth,
                        'child_count': child_count,
                        'namespace_count': len(namespaces)
                    },
                    'children': [self._element_to_dict(child) for child in filtered_children]
                },
                contract_version=CONTRACT_VERSION,
                confidence=1.0,
            )

            # Add namespace info if present
            if namespaces:
                result['namespaces'] = [
                    {'uri': uri, 'usage_count': count}
                    for uri, count in sorted(namespaces.items(), key=lambda x: x[1], reverse=True)
                ]

            # Add filtering info if applied
            if filtered_children != children:
                result['filtered'] = {
                    'showing': len(filtered_children),
                    'total': child_count
                }

            return result

        except ET.ParseError as e:
            logger.debug(f"Error parsing XML {self.path}: {e}")
            return ResultBuilder.create_error(
                result_type='xml_structure',
                source=self.path,
                error=f'XML parse error: {e}',
                contract_version=CONTRACT_VERSION,
                message='Failed to parse XML file',
                _has_errors=True,
            )
        except Exception as e:
            logger.debug(f"Error analyzing XML {self.path}: {e}")
            return ResultBuilder.create_error(
                result_type='xml_structure',
                source=self.path,
                error=str(e),
                contract_version=CONTRACT_VERSION,
                message='Failed to analyze XML file',
            )

    def _element_spans(self) -> List[Tuple[str, int, int]]:
        """(tag, first line, last line) of every element, in document order.

        ElementTree keeps no positions; expat reports the current line in
        both the start and the end handler, which is exactly the span.
        """
        spans: List[List[Any]] = []
        open_elements: List[int] = []
        parser = xml.parsers.expat.ParserCreate()

        def start(tag, _attrs):
            open_elements.append(len(spans))
            spans.append([tag, parser.CurrentLineNumber, parser.CurrentLineNumber])

        def end(_tag):
            spans[open_elements.pop()][2] = parser.CurrentLineNumber

        parser.StartElementHandler = start
        parser.EndElementHandler = end
        try:
            parser.Parse(self.content, True)
        except xml.parsers.expat.ExpatError:
            return []
        return [(tag, first, last) for tag, first, last in spans]

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Every element with this tag, as its source (BACK-1411).

        `reveal pom.xml dependencies` used to be "not found": the tag lookup
        in get_element() has no line numbers and the CLI only reaches it for
        a bare integer. A prefixed tag answers to its local name too
        (`element` finds `xs:element`), as the outline shows it.
        """
        matches = [(first, last) for tag, first, last in self._element_spans()
                   if name in (tag, tag.rsplit(':', 1)[-1])]
        if not matches:
            return None
        shown = matches[:10]
        sections = [
            {'line_start': first, 'line_end': last, 'source': '\n'.join(self.lines[first - 1:last])}
            for first, last in shown
        ]
        if len(matches) == 1:
            return {'name': name, **sections[0]}
        more = f", first {len(shown)} shown" if len(matches) > len(shown) else ""
        return {
            'name': f'{name} ({len(matches)} elements{more})',
            'line_start': shown[0][0],
            'line_end': shown[-1][1],
            'source': '\n\n'.join(section['source'] for section in sections),
            'sections': sections,
        }

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get specific element(s) by tag name.

        Args:
            element_name: Tag name to search for (without namespace prefix)
            **kwargs: Additional parameters (unused)

        Returns:
            Dict with matching elements or None if not found
        """
        try:
            root = ET.fromstring(self.content)

            # Search for all elements with matching tag
            matches = []

            def find_elements(elem: ET.Element, path: str = ""):
                tag = self._strip_namespace(elem.tag)
                current_path = f"{path}/{tag}" if path else tag

                if tag == element_name:
                    match = self._element_to_dict(elem)
                    match['path'] = current_path
                    matches.append(match)

                for child in elem:
                    find_elements(child, current_path)

            find_elements(root)

            if not matches:
                return None

            return {
                'tag': element_name,
                'match_count': len(matches),
                'matches': matches
            }

        except ET.ParseError:
            return None
        except Exception as e:
            logger.debug(f"Error extracting element {element_name} from {self.path}: {e}")
            return None
