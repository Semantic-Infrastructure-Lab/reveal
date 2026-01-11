"""GraphQL analyzer using tree-sitter."""
from typing import Dict, List, Any
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

    def _extract_types(self) -> List[Dict[str, Any]]:
        """Extract object type definitions."""
        types = []

        # Find all object type definitions
        type_defs = self._find_nodes_by_type('object_type_definition')

        for type_def in type_defs:
            name_node = None
            fields = []
            implements = []

            # Get type name
            for child in type_def.children:
                if child.type == 'name':
                    name_node = child
                    break

            if not name_node:
                continue

            name = self._get_node_text(name_node)

            # Skip Query, Mutation, Subscription (extracted separately)
            if name in ['Query', 'Mutation', 'Subscription']:
                continue

            # Get implemented interfaces
            for child in type_def.children:
                if child.type == 'implements_interfaces':
                    for iface_child in child.children:
                        if iface_child.type == 'named_type':
                            for name_child in iface_child.children:
                                if name_child.type == 'name':
                                    implements.append(self._get_node_text(name_child))

            # Get fields
            fields_def = None
            for child in type_def.children:
                if child.type == 'fields_definition':
                    fields_def = child
                    break

            if fields_def:
                for field_child in fields_def.children:
                    if field_child.type == 'field_definition':
                        field_name = None
                        for f in field_child.children:
                            if f.type == 'name':
                                field_name = self._get_node_text(f)
                                break
                        if field_name:
                            fields.append(field_name)

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

        # Find the Query/Mutation/Subscription type definition
        type_defs = self._find_nodes_by_type('object_type_definition')

        for type_def in type_defs:
            name_node = None
            for child in type_def.children:
                if child.type == 'name':
                    name_node = child
                    break

            if not name_node:
                continue

            name = self._get_node_text(name_node)

            if name != operation_type:
                continue

            # Extract fields (operations)
            fields_def = None
            for child in type_def.children:
                if child.type == 'fields_definition':
                    fields_def = child
                    break

            if not fields_def:
                continue

            for field_child in fields_def.children:
                if field_child.type == 'field_definition':
                    field_name = None
                    args = []
                    return_type = None

                    for f in field_child.children:
                        if f.type == 'name':
                            field_name = self._get_node_text(f)
                        elif f.type == 'arguments_definition':
                            # Extract argument names
                            for arg_child in f.children:
                                if arg_child.type == 'input_value_definition':
                                    for arg_part in arg_child.children:
                                        if arg_part.type == 'name':
                                            arg_name = self._get_node_text(arg_part)
                                            # Get arg type
                                            arg_type = None
                                            for type_child in arg_child.children:
                                                if type_child.type in ['type', 'non_null_type', 'list_type']:
                                                    arg_type = self._get_type_string(type_child)
                                                    break
                                            if arg_type:
                                                args.append(f"{arg_name}: {arg_type}")
                                            else:
                                                args.append(arg_name)
                                            break
                        elif f.type in ['type', 'non_null_type', 'list_type']:
                            return_type = self._get_type_string(f)

                    if field_name:
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
            name_node = None
            values = []

            for child in enum_def.children:
                if child.type == 'name':
                    name_node = child
                elif child.type == 'enum_values_definition':
                    for val_child in child.children:
                        if val_child.type == 'enum_value_definition':
                            for v in val_child.children:
                                if v.type == 'enum_value':
                                    values.append(self._get_node_text(v))

            if name_node:
                name = self._get_node_text(name_node)
                enums.append({
                    'line': enum_def.start_point[0] + 1,
                    'name': name,
                    'values': values,
                })

        return enums

    def _extract_interfaces(self) -> List[Dict[str, Any]]:
        """Extract interface type definitions."""
        interfaces = []

        iface_defs = self._find_nodes_by_type('interface_type_definition')

        for iface_def in iface_defs:
            name_node = None
            fields = []

            for child in iface_def.children:
                if child.type == 'name':
                    name_node = child
                elif child.type == 'fields_definition':
                    for field_child in child.children:
                        if field_child.type == 'field_definition':
                            for f in field_child.children:
                                if f.type == 'name':
                                    fields.append(self._get_node_text(f))
                                    break

            if name_node:
                name = self._get_node_text(name_node)
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
            name_node = None
            members = []

            for child in union_def.children:
                if child.type == 'name':
                    name_node = child
                elif child.type == 'union_member_types':
                    for member_child in child.children:
                        if member_child.type == 'named_type':
                            for m in member_child.children:
                                if m.type == 'name':
                                    members.append(self._get_node_text(m))

            if name_node:
                name = self._get_node_text(name_node)
                unions.append({
                    'line': union_def.start_point[0] + 1,
                    'name': name,
                    'members': members,
                })

        return unions

    def _extract_scalars(self) -> List[Dict[str, Any]]:
        """Extract custom scalar type definitions."""
        scalars = []

        scalar_defs = self._find_nodes_by_type('scalar_type_definition')

        for scalar_def in scalar_defs:
            for child in scalar_def.children:
                if child.type == 'name':
                    name = self._get_node_text(child)
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
            name_node = None
            fields = []

            for child in input_def.children:
                if child.type == 'name':
                    name_node = child
                elif child.type == 'input_fields_definition':
                    for field_child in child.children:
                        if field_child.type == 'input_value_definition':
                            for f in field_child.children:
                                if f.type == 'name':
                                    fields.append(self._get_node_text(f))
                                    break

            if name_node:
                name = self._get_node_text(name_node)
                inputs.append({
                    'line': input_def.start_point[0] + 1,
                    'name': name,
                    'fields': fields,
                })

        return inputs

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
