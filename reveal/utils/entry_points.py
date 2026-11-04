"""The active-entry-point filter: one owner for architecture, overview and the diff.

``imports://?entrypoints`` lists every file nothing but tests imports (fan-in 0).
Most of those are not places execution starts, so the briefs report only the
*active* ones: fan_out > 0, not a test file, not a package marker (``__init__.py``).
The rule text names a package marker only when a candidate's language has one
(``LanguageExtractor.package_marker``), so a Rust scan does not mention Python.
"""
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .path_utils import is_test_path

ENTRY_POINT_RULE_BASE = 'fan_out > 0, not a test file'


def active_entry_point_rule(markers: Iterable[str] = ()) -> str:
    """The predicate's text; ``markers`` are the package marker file names of the candidates' languages."""
    return ''.join([ENTRY_POINT_RULE_BASE, *(f', not {marker}' for marker in sorted(set(markers)))])


def is_active_entry_point(entry: Dict[str, Any]) -> bool:
    """True for a fan-in-0 row that is an active entry point (see the module docstring)."""
    if 'is_test' in entry:
        is_test = entry['is_test']
        if type(is_test) is not bool:
            raise ValueError('entrypoint is_test must be a boolean')
    else:
        is_test = is_test_path(entry['file'])
    return (
        entry.get('fan_out', 0) > 0
        and not is_test
        and Path(str(entry['file']).replace('\\', '/')).name != '__init__.py'
    )


def active_entry_points(entries: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [e for e in entries if is_active_entry_point(e)]


def entry_point_filter(entries: Iterable[Dict[str, Any]], markers: Iterable[str] = ()) -> Dict[str, Any]:
    """How many fan-in-0 files there are, how many of them are active, and the rule between them.
    ``markers`` are the package marker names of the candidates' languages, which the caller owns
    (``scanned_rule_traits``): this module sits below the analyzers and does not import them."""
    rows = list(entries)
    return {
        'fan_in_zero': len(rows),
        'active': len(active_entry_points(rows)),
        'rule': active_entry_point_rule(markers),
    }
