"""Text presentation of the same bounded project map returned as JSON."""
import sys
from typing import Any, Dict, Optional

from ..base import BaseRenderer
from ...analyzers.imports.service import edge_rule_lines
from ...utils import print_json_result
from ...utils.warning_render import meta_warning_lines


def _page_heading(name: str, page: dict) -> str:
    return f"\n{name}  (showing {page['returned']} of {page['total']} observed)"


def _render_scope(scope: dict) -> list[str]:
    if not scope:
        return ['\nCode census unavailable']
    qualification = '' if scope['complete'] else ' observed; census incomplete'
    lines = [f"\nCode scope  {scope['total_code_files']} recognized code files{qualification}",
             f"  {scope['counting_rule']}"]
    for row in scope['languages']:
        lines.append(f"  {row['language']}: {row['files']} files ({row.get('capability_tier', 'unknown')})")
    hidden = scope['hidden']
    if hidden['by_cause']:
        counts = ', '.join(f'{cause}: {count}' for cause, count in sorted(hidden['by_cause'].items()))
        lines.append(f"  Hidden entries (directories count as one entry): {counts}")
    return lines


def _render_import_coverage(metadata: dict, rules: dict) -> list[str]:
    budget = metadata['scan_budget']
    exact = 'exact' if budget['exact'] is True else 'lower bound' if budget['exact'] is False else 'unavailable'
    lines = [f"\nImport coverage  {metadata['scanned_files']} files scanned; source accounting {exact}",
             f"  Scan budget: kept {budget['returned']} of {budget['total']}; limit {budget['limit']}; capped {budget['capped']}"]
    if metadata['unsupported_extensions']:
        extensions = ', '.join(f'{ext}: {count}' for ext, count in sorted(metadata['unsupported_extensions'].items()))
        lines.append(f'  Import extraction unavailable for: {extensions}')
    regime = metadata.get('autoload_regime')
    if regime:
        lines.append(f"  Framework evidence: {regime['framework']} — {regime['evidence']}; static imports can omit convention-loaded files.")
    lines.extend('  ' + line for line in edge_rule_lines(rules))
    return lines


def _render_map(facts: dict) -> list[str]:
    lines = _render_import_coverage(facts['metadata'], facts['rules'])
    page = facts['fan_in']
    lines.append(_page_heading('Most imported files', page))
    for row in page['rows']:
        lines.append(f"  {row['file']}  fan-in {row['fan_in']}, fan-out {row['fan_out']}")
    page = facts['entrypoints']
    predicate = facts['entry_point_filter']
    lines += [_page_heading('Active entrypoint candidates', page),
              f"  {predicate['fan_in_zero']} raw candidates; {predicate['active']} active; {predicate['rule']}",
              '  Path basis: ' + predicate['path_basis']]
    for row in page['rows']:
        lines.append(f"  {row['file']}  fan-out {row['fan_out']}, test-only importers {row['test_only_importers']}")
    page = facts['components']
    lines += [_page_heading('Major components', page), '  Order: ' + facts['rules']['component_order']]
    for row in page['rows']:
        cohesion = 'n/a' if row['cohesion'] is None else str(row['cohesion'])
        lines.append(f"  {row['component']}  {row['files']} files; internal {row['internal']}, outgoing {row['outgoing']}, incoming {row['incoming']}; cohesion {cohesion}")
        if row['top_bridge']:
            lines.append(f"    Bridge: {row['top_bridge']}")
        if row['cohesion'] is None and not facts['rules'].get('cohesion_rule'):
            lines.append('    ' + row['cohesion_reason'])
    if facts['rules'].get('cohesion_rule'):
        lines.append('  ' + facts['rules']['cohesion_rule'])
    page = facts['cycles']
    lines.append(_page_heading('Cycle groups', page))
    for index, row in enumerate(page['rows'], 1):
        members, witness = row['members'], row['path']
        lines.append(f"  Group {index}: {', '.join(members['rows'])} (showing {members['returned']} of {members['total']} members)")
        lines.append(f"    Witness: {' -> '.join(witness['rows'])} (showing {witness['returned']} of {witness['total']} nodes)")
    return lines


def overview_text(report: Dict[str, Any], top: int = 5) -> str:
    # Projection already bounded both formats; the renderer never reslices or scans.
    lines = [f"Overview: {report['path']}"]
    lines.extend(_render_scope(report['scope']))
    lines.append('\n' + report['reading_note'])
    status = report['map_status']
    lines.append(f'Import map: {status}')
    if report['map'] is not None:
        lines.extend(_render_map(report['map']))
    lines.append('\n' + report['diagnostic_budget']['rule'])
    lines.extend(meta_warning_lines(report, heading='Caveats'))
    lines.append('\nNext questions')
    for step in report['next_steps']:
        lines += ['  ' + step['question'], '    ' + step['command']]
    return '\n'.join(lines) + '\n'


class OverviewRenderer(BaseRenderer):
    """Render one bounded ordinary overview; shared boundaries own diagnostics."""
    ACCEPTS_TOP = True
    RENDERS_META_WARNINGS = True

    @classmethod
    def render_structure(cls, result: Dict[str, Any], format: str = 'text', top: int = 5) -> Optional[str]:
        if format == 'json':
            print_json_result(result)
            return None
        if format in ('typed', 'grep'):
            print(f'Error: --format {format} is not implemented for overview. Use --format json or --format text instead.', file=sys.stderr)
            return None
        if result.get('type') == 'overview_diff':
            if 'analysis' in result:
                from ..diff import architecture_diff_text
                return architecture_diff_text(result, title='Overview Diff')
            return super().render_structure(result, format)
        return overview_text(result, top)

    @classmethod
    def exit_code(cls, result: Dict[str, Any], format: str = 'text') -> int:
        return 2 if format in ('typed', 'grep') else 0

    @classmethod
    def _render_text(cls, result: Dict[str, Any]) -> str:
        return overview_text(result)
