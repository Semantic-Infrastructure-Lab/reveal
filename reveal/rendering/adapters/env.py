"""Renderer for env:// environment variables adapter."""

from typing import Any, Dict

from reveal.utils import safe_json_dumps


def render_env_structure(data: Dict[str, Any], output_format: str) -> None:
    """Render environment variables structure.

    Args:
        data: Environment data from adapter
        output_format: Output format (text, json, grep)
    """
    if output_format == 'json':
        print(safe_json_dumps(data))
        return

    # Text format
    print(f"Environment Variables ({data['total_count']})")
    print()

    for category, variables in data['categories'].items():
        if not variables:
            continue

        print(f"{category} ({len(variables)}):")
        for var in variables:
            sensitive_marker = " (sensitive)" if var['sensitive'] else ""
            if output_format == 'grep':
                # grep format: env://VAR_NAME:value
                print(f"env://{var['name']}:{var['value']}")
            else:
                # text format
                print(f"  {var['name']:<30s} {var['value']}{sensitive_marker}")
        print()


def render_env_variable(data: Dict[str, Any], output_format: str) -> None:
    """Render single environment variable.

    Args:
        data: Variable data from adapter
        output_format: Output format (text, json, grep)
    """
    if output_format == 'json':
        print(safe_json_dumps(data))
        return

    if output_format == 'grep':
        print(f"env://{data['name']}:{data['value']}")
        return

    # Text format
    print(f"Environment Variable: {data['name']}")
    print(f"Category: {data['category']}")
    print(f"Value: {data['value']}")
    if data['sensitive']:
        print("Warning: Sensitive - This variable appears to contain sensitive data")
        print("    Use --show-secrets to display actual value")
    print(f"Length: {data['length']} characters")
