"""reveal overview — one-glance codebase dashboard."""

import argparse
import json
import logging
import sys
from argparse import Namespace
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from reveal.adapters.stats import StatsAdapter
from reveal.adapters.git import GitAdapter
from reveal.adapters.ast import AstAdapter
from reveal.adapters.imports import ImportsAdapter

logger = logging.getLogger(__name__)


# Map common extensions to display names
_EXT_LANG: Dict[str, str] = {
    '.py': 'Python', '.js': 'JavaScript', '.ts': 'TypeScript',
    '.jsx': 'JavaScript', '.tsx': 'TypeScript', '.rb': 'Ruby',
    '.go': 'Go', '.rs': 'Rust', '.java': 'Java', '.kt': 'Kotlin',
    '.swift': 'Swift', '.cs': 'C#', '.cpp': 'C++', '.c': 'C',
    '.php': 'PHP', '.lua': 'Lua', '.ex': 'Elixir', '.exs': 'Elixir',
    '.zig': 'Zig', '.dart': 'Dart', '.scala': 'Scala', '.sh': 'Shell',
    '.bash': 'Shell', '.ps1': 'PowerShell', '.sql': 'SQL',
    '.md': 'Markdown', '.yaml': 'YAML', '.yml': 'YAML',
    '.toml': 'TOML', '.json': 'JSON', '.jsonl': 'JSONL',
    '.html': 'HTML', '.xml': 'XML', '.csv': 'CSV',
    '.tf': 'Terraform', '.hcl': 'HCL', '.proto': 'Protobuf',
    '.graphql': 'GraphQL', '.gql': 'GraphQL',
    '.dockerfile': 'Dockerfile', '.ini': 'INI',
    '.ipynb': 'Jupyter', '.r': 'R',
    '.xlsx': 'Excel', '.docx': 'Word', '.pptx': 'PowerPoint',
}


def create_overview_parser() -> argparse.ArgumentParser:
    """Create parser for reveal overview subcommand."""
    from reveal.cli.parser import _build_global_options_parser
    parser = argparse.ArgumentParser(
        prog='reveal overview',
        parents=[_build_global_options_parser()],
        description='One-glance codebase dashboard: languages, quality, hotspots, recent activity.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  reveal overview               # Current directory\n"
            "  reveal overview ./src         # Specific directory\n"
            "  reveal overview . --no-git    # Skip git history section\n"
            "  reveal overview . --format json  # Machine-readable output\n"
        )
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='Directory to summarise (default: current directory)'
    )
    parser.add_argument(
        '--no-git',
        action='store_true',
        help='Skip the recent git activity section'
    )
    parser.add_argument(
        '--no-imports',
        action='store_true',
        help='Skip import graph analysis (architecture section)'
    )
    parser.add_argument(
        '--top',
        metavar='N',
        type=int,
        default=5,
        help='Number of items to show in each section (default: 5)'
    )
    return parser


def run_overview(args: Namespace) -> None:
    """Run the overview dashboard."""
    path = Path(args.path).resolve()
    if not path.exists():
        print(f"Error: path '{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    top = args.top
    no_git = getattr(args, 'no_git', False)
    no_imports = getattr(args, 'no_imports', False)

    stats = _run_stats(path)
    git_log = [] if no_git else _run_git_log(path, top)
    complex_fns = _run_complex_functions(path, top)
    architecture = {} if no_imports else _run_imports_analysis(path)

    report = {
        'path': str(path),
        'stats': stats,
        'git_log': git_log,
        'complex_functions': complex_fns,
        'architecture': architecture,
    }

    if args.format == 'json':
        print(json.dumps(report, indent=2, default=str))
        return

    _render_overview(report, top)


# ── Data collectors ────────────────────────────────────────────────────────────

def _run_stats(path: Path) -> Dict[str, Any]:
    """Fetch stats and hotspots via StatsAdapter."""
    try:
        return StatsAdapter(str(path), 'hotspots=true').get_structure()
    except Exception as exc:
        logger.warning("stats collection failed for %s: %s", path, exc)
        return {}


def _run_git_log(path: Path, limit: int) -> List[Dict[str, Any]]:
    """Fetch recent commits via GitAdapter."""
    try:
        data = GitAdapter(path=str(path), query={'type': 'log', 'limit': str(limit)}).get_structure()
        return data.get('history', [])
    except Exception as exc:
        logger.warning("git log collection failed for %s: %s", path, exc)
        return []


def _run_complex_functions(path: Path, limit: int) -> List[Dict[str, Any]]:
    """Fetch top complex functions via AstAdapter."""
    try:
        data = AstAdapter(str(path), f'complexity>9&sort=-complexity&limit={limit}').get_structure()
        return data.get('results', data.get('elements', []))
    except Exception as exc:
        logger.warning("AST collection failed for %s: %s", path, exc)
        return []


def _run_imports_analysis(path: Path) -> Dict[str, Any]:
    """Build import graph once and return architectural data for overview."""
    try:
        adapter = ImportsAdapter(str(path))
        adapter._build_graph(path)
        fan_in = adapter._format_fan_in()
        entrypoints = adapter._format_entrypoints()
        components = adapter._format_components()
        circular = adapter._format_circular()
        return {
            'fan_in': fan_in.get('entries', []),
            'entrypoints': entrypoints.get('entries', []),
            'components': components.get('components', []),
            'circular_count': circular.get('count', 0),
        }
    except Exception as exc:
        logger.warning("imports analysis failed for %s: %s", path, exc)
        return {'fan_in': [], 'entrypoints': [], 'components': [], 'circular_count': 0}


def _language_breakdown(files: List[Dict[str, Any]]) -> List[tuple]:
    """Derive language→file count from stats files list."""
    counts: Counter = Counter()
    for f in files:
        path = f.get('file', '')
        ext = Path(path).suffix.lower()
        # Dockerfile has no extension
        if not ext and Path(path).name.lower() == 'dockerfile':
            lang = 'Dockerfile'
        else:
            lang = _EXT_LANG.get(ext, ext.lstrip('.').upper() if ext else 'Other')
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


# ── Renderers ──────────────────────────────────────────────────────────────────

def _render_overview(report: Dict[str, Any], top: int) -> None:
    path_str = report['path']
    path = Path(path_str)
    stats = report['stats']
    git_log = report['git_log']
    complex_fns = report['complex_functions']
    architecture = report.get('architecture', {})

    summary = stats.get('summary', {})
    hotspots = stats.get('hotspots', [])
    files_list = stats.get('files', [])

    print()
    print(f"Overview: {path_str}")
    print("━" * 60)

    _render_codebase_stats(summary)
    _render_language_breakdown(files_list, top)
    _render_quality_pulse(summary, hotspots)
    _render_hotspots(hotspots, top)
    _render_complex_functions(complex_fns, base_path=path)
    _render_architecture(architecture, complex_fns, top, base_path=path)
    _render_git_log(git_log)
    _render_next_steps()


def _render_codebase_stats(summary: Dict[str, Any]) -> None:
    if not summary:
        return
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

    print(f"\nCodebase  {' · '.join(parts)}")


def _render_language_breakdown(files_list: List[Dict[str, Any]], top: int) -> None:
    if not files_list:
        return
    langs = _language_breakdown(files_list)
    total = sum(c for _, c in langs)
    shown = langs[:top]

    print("\nLanguages")
    for lang, count in shown:
        pct = int(count / total * 100) if total else 0
        bar = '█' * (pct // 5)
        print(f"  {lang:<16} {count:>4} files  {bar} {pct}%")
    remaining = len(langs) - len(shown)
    if remaining > 0:
        print(f"  ... and {remaining} more")


def _render_quality_pulse(summary: Dict[str, Any], hotspots: List[Dict[str, Any]]) -> None:
    if not summary:
        return
    avg_q = summary.get('avg_quality_score')
    avg_cx = summary.get('avg_complexity')
    critical = sum(1 for h in hotspots if h.get('quality_score', 100) < 70)
    warning = sum(1 for h in hotspots if 70 <= h.get('quality_score', 100) < 85)

    if avg_q is None:
        return

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

    print(f"\nQuality   {icon} {' · '.join(parts)}")


def _render_hotspots(hotspots: List[Dict[str, Any]], top: int) -> None:
    if not hotspots:
        return
    print(f"\nHotspots  (top {min(len(hotspots), top)} files needing attention)")
    for h in hotspots[:top]:
        name = h.get('file', '?')
        q = h.get('quality_score', '?')
        issues = h.get('issues', [])

        if isinstance(q, (int, float)):
            icon = '❌' if q < 70 else '⚠️ '
        else:
            icon = '  '

        issue_str = f"  — {', '.join(issues)}" if issues else ''
        print(f"  {icon} {name}  {q}/100{issue_str}")
        print(f"       → reveal {name}")


def _render_complex_functions(fns: List[Dict[str, Any]], base_path: Optional[Path] = None) -> None:
    if not fns:
        return
    print(f"\nComplex functions  (complexity > 9)")
    for fn in fns:
        name = fn.get('name', '?')
        cx = fn.get('complexity', '?')
        loc = fn.get('file', '')
        line = fn.get('line', '')
        lc = fn.get('line_count', '')

        # Show relative path if possible
        if loc and base_path:
            try:
                loc = Path(loc).relative_to(base_path).as_posix()
            except ValueError:
                pass

        icon = '❌' if isinstance(cx, int) and cx >= 20 else '⚠️ '
        lc_str = f"  {lc}L" if lc else ''
        loc_str = f"  {loc}:{line}" if loc else ''
        print(f"  {icon} {name}  cx:{cx}{lc_str}{loc_str}")


def _render_architecture(
    arch: Dict[str, Any],
    complex_fns: List[Dict[str, Any]],
    top: int,
    base_path: Optional[Path] = None,
) -> None:
    """Render architectural overview: entry points, core abstractions, components."""
    fan_in = arch.get('fan_in', [])
    entrypoints = arch.get('entrypoints', [])
    components = arch.get('components', [])
    circular_count = arch.get('circular_count', 0)

    if not fan_in and not entrypoints and not components:
        return

    print("\nArchitecture")

    parts = [f"circulars: {circular_count}"]
    if complex_fns:
        sample = complex_fns[:10]
        centroid = sum(f.get('complexity', 0) for f in sample) / len(sample)
        parts.append(f"complexity centroid: {centroid:.1f}")
    print(f"  {'  ·  '.join(parts)}")

    live_eps = [
        e for e in entrypoints
        if e.get('fan_out', 0) > 0
        and not _is_test_file(e['file'])
        and Path(e['file']).name != '__init__.py'
    ]
    if live_eps:
        print(f"  Entry points  ({len(entrypoints)} fan-in=0, {len(live_eps)} active)")
        for ep in live_eps[:top]:
            rel = _relpath(ep['file'], base_path)
            print(f"    {rel:<50}  fan-out {ep['fan_out']}")

    core = [e for e in fan_in if e.get('fan_in', 0) > 0][:5]
    if core:
        print("  Core abstractions  (most imported)")
        for e in core:
            rel = _relpath(e['file'], base_path)
            print(f"    {rel:<50}  fan-in {e['fan_in']}")

    if components:
        print(f"  Components  ({len(components)} directories, by cohesion)")
        for c in components[:top]:
            rel = _relpath(c['component'], base_path)
            cohesion = c['cohesion']
            bar = '█' * int(cohesion * 10) + '░' * (10 - int(cohesion * 10))
            print(f"    {rel:<42}  {cohesion:.2f}  {bar}  {c['files']} files")


def _is_test_file(file_str: str) -> bool:
    """Return True if file looks like a test file."""
    name = Path(file_str).name
    path_norm = file_str.replace('\\', '/')
    return name.startswith('test_') or name.endswith('_test.py') or '/test' in path_norm


def _relpath(file_str: str, base_path: Optional[Path]) -> str:
    """Return path relative to base_path if possible, else the original string."""
    if base_path:
        try:
            return Path(file_str).relative_to(base_path).as_posix()
        except ValueError:
            pass
    return file_str


def _render_git_log(history: List[Dict[str, Any]]) -> None:
    if not history:
        return
    print("\nRecent changes")
    for commit in history:
        ts = commit.get('timestamp')
        age = _age_label(ts)
        msg = commit.get('message', '').strip()
        sha = commit.get('hash', '')[:7]
        # Truncate long messages
        if len(msg) > 55:
            msg = msg[:52] + '...'
        age_str = f"{age:<8}" if age else ''
        print(f"  {age_str}  {msg}  [{sha}]")


def _render_next_steps() -> None:
    print("\nNext steps")
    print("  reveal hotspots .                    # Full hotspot breakdown")
    print("  reveal check .                       # Run quality rules")
    print("  reveal deps .                        # Dependency graph")
    print("  reveal 'imports://.?rank=fan-in'     # Full fan-in ranking")
    print("  reveal 'imports://.?entrypoints'     # All entry points")
    print("  reveal pack .                        # Agent context snapshot")
    print()
