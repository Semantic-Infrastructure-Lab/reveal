"""Value introspection and type analysis for JSON adapter."""

import json
import re
from pathlib import Path
from typing import Any, Dict, List


def get_type_str(value: Any) -> str:
    """Get human-readable type string for a value.

    Args:
        value: JSON value to analyze

    Returns:
        Human-readable type string
    """
    if value is None:
        return 'null'
    elif isinstance(value, bool):
        return 'bool'
    elif isinstance(value, int):
        return 'int'
    elif isinstance(value, float):
        return 'float'
    elif isinstance(value, str):
        return 'str'
    elif isinstance(value, list):
        if not value:
            return 'Array[empty]'
        # Infer element type from first few elements
        types = set(get_type_str(v) for v in value[:5])
        if len(types) == 1:
            return f'Array[{types.pop()}]'
        return f'Array[mixed: {", ".join(sorted(types))}]'
    elif isinstance(value, dict):
        return f'Object[{len(value)} keys]'
    return type(value).__name__


def infer_schema(value: Any, max_depth: int = 4, depth: int = 0) -> Any:
    """Recursively infer schema from value.

    Args:
        value: JSON value to analyze
        max_depth: Maximum recursion depth
        depth: Current depth

    Returns:
        Inferred schema structure
    """
    if depth > max_depth:
        return '...'

    if value is None:
        return 'null'
    elif isinstance(value, bool):
        return 'bool'
    elif isinstance(value, int):
        return 'int'
    elif isinstance(value, float):
        return 'float'
    elif isinstance(value, str):
        return 'str'
    elif isinstance(value, list):
        if not value:
            return 'Array[empty]'
        # Sample first few elements to infer schema
        sample = value[:3]
        schemas = [infer_schema(v, max_depth, depth + 1) for v in sample]
        # Check if all same type
        if all(s == schemas[0] for s in schemas):
            return f'Array[{schemas[0]}]' if isinstance(schemas[0], str) else {'Array': schemas[0]}
        return {'Array': schemas[0]}  # Use first as representative
    elif isinstance(value, dict):
        return {k: infer_schema(v, max_depth, depth + 1) for k, v in value.items()}
    return type(value).__name__


def flatten_value(value: Any, base_path: str = 'json') -> List[str]:
    """Generate flattened (gron-style) output for grep-able searching.

    Args:
        value: JSON value to flatten
        base_path: Base path for flattened output

    Returns:
        List of flattened assignment strings
    """
    lines: List[str] = []
    _flatten_recursive(value, base_path, lines)
    return lines


def _flatten_recursive(value: Any, path: str, lines: List[str]) -> None:
    """Recursively flatten JSON to assignment format.

    Args:
        value: Current value to flatten
        path: Current path string
        lines: List to append flattened lines to
    """
    if isinstance(value, dict):
        if not value:
            lines.append(f'{path} = {{}}')
        else:
            lines.append(f'{path} = {{}}')
            for k, v in value.items():
                # Use dot notation for simple keys, bracket for complex
                if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', k):
                    _flatten_recursive(v, f'{path}.{k}', lines)
                else:
                    _flatten_recursive(v, f'{path}["{k}"]', lines)
    elif isinstance(value, list):
        lines.append(f'{path} = []')
        for i, v in enumerate(value):
            _flatten_recursive(v, f'{path}[{i}]', lines)
    elif isinstance(value, str):
        lines.append(f'{path} = {json.dumps(value)}')
    elif isinstance(value, bool):
        lines.append(f'{path} = {str(value).lower()}')
    elif value is None:
        lines.append(f'{path} = null')
    else:
        lines.append(f'{path} = {value}')


def get_schema_result(value: Any, file_path: Path, json_path: List[str | int], max_depth: int = 4) -> Dict[str, Any]:
    """Generate schema/type structure result for value.

    Args:
        value: JSON value to analyze
        file_path: Source file path
        json_path: JSON navigation path
        max_depth: Maximum recursion depth

    Returns:
        Schema result dict
    """
    schema = infer_schema(value, max_depth)
    return {
        'contract_version': '1.0',
        'type': 'json_schema',
        'source': str(file_path),
        'source_type': 'file',
        'file': str(file_path),
        'path': '/'.join(str(p) for p in json_path) if json_path else '(root)',
        'schema': schema
    }


def get_flatten_result(value: Any, file_path: Path, json_path: List[str | int]) -> Dict[str, Any]:
    """Generate flattened (gron-style) output result.

    Args:
        value: JSON value to flatten
        file_path: Source file path
        json_path: JSON navigation path

    Returns:
        Flatten result dict
    """
    lines = flatten_value(value, 'json')
    return {
        'contract_version': '1.0',
        'type': 'json_flatten',
        'source': str(file_path),
        'source_type': 'file',
        'file': str(file_path),
        'path': '/'.join(str(p) for p in json_path) if json_path else '(root)',
        'lines': lines,
        'line_count': len(lines)
    }


def get_type_info_result(value: Any, file_path: Path, json_path: List[str | int]) -> Dict[str, Any]:
    """Get type information result for value at path.

    Args:
        value: JSON value to analyze
        file_path: Source file path
        json_path: JSON navigation path

    Returns:
        Type info result dict
    """
    return {
        'contract_version': '1.0',
        'type': 'json_type',
        'source': str(file_path),
        'source_type': 'file',
        'file': str(file_path),
        'path': '/'.join(str(p) for p in json_path) if json_path else '(root)',
        'value_type': get_type_str(value),
        'is_container': isinstance(value, (dict, list)),
        'length': len(value) if isinstance(value, (dict, list, str)) else None
    }


def get_keys_result(value: Any, file_path: Path, json_path: List[str | int]) -> Dict[str, Any]:
    """Get keys for object or indices for array.

    Args:
        value: JSON value to analyze
        file_path: Source file path
        json_path: JSON navigation path

    Returns:
        Keys result dict
    """
    if isinstance(value, dict):
        return {
            'contract_version': '1.0',
            'type': 'json_keys',
            'source': str(file_path),
            'source_type': 'file',
            'file': str(file_path),
            'path': '/'.join(str(p) for p in json_path) if json_path else '(root)',
            'keys': list(value.keys()),
            'count': len(value)
        }
    elif isinstance(value, list):
        return {
            'contract_version': '1.0',
            'type': 'json_keys',
            'source': str(file_path),
            'source_type': 'file',
            'file': str(file_path),
            'path': '/'.join(str(p) for p in json_path) if json_path else '(root)',
            'indices': list(range(len(value))),
            'count': len(value)
        }
    else:
        return {
            'contract_version': '1.0',
            'type': 'json_error',
            'source': str(file_path),
            'source_type': 'file',
            'error': f'Cannot get keys from {type(value).__name__}'
        }


def get_length_result(value: Any, file_path: Path, json_path: List[str | int]) -> Dict[str, Any]:
    """Get length of array, object, or string.

    Args:
        value: JSON value to analyze
        file_path: Source file path
        json_path: JSON navigation path

    Returns:
        Length result dict
    """
    if isinstance(value, (dict, list, str)):
        return {
            'contract_version': '1.0',
            'type': 'json_length',
            'source': str(file_path),
            'source_type': 'file',
            'file': str(file_path),
            'path': '/'.join(str(p) for p in json_path) if json_path else '(root)',
            'length': len(value),
            'value_type': get_type_str(value)
        }
    else:
        return {
            'contract_version': '1.0',
            'type': 'json_error',
            'source': str(file_path),
            'source_type': 'file',
            'error': f'Cannot get length of {type(value).__name__}'
        }
