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

from typing import Any, Dict, List, Optional


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


def render_meta_warnings(
    result: Dict[str, Any],
    *,
    heading: Optional[str] = None,
    skip_types: Optional[frozenset] = None,
) -> None:
    """Print *result*'s meta.warnings as human-readable lines.

    Args:
        heading: Section heading to print above the warnings; omitted when
            there are none, so a clean run prints nothing at all.
        skip_types: Warning `type`s the caller already renders inline in its
            own output — passing them here keeps the disclosure from appearing
            twice rather than silently dropping the whole block.
    """
    warnings = collect_meta_warnings(result)
    if skip_types:
        warnings = [w for w in warnings if w.get('type') not in skip_types]
    if not warnings:
        return
    if heading:
        print(f"\n{heading}")
    for warning in warnings:
        message = warning.get('message') or warning.get('code') or ''
        if message:
            print(f"  ⚠ {message}")
