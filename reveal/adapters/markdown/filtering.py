"""Filtering logic for markdown adapter."""

from pathlib import Path
from typing import Dict, Any, Optional, List

from ...utils.query_eval import presence_matches
from . import query as query_module


def matches_body_contains(path: Path, terms: List[str]) -> bool:
    """Check if file body text contains all terms (case-insensitive).

    Args:
        path: Path to markdown file
        terms: List of strings that must all appear in the body

    Returns:
        True if all terms are found in the body text
    """
    from . import files
    return body_has_terms(files.read_body_text(path), terms)


def body_has_terms(body: str, terms: List[str]) -> bool:
    """True if every term is in *body* (case-insensitive)."""
    body = body.lower()
    return all(term.lower() in body for term in terms)


# Heading-line hits count more than a plain body hit — a term appearing in a
# heading is a much stronger relevance signal than one buried in prose.
HEADING_HIT_WEIGHT = 3


def score_body_match(path: Path, terms: List[str], *, body: Optional[str] = None) -> Dict[str, Any]:
    """Score how strongly a file's body matches ``body-contains`` terms.

    A simple relevance score (term frequency + a heading-proximity boost) —
    not Beth's full phrase/authority model, just enough to sort multi-doc
    ``body-contains`` matches best-first instead of leaving them in
    filesystem order (BACK-869).

    Args:
        path: Path to markdown file
        terms: Terms that must all appear in the body (case-insensitive)
        body: Already-read body text; omitted callers retain the file-reading helper

    Returns:
        Dict with:
            score        — total_hits + heading_hits * HEADING_HIT_WEIGHT
            term_counts  — {term: total occurrences in body}
            heading_hits — {term: occurrences on a heading (#) line}
    """
    from . import files
    if body is None:
        body = files.read_body_text(path)
    lines = body.split('\n')

    term_counts: Dict[str, int] = {}
    heading_hits: Dict[str, int] = {}
    for term in terms:
        needle = term.lower()
        total = 0
        on_heading = 0
        for line in lines:
            line_lower = line.lower()
            occurrences = line_lower.count(needle)
            if not occurrences:
                continue
            total += occurrences
            if line.lstrip().startswith('#'):
                on_heading += occurrences
        term_counts[term] = total
        heading_hits[term] = on_heading

    score = sum(term_counts.values()) + sum(heading_hits.values()) * HEADING_HIT_WEIGHT
    return {'score': score, 'term_counts': term_counts, 'heading_hits': heading_hits}


def matches_all_filters(frontmatter: Optional[Dict[str, Any]], filters: List[Any]) -> bool:
    """Whether *frontmatter* meets every where term (AND), by the shared rules: presence through
    ``presence_matches`` (``F`` exists, ``!F`` missing), values through ``compare`` (case-insensitive, glob, numeric).
    A document without front matter has no fields: only a missing-field term matches it.

    Args:
        frontmatter: Parsed frontmatter dict (or None)
        filters: The shared parser's QueryFilter objects (field/op/value)
    """
    for term in filters:
        value = (frontmatter or {}).get(term.field)
        presence = presence_matches(term.op, value)
        if presence is not None:
            if not presence:
                return False
        elif frontmatter is None or not query_module.compare(value, term.op, term.value):
            return False
    return True
