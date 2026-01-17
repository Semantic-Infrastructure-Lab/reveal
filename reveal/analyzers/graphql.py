"""GraphQL analyzer using tree-sitter."""
from typing import Dict, List, Any, Optional, Tuple
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.graphql', '.gql', name='GraphQL', icon='🔷')
class GraphQLAnalyzer(TreeSitterAnalyzer):
    """GraphQL schema and query language analyzer.

    Supports GraphQL schema definitions (.graphql)
    and GraphQL query files (.gql).
    """
    language = 'graphql'

    def get_structure(self, head: int = None, tail: int = None,
                      range: tuple = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Extract GraphQL schema structure."""
        if not self.tree:
            return {}

        structure = {}

        # Extract schema elements
        structure['types'] = self._extract_types()
        structure['queries'] = self._extract_operations('Query')
        structure['mutations'] = self._extract_operations('Mutation')
        structure['subscriptions'] = self._extract_operations('Subscription')
        structure['enums'] = self._extract_enums()
        structure['interfaces'] = self._extract_interfaces()
        structure['unions'] = self._extract_unions()
        structure['scalars'] = self._extract_scalars()
        structure['inputs'] = self._extract_input_types()

        # Apply semantic slicing to each category
        if head or tail or range:
            for category in structure:
                structure[category] = self._apply_semantic_slice(
                    structure[category], head, tail, range
                )

        # Remove empty categories
        return {k: v for k, v in structure.items() if v}

    def _get_name_from_node(self, node) -> Optional[str]:
        """Extract name from a node's children.

        Args:
            node: Tree-sitter node to extract name from

        Returns:
            Name as string, or None if no name found
        """
        for child in node.children:
            if child.type == 'name':
                return self._get_node_text(child)
        return None

    def _get_fields_definition(self, node) -> Optional[Any]:
        """Get fields_definition child node.

        Args:
            node: Parent node to search

        Returns:
            fields_definition node or None
        """
        for child in node.children:
            if child.type == 'fields_definition':
                return child
        return None

    def _extract_field_names(self, fields_def) -> List[str]:
        """Extract field names from fields_definition node.

        Args:
            fields_def: fields_definition node

        Returns:
            List of field names
        """
        fields = []
        for field_child in fields_def.children:
            if field_child.type == 'field_definition':
                field_name = self._get_name_from_node(field_child)
                if field_name:
                    fields.append(field_name)
        return fields

    def _extract_implements(self, type_def) -> List[str]:
        """Extract implemented interfaces from type definition.

        Args:
            type_def: object_type_definition node

        Returns:
            List of interface names
        """
        implements = []
        for child in type_def.children:
            if child.type == 'implements_interfaces':
                for iface_child in child.children:
                    if iface_child.type == 'named_type':
                        iface_name = self._get_name_from_node(iface_child)
                        if iface_name:
                            implements.append(iface_name)
        return implements

    def _extract_arguments(self, args_def_node) -> List[str]:
        """Extract arguments from arguments_definition node.

        Args:
            args_def_node: arguments_definition node

        Returns:
            List of argument strings (e.g., ["id: ID!", "name: String"])
        """
        args = []
        for arg_child in args_def_node.children:
            if arg_child.type == 'input_value_definition':
                arg_name = self._get_name_from_node(arg_child)
                if arg_name:
                    # Get argument type
                    arg_type = self._get_field_type(arg_child)
                    if arg_type:
                        args.append(f"{arg_name}: {arg_type}")
                    else:
                        args.append(arg_name)
        return args

    def _get_field_type(self, field_node) -> Optional[str]:
        """Get the return type from a field node.

        Args:
            field_node: field_definition or input_value_definition node

        Returns:
            Type string (e.g., "User!", "[Post!]") or None
        """
        for child in field_node.children:
            if child.type in ['type', 'non_null_type', 'list_type']:
                return self._get_type_string(child)
        return None

    def _extract_field_info(self, field_node) -> Tuple[Optional[str], List[str], Optional[str]]:
        """Extract name, arguments, and return type from field_definition.

        Args:
            field_node: field_definition node

        Returns:
            Tuple of (field_name, arguments, return_type)
        """
        field_name = None
        args = []
        return_type = None

        for child in field_node.children:
            if child.type == 'name':
                field_name = self._get_node_text(child)
            elif child.type == 'arguments_definition':
                args = self._extract_arguments(child)
            elif child.type in ['type', 'non_null_type', 'list_type']:
                return_type = self._get_type_string(child)

        return field_name, args, return_type

    def _extract_types(self) -> List[Dict[str, Any]]:
        """Extract object type definitions."""
        types = []
        type_defs = self._find_nodes_by_type('object_type_definition')

        for type_def in type_defs:
            name = self._get_name_from_node(type_def)
            if not name:
                continue

            # Skip Query, Mutation, Subscription (extracted separately)
            if name in ['Query', 'Mutation', 'Subscription']:
                continue

            # Get implemented interfaces
            implements = self._extract_implements(type_def)

            # Get fields
            fields_def = self._get_fields_definition(type_def)
            fields = self._extract_field_names(fields_def) if fields_def else []

            type_info = {
                'line': type_def.start_point[0] + 1,
                'name': name,
                'fields': fields,
            }

            if implements:
                type_info['implements'] = ', '.join(implements)

            types.append(type_info)

        return types

    def _extract_operations(self, operation_type: str) -> List[Dict[str, Any]]:
        """Extract Query, Mutation, or Subscription operations."""
        operations = []
        type_defs = self._find_nodes_by_type('object_type_definition')

        for type_def in type_defs:
            name = self._get_name_from_node(type_def)
            if name != operation_type:
                continue

            # Extract fields (operations)
            fields_def = self._get_fields_definition(type_def)
            if not fields_def:
                continue

            for field_child in fields_def.children:
                if field_child.type == 'field_definition':
                    field_name, args, return_type = self._extract_field_info(field_child)

                    if field_name:
                        # Build signature
                        if args:
                            signature = f"{field_name}({', '.join(args)})"
                        else:
                            signature = field_name

                        if return_type:
                            signature += f": {return_type}"

                        operations.append({
                            'line': field_child.start_point[0] + 1,
                            'name': field_name,
                            'signature': signature,
                        })

        return operations

    def _extract_enums(self) -> List[Dict[str, Any]]:
        """Extract enum type definitions."""
        enums = []
        enum_defs = self._find_nodes_by_type('enum_type_definition')

        for enum_def in enum_defs:
            name = self._get_name_from_node(enum_def)
            if not name:
                continue

            values = []
            for child in enum_def.children:
                if child.type == 'enum_values_definition':
                    values = self._extract_enum_values(child)

            enums.append({
                'line': enum_def.start_point[0] + 1,
                'name': name,
                'values': values,
            })

        return enums

    def _extract_enum_values(self, enum_values_def) -> List[str]:
        """Extract enum values from enum_values_definition node.

        Args:
            enum_values_def: enum_values_definition node

        Returns:
            List of enum value names
        """
        values = []
        for val_child in enum_values_def.children:
            if val_child.type == 'enum_value_definition':
                for v in val_child.children:
                    if v.type == 'enum_value':
                        values.append(self._get_node_text(v))
        return values

    def _extract_interfaces(self) -> List[Dict[str, Any]]:
        """Extract interface type definitions."""
        interfaces = []
        iface_defs = self._find_nodes_by_type('interface_type_definition')

        for iface_def in iface_defs:
            name = self._get_name_from_node(iface_def)
            if not name:
                continue

            fields_def = self._get_fields_definition(iface_def)
            fields = self._extract_field_names(fields_def) if fields_def else []

            interfaces.append({
                'line': iface_def.start_point[0] + 1,
                'name': name,
                'fields': fields,
            })

        return interfaces

    def _extract_unions(self) -> List[Dict[str, Any]]:
        """Extract union type definitions."""
        unions = []
        union_defs = self._find_nodes_by_type('union_type_definition')

        for union_def in union_defs:
            name = self._get_name_from_node(union_def)
            if not name:
                continue

            members = []
            for child in union_def.children:
                if child.type == 'union_member_types':
                    members = self._extract_union_members(child)

            unions.append({
                'line': union_def.start_point[0] + 1,
                'name': name,
                'members': members,
            })

        return unions

    def _extract_union_members(self, union_member_types) -> List[str]:
        """Extract union member types.

        Args:
            union_member_types: union_member_types node

        Returns:
            List of member type names
        """
        members = []
        for member_child in union_member_types.children:
            if member_child.type == 'named_type':
                member_name = self._get_name_from_node(member_child)
                if member_name:
                    members.append(member_name)
        return members

    def _extract_scalars(self) -> List[Dict[str, Any]]:
        """Extract custom scalar type definitions."""
        scalars = []
        scalar_defs = self._find_nodes_by_type('scalar_type_definition')

        for scalar_def in scalar_defs:
            name = self._get_name_from_node(scalar_def)
            if name:
                scalars.append({
                    'line': scalar_def.start_point[0] + 1,
                    'name': name,
                })

        return scalars

    def _extract_input_types(self) -> List[Dict[str, Any]]:
        """Extract input object type definitions."""
        inputs = []
        input_defs = self._find_nodes_by_type('input_object_type_definition')

        for input_def in input_defs:
            name = self._get_name_from_node(input_def)
            if not name:
                continue

            fields = []
            for child in input_def.children:
                if child.type == 'input_fields_definition':
                    fields = self._extract_input_field_names(child)

            inputs.append({
                'line': input_def.start_point[0] + 1,
                'name': name,
                'fields': fields,
            })

        return inputs

    def _extract_input_field_names(self, input_fields_def) -> List[str]:
        """Extract field names from input_fields_definition node.

        Args:
            input_fields_def: input_fields_definition node

        Returns:
            List of field names
        """
        fields = []
        for field_child in input_fields_def.children:
            if field_child.type == 'input_value_definition':
                field_name = self._get_name_from_node(field_child)
                if field_name:
                    fields.append(field_name)
        return fields

    def _get_type_string(self, type_node) -> str:
        """Convert a type node to a string representation."""
        if type_node.type == 'non_null_type':
            # Get the inner type and add !
            for child in type_node.children:
                if child.type in ['named_type', 'list_type']:
                    return self._get_type_string(child) + '!'
            return self._get_node_text(type_node)
        elif type_node.type == 'list_type':
            # Get the inner type and wrap in []
            for child in type_node.children:
                if child.type in ['type', 'named_type', 'non_null_type']:
                    return '[' + self._get_type_string(child) + ']'
            return self._get_node_text(type_node)
        elif type_node.type == 'named_type':
            # Get the name
            for child in type_node.children:
                if child.type == 'name':
                    return self._get_node_text(child)
        elif type_node.type == 'type':
            # Recurse into type wrapper
            for child in type_node.children:
                if child.type in ['named_type', 'list_type', 'non_null_type']:
                    return self._get_type_string(child)

        return self._get_node_text(type_node)
