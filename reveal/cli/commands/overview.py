"""reveal overview — one-glance codebase dashboard."""

import argparse
import json
import subprocess
import sys
from argparse import Namespace
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional


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

    stats = _run_stats(path)
    git_log = [] if no_git else _run_git_log(path, top)
    complex_fns = _run_complex_functions(path, top)

    report = {
        'path': str(path),
        'stats': stats,
        'git_log': git_log,
        'complex_functions': complex_fns,
    }

    if args.format == 'json':
        print(json.dumps(report, indent=2, default=str))
        return

    _render_overview(report, top)


# ── Data collectors ────────────────────────────────────────────────────────────

def _run_stats(path: Path) -> Dict[str, Any]:
    """Fetch stats and hotspots via stats://."""
    try:
        result = subprocess.run(
            ['reveal', f'stats://{path}?hotspots=true', '--format=json'],
            capture_output=True, text=True, timeout=120
        )
        if result.stdout.strip():
            return json.loads(result.stdout)
    except Exception:
        pass
    return {}


def _run_git_log(path: Path, limit: int) -> List[Dict[str, Any]]:
    """Fetch recent commits via git://."""
    try:
        result = subprocess.run(
            ['reveal', f'git://{path}?type=log&limit={limit}', '--format=json'],
            capture_output=True, text=True, timeout=30
        )
        if result.stdout.strip():
            data = json.loads(result.stdout)
            return data.get('history', [])
    except Exception:
        pass
    return []


def _run_complex_functions(path: Path, limit: int) -> List[Dict[str, Any]]:
    """Fetch top complex functions via ast://."""
    try:
        result = subprocess.run(
            ['reveal',
             f'ast://{path}?complexity>9&sort=-complexity&limit={limit}',
             '--format=json'],
            capture_output=True, text=True, timeout=60
        )
        if result.stdout.strip():
            data = json.loads(result.stdout)
            return data.get('results', data.get('elements', []))
    except Exception:
        pass
    return []


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
                loc = str(Path(loc).relative_to(base_path))
            except ValueError:
                pass

        icon = '❌' if isinstance(cx, int) and cx >= 20 else '⚠️ '
        lc_str = f"  {lc}L" if lc else ''
        loc_str = f"  {loc}:{line}" if loc else ''
        print(f"  {icon} {name}  cx:{cx}{lc_str}{loc_str}")


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
    print("  reveal hotspots .     # Full hotspot breakdown")
    print("  reveal check .        # Run quality rules")
    print("  reveal pack .         # Agent context snapshot")
    print()
