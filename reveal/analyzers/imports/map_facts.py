"""Bounded project-map facts from complete, existing ImportView answers.

This projection does no discovery or analysis. Composition diagnostics and the
independent code census remain the caller's responsibility. Exact presentation
totals describe the supplied graph, whose scan budget and losses remain visible.
"""
from copy import deepcopy
from pathlib import Path
from typing import Any, TypedDict

from .service import architecture_edge_rules
from ...utils.entry_points import active_entry_points, entry_point_filter
from ...utils.path_utils import to_posix, to_relative_display


class BoundedRows(TypedDict):
    rows: list[Any]
    total: int
    returned: int
    omitted: int


class MapFacts(TypedDict):
    fan_in: BoundedRows
    entrypoints: BoundedRows
    components: BoundedRows
    cycles: BoundedRows
    rules: dict[str, Any]
    entry_point_filter: dict[str, Any]
    metadata: dict[str, Any]


def _count(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f'{label} must be a nonnegative integer')
    return value


def _paths(rows: Any, label: str) -> list[str]:
    if not isinstance(rows, list) or any(not isinstance(p, str) or not p for p in rows):
        raise ValueError(f'{label} must be a list of nonempty paths')
    return rows


def _rows(answer: dict[str, Any], field: str, total: str | None = None) -> list[dict[str, Any]]:
    rows = answer[field]
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f'{field} must contain records')
    if total is not None and _count(answer[total], total) != len(rows):
        raise ValueError(f'{field} must be complete before map projection')
    if not isinstance(answer.get('edge_rule'), dict):
        raise ValueError(f'{field} requires its counting rule')
    return rows


def _page(rows: list[Any], top: int) -> BoundedRows:
    selected = rows[:top]
    return {'rows': selected, 'total': len(rows), 'returned': len(selected),
            'omitted': len(rows) - len(selected)}


def _path(value: str, base: Path) -> str:
    # Normalize native spellings before lexical path operations, also on POSIX.
    return to_relative_display(to_posix(value), base)


def _relationship(row: dict[str, Any], base: Path, *, component: bool = False) -> dict[str, Any]:
    result = deepcopy(row)
    key = 'component' if component else 'file'
    _paths([row[key]], key)
    result[key] = _path(row[key], base)
    counts = ('files', 'internal', 'outgoing', 'incoming') if component else ('fan_out',)
    for field in counts:
        _count(row[field], field)
    if component:
        cohesion = row['cohesion']
        if cohesion is None:
            if not isinstance(row.get('cohesion_reason'), str):
                raise ValueError('declined cohesion requires its reason')
        elif type(cohesion) not in (int, float) or not 0 <= cohesion <= 1:
            raise ValueError('cohesion must be a fraction or declined')
        if row['top_bridge'] is not None:
            _paths([row['top_bridge']], 'top_bridge')
            result['top_bridge'] = _path(row['top_bridge'], base)
    return result


def _metadata(metadata: dict[str, Any], base: Path) -> dict[str, Any]:
    result = deepcopy(metadata)
    for field in ('files_failed', 'files_lost'):
        count = _count(metadata[field + '_count'], field + '_count')
        paths = _paths(metadata[field], field)
        if len(paths) != min(count, 50):
            raise ValueError(f'{field} must retain its existing first-50 bound')
        result[field] = [_path(p, base) for p in paths]
    if metadata['files_lost_count'] > metadata['files_failed_count']:
        raise ValueError('lost files cannot exceed failed files')
    diagnostics = metadata['extraction_diagnostics']
    if not isinstance(diagnostics, dict):
        raise ValueError('extraction_diagnostics must retain causes by path')
    _paths(list(diagnostics), 'extraction_diagnostics')
    if any(not isinstance(causes, dict) for causes in diagnostics.values()):
        raise ValueError('extraction diagnostics must contain cause records')
    result['extraction_diagnostics'] = {_path(p, base): causes for p, causes in result['extraction_diagnostics'].items()}
    for extension, count in metadata['unsupported_extensions'].items():
        _paths([extension], 'unsupported extension')
        _count(count, 'unsupported extension count')
    return result


def project_map_facts(fan_in: dict[str, Any], entrypoints: dict[str, Any],
                      components: dict[str, Any], circular: dict[str, Any],
                      metadata: dict[str, Any], *, path: Path, top: int = 5) -> MapFacts:
    """Project complete ImportView responses; zero shows no rows, preserving totals.

    ImportView must have no ``top`` cap. Fan-in/components count all edges;
    entrypoints ignore test importers; cycles exclude local imports. Those rules
    come from each response, never from a new graph interpretation here. Cycles
    bound groups, members and witness-path nodes separately with the same top.
    Required metadata (including unabridged extraction causes) is not display-cut.
    Invalid or pre-cut inputs raise rather than becoming an exact empty answer.
    """
    _count(top, 'top')
    fans = _rows(fan_in, 'entries', 'total')
    entries = _rows(entrypoints, 'entries')
    _count(entrypoints['total_scanned'], 'total_scanned')
    if len(entries) > entrypoints['total_scanned']:
        raise ValueError('entrypoints exceed scanned population')
    component_rows = _rows(components, 'components', 'total')
    groups = circular['cycles']
    witnesses = circular['cycle_paths']
    if not isinstance(groups, list) or not isinstance(witnesses, list):
        raise ValueError('cycles and witness paths must be lists')
    if _count(circular['count'], 'cycle count') != len(groups) or len(groups) != len(witnesses):
        raise ValueError('cycle groups and witnesses must be complete')
    if not isinstance(circular.get('edge_rule'), dict):
        raise ValueError('cycles require their counting rule')
    projected_fans = []
    for row in fans:
        _count(row['fan_in'], 'fan_in')
        projected = _relationship(row, path)
        if row['fan_in'] > 0:
            projected_fans.append(projected)
    projected_entries = [_relationship(row, path) for row in entries]
    # Apply the shared predicate after path normalization for native spellings.
    active = active_entry_points(projected_entries)
    projected_components = [_relationship(row, path, component=True) for row in component_rows]
    projected_components.sort(key=lambda row: (-row['files'], row['component']))
    cycles = []
    for group, witness in zip(groups, witnesses):
        members = [_path(p, path) for p in _paths(group, 'cycle members')]
        witness_paths = [_path(p, path) for p in _paths(witness, 'cycle witness')]
        cycles.append({'members': _page(members, top), 'path': _page(witness_paths, top)})
    rules = architecture_edge_rules(fan_in, entrypoints, components, circular)
    rules['component_order'] = 'covered file count descending, then component path ascending'
    if 'cohesion_rule' in components:
        rules['cohesion_rule'] = components['cohesion_rule']
    return {'fan_in': _page(projected_fans, top), 'entrypoints': _page(active, top),
            'components': _page(projected_components, top), 'cycles': _page(cycles, top),
            'rules': deepcopy(rules), 'entry_point_filter': entry_point_filter(projected_entries),
            'metadata': _metadata(metadata, path)}
