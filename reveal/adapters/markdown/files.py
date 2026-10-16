"""File operations for markdown adapter."""

import logging
import re
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, cast

from ...registry import get_markdown_extensions
from ...utils.path_utils import _walk_code_files, to_posix, to_relative_display

logger = logging.getLogger(__name__)


def find_markdown_files(base_path: Path) -> List[Path]:
    """Find all markdown files in base_path recursively.

    Args:
        base_path: Directory or file path to search

    Returns:
        List of Path objects to markdown files
    """
    if not base_path.exists():
        return []

    md_exts = tuple(get_markdown_extensions())

    if base_path.is_file():
        if base_path.suffix.lower() in md_exts:
            return [base_path]
        return []

    # The shared walk (BACK-1516): what git ignores (BACK-1386), REVEAL_IGNORE and
    # --exclude. Its own os.walk honored only .gitignore. Only .git is pruned beyond
    # those -- the code walkers' skip list (build/, dist/, vendor/...) is not applied to docs.
    return sorted(fp for fp in _walk_code_files(base_path, prune_noise=False)
                  if fp.name.lower().endswith(md_exts))


def unreadable_warning(unreadable: List[Tuple[str, str]], consequence: str,
                       base: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """One ``unreadable_files`` meta warning for markdown files that could not be read
    (BACK-1854); None when none failed. *consequence* says what is missing."""
    if not unreadable:
        return None
    paths = sorted(unreadable)
    shown = [to_relative_display(f, base) if base else to_posix(f) for f, _ in paths[:5]]
    more = f" and {len(paths) - len(shown)} more" if len(paths) > len(shown) else ''
    causes = ', '.join(sorted({cause.split(':', 1)[0] for _, cause in paths}))
    return {
        'type': 'unreadable_files',
        'count': len(paths),
        'files': shown,
        'message': f"{len(paths)} file(s) could not be read ({causes}) -- {consequence}: "
                   f"{', '.join(shown)}{more}",
    }


def read_body_outcome(path: Path) -> Tuple[str, Optional[str]]:
    """``(body, failure)``: the body text of a markdown file (content after frontmatter), or
    ``('', "ErrorType: message")`` when the file could not be read -- an empty body that
    means "unreadable", which a caller must not treat as "contains nothing" (BACK-1854)."""
    try:
        content = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as e:
        logger.warning(f"Failed to read {path}, treating body as empty: {e}")
        return '', f"{type(e).__name__}: {e}"

    if not content.startswith('---'):
        return content, None

    end_match = re.search(r'\n---\s*\n', content[3:])
    if not end_match:
        return content, None

    body_start = 3 + end_match.end()
    return content[body_start:], None


def read_body_text(path: Path) -> str:
    """Read the body text of a markdown file (content after frontmatter).

    Args:
        path: Path to markdown file

    Returns:
        Body text as string, or full content if no frontmatter; '' when the file cannot be
        read (use read_body_outcome to tell that from an empty body)
    """
    return read_body_outcome(path)[0]


def extract_internal_links(path: Path, base_path: Path) -> List[str]:
    """``extract_internal_links_outcome`` without the failure: [] for an unreadable file."""
    return extract_internal_links_outcome(path, base_path)[0]


def extract_internal_links_outcome(path: Path, base_path: Path) -> Tuple[List[str], Optional[str]]:
    """``(links, failure)``: internal markdown links from a file as relative paths;
    ``([], "ErrorType: message")`` when the file could not be read (BACK-1854).

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
    except (OSError, UnicodeDecodeError) as e:
        logger.warning(f"Failed to read {path}, reporting no internal links: {e}")
        return [], f"{type(e).__name__}: {e}"

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
        except (OSError, RuntimeError, ValueError):  # unresolvable: a symlink loop, a NUL in the URL
            continue

        # Must exist and live under base_path
        try:
            rel = resolved.relative_to(base_resolved)
        except ValueError:
            continue

        if not resolved.exists():
            continue

        rel_str = to_posix(rel)
        if rel_str not in seen:
            seen.add(rel_str)
            results.append(rel_str)

    return sorted(results), None


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
    except (OSError, UnicodeDecodeError) as exc:
        return {'frontmatter': None, 'status': 'missing', 'error': f'unreadable: {exc}'}

    if not content.startswith('---'):
        return {'frontmatter': None, 'status': 'missing', 'error': None}

    end_match = re.search(r'\n---\s*\n', content[3:])
    if not end_match:
        return {'frontmatter': None, 'status': 'malformed', 'error': 'no closing --- delimiter found'}

    yaml_content = content[3:end_match.start() + 3]

    try:
        result = yaml.safe_load(yaml_content)
    except (yaml.YAMLError, ValueError, RecursionError) as exc:
        # ValueError: safe_load builds a date as it parses, so `date: 2001-02-30` raises it
        # (not a YAMLError) and used to end the whole query over one document (BACK-1855).
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
