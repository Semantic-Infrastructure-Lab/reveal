"""File operations for markdown adapter."""

import os
import re
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List, cast


def find_markdown_files(base_path: Path) -> List[Path]:
    """Find all markdown files in base_path recursively.

    Args:
        base_path: Directory or file path to search

    Returns:
        List of Path objects to markdown files
    """
    files: List[Path] = []
    if not base_path.exists():
        return files

    if base_path.is_file():
        if base_path.suffix.lower() in ('.md', '.markdown'):
            return [base_path]
        return []

    for root, _, filenames in os.walk(base_path):
        for filename in filenames:
            if filename.lower().endswith(('.md', '.markdown')):
                files.append(Path(root) / filename)

    return sorted(files)


def extract_frontmatter(path: Path) -> Optional[Dict[str, Any]]:
    """Extract YAML frontmatter from a markdown file.

    Args:
        path: Path to markdown file

    Returns:
        Frontmatter dict or None if no valid frontmatter
    """
    try:
        content = path.read_text(encoding='utf-8')
    except Exception:
        return None

    # Check for frontmatter
    if not content.startswith('---'):
        return None

    # Find closing ---
    end_match = re.search(r'\n---\s*\n', content[3:])
    if not end_match:
        return None

    yaml_content = content[3:end_match.start() + 3]

    try:
        result = yaml.safe_load(yaml_content)
        return cast(Dict[str, Any], result) if result is not None else None
    except yaml.YAMLError:
        return None
