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
    print("Python Environment")
    print()
    print(f"Version:        {data['version']} ({data['implementation']})")
    print(f"Executable:     {data['executable']}")
    print(f"Platform:       {data['platform']} ({data['architecture']})")
    print()

    # Virtual environment
    venv = data['virtual_env']
    if venv['active']:
        print("Virtual Env:    * Active")
        print(f"  Path:         {venv['path']}")
        print(f"  Type:         {venv.get('type', 'venv')}")
    else:
        print("Virtual Env:    X Not active")
    print()

    print(f"Packages:       {data['packages_count']} installed")
    print(f"Modules:        {data['modules_loaded']} loaded")
    print()

    # Available elements (Phase 5: Element Discovery)
    if data.get('available_elements'):
        print("📍 Available elements:")
        for elem in data['available_elements']:
            name = elem['name']
            desc = elem['description']
            print(f"  /{name:<12} {desc}")
        print()
        # Show example usage hint with first element
        if data['available_elements']:
            example = data['available_elements'][0]['example']
            print(f"💡 Try: {example}")


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


def _render_doctor_item(item: Dict[str, Any], icon: str, show_impact: bool) -> None:
    """Print a single diagnostic item with optional impact line."""
    print(f"  {icon} [{item['category']}] {item['message']}")
    if show_impact and 'impact' in item:
        print(f"     Impact: {item['impact']}")


def _render_doctor_section(label: str, items: list, icon: str, show_impact: bool) -> None:
    """Print a labelled section of diagnostic items."""
    if not items:
        return
    print(f"{label} ({len(items)}):")
    for item in items:
        _render_doctor_item(item, icon, show_impact=show_impact)
    print()


def _render_python_doctor(data: Dict[str, Any]) -> None:
    """Render Python environment health diagnostics."""
    status_icon = "*" if data['status'] == 'healthy' else "!"
    print(f"Python Environment Health: {status_icon} {data['status'].upper()}")
    print(f"Health Score: {data['health_score']}/100")
    print()

    _render_doctor_section("Issues", data.get('issues') or [], 'X', show_impact=True)
    _render_doctor_section("Warnings", data.get('warnings') or [], '!', show_impact=True)
    _render_doctor_section("Info", data.get('info') or [], 'i', show_impact=False)

    if data.get('recommendations'):
        print(f"Recommendations ({len(data['recommendations'])}):")
        for item in data['recommendations']:
            print(f"  > {item['message']}")
            for cmd in item.get('commands', []):
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
        print("Virtual Environment: * Active")
        print(f"  Path: {venv['path']}")
        print(f"  Type: {venv.get('type', 'venv')}")
    else:
        print("Virtual Environment: X Not active")
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
        print("Status:    * Active")
        print(f"Path:      {data['path']}")
        print(f"Type:      {data.get('type', 'venv')}")
        if 'prompt' in data:
            print(f"Prompt:    {data['prompt']}")
        if 'python_version' in data:
            print(f"Python:    {data['python_version']}")
    else:
        print("Status:    X Not active")
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


def _handle_python_error(data: Dict[str, Any]) -> None:
    """Handle and display Python runtime error."""
    print(f"Error: {data['error']}", file=sys.stderr)
    if 'details' in data:
        print(f"Details: {data['details']}", file=sys.stderr)
    sys.exit(1)


def _detect_python_element_type(data: Dict[str, Any]) -> str:
    """Detect Python element type from data structure.

    Returns:
        Element type identifier string.
    """
    if 'packages' in data and 'count' in data:
        return 'packages'
    elif 'loaded' in data and 'count' in data:
        return 'modules'
    elif 'health_score' in data and 'checks_performed' in data:
        return 'doctor'
    elif 'status' in data and 'issues' in data:
        return 'bytecode'
    elif 'sys_path' in data:
        return 'env_config'
    elif 'executable' in data and 'compiler' in data:
        return 'version'
    elif 'active' in data:
        return 'venv_status'
    elif 'name' in data and 'version' in data and 'location' in data:
        return 'package_details'
    else:
        return 'unknown'


# Dispatch table mapping element types to renderers
_PYTHON_ELEMENT_RENDERERS = {
    'packages': _render_python_packages,
    'modules': _render_python_modules,
    'doctor': _render_python_doctor,
    'bytecode': _render_python_bytecode,
    'env_config': _render_python_env_config,
    'version': _render_python_version,
    'venv_status': _render_python_venv_status,
    'package_details': _render_python_package_details,
}


def render_python_element(data: Dict[str, Any], output_format: str) -> None:
    """Render specific Python runtime element.

    Args:
        data: Python element data from adapter
        output_format: Output format (text, json, grep)
    """
    if output_format == 'json':
        print(safe_json_dumps(data))
        return

    if 'error' in data:
        _handle_python_error(data)
        return

    element_type = _detect_python_element_type(data)
    renderer = _PYTHON_ELEMENT_RENDERERS.get(element_type)

    if renderer:
        renderer(data)
    else:
        print(safe_json_dumps(data))
