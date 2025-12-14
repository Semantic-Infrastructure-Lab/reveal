"""Renderer for json:// navigation adapter."""

import json
import sys
from typing import Any, Dict


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

    # Handle errors
    if result_type == 'json-error':
        print(f"Error: {data.get('error', 'Unknown error')}", file=sys.stderr)
        if 'valid_queries' in data:
            print(f"Valid queries: {', '.join(data['valid_queries'])}", file=sys.stderr)
        sys.exit(1)

    # Text format rendering
    file_path = data.get('file', '')
    json_path = data.get('path', '(root)')

    if result_type == 'json-value':
        value = data.get('value')
        value_type = data.get('value_type', '')
        print(f"File: {file_path}")
        print(f"Path: {json_path}")
        print(f"Type: {value_type}")
        print()
        if isinstance(value, (dict, list)):
            print(json.dumps(value, indent=2))
        else:
            print(value)

    elif result_type == 'json-schema':
        schema = data.get('schema', {})
        print(f"File: {file_path}")
        print(f"Path: {json_path}")
        print()
        print("Schema:")
        print(json.dumps(schema, indent=2))

    elif result_type == 'json-flatten':
        print(f"# File: {file_path}")
        print(f"# Path: {json_path}")
        print()
        for line in data.get('lines', []):
            print(line)

    elif result_type == 'json-type':
        print(f"File: {file_path}")
        print(f"Path: {json_path}")
        print(f"Type: {data.get('value_type', 'unknown')}")
        if data.get('length') is not None:
            print(f"Length: {data['length']}")

    elif result_type == 'json-keys':
        print(f"File: {file_path}")
        print(f"Path: {json_path}")
        print(f"Count: {data.get('count', 0)}")
        print()
        if 'keys' in data:
            for key in data['keys']:
                print(f"  {key}")
        elif 'indices' in data:
            print(f"  [0..{data['count'] - 1}]")

    elif result_type == 'json-length':
        print(f"File: {file_path}")
        print(f"Path: {json_path}")
        print(f"Type: {data.get('value_type', 'unknown')}")
        print(f"Length: {data.get('length', 0)}")

    else:
        # Fallback: just dump as JSON
        print(json.dumps(data, indent=2))
