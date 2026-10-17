"""Returned text sections for deps://; emission and diagnostics use the shared boundary."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import BaseRenderer, capped_section
from ...utils.path_utils import to_relative_display
from ...utils.results import outcome_of

# ── Renderers ──────────────────────────────────────────────────────────────────

def _render_summary(analysis: Dict[str, Any], cycle_count: int, unused_count: int,
                    meta: Optional[Dict[str, Any]] = None,
                    skipped: Optional[List[str]] = None,
                    circular_evidence: Optional[Dict[str, Any]] = None) -> List[str]:
    lines: List[str] = []
    meta = meta or {}
    skipped = skipped or []
    total_files = analysis['total_files']
    total_imports = analysis['total_imports']
    ext_pkgs = len(analysis['external_packages'])
    stdlib_pkgs = len(analysis['stdlib_packages'])
    scanned = meta.get('scanned_files', total_files)

    # BACK-1405: `total_files` counts files WITH imports; alone it read "0 files ✅"
    # for 58 scanned PHP files whose includes are all computed paths.
    files_part = (f"{scanned:,} files ({total_files:,} with imports)"
                  if scanned != total_files else f"{total_files:,} files")
    parts = [
        files_part,
        f"{total_imports:,} imports",
        f"{ext_pkgs} unresolved packages",
        f"{stdlib_pkgs} stdlib packages",
    ]

    health_parts = []
    if 'circular' in skipped:
        health_parts.append("— circular deps not checked (--no-circular)")
    else:
        health_parts.extend(_circular_health(cycle_count, total_imports, circular_evidence))
    if 'unused' in skipped:
        health_parts.append("— unused imports not checked (--no-unused)")
    elif unused_count:
        health_parts.append(f"⚠️  {unused_count} unused import(s)")

    lines.append(f"\nSummary   {' · '.join(parts)}")
    if health_parts:
        lines.append(f"Health    {' · '.join(health_parts)}")
    failed = meta.get('files_failed_count') or 0
    if failed:
        lines.append(f"          ⚠ {failed} file(s) parsed with errors; their imports above may be incomplete")
    unsupported = meta.get('unsupported_extensions') or {}
    if unsupported:
        listing = ', '.join(f"{ext} ({n})" for ext, n in unsupported.items())
        lines.append(f"          ⚠ No import extraction for: {listing}")
    return lines


def _circular_health(cycle_count: int, total_imports: int,
                     evidence: Optional[Dict[str, Any]]) -> List[str]:
    state = evidence.get('completeness') if evidence else None
    parts = [f"❌ {cycle_count} circular dep(s)"] if cycle_count else []
    if state in ('incomplete', 'failed'):
        label = 'unavailable' if state == 'failed' else 'incomplete'
        parts.append(f"⚠ circular dependency analysis {label}")
    elif not cycle_count:
        parts.append("✅ no circular deps" if total_imports else
                     "— no imports found, so nothing to check for cycles")
    return parts


def _render_external_packages(analysis: Dict[str, Any], top: int) -> List[str]:
    lines: List[str] = []
    packages = analysis['external_packages']
    if not packages:
        return []
    shown = packages[:top]
    # BACK-1262: on a mixed-stack repo this list interleaves ecosystems --
    # pytest/pydantic/fastapi next to @mui/material and react -- sorted by
    # usage with nothing saying which is which, so it is easy to misattribute
    # at a glance. The per-file language classification already exists upstream.
    langs = analysis.get('external_package_languages', {})
    multi_stack = len({l for ls in langs.values() for l in ls}) > 1
    # BACK-1193: honest label — these are modules resolve_import() could not
    # place in-tree. Most are real third-party packages, but an unresolved
    # local (load-path boundary, missing file_index coverage) lands here too.
    lines.append(f"\nUnresolved packages (third-party or unresolved-local)  (top {len(shown)} by usage)")
    def package_line(item: tuple) -> str:
        pkg, count = item
        label = f"  [{', '.join(langs.get(pkg, [])) or '?'}]" if multi_stack else ''
        return f"  {pkg:<30} {count:>4} use(s){label}"

    lines += capped_section(packages, top, package_line, indent='  ')
    return lines


def _render_circular(cycles: List, cycle_count: int, base_path: Path, top: int) -> List[str]:
    lines: List[str] = []
    if cycle_count == 0:
        return []
    lines.append(f"\nCircular dependencies  ({cycle_count} cycle(s))")
    lines += capped_section(
        cycles, top,
        lambda cycle: f"  ❌ {' → '.join(to_relative_display(fp, base_path) for fp in cycle)}",
        indent='  ', suffix=f"  (run: reveal '{_imports_uri(base_path)}?circular')")
    return lines


def _render_unused(unused: List[Dict[str, Any]], base_path: Path, top: int) -> List[str]:
    lines: List[str] = []
    if not unused:
        return []
    lines.append(f"\nUnused imports  ({len(unused)} found)")

    def unused_line(imp: Dict[str, Any]) -> str:
        # Only names the unused analysis selected, not every name in the statement.
        names = imp.get('unused_names') or imp.get('names', [])
        name_str = f".{', '.join(names)}" if names else ''
        rel = to_relative_display(imp.get('file', '?'), base_path)
        return f"  ⚠️  {rel}:{imp.get('line', '?')}  {imp.get('module', '?')}{name_str}"

    lines += capped_section(
        unused, top, unused_line, indent='  ',
        suffix=f"  (run: reveal '{_imports_uri(base_path)}?unused')")
    return lines


def _render_top_importers(analysis: Dict[str, Any], top: int) -> List[str]:
    lines: List[str] = []
    importers = analysis['top_importers']
    if not importers:
        return []
    shown = importers[:top]
    max_count = shown[0]['count'] if shown else 1
    lines.append("\nTop importers  (files with most dependencies)")
    def importer_line(item: Dict[str, Any]) -> str:
        count = item['count']
        bar = '█' * (int(count / max_count * 15) if max_count else 0)
        return f"  {item['file']:<50} {count:>3}  {bar}"

    lines += capped_section(importers, top, importer_line, indent='  ',
                            suffix=' (--format json lists all)')
    return lines


def _imports_uri(path: Path) -> str:
    """The imports:// URI for the scanned path, runnable from any cwd (BACK-1420)."""
    return f"imports://{path}"


def _render_next_steps(path: Path) -> List[str]:
    lines: List[str] = []
    uri = _imports_uri(path)
    lines.append("\nNext steps")
    lines.append(f"  reveal '{uri}?circular'    # Full circular dep list")
    lines.append(f"  reveal '{uri}?unused'      # All unused imports")
    lines.append(f"  reveal '{uri}?violations'  # Layer violation check")
    lines.append("")
    return lines


def _render_deps(report: Dict[str, Any], top: int) -> List[str]:
    lines: List[str] = []
    from ...adapters.deps import _analyse_imports

    path_str = report['path']
    base = report['base']
    circular = report['circular']
    unused = report['unused']

    files = base.get('files', {})
    analysis = _analyse_imports(files, Path(path_str))

    cycles = circular.get('cycles', [])
    evidence = report.get('analysis', {})
    cycle_count = evidence.get('findings', {}).get('circular', circular.get('count', 0))

    lines.append("")
    lines.append(f"Dependencies: {path_str}")
    lines.append("━" * 60)

    # BACK-1261: deps.json carried autoload_regime from the start and the text
    # render never showed it, while all three sibling import-graph adapters
    # print it. On a Rails/Django/Laravel codebase the entire dependency report
    # below describes the small explicit import graph, not real usage -- the
    # one caveat a reader most needs, and the only adapter that withheld it.
    from ...adapters.imports import autoload_regime_warning, unused_not_checked_line
    base_meta = report.get('base', {}).get('metadata', {}) or {}
    warning = autoload_regime_warning(base_meta.get('autoload_regime'))
    if warning:
        lines.append(f"\n{warning}")

    skipped = report.get('skipped') or []
    lines += _render_summary(analysis, cycle_count, len(unused), base_meta, skipped=skipped,
                             circular_evidence=evidence.get('components', {}).get('circular'))
    # Per-language "not checked" is moot when --no-unused turned the check off.
    if 'unused' not in skipped:
        not_checked_note = unused_not_checked_line(base_meta.get('unused_not_checked_extensions') or {})
        if not_checked_note:
            lines.append(f"          {not_checked_note}")
    lines += _render_external_packages(analysis, top)
    lines += _render_circular(cycles, cycle_count, Path(path_str), top)
    lines += _render_unused(unused, Path(path_str), top)
    lines += _render_top_importers(analysis, top)
    lines += _render_next_steps(Path(path_str))
    return lines


def deps_text(report: Dict[str, Any], top: int = 10) -> str:
    return "\n".join(_render_deps(report, top)) + "\n"


class DepsRenderer(BaseRenderer):
    """Dependency dashboard renderer with a pure text body."""

    ACCEPTS_TOP = True

    @classmethod
    def render_structure(cls, result: Dict[str, Any], format: str = 'text',
                         top: int = 10) -> Optional[str]:
        if format == 'json' or outcome_of(result) == 'failed':
            return super().render_structure(result, format)
        return deps_text(result, top)

    @classmethod
    def _render_text(cls, result: Dict[str, Any]) -> str:
        return deps_text(result)
