"""Renderer for python:// runtime inspection adapter."""

import sys
from typing import Any, Dict

from reveal.utils import safe_json_dumps


def render_python_structure(data: Dict[str, Any], output_format: str) -> None:
    """Render Python environment overview.

    Args:
        data: Python environment data from adapter
        output_format: Output format (text, json, grep)
    """
    if output_format == 'json':
        print(safe_json_dumps(data))
        return

    # Text format
    print(f"Python Environment")
    print()
    print(f"Version:        {data['version']} ({data['implementation']})")
    print(f"Executable:     {data['executable']}")
    print(f"Platform:       {data['platform']} ({data['architecture']})")
    print()

    # Virtual environment
    venv = data['virtual_env']
    if venv['active']:
        print(f"Virtual Env:    * Active")
        print(f"  Path:         {venv['path']}")
        print(f"  Type:         {venv.get('type', 'venv')}")
    else:
        print(f"Virtual Env:    X Not active")
    print()

    print(f"Packages:       {data['packages_count']} installed")
    print(f"Modules:        {data['modules_loaded']} loaded")


def _render_python_packages(data: Dict[str, Any]) -> None:
    """Render list of installed packages."""
    print(f"Installed Packages ({data['count']})")
    print()
    for pkg in data['packages']:
        print(f"  {pkg['name']:<30s} {pkg['version']:<15s} {pkg['location']}")


def _render_python_modules(data: Dict[str, Any]) -> None:
    """Render list of loaded modules."""
    print(f"Loaded Modules ({data['count']})")
    print()
    for mod in data['loaded'][:50]:  # Limit to first 50
        file_info = f" ({mod['file']})" if mod['file'] else " (built-in)"
        print(f"  {mod['name']}{file_info}")
    if data['count'] > 50:
        print(f"\n  ... and {data['count'] - 50} more modules")


def _render_python_doctor(data: Dict[str, Any]) -> None:
    """Render Python environment health diagnostics."""
    status_icon = "*" if data['status'] == 'healthy' else "!"
    print(f"Python Environment Health: {status_icon} {data['status'].upper()}")
    print(f"Health Score: {data['health_score']}/100")
    print()

    if data.get('issues'):
        print(f"Issues ({len(data['issues'])}):")
        for issue in data['issues']:
            print(f"  X [{issue['category']}] {issue['message']}")
            if 'impact' in issue:
                print(f"     Impact: {issue['impact']}")
        print()

    if data.get('warnings'):
        print(f"Warnings ({len(data['warnings'])}):")
        for warn in data['warnings']:
            print(f"  ! [{warn['category']}] {warn['message']}")
            if 'impact' in warn:
                print(f"     Impact: {warn['impact']}")
        print()

    if data.get('info'):
        print(f"Info ({len(data['info'])}):")
        for info in data['info']:
            print(f"  i [{info['category']}] {info['message']}")
        print()

    if data.get('recommendations'):
        print(f"Recommendations ({len(data['recommendations'])}):")
        for rec in data['recommendations']:
            print(f"  > {rec['message']}")
            if 'commands' in rec:
                for cmd in rec['commands']:
                    print(f"     $ {cmd}")
        print()

    print(f"Checks performed: {', '.join(data['checks_performed'])}")


def _render_python_bytecode(data: Dict[str, Any]) -> None:
    """Render bytecode debugging information."""
    print(f"Bytecode Check: {data['status'].upper()}")
    print()

    if data['issues']:
        print(f"Found {len(data['issues'])} issues:")
        print()
        for issue in data['issues']:
            severity_marker = "! " if issue['severity'] == 'warning' else "i "
            print(f"{severity_marker} {issue['type']}")
            print(f"   File: {issue.get('file', issue.get('pyc_file', 'unknown'))}")
            print(f"   Problem: {issue['problem']}")
            print(f"   Fix: {issue['fix']}")
            print()
    else:
        print("* No bytecode issues found")


def _render_python_env_config(data: Dict[str, Any]) -> None:
    """Render Python environment configuration details."""
    print("Python Environment Configuration")
    print()

    venv = data['virtual_env']
    if venv['active']:
        print(f"Virtual Environment: * Active")
        print(f"  Path: {venv['path']}")
        print(f"  Type: {venv.get('type', 'venv')}")
    else:
        print(f"Virtual Environment: X Not active")
    print()

    print(f"sys.path ({data['sys_path_count']} entries):")
    for path in data['sys_path']:
        print(f"  {path}")
    print()

    print("Flags:")
    for flag, value in data['flags'].items():
        print(f"  {flag}: {value}")


def _render_python_version(data: Dict[str, Any]) -> None:
    """Render Python version details."""
    print("Python Version Details")
    print()
    print(f"Version:        {data['version']}")
    print(f"Implementation: {data['implementation']}")
    print(f"Compiler:       {data['compiler']}")
    print(f"Build:          {data['build_number']} ({data['build_date']})")
    print(f"Executable:     {data['executable']}")
    print(f"Prefix:         {data['prefix']}")
    print(f"Base Prefix:    {data['base_prefix']}")
    print(f"Platform:       {data['platform']} ({data['architecture']})")


def _render_python_venv_status(data: Dict[str, Any]) -> None:
    """Render virtual environment status."""
    print("Virtual Environment Status")
    print()
    if data['active']:
        print(f"Status:    * Active")
        print(f"Path:      {data['path']}")
        print(f"Type:      {data.get('type', 'venv')}")
        if 'prompt' in data:
            print(f"Prompt:    {data['prompt']}")
        if 'python_version' in data:
            print(f"Python:    {data['python_version']}")
    else:
        print(f"Status:    X Not active")
        print()
        print("No virtual environment detected.")
        print("Checked: VIRTUAL_ENV, sys.prefix, CONDA_DEFAULT_ENV")


def _render_python_package_details(data: Dict[str, Any]) -> None:
    """Render individual package details."""
    print(f"Package: {data['name']}")
    print()
    print(f"Version:    {data['version']}")
    print(f"Location:   {data['location']}")
    if 'summary' in data:
        print(f"Summary:    {data.get('summary', 'N/A')}")
    if 'author' in data:
        print(f"Author:     {data.get('author', 'N/A')}")
    if 'license' in data:
        print(f"License:    {data.get('license', 'N/A')}")
    if 'homepage' in data:
        print(f"Homepage:   {data.get('homepage', 'N/A')}")
    if 'dependencies' in data and data['dependencies']:
        print()
        print(f"Dependencies ({len(data['dependencies'])}):")
        for dep in data['dependencies']:
            print(f"  * {dep}")


def render_python_element(data: Dict[str, Any], output_format: str) -> None:
    """Render specific Python runtime element.

    Args:
        data: Python element data from adapter
        output_format: Output format (text, json, grep)
    """
    if output_format == 'json':
        print(safe_json_dumps(data))
        return

    # Handle errors
    if 'error' in data:
        print(f"Error: {data['error']}", file=sys.stderr)
        if 'details' in data:
            print(f"Details: {data['details']}", file=sys.stderr)
        sys.exit(1)

    # Detect element type and dispatch to appropriate renderer
    if 'packages' in data and 'count' in data:
        _render_python_packages(data)
    elif 'loaded' in data and 'count' in data:
        _render_python_modules(data)
    elif 'health_score' in data and 'checks_performed' in data:
        _render_python_doctor(data)
    elif 'status' in data and 'issues' in data:
        _render_python_bytecode(data)
    elif 'sys_path' in data:
        _render_python_env_config(data)
    elif 'executable' in data and 'compiler' in data:
        _render_python_version(data)
    elif 'active' in data:
        _render_python_venv_status(data)
    elif 'name' in data and 'version' in data and 'location' in data:
        _render_python_package_details(data)
    else:
        # Generic fallback
        print(safe_json_dumps(data))
