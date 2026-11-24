"""Render an adapter result's meta.warnings into its human output (BACK-1261).

The JSON is honest; the text/markdown render is where caveats went missing, and
the text render is what humans and LLM readers actually read. Measured cases:

- overview://'s complex_functions section carried
  `meta.warnings: [{"type": "truncated", "message": "showing 5 of 97"}]` and
  rendered 5 rows with no indicator -- while the Hotspots and Entry-points
  sections in the *same file* printed "... and N more". On a Python corpus the
  same section hid 448 of 453 (98.9%) silently.
- patches://'s render never printed its own advisory, nor that patch detection
  is Python-scoped -- while testability:// printed exactly that disclosure for
  the identical limitation. A reader running patches:// alone on a Ruby or TS
  repo reads "No patch pressure groups found" as *clean* rather than *not
  measured*.

Rendering was a per-template choice, so it was uneven -- which is worse for a
reader than being absent, since nothing in the output says which sections are
complete. This makes it one call.
"""

from itertools import chain
from typing import Any, Dict, List, Optional

from reveal.utils.results import RESULT_CONTROL_WARNINGS


def collect_meta_warnings(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return meta.warnings from *result*, tolerating either nesting.

    Adapters put warnings on `meta` (v1.1 envelope) or `_meta` (the older
    per-adapter block); a renderer should not have to know which.
    """
    warnings: List[Dict[str, Any]] = []
    for key in ('meta', '_meta'):
        block = result.get(key)
        if isinstance(block, dict):
            entries = block.get('warnings')
            if isinstance(entries, list):
                warnings.extend(w for w in entries if isinstance(w, dict))
    return warnings


def meta_warning_lines(
    result: Dict[str, Any],
    *,
    heading: Optional[str] = None,
    skip_types: Optional[frozenset] = None,
) -> List[str]:
    """The lines render_meta_warnings prints, for a renderer that returns its text body.

    Args:
        heading: Section heading above the warnings; omitted when there are none, so a
            clean run yields no lines at all.
        skip_types: Warning `type`s the caller already renders inline in its
            own output — passing them here keeps the disclosure from appearing
            twice rather than silently dropping the whole block.
    """
    # 'truncated' is printed once, after the render, by the seam every result leaves
    # through (display/formatting.print_result_control_notes: the URI router's _emit_result, file
    # mode's show_structure and the subcommands' emit_subcommand_result, BACK-1059/1544/1548).
    # So is 'unknown_sort_field' (BACK-1644): both are RESULT_CONTROL_WARNINGS.
    skip = set(RESULT_CONTROL_WARNINGS) | set(skip_types or ())
    warnings = [w for w in collect_meta_warnings(result) if w.get('type') not in skip]
    # A partial scan's errors are as material as its warnings.
    meta = result.get('meta') or {}
    warnings.extend(e for e in meta.get('errors', []) if isinstance(e, dict))
    if not warnings:
        return []
    lines = [f"\n{heading}"] if heading else []
    for warning in warnings:
        message = warning.get('message') or warning.get('code') or ''
        if message:
            lines.append(f"  ⚠ {message}")
    return lines


def render_meta_warnings(
    result: Dict[str, Any],
    *,
    heading: Optional[str] = None,
    skip_types: Optional[frozenset] = None,
) -> None:
    """Print *result*'s meta.warnings as human-readable lines (see meta_warning_lines)."""
    for line in meta_warning_lines(result, heading=heading, skip_types=skip_types):
        print(line)


def _object_sentences(value: Dict[str, Any]) -> List[str]:
    """The sentences under a parent object, in order: an object with a ``text`` sentence (an ``edge_rule``) contributes
    that one, otherwise each nonempty string field and each nested object's sentences."""
    if isinstance(value.get('text'), str) and value['text']:
        return [value['text']]
    sentences: List[str] = []
    for item in value.values():
        if isinstance(item, str) and item:
            sentences.append(item)
        elif isinstance(item, dict):
            sentences.extend(_object_sentences(item))
    return sentences


def _rule_field_values(result: Dict[str, Any], fields: tuple[str, ...]) -> Dict[str, List[str]]:
    """Each field that holds a rule, as its lines: a nonempty string, a nonempty list of sentences (git ownership's
    ``_meta.known_limits``), or a parent object holding sentences (overview's ``map.rules``)."""
    rules: Dict[str, List[str]] = {}
    for path in fields:
        value: Any = result
        for key in path.split('.'):
            value = value.get(key) if isinstance(value, dict) else None
        if isinstance(value, str) and value:
            rules[path] = [value]
        elif isinstance(value, list) and value and all(isinstance(item, str) and item for item in value):
            rules[path] = list(value)
        elif isinstance(value, dict) and _object_sentences(value):
            rules[path] = _object_sentences(value)
    return rules


def rule_text_lines(
    result: Dict[str, Any], *, fields: tuple[str, ...], standing_types: frozenset,
    detail: bool = False, detail_supported: bool = False, preserve_codes: frozenset = frozenset(),
) -> List[str]:
    """One opt-in pointer to existing JSON facts, with full text on a detailed view.

    Read only: neither the result nor its frozen JSON envelope acquires fields.
    Request-specific warnings still belong to the normal warning renderer.
    """
    rules = _rule_field_values(result, fields)
    caveats = [w for w in collect_meta_warnings(result)
               if w.get('type') in standing_types and w.get('code') not in preserve_codes]
    if not rules and not caveats:
        return []
    locations = list(rules)
    for key in ('meta', '_meta'):
        if caveats and isinstance(result.get(key), dict) and result[key].get('warnings'):
            locations.append(f'{key}.warnings')
    pointer = f"Rules: --format json ({', '.join(locations)})"
    if detail_supported:
        pointer += '; --detail full for full text'
    lines = [pointer]
    if detail:
        lines.extend(chain.from_iterable(rules.values()))
        lines.extend(f"⚠ {w['message']}" for w in caveats if w.get('message'))
    return lines
