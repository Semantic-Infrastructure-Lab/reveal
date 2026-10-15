"""Returned hotspots text; shared emission preserves diagnostics and failures."""
from typing import Any, Dict, List, Optional, Set
from ..base import BaseRenderer
from ...utils.formatting import cwd_path
from ...utils.results import outcome_of

def _render_file_hotspots(hotspots: List[Dict[str, Any]], top: int, root: str='') -> List[str]:
    lines: List[str] = []
    if not hotspots:
        return lines
    lines.append(f'\nFile hotspots (top {min(len(hotspots), top)} by severity):')
    for h in hotspots:
        name = h.get('file', '?')
        quality = h.get('quality_score', '?')
        score = h.get('hotspot_score', 0)
        issues = h.get('issues', [])
        details = h.get('details', {})
        line_count = details.get('lines', '')
        if isinstance(quality, (int, float)):
            if quality < 70:
                icon = '❌'
            elif quality < 85:
                icon = '⚠️ '
            else:
                icon = '💡'
        else:
            icon = '  '
        lines_str = f'  {line_count}L' if line_count else ''
        lines.append(f'  {icon} {name}')
        lines.append(f'      quality: {quality}/100  score: {score}{lines_str}')
        if issues:
            lines.append(f"      issues: {', '.join(issues)}")
        lines.append(f'      → reveal {cwd_path(root, name)}')
    return lines


def _render_function_hotspots(fns: List[Dict[str, Any]], test_index: Optional[Set[str]]=None) -> List[str]:
    from ...adapters.hotspots import _is_covered
    lines: List[str] = []
    if not fns:
        return lines
    has_coverage_info = test_index is not None
    lines.append('\nComplex functions:')
    if has_coverage_info:
        lines.append('  (✅ = test found  ⚪ = no test found  ❔ = unknown for this language)')
    for fn in fns:
        name = fn.get('name', '?')
        cx = fn.get('complexity', '?')
        loc = fn.get('file', '')
        line = fn.get('line', '')
        line_count = fn.get('line_count', '')
        if isinstance(cx, int) and cx >= 20:
            icon = '❌'
        elif isinstance(cx, int) and cx >= 15:
            icon = '⚠️ '
        else:
            icon = '💡'
        if test_index is not None:
            hint = fn.get('has_test_hint', ...)
            if hint is None:
                cov = '❔'
            elif hint is ...:
                cov = '✅' if _is_covered(name, loc, test_index) else '⚪'
            else:
                cov = '✅' if hint else '⚪'
            cov_str = f' {cov}'
        else:
            cov_str = ''
        loc_str = f'  {loc}' if loc else ''
        lc_str = f'  ({line_count}L)' if line_count else ''
        lines.append(f'  {icon}{cov_str} {name}  complexity: {cx}{lc_str}{loc_str}:{line}')
    return lines


def _render_summary(file_hotspots: List[Dict[str, Any]], fn_hotspots: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    critical_files = sum((1 for h in file_hotspots if h.get('quality_score', 100) < 70))
    critical_fns = sum((1 for f in fn_hotspots if f.get('complexity', 0) > 20))
    total = len(file_hotspots) + len(fn_hotspots)
    lines.append('')
    if critical_files or critical_fns:
        parts = []
        if critical_files:
            parts.append(f'{critical_files} critical file(s)')
        if critical_fns:
            parts.append(f'{critical_fns} critical function(s)')
        lines.append(f"Summary: {total} hotspot(s) — {', '.join(parts)} need immediate attention ❌")
    else:
        lines.append(f'Summary: {total} hotspot(s) — no critical issues, review when convenient ⚠️')
    lines.append('')
    return lines


def _render_report(report: Dict[str, Any], top: int, test_index: Optional[Set[str]]=None) -> List[str]:
    lines: List[str] = []
    path = report['path']
    file_hotspots = report['file_hotspots']
    fn_hotspots = report['function_hotspots']
    lines.append('')
    lines.append(f'Hotspots: {path}')
    lines.append('━' * 50)
    if not file_hotspots and (not fn_hotspots):
        meta = report.get('meta') or {}
        incomplete = meta.get('errors') or meta.get('warnings')
        lines.append('\nNo hotspots found in the analyzed population.' if incomplete
                     else '\nNo hotspots found ✅  Code quality looks good.')
        lines.append('')
        return lines
    lines.extend(_render_file_hotspots(file_hotspots, top, root=path))
    lines.extend(_render_function_hotspots(fn_hotspots, test_index=test_index))
    lines.extend(_render_summary(file_hotspots, fn_hotspots))
    return lines


class HotspotsRenderer(BaseRenderer):
    @classmethod
    def render_structure(cls, result: Dict[str, Any], format: str = 'text',
                         top: int = 10, test_index: Optional[Set[str]] = None) -> Optional[str]:
        if format == 'json' or outcome_of(result) == 'failed':
            return super().render_structure(result, format)
        return '\n'.join(_render_report(result, top, test_index)) + '\n'

    @classmethod
    def _render_text(cls, result: Dict[str, Any]) -> str:
        return '\n'.join(_render_report(result, 10)) + '\n'
