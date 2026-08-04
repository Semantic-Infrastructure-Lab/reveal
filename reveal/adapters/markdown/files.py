"""File operations for markdown adapter."""

import os
import re
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List, cast

from ...registry import get_markdown_extensions


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

    md_exts = tuple(get_markdown_extensions())

    if base_path.is_file():
        if base_path.suffix.lower() in md_exts:
            return [base_path]
        return []

    for root, _, filenames in os.walk(base_path):
        for filename in filenames:
            if filename.lower().endswith(md_exts):
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
        if not url_file.lower().endswith(tuple(get_markdown_extensions())):
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
    return extract_frontmatter_diagnostic(path)['frontmatter']


def extract_frontmatter_diagnostic(path: Path) -> Dict[str, Any]:
    """Extract YAML frontmatter, distinguishing *why* it's missing (BACK-871).

    ``extract_frontmatter`` collapses "no frontmatter block", "block present
    but truncated/invalid YAML", and "block parses to a non-mapping" into a
    single ``None`` — fine for filtering, useless for a lint report that needs
    to tell an author *what's wrong*.

    Args:
        path: Path to markdown file

    Returns:
        Dict with keys:
            frontmatter — parsed dict, or None if not 'ok'
            status      — one of 'ok', 'missing', 'malformed'
            error       — human-readable reason when status != 'ok', else None
    """
    try:
        content = path.read_text(encoding='utf-8')
    except Exception as exc:
        return {'frontmatter': None, 'status': 'missing', 'error': f'unreadable: {exc}'}

    if not content.startswith('---'):
        return {'frontmatter': None, 'status': 'missing', 'error': None}

    end_match = re.search(r'\n---\s*\n', content[3:])
    if not end_match:
        return {'frontmatter': None, 'status': 'malformed', 'error': 'no closing --- delimiter found'}

    yaml_content = content[3:end_match.start() + 3]

    try:
        result = yaml.safe_load(yaml_content)
    except yaml.YAMLError as exc:
        return {'frontmatter': None, 'status': 'malformed', 'error': str(exc)}

    if result is None:
        return {'frontmatter': None, 'status': 'malformed', 'error': 'frontmatter block is empty'}
    if not isinstance(result, dict):
        return {
            'frontmatter': None,
            'status': 'malformed',
            'error': f'frontmatter is not a mapping (got {type(result).__name__})',
        }

    return {'frontmatter': cast(Dict[str, Any], result), 'status': 'ok', 'error': None}
