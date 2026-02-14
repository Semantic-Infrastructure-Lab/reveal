"""Result building and processing for markdown adapter."""

from pathlib import Path
from typing import Dict, Any, Optional, List

from ...utils.results import ResultBuilder


def build_result_item(path: Path, frontmatter: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Build result item dict with path and frontmatter fields.

    Args:
        path: Path to markdown file
        frontmatter: Parsed frontmatter dict (or None)

    Returns:
        Result item dict
    """
    result = {
        'path': str(path),
        'relative_path': str(path.relative_to(Path.cwd())
                            if path.is_relative_to(Path.cwd())
                            else path),
        'has_frontmatter': frontmatter is not None,
    }

    # Include key frontmatter fields
    if frontmatter:
        for key in ['title', 'type', 'status', 'tags', 'topics']:
            if key in frontmatter:
                result[key] = frontmatter[key]

    return result


def create_sort_key(item: Dict[str, Any], sort_field: str, sort_descending: bool) -> tuple:
    """Create sort key for an item based on sort_field.

    Args:
        item: Result item dict
        sort_field: Field name to sort by
        sort_descending: Whether to sort descending

    Returns:
        Sort key tuple
    """
    # Check if field exists in the result dict (including frontmatter fields)
    if sort_field in item:
        value = item[sort_field]
        # Handle None values (sort to end)
        if value is None:
            return (1, 0) if sort_descending else (0, 0)
        # Handle list values (use first element)
        if isinstance(value, list):
            return (0, str(value[0]) if value else '')
        return (0, value)
    return (1, 0) if sort_descending else (0, 0)


def apply_sorting(results: List[Dict[str, Any]], sort_field: str, sort_descending: bool) -> List[Dict[str, Any]]:
    """Apply sorting to results.

    Args:
        results: List of result items
        sort_field: Field name to sort by (or None)
        sort_descending: Whether to sort descending

    Returns:
        Sorted list of results
    """
    if not sort_field:
        return results

    try:
        return sorted(
            results,
            key=lambda item: create_sort_key(item, sort_field, sort_descending),
            reverse=sort_descending
        )
    except Exception:
        # If sorting fails, continue without sorting
        return results


def apply_pagination(results: List[Dict[str, Any]], offset: int, limit: Optional[int]) -> List[Dict[str, Any]]:
    """Apply offset and limit to results.

    Args:
        results: List of result items
        offset: Number of results to skip
        limit: Maximum number of results to return (or None)

    Returns:
        Paginated list of results
    """
    if offset:
        results = results[offset:]
    if limit is not None:
        results = results[:limit]
    return results


def build_response_dict(
    base_path: Path,
    query: str,
    filters: List[tuple],
    files: List[Path],
    total_matches: int,
    controlled_results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Build response dict with metadata.

    Args:
        base_path: Base path for the query
        query: Query string
        filters: List of filter tuples
        files: All markdown files found
        total_matches: Total number of matching files
        controlled_results: Filtered, sorted, and paginated results

    Returns:
        Complete response dict
    """
    return ResultBuilder.create(
        result_type='markdown_query',
        source=base_path,
        data={
            'base_path': str(base_path),
            'query': query,
            'filters': [
                {'field': f, 'operator': o, 'value': v}
                for f, o, v in filters
            ],
            'total_files': len(files),
            'matched_files': total_matches,
            'results': controlled_results,
        }
    )


def add_truncation_warning(
    response: Dict[str, Any],
    displayed: int,
    total_matches: int
) -> None:
    """Add truncation warning to response if results were limited.

    Args:
        response: Response dict to modify
        displayed: Number of results being displayed
        total_matches: Total number of matching results

    Modifies response in place.
    """
    if displayed < total_matches:
        response['warnings'] = [{
            'type': 'truncated',
            'message': f'Results truncated: showing {displayed} of {total_matches} total matches'
        }]
        response['displayed_results'] = displayed
        response['total_matches'] = total_matches
