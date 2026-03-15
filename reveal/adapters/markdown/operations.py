"""High-level operations for markdown adapter."""

from collections import Counter
from pathlib import Path
from typing import Dict, Any, Optional

from . import files, filtering, results
from ...utils.parallel import grep_files


def get_structure(
    base_path: Path,
    query: str,
    filters: list,
    query_filters: list,
    result_control: Any,
    body_contains: Optional[list] = None,
) -> Dict[str, Any]:
    """Query markdown files and return matching results.

    Args:
        base_path: Directory to search
        query: Query string
        filters: Legacy filters
        query_filters: New query filters
        result_control: ResultControl object with sort/limit/offset
        body_contains: Optional list of terms that must appear in body text

    Returns:
        Dict containing matched files with frontmatter summary
    """
    all_files = files.find_markdown_files(base_path)

    # Fast parallel pre-filter: eliminate files that can't possibly match
    # before the expensive frontmatter parse + body-only verification.
    # grep_files scans whole-file bytes; matches_body_contains re-checks
    # body-only content to drop any frontmatter false-positives.
    candidates = grep_files(all_files, body_contains) if body_contains else all_files

    matched_results = []

    # Build results for matching files
    for path in candidates:
        frontmatter = files.extract_frontmatter(path)
        if not filtering.matches_all_filters(frontmatter, filters, query_filters):
            continue
        if body_contains and not filtering.matches_body_contains(path, body_contains):
            continue
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


def aggregate_field_values(
    base_path: Path,
    field: str,
    filters: list,
    query_filters: list,
    body_contains: Optional[list] = None,
) -> Dict[str, Any]:
    """Count occurrences of each value for a frontmatter field across matched files.

    List-valued fields (e.g. beth_topics: [reveal, deployment]) are expanded
    so each list item is counted individually.

    Args:
        base_path: Directory to search
        field: Frontmatter field name to aggregate (e.g. 'type', 'beth_topics')
        filters: Legacy query filters
        query_filters: New query filters
        body_contains: Optional list of terms that must appear in body text

    Returns:
        Dict with aggregate frequency table sorted by count descending
    """
    all_files = files.find_markdown_files(base_path)
    candidates = grep_files(all_files, body_contains) if body_contains else all_files
    counts: Counter = Counter()
    matched = 0
    missing = 0

    for path in candidates:
        frontmatter = files.extract_frontmatter(path)
        if not filtering.matches_all_filters(frontmatter, filters, query_filters):
            continue
        if body_contains and not filtering.matches_body_contains(path, body_contains):
            continue
        matched += 1
        value = (frontmatter or {}).get(field)
        if value is None:
            missing += 1
        elif isinstance(value, list):
            for item in value:
                if item is not None:
                    counts[str(item)] += 1
        else:
            counts[str(value)] += 1

    aggregate = [
        {'value': val, 'count': cnt}
        for val, cnt in counts.most_common()
    ]

    return {
        'field': field,
        'total_files': len(all_files),
        'matched_files': matched,
        'files_missing_field': missing,
        'aggregate': aggregate,
    }


def build_link_graph(base_path: Path) -> Dict[str, Any]:
    """Build a cross-file link graph for all markdown files under base_path.

    For each file, discovers which other files it links to (forward edges) and
    which files link back to it (back-edges / backlinks).  Files with neither
    forward nor backward links are reported as ``isolated``.

    Args:
        base_path: Root directory to index.

    Returns:
        Dict with keys:
            total_files   — number of markdown files found
            total_edges   — total number of directed link edges
            nodes         — list of node dicts, each with:
                            file, links_to, linked_by
            isolated      — list of filenames with zero edges (in or out)
    """
    all_files = files.find_markdown_files(base_path)
    base_resolved = base_path.resolve()

    # Map relative-path-string → list of relative-path-string targets
    forward: Dict[str, List[str]] = {}
    for md_path in all_files:
        try:
            rel = str(md_path.resolve().relative_to(base_resolved)).replace('\\', '/')
        except ValueError:
            continue
        forward[rel] = files.extract_internal_links(md_path, base_path)

    # Build reverse index
    reverse: Dict[str, List[str]] = {k: [] for k in forward}
    for src, targets in forward.items():
        for tgt in targets:
            if tgt in reverse:
                if src not in reverse[tgt]:
                    reverse[tgt].append(src)
            # tgt may be outside the set if file was deleted; skip silently

    total_edges = sum(len(v) for v in forward.values())

    nodes = [
        {
            'file': rel,
            'links_to': sorted(forward.get(rel, [])),
            'linked_by': sorted(reverse.get(rel, [])),
        }
        for rel in sorted(forward)
    ]

    isolated = [
        n['file'] for n in nodes
        if not n['links_to'] and not n['linked_by']
    ]

    return {
        'total_files': len(all_files),
        'total_edges': total_edges,
        'nodes': nodes,
        'isolated': isolated,
    }


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
