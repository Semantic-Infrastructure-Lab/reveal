"""High-level operations for markdown adapter."""

from pathlib import Path
from typing import Dict, Any, Optional

from . import files, filtering, results


def get_structure(
    base_path: Path,
    query: str,
    filters: list,
    query_filters: list,
    result_control: Any
) -> Dict[str, Any]:
    """Query markdown files and return matching results.

    Args:
        base_path: Directory to search
        query: Query string
        filters: Legacy filters
        query_filters: New query filters
        result_control: ResultControl object with sort/limit/offset

    Returns:
        Dict containing matched files with frontmatter summary
    """
    all_files = files.find_markdown_files(base_path)
    matched_results = []

    # Build results for matching files
    for path in all_files:
        frontmatter = files.extract_frontmatter(path)
        if filtering.matches_all_filters(frontmatter, filters, query_filters):
            result = results.build_result_item(path, frontmatter)
            matched_results.append(result)

    # Apply result control (sort, limit, offset)
    total_matches = len(matched_results)
    sorted_results = results.apply_sorting(
        matched_results,
        result_control.sort_field,
        result_control.sort_descending
    )
    controlled_results = results.apply_pagination(
        sorted_results,
        result_control.offset,
        result_control.limit
    )

    # Build response with metadata
    response = results.build_response_dict(
        base_path,
        query,
        filters,
        all_files,
        total_matches,
        controlled_results
    )

    # Add truncation warning if needed
    displayed = len(controlled_results)
    results.add_truncation_warning(response, displayed, total_matches)

    return response


def get_element(base_path: Path, element_name: str) -> Optional[Dict[str, Any]]:
    """Get frontmatter from a specific file.

    Args:
        base_path: Base path to search from
        element_name: Filename or path to check

    Returns:
        Dict with file frontmatter details
    """
    # Try to find the file
    target = base_path / element_name
    if not target.exists():
        target = Path(element_name)

    if not target.exists():
        return None

    frontmatter = files.extract_frontmatter(target)

    return {
        'path': str(target),
        'has_frontmatter': frontmatter is not None,
        'frontmatter': frontmatter,
    }


def get_metadata(base_path: Path) -> Dict[str, Any]:
    """Get metadata about the query scope.

    Args:
        base_path: Directory to analyze

    Returns:
        Dict with query metadata
    """
    all_files = files.find_markdown_files(base_path)
    with_fm = sum(1 for f in all_files if files.extract_frontmatter(f) is not None)

    return {
        'type': 'markdown_query',
        'base_path': str(base_path),
        'total_files': len(all_files),
        'with_frontmatter': with_fm,
        'without_frontmatter': len(all_files) - with_fm,
    }
