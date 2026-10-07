"""Text body for surface:// results; format and diagnostics use the shared boundary."""

from typing import Any, Dict, List, Optional

from ..base import BaseRenderer
from ...utils import print_json_result
from ...utils.results import outcome_of

_SURFACE_LABELS = {
    'cli': 'CLI commands / arguments',
    'http': 'HTTP routes',
    'mcp': 'MCP tool registrations',
    'env': 'Environment variables',
    'network': 'Network I/O (imports)',
    'db': 'Database / storage (imports)',
    'sdk': 'External SDK (imports)',
    'fs': 'Filesystem writes',
    'subprocess': 'Subprocess / shell execution',
}

_LANGUAGE_NAMES = {
    'python': 'Python', 'typescript': 'TypeScript/JavaScript', 'java': 'Java', 'csharp': 'C#',
    'php': 'PHP', 'swift': 'Swift', 'kotlin': 'Kotlin', 'ruby': 'Ruby', 'go': 'Go',
    'rust': 'Rust', 'cpp': 'C++',
}

_TAXONOMY_NOTE = "ℹ Taxonomy-based — project-specific clients outside known libraries not detected."


def _recovered_note(recovered_files: List[str], error_region_entries: int) -> str:
    """BACK-1480: files tree-sitter parsed only by guessing across an ERROR/MISSING region."""
    shown = ', '.join(recovered_files[:5])
    more = f" (+{len(recovered_files) - 5} more)" if len(recovered_files) > 5 else ''
    return (f"{len(recovered_files)} file(s) parsed with error recovery; "
            f"{error_region_entries} entries lie in a recovered region (tagged 'in_error_region', "
            f"may be fabricated): {shown}{more}")


def _unparsed_note(unparsed_files: List[str]) -> str:
    shown = ', '.join(unparsed_files[:5])
    more = f" (+{len(unparsed_files) - 5} more)" if len(unparsed_files) > 5 else ''
    return (f"{len(unparsed_files)} file(s) could not be parsed and contribute no entries: "
            f"{shown}{more}")


def _count_error_region(surfaces: Dict[str, List[Dict[str, Any]]]) -> int:
    return sum(1 for entries in surfaces.values() for e in entries if e.get('in_error_region'))


def _not_implemented(report: Dict[str, Any]) -> List[str]:
    """BACK-1332: say which zero counts are missing detectors, not clean results."""
    missing = report.get('matrix', {}).get('not_implemented', {})
    if not missing:
        return []
    lines = ["Not implemented for scanned languages (a 0 here is not a clean result):"]
    for category, langs in missing.items():
        names = ', '.join(_LANGUAGE_NAMES.get(lang, lang) for lang in langs)
        lines.append(f"  {category}: {names}")
    lines.append('')
    return lines


def _empty_report(report: Dict[str, Any], warning: str) -> List[str]:
    lines: List[str] = []
    if not warning:
        lang = report.get('unsupported_language', '')
        if lang:
            lines.append("  reveal surface currently supports Python, TypeScript, JavaScript, Java, C#, PHP, Swift, Kotlin, Ruby, Go, Rust, and C++.")
            lines.append(f"  No supported files found — detected {lang}.")
        else:
            lines.append("  No external surfaces detected.")
        lines.append('')
    lines.extend([_TAXONOMY_NOTE, ''])
    return lines


def _by_dir(rows: List[Dict[str, Any]], top: Optional[int]) -> List[str]:
    shown = rows[:top] if top is not None else rows
    width = max((len(r['dir']) for r in shown), default=0)
    lines = [f"By directory ({len(rows)}):"]
    for row in shown:
        cells = '  '.join(f"{cat} {row['counts'][cat]}" for cat in _SURFACE_LABELS if cat in row['counts'])
        lines.append(f"  {row['dir']:<{width}}  {row['total']:>4}  {cells}")
    if len(rows) > len(shown):
        lines.append(f"  … {len(rows) - len(shown)} more directories (use --top {len(rows)} to see all)")
    lines.extend(['', _TAXONOMY_NOTE, ''])
    return lines


def _entry(surface_type: str, entry: Dict[str, Any]) -> Optional[str]:
    file_path = entry.get('file', '')
    line = entry.get('line', '')
    loc = f"  {file_path}:{line}" if file_path else ''
    if entry.get('in_error_region'):
        loc += '  [parse-recovered]'
    if entry.get('declaration_shaped'):
        loc += '  [declaration-shaped: may be a variable]'

    name = entry.get('name', '?')
    if surface_type == 'cli':
        kind = entry.get('type', '')
        if kind == 'argument':
            return f"  {name}{loc}"
        if kind == 'subcommand':
            return f"  subcommand: {name}{loc}"
        if kind == 'main':
            return f"  entrypoint: {name}{loc}"
        return f"  @{entry.get('decorator', '?')}  {name}{loc}"
    if surface_type == 'http':
        # BACK-1244: flag test-spec-sourced entries inline, not just in
        # known_limits -- easy to miss a text summary note once a scan
        # scrolls past it.
        marker = '  [test]' if entry.get('test_origin') else ''
        # BACK-1417: a Rails route declared under `if Rails.env.test?` etc.
        if entry.get('condition'):
            marker += f"  [{entry['condition']}]"
        return f"  {entry.get('methods', 'ANY')}  {entry.get('path', '?')}  → {name}{loc}{marker}"
    if surface_type in ('mcp', 'env', 'subprocess'):
        return f"  {name}{loc}"
    if surface_type in ('network', 'db', 'sdk'):
        return f"  import {name}{loc}"
    if surface_type == 'fs':
        target = entry.get('target', '?')
        if target and target != '?':
            return f"  {name}({target}){loc}"
        return f"  {name}{loc}"
    return None


def surface_text(report: Dict[str, Any], top: Optional[int] = None) -> str:
    """The text report for one surface scan."""
    surfaces = report['surfaces']
    total = report['total']
    lines = ['', f"Surface: {report['path']}", "━" * 50]
    # BACK-518: warn when reveal only understood a minority of the tree — the
    # results (total>0) are a supported-language subset, or the emptiness
    # (total==0) is a false-clean on a mostly-unsupported repo, not a real
    # "no surfaces" verdict. The coverage warning is the authoritative signal
    # and supersedes the legacy detect_non_python_language decline below.
    warning = report.get('coverage', {}).get('warning', '')
    if warning:
        lines.extend([warning, ''])
    if report.get('unparsed_files'):
        lines.extend([f"⚠ {_unparsed_note(report['unparsed_files'])}", ''])
    if report.get('recovered_files'):
        lines.extend([f"⚠ {_recovered_note(report['recovered_files'], _count_error_region(surfaces))}", ''])
    lines.append(f"Total surface entries: {total}")
    if top is not None:
        unit = 'directories' if 'by_dir' in report else 'per category'
        lines.append(f"Showing top {top} {unit}  (use --top N or omit for all)")
    lines.append('')
    lines.extend(_not_implemented(report))

    if total == 0:
        lines.extend(_empty_report(report, warning))
    elif 'by_dir' in report:
        lines.extend(_by_dir(report['by_dir'], top))
    else:
        for key, label in _SURFACE_LABELS.items():
            entries = surfaces.get(key, [])
            if not entries:
                continue
            shown = entries[:top] if top is not None else entries
            lines.append(f"{label} ({len(entries)}):")
            lines.extend(text for text in (_entry(key, e) for e in shown) if text is not None)
            if len(entries) > len(shown):
                lines.append(f"  … {len(entries) - len(shown)} more "
                             f"(use --top {len(entries)} or --type {key} to see all)")
            lines.append('')
        lines.extend([_TAXONOMY_NOTE, ''])
    return '\n'.join(lines) + '\n'


class SurfaceRenderer(BaseRenderer):
    """Renderer for surface:// results."""

    @classmethod
    def render_structure(cls, result: Dict[str, Any], format: str = 'text',
                         top: Optional[int] = None) -> Optional[str]:
        if format == 'json':
            print_json_result(result)
            return None
        if outcome_of(result) == 'failed':
            return super().render_structure(result, format)
        return surface_text(result, top)

    @classmethod
    def _render_text(cls, result: Dict[str, Any]) -> str:
        return surface_text(result)
