"""XML file analyzer.

Handles XML configuration and data files.
Common uses: Maven pom.xml, Spring configs, Android manifests, SOAP APIs.
"""

import xml.etree.ElementTree as ET
import logging
from typing import Dict, Any, Optional
from ..base import FileAnalyzer
from ..registry import register

logger = logging.getLogger(__name__)


@register('.xml', name='XML', icon='📄')
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
            filtered_children = children
            if head is not None:
                filtered_children = children[:head]
            elif tail is not None:
                filtered_children = children[-tail:]
            elif range is not None:
                start, end = range
                filtered_children = children[start-1:end]
            elif child_count > 10:
                # Default: show first 10 children if more than 10
                filtered_children = children[:10]

            # Convert root and children to dict
            root_data: Dict[str, Any] = {
                'tag': self._strip_namespace(root.tag),
                'namespace': self._get_namespace(root.tag),
            }

            if root.attrib:
                root_data['attributes'] = dict(root.attrib)

            result = {
                'contract_version': '1.0',
                'type': 'xml_structure',
                'source': str(self.path),
                'source_type': 'file',
                'root': root_data,
                'statistics': {
                    'total_elements': total_elements,
                    'max_depth': max_depth,
                    'child_count': child_count,
                    'namespace_count': len(namespaces)
                },
                'children': [self._element_to_dict(child) for child in filtered_children]
            }

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
            return {
                'error': f'XML parse error: {e}',
                'message': 'Failed to parse XML file'
            }
        except Exception as e:
            logger.debug(f"Error analyzing XML {self.path}: {e}")
            return {
                'error': str(e),
                'message': 'Failed to analyze XML file'
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
