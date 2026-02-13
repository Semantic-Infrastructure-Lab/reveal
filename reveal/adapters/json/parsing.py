"""Path parsing and JSON loading functions for JSON adapter."""

import json
import os
import re
from pathlib import Path
from typing import Any, List, Optional, Tuple, cast


def parse_path(path: str) -> Tuple[Path, List[str | int], Optional[Tuple[Optional[int], Optional[int]]]]:
    """Parse file path and JSON navigation path.

    Handles: file.json, file.json/key, file.json/arr[0:3]

    Args:
        path: Full path string (file + optional JSON path)

    Returns:
        Tuple of (file_path, json_path_components, slice_spec)
    """
    # Expand ~ to home directory first
    path = os.path.expanduser(path)

    json_path: List[str | int] = []
    slice_spec: Optional[Tuple[Optional[int], Optional[int]]] = None

    # Find the .json file boundary
    json_match = re.search(r'(.*?\.json[l]?)(/.+)?$', path, re.IGNORECASE)

    if json_match:
        file_path = Path(json_match.group(1))
        json_nav = json_match.group(2)

        if json_nav:
            # Parse JSON path: /key/0/subkey or /arr[0:3]
            json_path, slice_spec = parse_json_path(json_nav)
    else:
        # No .json extension found, treat entire path as file
        file_path = Path(path)

    return file_path, json_path, slice_spec


def parse_json_path(nav_path: str) -> Tuple[List[str | int], Optional[Tuple[Optional[int], Optional[int]]]]:
    """Parse JSON navigation path into components.

    Args:
        nav_path: Navigation path string (e.g., "/key/0" or "/arr[0:3]")

    Returns:
        Tuple of (json_path_components, slice_spec)
    """
    json_path: List[str | int] = []
    slice_spec: Optional[Tuple[Optional[int], Optional[int]]] = None

    # Remove leading slash
    nav_path = nav_path.lstrip('/')

    # Check for array slice at end: key[0:3]
    slice_match = re.search(r'\[(-?\d*):(-?\d*)\]$', nav_path)
    if slice_match:
        start = int(slice_match.group(1)) if slice_match.group(1) else None
        end = int(slice_match.group(2)) if slice_match.group(2) else None
        slice_spec = (start, end)
        nav_path = nav_path[:slice_match.start()]

    # Check for single array index at end: key[0]
    index_match = re.search(r'\[(-?\d+)\]$', nav_path)
    if index_match and not slice_spec:
        # Convert [n] to path component
        nav_path = nav_path[:index_match.start()]
        if nav_path:
            json_path = cast(List[str | int], nav_path.split('/'))
        json_path.append(int(index_match.group(1)))
        return json_path, slice_spec

    # Split path components
    if nav_path:
        for part in nav_path.split('/'):
            if part.isdigit() or (part.startswith('-') and part[1:].isdigit()):
                json_path.append(int(part))
            else:
                json_path.append(part)

    return json_path, slice_spec


def load_json(file_path: Path) -> Any:
    """Load and parse JSON file.

    Args:
        file_path: Path to JSON file

    Returns:
        Parsed JSON data

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file is not valid JSON
    """
    if not file_path.exists():
        raise FileNotFoundError(f"JSON file not found: {file_path}")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        # Detect file type and provide helpful error message
        file_ext = file_path.suffix.lower()
        file_type_hints = {
            '.toml': ('TOML', 'a TOML configuration file'),
            '.yaml': ('YAML', 'a YAML file'),
            '.yml': ('YAML', 'a YAML file'),
            '.xml': ('XML', 'an XML file'),
            '.ini': ('INI', 'an INI configuration file'),
            '.cfg': ('Config', 'a configuration file'),
        }

        if file_ext in file_type_hints:
            file_type, description = file_type_hints[file_ext]
            raise ValueError(
                f"Error: {file_path.name} is {description}, not JSON.\n"
                f"Suggestion: Use 'reveal {file_path}' instead of 'reveal json://{file_path}'"
            ) from e
        else:
            raise ValueError(
                f"Error: {file_path.name} is not valid JSON.\n"
                f"Parse error at line {e.lineno}, column {e.colno}: {e.msg}\n"
                f"Suggestion: Check file format or use 'reveal {file_path}' for structure analysis"
            ) from e
