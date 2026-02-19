"""Renderer for json:// navigation adapter."""

import json
import sys
from typing import Any, Dict


def _print_header(file_path: str, json_path: str) -> None:
    print(f"File: {file_path}")
    print(f"Path: {json_path}")


def _render_json_error(data: Dict[str, Any]) -> None:
    print(f"Error: {data.get('error', 'Unknown error')}", file=sys.stderr)
    if 'valid_queries' in data:
        print(f"Valid queries: {', '.join(data['valid_queries'])}", file=sys.stderr)
    sys.exit(1)


def _render_json_value(data: Dict[str, Any], file_path: str, json_path: str) -> None:
    value = data.get('value')
    _print_header(file_path, json_path)
    print(f"Type: {data.get('value_type', '')}")
    print()
    if isinstance(value, (dict, list)):
        print(json.dumps(value, indent=2))
    else:
        print(value)


def _render_json_schema(data: Dict[str, Any], file_path: str, json_path: str) -> None:
    _print_header(file_path, json_path)
    print()
    print("Schema:")
    print(json.dumps(data.get('schema', {}), indent=2))


def _render_json_flatten(data: Dict[str, Any], file_path: str, json_path: str) -> None:
    print(f"# File: {file_path}")
    print(f"# Path: {json_path}")
    print()
    for line in data.get('lines', []):
        print(line)


def _render_json_type(data: Dict[str, Any], file_path: str, json_path: str) -> None:
    _print_header(file_path, json_path)
    print(f"Type: {data.get('value_type', 'unknown')}")
    if data.get('length') is not None:
        print(f"Length: {data['length']}")


def _render_json_keys(data: Dict[str, Any], file_path: str, json_path: str) -> None:
    _print_header(file_path, json_path)
    print(f"Count: {data.get('count', 0)}")
    print()
    if 'keys' in data:
        for key in data['keys']:
            print(f"  {key}")
    elif 'indices' in data:
        print(f"  [0..{data['count'] - 1}]")


def _render_json_length(data: Dict[str, Any], file_path: str, json_path: str) -> None:
    _print_header(file_path, json_path)
    print(f"Type: {data.get('value_type', 'unknown')}")
    print(f"Length: {data.get('length', 0)}")


_TYPE_RENDERERS = {
    'json-value': _render_json_value,
    'json-schema': _render_json_schema,
    'json-flatten': _render_json_flatten,
    'json-type': _render_json_type,
    'json-keys': _render_json_keys,
    'json-length': _render_json_length,
}


def render_json_result(data: Dict[str, Any], output_format: str) -> None:
    """Render JSON adapter result.

    Args:
        data: Result from JSON adapter
        output_format: Output format (text, json)
    """
    result_type = data.get('type', 'unknown')

    if output_format == 'json':
        print(json.dumps(data, indent=2))
        return

    if result_type == 'json-error':
        _render_json_error(data)

    file_path = data.get('file', '')
    json_path = data.get('path', '(root)')
    renderer = _TYPE_RENDERERS.get(result_type)
    if renderer:
        renderer(data, file_path, json_path)
    else:
        print(json.dumps(data, indent=2))
