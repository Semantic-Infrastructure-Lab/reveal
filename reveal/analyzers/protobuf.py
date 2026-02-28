"""Protocol Buffers analyzer using tree-sitter."""
from typing import Dict, List, Any, Optional, Tuple
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.proto', name='Protocol Buffers', icon='📦')
class ProtobufAnalyzer(TreeSitterAnalyzer):
    """Protocol Buffers (.proto) file analyzer.

    Supports both proto2 and proto3 syntax for gRPC service definitions
    and message schemas.
    """
    language = 'proto'

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Extract Protocol Buffers structure."""
        if not self.tree:
            return {}

        structure = {}

        # Extract package info
        package = self._extract_package()
        if package:
            structure['package'] = [package]

        # Extract schema elements
        services_data = self._extract_services()
        structure['services'] = [{'line_start': s['line_start'], 'name': s['name']} for s in services_data]

        # Extract RPCs as separate category
        rpcs = []
        for service in services_data:
            for rpc in service.get('rpcs', []):
                rpcs.append(rpc)
        if rpcs:
            structure['rpcs'] = rpcs

        structure['messages'] = self._extract_messages()
        structure['enums'] = self._extract_enums()

        # Apply semantic slicing to each category
        if head or tail or range:
            for category in structure:
                if category != 'package':  # Don't slice package (only one)
                    structure[category] = self._apply_semantic_slice(
                        structure[category], head, tail, range
                    )

        # Remove empty categories and add output contract fields
        return {
            'contract_version': '1.0',
            'type': 'protobuf_structure',
            'source': str(self.path),
            'source_type': 'file',
            **{k: v for k, v in structure.items() if v},
        }

    def _extract_package(self) -> Optional[Dict[str, Any]]:
        """Extract package declaration."""
        package_nodes = self._find_nodes_by_type('package')

        for pkg_node in package_nodes:
            for child in pkg_node.children:
                if child.type == 'full_ident':
                    package_name = self._get_node_text(child)
                    return {
                        'line_start': pkg_node.start_point[0] + 1,
                        'name': package_name,
                    }

        return None

    def _extract_services(self) -> List[Dict[str, Any]]:
        """Extract gRPC service definitions."""
        services = []
        service_nodes = self._find_nodes_by_type('service')

        for service_node in service_nodes:
            service_name = self._get_service_name(service_node)
            if not service_name:
                continue

            rpcs = self._extract_service_rpcs(service_node)
            services.append({
                'line_start': service_node.start_point[0] + 1,
                'name': service_name,
                'rpcs': rpcs,
            })

        return services

    def _get_service_name(self, service_node: Any) -> Optional[str]:
        """Extract service name from service node."""
        for child in service_node.children:
            if child.type == 'service_name':
                for name_child in child.children:
                    if name_child.type == 'identifier':
                        return self._get_node_text(name_child)
        return None

    def _extract_service_rpcs(self, service_node: Any) -> List[Dict[str, Any]]:
        """Extract all RPC methods from a service node."""
        rpcs = []
        rpc_nodes = self._find_nodes_in_subtree(service_node, 'rpc')

        for rpc_node in rpc_nodes:
            rpc_data = self._extract_single_rpc(rpc_node)
            if rpc_data:
                rpcs.append(rpc_data)

        return rpcs

    def _extract_single_rpc(self, rpc_node: Any) -> Optional[Dict[str, Any]]:
        """Extract details of a single RPC method."""
        rpc_name = self._get_rpc_name(rpc_node)
        request_type, response_type = self._get_rpc_types(rpc_node)
        is_streaming_request, is_streaming_response = self._get_rpc_streaming(rpc_node)

        if not (rpc_name and request_type and response_type):
            return None

        signature = self._build_rpc_signature(
            rpc_name, request_type, response_type,
            is_streaming_request, is_streaming_response
        )

        return {
            'name': rpc_name,
            'signature': signature,
            'line_start': rpc_node.start_point[0] + 1,
        }

    def _get_rpc_name(self, rpc_node: Any) -> Optional[str]:
        """Extract RPC method name."""
        for child in rpc_node.children:
            if child.type == 'rpc_name':
                for name_child in child.children:
                    if name_child.type == 'identifier':
                        return self._get_node_text(name_child)
        return None

    def _get_rpc_types(self, rpc_node: Any) -> Tuple[Optional[str], Optional[str]]:
        """Extract request and response types from RPC node."""
        request_type = None
        response_type = None

        for child in rpc_node.children:
            if child.type == 'message_or_enum_type':
                if request_type is None:
                    # First occurrence is request type
                    for type_child in child.children:
                        if type_child.type == 'identifier':
                            request_type = self._get_node_text(type_child)
                            break
                else:
                    # Second occurrence is response type
                    for type_child in child.children:
                        if type_child.type == 'identifier':
                            response_type = self._get_node_text(type_child)
                            break

        return request_type, response_type

    def _get_rpc_streaming(self, rpc_node: Any) -> Tuple[bool, bool]:
        """Determine if RPC uses streaming for request/response."""
        is_streaming_request = False
        is_streaming_response = False

        # Find returns position for reference
        returns_pos = None
        for child in rpc_node.children:
            if child.type == 'returns':
                returns_pos = child.start_point[0]
                break

        # Check each stream keyword position
        for child in rpc_node.children:
            if child.type == 'stream':
                stream_pos = child.start_point[0]
                if returns_pos is None or stream_pos < returns_pos:
                    is_streaming_request = True
                else:
                    is_streaming_response = True

        return is_streaming_request, is_streaming_response

    def _build_rpc_signature(self, rpc_name: str, request_type: str, response_type: str,
                            is_streaming_request: bool, is_streaming_response: bool) -> str:
        """Build RPC signature string."""
        req = f"stream {request_type}" if is_streaming_request else request_type
        resp = f"stream {response_type}" if is_streaming_response else response_type
        return f"{rpc_name}({req}) returns ({resp})"

    def _extract_messages(self) -> List[Dict[str, Any]]:
        """Extract message definitions."""
        messages = []
        for msg_node in self._find_nodes_by_type('message'):
            message_name = self._get_message_name(msg_node)
            if not message_name:
                continue
            fields = [
                info
                for field_node in self._find_nodes_in_subtree(msg_node, 'field')
                if (info := self._format_field_info(field_node)) is not None
            ]
            messages.append({
                'line_start': msg_node.start_point[0] + 1,
                'name': message_name,
                'fields': fields,
            })
        return messages

    def _get_message_name(self, msg_node: Any) -> Optional[str]:
        """Extract identifier string from a message node's message_name child."""
        for child in msg_node.children:
            if child.type == 'message_name':
                for name_child in child.children:
                    if name_child.type == 'identifier':
                        return self._get_node_text(name_child)
        return None

    def _format_field_info(self, field_node: Any) -> Optional[str]:
        """Build a display string for a protobuf field node, or None if unnamed."""
        field_type = field_name = field_number = None
        for child in field_node.children:
            if child.type == 'type':
                field_type = self._get_node_text(child)
            elif child.type == 'identifier':
                field_name = self._get_node_text(child)
            elif child.type == 'field_number':
                field_number = self._get_node_text(child)
        if not field_name:
            return None
        info = f"{field_type} {field_name}" if field_type else field_name
        if field_number:
            info += f" = {field_number}"
        return info

    def _get_enum_name(self, enum_node: Any) -> Optional[str]:
        """Extract name string from an enum node."""
        for child in enum_node.children:
            if child.type == 'enum_name':
                for name_child in child.children:
                    if name_child.type == 'identifier':
                        return self._get_node_text(name_child)
        return None

    def _get_enum_field_value(self, enum_field: Any) -> Optional[str]:
        """Build 'name = number' string from an enum_field node."""
        value_name = None
        value_number = None
        for field_child in enum_field.children:
            if field_child.type == 'identifier':
                value_name = self._get_node_text(field_child)
            elif field_child.type == 'int_lit':
                value_number = self._get_node_text(field_child)
        if not value_name:
            return None
        return f"{value_name} = {value_number}" if value_number else value_name

    def _get_enum_body_values(self, enum_node: Any) -> List[str]:
        """Extract all value strings from an enum node's body."""
        values = []
        for child in enum_node.children:
            if child.type == 'enum_body':
                for body_child in child.children:
                    if body_child.type == 'enum_field':
                        val = self._get_enum_field_value(body_child)
                        if val:
                            values.append(val)
        return values

    def _extract_enums(self) -> List[Dict[str, Any]]:
        """Extract enum definitions."""
        enums = []
        for enum_node in self._find_nodes_by_type('enum'):
            enum_name = self._get_enum_name(enum_node)
            if not enum_name:
                continue
            enums.append({
                'line_start': enum_node.start_point[0] + 1,
                'name': enum_name,
                'values': self._get_enum_body_values(enum_node),
            })
        return enums

    def _find_nodes_in_subtree(self, root_node: Any, node_type: str) -> List[Any]:
        """Find all nodes of a specific type within a subtree."""
        nodes = []

        def walk(node):
            if node.type == node_type:
                nodes.append(node)
            for child in node.children:
                walk(child)

        walk(root_node)
        return nodes
