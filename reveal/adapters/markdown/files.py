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


def read_body_text(path: Path) -> str:
    """Read the body text of a markdown file (content after frontmatter).

    Args:
        path: Path to markdown file

    Returns:
        Body text as string, or full content if no frontmatter
    """
    try:
        content = path.read_text(encoding='utf-8')
    except Exception:
        return ''

    if not content.startswith('---'):
        return content

    end_match = re.search(r'\n---\s*\n', content[3:])
    if not end_match:
        return content

    body_start = 3 + end_match.end()
    return content[body_start:]


def extract_internal_links(path: Path, base_path: Path) -> List[str]:
    """Extract internal markdown links from a file, returning relative paths.

    Scans for ``[text](url)`` patterns.  Skips external links (http/https/mailto)
    and anchor-only links (#section).  Resolves each URL relative to the source
    file's directory, then expresses the target as a path relative to base_path.
    Only returns targets that actually exist on disk within base_path.

    Args:
        path: Source markdown file.
        base_path: The directory being indexed (links outside it are ignored).

    Returns:
        Sorted list of relative path strings (using forward slashes).
    """
    try:
        content = path.read_text(encoding='utf-8')
    except Exception:
        return []

    # [text](url) — grab the URL portion
    pattern = re.compile(r'\[([^\]]*)\]\(([^)\s]+)[^)]*\)')
    base_resolved = base_path.resolve()
    seen: set = set()
    results: List[str] = []

    for m in pattern.finditer(content):
        url = m.group(2)
        # Skip external, anchor-only, and non-markdown links
        if url.startswith(('http://', 'https://', 'mailto:', '//')):
            continue
        if url.startswith('#'):
            continue
        # Strip inline anchor from the filename
        url_file = url.split('#')[0]
        if not url_file:
            continue
        if not url_file.lower().endswith(('.md', '.markdown')):
            continue

        # Resolve relative to the source file's directory
        try:
            resolved = (path.parent / url_file).resolve()
        except Exception:
            continue

        # Must exist and live under base_path
        try:
            rel = resolved.relative_to(base_resolved)
        except ValueError:
            continue

        if not resolved.exists():
            continue

        rel_str = str(rel).replace('\\', '/')
        if rel_str not in seen:
            seen.add(rel_str)
            results.append(rel_str)

    return sorted(results)


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
