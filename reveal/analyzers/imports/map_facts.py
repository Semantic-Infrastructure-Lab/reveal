"""Bounded project-map facts from complete, existing ImportView answers.

This projection does no discovery or analysis. Composition diagnostics and the
independent code census remain the caller's responsibility. Exact presentation
totals describe the supplied graph, whose scan budget and losses remain visible.
"""
from copy import deepcopy
from pathlib import Path
from typing import Any, TypedDict

from .service import architecture_edge_rules
from ...utils.entry_points import is_active_entry_point, entry_point_filter
from ...utils.path_utils import TestLayout, is_test_path, to_posix, to_relative_display


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


def _validate_rule(answer: dict[str, Any]) -> None:
    rule = answer.get('edge_rule')
    if (not isinstance(rule, dict) or not isinstance(rule.get('text'), str)
            or not rule['text'].strip() or rule.get('lazy') not in ('include', 'exclude', 'only')
            or rule.get('tests') not in ('included', 'importers_not_counted')
            or rule.get('scope') not in ('scanned_path', 'scan_root')):
        raise ValueError('map facts require their complete counting rule')


def _rows(answer: dict[str, Any], field: str, total: str | None = None) -> list[dict[str, Any]]:
    rows = answer[field]
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f'{field} must contain records')
    if total is not None and _count(answer[total], total) != len(rows):
        raise ValueError(f'{field} must be complete before map projection')
    _validate_rule(answer)
    return rows


def _page(rows: list[Any], top: int) -> BoundedRows:
    selected = rows[:top]
    return {'rows': selected, 'total': len(rows), 'returned': len(selected),
            'omitted': len(rows) - len(selected)}


def _path(value: str, base: Path) -> str:
    # Normalize native spellings before lexical path operations, also on POSIX.
    return to_relative_display(to_posix(value), base)


def _cycle(group: Any, witness: Any, base: Path, top: int) -> dict[str, BoundedRows]:
    members = [_path(p, base) for p in _paths(group, 'cycle members')]
    witness_paths = [_path(p, base) for p in _paths(witness, 'cycle witness')]
    if len(set(members)) < 2:
        raise ValueError('cycle group requires at least two distinct members')
    if not witness_paths or not set(witness_paths).issubset(members):
        raise ValueError('cycle witness requires nodes within its group')
    return {'members': _page(members, top), 'path': _page(witness_paths, top)}


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
            if not isinstance(row.get('cohesion_reason'), str) or not row['cohesion_reason'].strip():
                raise ValueError('declined cohesion requires its reason')
        elif type(cohesion) not in (int, float) or not 0 <= cohesion <= 1:
            raise ValueError('cohesion must be a fraction or declined')
        if row['top_bridge'] is not None:
            _paths([row['top_bridge']], 'top_bridge')
            result['top_bridge'] = _path(row['top_bridge'], base)
    return result


def _validate_measured_budget(value: dict[str, Any]) -> None:
    limit = value['limit']
    total, returned, exact = value['total'], value['returned'], value['exact']
    _count(total, 'scan_budget.total')
    _count(returned, 'scan_budget.returned')
    if type(exact) is not bool or value['scope'] != 'scan':
        raise ValueError('scan_budget measured accounting requires scan scope and boolean exactness')
    if returned > total or (limit is not None and returned > limit):
        raise ValueError('scan_budget returned count exceeds its total or limit')
    if value['capped'] and (exact or total <= returned):
        raise ValueError('scan_budget capped accounting requires an inexact larger total')


def validate_scan_budget(value: Any) -> None:
    """Require the existing ImportView scan-accounting record, including honest unknowns."""
    fields = {'scope', 'limit', 'total', 'returned', 'exact', 'capped'}
    if not isinstance(value, dict) or not fields.issubset(value):
        raise ValueError('scan_budget must retain its complete accounting record')
    if value['scope'] not in ('scan', 'source_candidates') or type(value['capped']) is not bool:
        raise ValueError('scan_budget requires its source scope and boolean capped state')
    if value['limit'] is not None:
        _count(value['limit'], 'scan_budget.limit')
    if value['total'] is None and value['returned'] is None and value['exact'] is None:
        if value['scope'] != 'source_candidates' or value['capped']:
            raise ValueError('scan_budget unavailable accounting requires uncapped source_candidates')
        return
    _validate_measured_budget(value)


def _metadata(metadata: dict[str, Any], base: Path) -> dict[str, Any]:
    _count(metadata.get('scanned_files'), 'scanned_files')
    validate_scan_budget(metadata.get('scan_budget'))
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


def _entrypoint_rows(entries: list[dict[str, Any]], path: Path,
                     test_layout: TestLayout | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    # Validate producer facts in their source coordinates before projecting paths.
    source_entries = [{**row, 'file': to_posix(row['file'])} for row in entries]
    classifier = test_layout.is_test if test_layout is not None else is_test_path
    for row in source_entries:
        if type(row.get('is_test')) is not bool or row['is_test'] != classifier(row['file']):
            raise ValueError('entrypoint is_test must retain the producer path classification')
        _count(row.get('test_only_importers'), 'entrypoint test_only_importers')
    projected_entries = [_relationship(row, path) for row in entries]
    active = [projected for source, projected in zip(source_entries, projected_entries)
              if is_active_entry_point(source)]
    predicate = entry_point_filter(source_entries)
    predicate['path_basis'] = 'producer paths before target-relative display'
    return active, predicate


def project_map_facts(fan_in: dict[str, Any], entrypoints: dict[str, Any],
                      components: dict[str, Any], circular: dict[str, Any],
                      metadata: dict[str, Any], *, path: Path, top: int = 5,
                      test_layout: TestLayout | None = None) -> MapFacts:
    """Project complete ImportView responses; zero shows no rows, preserving totals.

    Responses must be complete; ImportView must have no ``top`` cap. The
    entrypoints producer is uncapped and has no separate candidate total, so
    completeness there is a caller precondition, not independently proved here.
    Fan-in/components count all edges;
    entrypoints ignore test importers; cycles exclude local imports. Those rules
    come from each response, never from a new graph interpretation here. Cycles
    bound groups, members and witness-path nodes separately with the same top.
    Required metadata (including unabridged extraction causes) is not display-cut.
    Null scan accounting stays unavailable, never proof of an exact empty scan.
    Malformed or detectably cut inputs raise rather than becoming an exact empty answer.
    """
    _count(top, 'top')
    display_base = path.parent if path.is_file() else path
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
    _validate_rule(circular)
    projected_fans = []
    for row in fans:
        _count(row['fan_in'], 'fan_in')
        projected = _relationship(row, display_base)
        if row['fan_in'] > 0:
            projected_fans.append(projected)
    active, predicate = _entrypoint_rows(entries, display_base, test_layout)
    projected_components = [_relationship(row, display_base, component=True) for row in component_rows]
    projected_components.sort(key=lambda row: (-row['files'], row['component']))
    paired = sorted(zip(groups, witnesses),
                    key=lambda pair: tuple(sorted(_path(member, display_base)
                                                  for member in _paths(pair[0], 'cycle members'))))
    cycles = [_cycle(group, witness, display_base, top) for group, witness in paired]
    rules = architecture_edge_rules(fan_in, entrypoints, components, circular)
    rules['component_order'] = 'covered file count descending, then component path ascending'
    if 'cohesion_rule' in components:
        rules['cohesion_rule'] = components['cohesion_rule']
    return {'fan_in': _page(projected_fans, top), 'entrypoints': _page(active, top),
            'components': _page(projected_components, top), 'cycles': _page(cycles, top),
            'rules': deepcopy(rules), 'entry_point_filter': predicate,
            'metadata': _metadata(metadata, display_base)}
