"""High-level operations for markdown adapter."""

import hashlib
import stat as stat_module
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from . import files, filtering, results
from ...core import disk_cache
from ...utils.parallel import grep_files, worker_lost_warning
from ...utils.query import unknown_sort_field_warning
from ...utils.results import note_warning
from ...utils.path_utils import failure_of, to_posix, traversal_failed_warning
from ...reveal_types import PathFailure

_LINK_GRAPH_CACHE_NAMESPACE = "markdown_link_graph"


@dataclass
class _QuerySources:
    items: List[Dict[str, Any]] = field(default_factory=list)
    seen_fields: set = field(default_factory=set)
    unreadable: List[Tuple[str, str]] = field(default_factory=list)
    lost: List[Path] = field(default_factory=list)
    analyzed: int = 0
    failed: set[Path] = field(default_factory=set)


def _prefilter_unreadable(candidates) -> List[Tuple[str, str]]:
    return [(failure.path, failure.cause) for failure in getattr(candidates, 'unreadable', [])]


def _query_candidate(path: Path, filters: list, query_filters: list,
                     body_contains: Optional[list], extra_fields: Optional[list],
                     explain: bool) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """One source decision; body selection and ranking share the same UTF-8 read."""
    body = ''
    if body_contains:
        content = path.read_text(encoding='utf-8')
        frontmatter = files.extract_frontmatter_diagnostic(path, content=content)['frontmatter']
        body, _ = files.read_body_outcome(path, content=content)
    else:
        frontmatter = files.extract_frontmatter(path)
    if not filtering.matches_all_filters(frontmatter, filters, query_filters):
        return frontmatter, None
    if body_contains and not filtering.body_has_terms(body, body_contains):
        return frontmatter, None
    item = results.build_result_item(path, frontmatter, extra_fields)
    if body_contains:
        score_info = filtering.score_body_match(path, body_contains, body=body)
        item['relevance_score'] = score_info['score']
        if explain:
            item['relevance_explain'] = {
                'term_counts': score_info['term_counts'],
                'heading_hits': score_info['heading_hits'],
            }
    return frontmatter, item


def _collect_query_sources(all_files: List[Path], filters: list, query_filters: list,
                           body_contains: Optional[list], extra_fields: Optional[list],
                           explain: bool) -> _QuerySources:
    candidates = grep_files(all_files, body_contains) if body_contains else all_files
    collected = _QuerySources(lost=list(getattr(candidates, 'lost', [])))
    collected.unreadable = _prefilter_unreadable(candidates)
    collected.failed = set(collected.lost) | {Path(path) for path, _ in collected.unreadable}
    # A completed prefilter nonmatch establishes a required source decision too.
    collected.analyzed = len(all_files) - len(candidates) - len(collected.failed)
    for path in candidates:
        try:
            frontmatter, item = _query_candidate(
                path, filters, query_filters, body_contains, extra_fields, explain)
        except (OSError, UnicodeDecodeError) as exc:
            if not body_contains:
                raise
            collected.failed.add(path)
            collected.unreadable.append((to_posix(path), failure_of(exc).cause))
            continue
        collected.analyzed += 1
        if frontmatter:
            collected.seen_fields.update(frontmatter)
        if item is not None:
            collected.items.append(item)
    return collected


def get_structure(
    base_path: Path,
    query: str,
    filters: list,
    query_filters: list,
    result_control: Any,
    body_contains: Optional[list] = None,
    extra_fields: Optional[list] = None,
    explain: bool = False,
) -> Dict[str, Any]:
    """Query markdown files and return matching results.

    Args:
        base_path: Directory to search
        query: Query string
        filters: Legacy filters
        query_filters: New query filters
        result_control: ResultControl object with sort/limit/offset
        body_contains: Optional list of terms that must appear in body text
        extra_fields: Optional list of additional frontmatter fields to include in results
        explain: When body_contains is set, include a per-hit score breakdown
            (term_counts, heading_hits) alongside relevance_score

    Returns:
        Dict containing matched files with frontmatter summary. When
        body_contains is set, each result also carries relevance_score and
        results are ranked best-first unless the caller specified an explicit
        sort field (BACK-869).
    """
    discovery: List[PathFailure] = []
    if body_contains:
        all_files = files.find_markdown_files(base_path, on_error=lambda exc: discovery.append(failure_of(exc)))
    else:
        all_files = files.find_markdown_files(base_path)
    collected = _collect_query_sources(all_files, filters, query_filters, body_contains, extra_fields, explain)
    matched_results = collected.items

    # Apply result control (sort, limit, offset). A multi-doc body-contains
    # search with no explicit sort= ranks best-first by relevance_score
    # instead of falling back to filesystem order.
    total_matches = len(matched_results)
    sort_field = result_control.sort_field
    sort_descending = result_control.sort_descending
    if body_contains and not sort_field:
        sort_field = 'relevance_score'
        sort_descending = True
    sorted_results = results.apply_sorting(
        matched_results,
        sort_field,
        sort_descending
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
    if body_contains:
        analysis: results.BodySearchAnalysis = {
            'candidate_files': len(all_files), 'analyzed_files': collected.analyzed,
            'failed_files': len(collected.failed), 'discovery_failures': len(discovery),
        }
        response['analysis'] = analysis

    # Add truncation warning if needed
    displayed = len(controlled_results)
    results.add_truncation_warning(response, displayed, total_matches)
    note_warning(response, unknown_sort_field_warning(result_control.sort_field, matched_results))
    note_warning(response, worker_lost_warning(
        collected.lost, "they were not searched, so matches may be missing", base_path))  # BACK-1754
    note_warning(response, files.unreadable_warning(
        collected.unreadable, "required document evidence is missing, so matches or ranking may be incomplete", base_path))
    discovery_warning = traversal_failed_warning(discovery, base_path)
    note_warning(response, dict(discovery_warning) if discovery_warning else None)

    # Add hint when filter matches very few files (likely front matter mismatch)
    results.add_low_match_rate_hint(response, len(all_files), total_matches, filters)

    # Disclose when a zero-match result traces to a filter field that never
    # appeared in any scanned file's frontmatter — typo vs. genuine zero (BACK-1111)
    results.add_unknown_filter_field_hint(response, total_matches, collected.seen_fields, filters, query_filters)

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
    unreadable = _prefilter_unreadable(candidates)

    for path in candidates:
        frontmatter = files.extract_frontmatter(path)
        if not filtering.matches_all_filters(frontmatter, filters, query_filters):
            continue
        if body_contains:
            body, failure = files.read_body_outcome(path)
            if failure:
                unreadable.append((str(path), failure))
                continue
            if not filtering.body_has_terms(body, body_contains):
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

    result: Dict[str, Any] = {
        'field': field,
        'total_files': len(all_files),
        'matched_files': matched,
        'files_missing_field': missing,
        'aggregate': aggregate,
    }
    if unreadable:
        result['unreadable_files'] = [list(item) for item in unreadable]  # BACK-1854
    return result


def _link_graph_fingerprint(base_path: Path, all_files: List[Path]) -> Optional[str]:
    """Disk-cache key for a markdown tree's link graph, or None to skip caching.

    Mirrors I002's ``_tree_fingerprint`` (BACK-536 pattern): digest each
    file's ``(relpath, mtime_ns, size)`` rather than content, so the key is a
    cheap stat walk instead of a re-read. A content edit bumps mtime_ns; an
    add/delete/rename changes the file set — either changes the digest, so a
    stale graph is never served.

    Returns None (caller skips the cache) on any stat/walk error, so a
    transient filesystem hiccup falls open to the uncached (correct) path.
    """
    try:
        base_resolved = base_path.resolve()
        hasher = hashlib.sha256()
        entries = []
        for file_path in all_files:
            try:
                st = file_path.stat()
            except OSError:
                return None
            if not stat_module.S_ISREG(st.st_mode):
                continue
            try:
                rel = str(file_path.resolve().relative_to(base_resolved))
            except ValueError:
                rel = str(file_path)
            entries.append((rel, st.st_mtime_ns, st.st_size))
        entries.sort()
        for rel, mtime_ns, size in entries:
            hasher.update(rel.encode("utf-8", "replace"))
            hasher.update(f"\x00{mtime_ns}\x01{size}\x02".encode("ascii"))
        return hasher.hexdigest()
    except OSError:
        return None


def _storable(unreadable: List[List[str]]) -> bool:
    """Whether a graph with these unreadable files is the tree's answer for its stat key.

    A read failure the bytes did not cause (BACK-2119) is returned, never stored: chmod
    leaves the (relpath, mtime_ns, size) key unchanged, so the entry would outlive the fix.
    A content failure is the same on every read of unchanged bytes and may be stored.
    """
    return all(files.is_content_failure(failure) for _, failure in unreadable)


def _cached_link_graph(fingerprint: Optional[str]) -> Optional[Dict[str, Any]]:
    """The stored graph for *fingerprint*, or None. An entry written before BACK-2119 may carry
    an environmental failure; it is treated as a miss and rebuilt."""
    if fingerprint is None:
        return None
    cached = disk_cache.get(_LINK_GRAPH_CACHE_NAMESPACE, fingerprint)
    if cached is not None and _storable(cached.get('unreadable_files', [])):
        return cached
    return None


def build_link_graph(base_path: Path) -> Dict[str, Any]:
    """Build a cross-file link graph for all markdown files under base_path.

    For each file, discovers which other files it links to (forward edges) and
    which files link back to it (back-edges / backlinks).  Files with neither
    forward nor backward links are reported as ``isolated``.

    Results are cached on disk keyed by a fingerprint of every markdown
    file's (relpath, mtime_ns, size) (BACK-866) — every Beth-parity feature
    built on this (?link-graph, ?backlinks=, ?lint's future needs, --related's
    link-derived fallback) re-walks the same tree per call otherwise.

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

    fingerprint = _link_graph_fingerprint(base_path, all_files)
    cached = _cached_link_graph(fingerprint)
    if cached is not None:
        return cached

    base_resolved = base_path.resolve()

    # Map relative-path-string → list of relative-path-string targets
    forward: Dict[str, List[str]] = {}
    unreadable: List[List[str]] = []
    for md_path in all_files:
        try:
            rel = str(md_path.resolve().relative_to(base_resolved)).replace('\\', '/')
        except ValueError:
            continue
        forward[rel], failure = files.extract_internal_links_outcome(md_path, base_path)
        if failure:
            unreadable.append([rel, failure])

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

    graph = {
        'total_files': len(all_files),
        'total_edges': total_edges,
        'nodes': nodes,
        'isolated': isolated,
    }
    if unreadable:
        graph['unreadable_files'] = unreadable  # BACK-1854: a stored content failure still says it on a hit
    if fingerprint is not None and _storable(unreadable):
        disk_cache.put(_LINK_GRAPH_CACHE_NAMESPACE, fingerprint, graph)
    return graph


def get_backlinks(base_path: Path, target: str) -> Dict[str, Any]:
    """Find which files link to a single target doc — a pre-edit staleness check.

    Reuses ``build_link_graph`` (backlinks require scanning every file's
    outbound links regardless of how many targets you care about) but returns
    only the one node instead of the whole tree, so callers checking "who
    references this doc before I rename it" don't pay for output they didn't
    ask for.

    Args:
        base_path: Root directory to index.
        target: Path to the doc to look up, relative to base_path (e.g.
            'guides/auth.md'). A bare filename (e.g. 'auth.md') matches by
            basename if no exact relative-path match is found.

    Returns:
        Dict with keys:
            target      — the resolved relative path that was matched
            found       — whether a matching file was located
            linked_by   — files that link to target (empty if not found)
            links_to    — files target links to (empty if not found)
            ambiguous   — present + True when a bare filename matched >1 file
            candidates  — present when ambiguous, the list of matching paths
            total_files — number of markdown files scanned
    """
    graph = build_link_graph(base_path)
    result = _lookup_backlinks(graph, target)
    if graph.get('unreadable_files'):
        result['unreadable_files'] = graph['unreadable_files']  # BACK-1854
    return result


def _lookup_backlinks(graph: Dict[str, Any], target: str) -> Dict[str, Any]:
    """The backlinks answer for *target* from a built link *graph* (see get_backlinks)."""
    target_norm = target.strip().lstrip('./')

    node = next((n for n in graph['nodes'] if n['file'] == target_norm), None)
    if node is not None:
        return {
            'target': node['file'],
            'found': True,
            'linked_by': node['linked_by'],
            'links_to': node['links_to'],
            'total_files': graph['total_files'],
        }

    basename = target_norm.rsplit('/', 1)[-1]
    candidates = [n for n in graph['nodes'] if n['file'].rsplit('/', 1)[-1] == basename]
    if len(candidates) == 1:
        node = candidates[0]
        return {
            'target': node['file'],
            'found': True,
            'linked_by': node['linked_by'],
            'links_to': node['links_to'],
            'total_files': graph['total_files'],
        }
    if len(candidates) > 1:
        return {
            'target': target_norm,
            'found': False,
            'ambiguous': True,
            'candidates': sorted(n['file'] for n in candidates),
            'linked_by': [],
            'links_to': [],
            'total_files': graph['total_files'],
        }

    return {
        'target': target_norm,
        'found': False,
        'linked_by': [],
        'links_to': [],
        'total_files': graph['total_files'],
    }


def lint_frontmatter(base_path: Path, required_fields: Optional[list] = None) -> Dict[str, Any]:
    """Scan a directory tree for frontmatter problems (BACK-871).

    Mirrors beth quality's ``frontmatter-lint`` maintenance-queue view: a
    single pass over every markdown file that surfaces malformed YAML
    (``extract_frontmatter`` today silently collapses this to ``None``,
    indistinguishable from "no frontmatter"), files missing configurable
    required fields, and files with no frontmatter block at all — as one
    list, not a file-at-a-time crawl.

    Args:
        base_path: Root directory to scan.
        required_fields: Optional list of frontmatter field names that must
            be present (and non-null) on every file that has a frontmatter
            block. Files with no block are reported as 'no_frontmatter'
            regardless of this list — they can't be missing fields they
            never had a chance to declare.

    Returns:
        Dict with keys:
            total_files  — number of markdown files scanned
            issues_found — len(issues)
            issues       — list of {file, issue, detail}, where issue is one
                            of 'no_frontmatter', 'malformed_yaml',
                            'missing_fields' and detail carries the parse
                            error string or the list of missing field names
    """
    all_files = files.find_markdown_files(base_path)
    base_resolved = base_path.resolve()
    issues = []

    for path in all_files:
        try:
            rel = str(path.resolve().relative_to(base_resolved)).replace('\\', '/')
        except ValueError:
            rel = str(path)

        diagnosis = files.extract_frontmatter_diagnostic(path)
        status = diagnosis['status']

        if status == 'missing':
            issues.append({'file': rel, 'issue': 'no_frontmatter', 'detail': None})
        elif status == 'malformed':
            issues.append({'file': rel, 'issue': 'malformed_yaml', 'detail': diagnosis['error']})
        elif required_fields:
            frontmatter = diagnosis['frontmatter'] or {}
            missing = [f for f in required_fields if frontmatter.get(f) is None]
            if missing:
                issues.append({'file': rel, 'issue': 'missing_fields', 'detail': missing})

    return {
        'total_files': len(all_files),
        'issues_found': len(issues),
        'issues': issues,
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
