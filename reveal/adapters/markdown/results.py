"""Result building and processing for markdown adapter."""

import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from reveal.reveal_types import CONTRACT_VERSION

from ...utils.results import ResultBuilder
from ...utils.path_utils import to_posix


def build_result_item(
    path: Path,
    frontmatter: Optional[Dict[str, Any]],
    extra_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build result item dict with path and frontmatter fields.

    Args:
        path: Path to markdown file
        frontmatter: Parsed frontmatter dict (or None)
        extra_fields: Additional frontmatter field names to include in result

    Returns:
        Result item dict
    """
    stat = path.stat()
    result = {
        'path': str(path),
        'relative_path': to_posix(path.relative_to(Path.cwd())
                                 if path.is_relative_to(Path.cwd())
                                 else path),
        'has_frontmatter': frontmatter is not None,
        'mtime': stat.st_mtime,
        'modified': datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds'),
    }

    # Include key frontmatter fields
    if frontmatter:
        for key in ['title', 'type', 'status', 'tags', 'topics']:
            if key in frontmatter:
                result[key] = frontmatter[key]

        # Include any caller-requested extra fields
        if extra_fields:
            for key in extra_fields:
                if key in frontmatter and key not in result:
                    result[key] = frontmatter[key]
            result['_extra_fields'] = extra_fields

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
        contract_version=CONTRACT_VERSION,
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


def add_low_match_rate_hint(
    response: Dict[str, Any],
    total_files: int,
    total_matches: int,
    filters: List[tuple]
) -> None:
    """Add a hint when the match rate is very low, suggesting the filter requires front matter.

    Args:
        response: Response dict to modify
        total_files: Total number of files scanned
        total_matches: Number of files that matched
        filters: List of (field, operator, value) filter tuples

    Modifies response in place.
    """
    if total_files < 5 or total_matches == 0 or not filters:
        return
    match_rate = total_matches / total_files
    if match_rate < 0.05:
        # Find type= filter if present
        type_filters = [v for f, o, v in filters if f == 'type']
        if type_filters:
            hint = (
                f"Only {total_matches} of {total_files} files matched. "
                f"The 'type' filter matches only files with 'type: {type_filters[0]}' in YAML front matter. "
                f"Files without front matter are excluded. "
                f"See: reveal help://markdown"
            )
        else:
            hint = (
                f"Only {total_matches} of {total_files} files matched. "
                f"Filters apply to YAML front matter fields — files without front matter are excluded. "
                f"See: reveal help://markdown"
            )
        if 'hints' not in response:
            response['hints'] = []
        response['hints'].append({'type': 'low_match_rate', 'message': hint})


def add_unknown_filter_field_hint(
    response: Dict[str, Any],
    total_matches: int,
    seen_fields: set,
    filters: List[tuple],
    query_filters: list,
) -> None:
    """Disclose when a zero-match result is caused by a filter field that
    never appeared in any scanned file's frontmatter — distinguishing a
    typo'd field name from a genuine "0 of N files have this value" answer
    (BACK-1111).

    The '!' (missing-field) operator is excluded: for that operator, zero
    matches means the field WAS present everywhere, which is unrelated to
    this disclosure.

    Args:
        response: Response dict to modify
        total_matches: Number of files that matched
        seen_fields: Union of frontmatter keys observed across scanned files
        filters: Legacy (field, operator, value) filter tuples
        query_filters: New-syntax QueryFilter objects (field/op/value)

    Modifies response in place.
    """
    if total_matches != 0:
        return

    unknown_fields = sorted({
        field for field, op, _value in filters
        if op != '!' and field not in seen_fields
    } | {
        qf.field for qf in query_filters
        if qf.op != '!' and qf.field not in seen_fields
    })
    if not unknown_fields:
        return

    fields_str = ', '.join(f"'{f}'" for f in unknown_fields)
    hint = (
        f"Filter field(s) {fields_str} never appear in any scanned file's "
        f"front matter — this may be a typo rather than a genuine zero-match. "
        f"See: reveal help://markdown"
    )
    if 'hints' not in response:
        response['hints'] = []
    response['hints'].append({'type': 'unknown_filter_field', 'message': hint})
