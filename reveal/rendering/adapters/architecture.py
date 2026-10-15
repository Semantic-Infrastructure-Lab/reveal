"""Returned architecture briefs; shared emission owns failures and output."""
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import BaseRenderer, capped_section
from ...utils.results import outcome_of
from ...utils.warning_render import meta_warning_lines


def _render_entry_points(entry_points: List[Dict], top: int, base_path: Path) -> List[str]:
    from ...adapters.architecture import _relpath
    if not entry_points:
        return []
    return [f"Entry Points  ({len(entry_points)} active)", *capped_section(
        entry_points, top,
        lambda ep: f"  {_relpath(ep['file'], base_path):<54}  fan-out {ep['fan_out']}",
        indent='  ', suffix=' (--format json lists all)'), '']


def _render_core_abstractions(core: List[Dict], top: int, base_path: Path) -> List[str]:
    from ...adapters.architecture import _relpath, _is_reexport_file
    candidates = [e for e in core if e.get('fan_in', 0) > 0 and not _is_reexport_file(e['file'])]
    if not candidates:
        return []
    return ['Core Abstractions  (most imported)', *capped_section(
        candidates, top,
        lambda e: f"  {_relpath(e['file'], base_path):<54}  fan-in {e['fan_in']}",
        indent='  ', suffix=' (--format json lists all)'), '']


def _render_components(components: List[Dict], top: int, base_path: Path) -> List[str]:
    from ...adapters.architecture import _relpath
    if not components:
        return []
    def component_line(c):
        cohesion = c['cohesion']
        bar = '█' * int(cohesion * 10) + '░' * (10 - int(cohesion * 10))
        return f"  {_relpath(c['component'], base_path):<44}  {cohesion:.2f}  {bar}  {c['files']} files"
    return [f"Components  ({len(components)} directories)", *capped_section(
        components, top, component_line, indent='  ', suffix=' (--format json lists all)'), '']


def _render_risks(risks: List[Dict]) -> List[str]:
    if not risks:
        return []
    lines = [f"Risks  ({len(risks)} found)"]
    for risk in risks:
        detail = risk.get('detail', '')
        suffix = f"  ({detail})" if detail else ''
        lines.append(f"  ⚠ {risk['description']}{suffix}")
    return [*lines, '']


def _render_next_commands(commands: List[str]) -> List[str]:
    return ['Next Commands', *(f'  {cmd}' for cmd in commands)] if commands else []


def _render_brief(report: Dict[str, Any], top: int, base_path: Path,
                  no_imports: bool = False) -> List[str]:
    from ...adapters.imports import coverage_warning_line
    facts = report['facts']
    lines = [f"Architecture Brief: {report['path']}\n"]
    warning = coverage_warning_line(report.get('unsupported_extensions', {}))
    if warning:
        lines.append(f'{warning}\n')
    lines += _render_entry_points(facts.get('entry_points', []), top, base_path)
    lines += _render_core_abstractions(facts.get('core_abstractions', []), top, base_path)
    lines += _render_components(facts.get('components', []), top, base_path)
    lines += _render_risks(report.get('risks', []))
    lines += _render_next_commands(report.get('next_commands', []))
    if not no_imports:
        # The adapter records framework evidence; rendering never rediscovers it.
        regime_warning = next((r.get('detail') for r in report.get('risks', [])
                               if r.get('type') == 'autoload_regime'), None)
        if regime_warning:
            lines.append(f'\n{regime_warning}')
        lines.append('\nNote: static imports only — dynamically loaded files (plugins, registries) may appear as entry points.')
    lines += meta_warning_lines(report, heading='Caveats')
    return lines


class ArchitectureRenderer(BaseRenderer):
    ACCEPTS_TOP = True
    RENDERS_META_WARNINGS = True

    @classmethod
    def render_structure(cls, result: Dict[str, Any], format: str = 'text',
                         top: int = 5, no_imports: bool = False) -> Optional[str]:
        if format == 'json' or outcome_of(result) == 'failed':
            return super().render_structure(result, format)
        return '\n'.join(_render_brief(result, top, Path(result['path']),
                         result.get('no_imports', no_imports))) + '\n'

    @classmethod
    def _render_text(cls, result: Dict[str, Any]) -> str:
        return cls.render_structure(result) or ''
