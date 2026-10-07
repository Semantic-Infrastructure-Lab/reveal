"""Text body for overview:// results; format and diagnostics use the shared boundary.

Each section builder returns its lines; ``overview_text`` joins them. The result's
caveats are part of the body (before "Next steps"), so the renderer opts out of the
generic warning footer (RENDERS_META_WARNINGS).
"""

import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import BaseRenderer
from ...registry import display_name_for_extension
from ...utils import print_json_result
from ...utils.formatting import cwd_path
from ...utils.path_utils import is_test_path, to_relative_display
from ...utils.query_control import omitted_line
from ...utils.warning_render import meta_warning_lines


# Display labels for extensions the language registry doesn't know at all
# (BACK-431 Issue B #5) — these are document/data formats, not tree-sitter
# languages, so they aren't derivable from language_for_extension(); genuinely
# different knowledge from the language-identity table, not a parallel copy
# of it. Extensions the registry *does* know (code + config languages like
# JSON/YAML/HCL) are resolved via display_name_for_extension() instead — see
# _language_breakdown().
_NON_CODE_EXT_LABELS: Dict[str, str] = {
    '.jsonl': 'JSONL', '.html': 'HTML', '.xml': 'XML', '.csv': 'CSV',
    '.dockerfile': 'Dockerfile', '.ini': 'INI', '.ipynb': 'Jupyter',
    '.xlsx': 'Excel', '.docx': 'Word', '.pptx': 'PowerPoint',
}


def _is_test_file(file_str: str) -> bool:
    """Return True if file looks like a test file (shared classifier, BACK-1277)."""
    return is_test_path(file_str.replace('\\', '/'))


def _relpath(file_str: str, base_path: Optional[Path]) -> str:
    """Return path relative to base_path if possible, else the original string.

    BACK-1194: delegates to the shared, resolve()-aware helper — see
    to_relative_display()'s docstring for why the old lexical-only
    relative_to() let absolute paths leak through on relative CLI targets.
    """
    return to_relative_display(file_str, base_path)


def _language_breakdown(files: List[Dict[str, Any]]) -> List[tuple]:
    """Derive language→file count from stats files list."""
    counts: Counter = Counter()
    for f in files:
        path = f.get('file', '')
        ext = Path(path).suffix.lower()
        # Dockerfile has no extension
        if f.get('language'):
            lang = f['language']
        elif not ext and Path(path).name.lower() == 'dockerfile':
            lang = 'Dockerfile'
        else:
            lang = (
                display_name_for_extension(ext)
                or _NON_CODE_EXT_LABELS.get(ext)
                or (ext.lstrip('.').upper() if ext else 'Other')
            )
        counts[lang] += 1
    return counts.most_common()


def _age_label(timestamp: Optional[int]) -> str:
    """Convert unix timestamp to human-friendly age string."""
    if not timestamp:
        return ''
    now = datetime.now(timezone.utc).timestamp()
    diff = int(now - timestamp)
    if diff < 3600:
        return f"{diff // 60}m ago"
    if diff < 86400:
        return f"{diff // 3600}h ago"
    days = diff // 86400
    return f"{days}d ago"


def _render_codebase_stats(summary: Dict[str, Any]) -> List[str]:
    if not summary:
        return []
    total_files = summary.get('total_files', 0)
    total_lines = summary.get('total_lines', 0)
    total_fns = summary.get('total_functions', 0)
    total_cls = summary.get('total_classes', 0)

    parts = [f"{total_files:,} files"]
    if total_lines:
        parts.append(f"{total_lines:,} lines")
    if total_fns:
        parts.append(f"{total_fns:,} functions")
    if total_cls:
        parts.append(f"{total_cls:,} classes")

    return [f"\nCodebase  {' · '.join(parts)}"]


def _render_language_breakdown(files_list: List[Dict[str, Any]], top: int) -> List[str]:
    if not files_list:
        return []
    langs = _language_breakdown(files_list)
    total = sum(c for _, c in langs)
    shown = langs[:top]

    lines = ["\nLanguages"]
    for lang, count in shown:
        pct = int(count / total * 100) if total else 0
        bar = '█' * (pct // 5)
        lines.append(f"  {lang:<16} {count:>4} files  {bar} {pct}%")
    remaining = len(langs) - len(shown)
    if remaining > 0:
        lines.append(f"  ... and {remaining} more (use --all)")
    return lines


def _render_quality_pulse(summary: Dict[str, Any], hotspots: List[Dict[str, Any]]) -> List[str]:
    if not summary:
        return []
    avg_q = summary.get('avg_quality_score')
    avg_cx = summary.get('avg_complexity')
    critical = sum(1 for h in hotspots if h.get('quality_score', 100) < 70)
    warning = sum(1 for h in hotspots if 70 <= h.get('quality_score', 100) < 85)

    if avg_q is None:
        return []

    if avg_q >= 90:
        icon = '✅'
    elif avg_q >= 75:
        icon = '⚠️ '
    else:
        icon = '❌'

    parts = [f"{avg_q}/100 avg quality"]
    if avg_cx is not None and avg_cx > 0:
        parts.append(f"avg complexity {avg_cx:.1f}")
    if critical:
        parts.append(f"{critical} critical file(s)")
    elif warning:
        parts.append(f"{warning} warning file(s)")
    else:
        parts.append("no hotspots")

    return [f"\nQuality   {icon} {' · '.join(parts)}"]


def _render_hotspots(hotspots: List[Dict[str, Any]], top: int, root: str = '') -> List[str]:
    if not hotspots:
        return []
    lines = [f"\nHotspots  (top {min(len(hotspots), top)} files needing attention)"]
    for h in hotspots[:top]:
        name = h.get('file', '?')
        q = h.get('quality_score', '?')
        issues = h.get('issues', [])

        if isinstance(q, (int, float)):
            icon = '❌' if q < 70 else '⚠️ '
        else:
            icon = '  '

        issue_str = f"  — {', '.join(issues)}" if issues else ''
        lines.append(f"  {icon} {name}  {q}/100{issue_str}")
        lines.append(f"       → reveal {cwd_path(root, name)}")
    remaining = len(hotspots) - min(len(hotspots), top)
    if remaining > 0:
        lines.append(f"  ... and {remaining} more (use --all)")
    return lines


def _render_complex_functions(fns: List[Dict[str, Any]], base_path: Optional[Path] = None) -> List[str]:
    if not fns:
        return []
    lines = ["\nComplex functions  (complexity > 9)"]
    for fn in fns:
        name = fn.get('name', '?')
        cx = fn.get('complexity', '?')
        loc = fn.get('file', '')
        line = fn.get('line', '')
        lc = fn.get('line_count', '')

        # Show relative path if possible
        if loc and base_path:
            loc = _relpath(loc, base_path)

        icon = '❌' if isinstance(cx, int) and cx >= 20 else '⚠️ '
        lc_str = f"  {lc}L" if lc else ''
        loc_str = f"  {loc}:{line}" if loc else ''
        lines.append(f"  {icon} {name}  cx:{cx}{lc_str}{loc_str}")
    return lines


def _architecture_entry_points(entrypoints: List[Dict[str, Any]], top: int,
                               base_path: Optional[Path]) -> List[str]:
    live_eps = [
        e for e in entrypoints
        if e.get('fan_out', 0) > 0
        and not _is_test_file(e['file'])
        and Path(e['file']).name != '__init__.py'
    ]
    if not live_eps:
        return []
    lines = [f"  Entry points  ({len(entrypoints)} fan-in=0, {len(live_eps)} active)"]
    for ep in live_eps[:top]:
        rel = _relpath(ep['file'], base_path)
        lines.append(f"    {rel:<50}  fan-out {ep['fan_out']}")
    remaining = len(live_eps) - min(len(live_eps), top)
    if remaining > 0:
        lines.append(f"    ... and {remaining} more (use --all)")
    return lines


def _architecture_components(components: List[Dict[str, Any]], top: int,
                             base_path: Optional[Path]) -> List[str]:
    if not components:
        return []
    lines = [f"  Components  ({len(components)} directories, by cohesion)"]
    for c in components[:top]:
        rel = _relpath(c['component'], base_path)
        cohesion = c['cohesion']
        bar = '█' * int(cohesion * 10) + '░' * (10 - int(cohesion * 10))
        lines.append(f"    {rel:<42}  {cohesion:.2f}  {bar}  {c['files']} files")
    remaining = len(components) - min(len(components), top)
    if remaining > 0:
        lines.append(f"    ... and {remaining} more (use --all)")
    return lines


def _render_architecture(
    arch: Dict[str, Any],
    complex_fns: List[Dict[str, Any]],
    top: int,
    base_path: Optional[Path] = None,
) -> List[str]:
    """Architectural overview: entry points, core abstractions, components."""
    fan_in = arch.get('fan_in', [])
    entrypoints = arch.get('entrypoints', [])
    components = arch.get('components', [])
    circular_count = arch.get('circular_count', 0)
    unsupported = arch.get('unsupported_extensions', {})

    if not fan_in and not entrypoints and not components and not unsupported:
        return []

    lines = ["\nArchitecture"]

    from reveal.adapters.imports import coverage_warning_line, detect_autoload_regime, autoload_regime_warning
    warning = coverage_warning_line(unsupported)
    if warning:
        lines.append(f"  {warning}")

    if base_path is not None:
        regime = detect_autoload_regime(base_path)
        if regime:
            # BACK-1245: same disclosure as architecture://'s text/JSON forms
            # -- this summary view shares the identical fan-in/circular data.
            lines.append(f"  {autoload_regime_warning(regime)}")

    if not fan_in and not entrypoints and not components:
        return lines

    parts = [f"circulars: {circular_count}"]
    if complex_fns:
        sample = complex_fns[:10]
        centroid = sum(f.get('complexity', 0) for f in sample) / len(sample)
        parts.append(f"complexity centroid: {centroid:.1f}")
    lines.append(f"  {'  ·  '.join(parts)}")

    lines.extend(_architecture_entry_points(entrypoints, top, base_path))

    all_core = [e for e in fan_in if e.get('fan_in', 0) > 0]
    core = all_core[:5]
    if core:
        lines.append("  Core abstractions  (most imported)")
        for e in core:
            rel = _relpath(e['file'], base_path)
            lines.append(f"    {rel:<50}  fan-in {e['fan_in']}")
        footer = omitted_line(len(all_core), len(core), '    ')
        if footer:
            lines.append(footer)

    lines.extend(_architecture_components(components, top, base_path))
    return lines


def _render_git_log(history: List[Dict[str, Any]], foreign_root: Optional[str] = None) -> List[str]:
    if not history:
        return []
    lines = ["\nRecent changes"]
    if foreign_root:
        # foreign_root is spelled from the cwd (BACK-1366), so it can be '.' or '../..'.
        lines.append(f"  ⚠ this directory has no .git of its own — history is from the enclosing repo at '{foreign_root}'")
    for commit in history:
        ts = commit.get('timestamp')
        age = _age_label(ts)
        msg = commit.get('message', '').strip()
        sha = commit.get('hash', '')[:7]
        # Truncate long messages
        if len(msg) > 55:
            msg = msg[:52] + '...'
        age_str = f"{age:<8}" if age else ''
        lines.append(f"  {age_str}  {msg}  [{sha}]")
    return lines


def _render_next_steps(path: str) -> List[str]:
    """Commands for the scanned path, runnable from any cwd (BACK-1420)."""
    return ["\nNext steps",
            f"  reveal hotspots {path}                    # Full hotspot breakdown",
            f"  reveal check {path}                       # Run quality rules",
            f"  reveal deps {path}                        # Dependency graph",
            f"  reveal 'imports://{path}?rank=fan-in'     # Full fan-in ranking",
            f"  reveal 'imports://{path}?entrypoints'     # All entry points",
            f"  reveal pack {path}                        # Agent context snapshot",
            ""]


def _render_overview(report: Dict[str, Any], top: int) -> List[str]:
    path_str = report['path']
    path = Path(path_str)
    stats = report['stats']
    complex_fns = report['complex_functions']

    summary = stats.get('summary', {})
    hotspots = stats.get('hotspots', [])
    files_list = stats.get('files', [])

    lines = ["", f"Overview: {path_str}", "━" * 60]
    lines += _render_codebase_stats(summary)
    lines += _render_language_breakdown(files_list, top)
    lines += _render_quality_pulse(summary, hotspots)
    lines += _render_hotspots(hotspots, top, root=path_str)
    lines += _render_complex_functions(complex_fns, base_path=path)
    lines += _render_architecture(report.get('architecture', {}), complex_fns, top, base_path=path)
    lines += _render_git_log(report['git_log'], report.get('git_foreign_root'))
    # BACK-1261: the JSON documented these and the render dropped them, so a
    # section showing 5 of 97 complex functions looked complete. Rendered after
    # the body rather than inline because they describe the report as a whole.
    lines += meta_warning_lines(report, heading="Caveats")
    lines += _render_next_steps(path_str)
    return lines


def overview_text(report: Dict[str, Any], top: int) -> str:
    """The text report for one overview."""
    return '\n'.join(_render_overview(report, top)) + '\n'


class OverviewRenderer(BaseRenderer):
    """Renderer for overview:// results."""

    ACCEPTS_TOP = True  # render_structure(top=) is fed by handle_uri (--all/--verbose, ?top=N BACK-1606)
    RENDERS_META_WARNINGS = True  # the Caveats section sits before Next steps, inside the body

    @classmethod
    def render_structure(cls, result: Dict[str, Any], format: str = 'text', top: int = 5) -> Optional[str]:
        if format == 'json':
            print_json_result(result)
            return None
        if format in ('typed', 'grep'):
            # BACK-1035: previously fell through to the text renderer below,
            # silently ignoring the requested format (confirmed byte-identical
            # to --format text via diff). overview is an aggregate dashboard,
            # not a line-oriented findings list, so there's no faithful
            # typed/grep rendering to fall back to — fail loud instead of
            # lying about the output shape.
            print(f"Error: --format {format} is not yet implemented for overview. "
                  "Use --format json or --format text instead.", file=sys.stderr)
            return None
        return overview_text(result, top)

    @classmethod
    def exit_code(cls, result: Dict[str, Any], format: str = 'text') -> int:
        return 2 if format in ('typed', 'grep') else 0

    @classmethod
    def _render_text(cls, result: Dict[str, Any]) -> str:
        return overview_text(result, 5)
