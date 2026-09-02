"""overview:// adapter - one-glance codebase dashboard.

Scan/render logic lives here (BACK-901/BACK-958); `cli/commands/overview.py`
is a thin argparse shim over this adapter, matching the URI/adapter contract
every other capability follows.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from reveal.capabilities import scope_dict_for_path
from reveal.registry import display_name_for_extension
from reveal.reveal_types import CONTRACT_VERSION

from .ast import AstAdapter
from .base import ResourceAdapter, register_adapter, register_renderer
from .git import GitAdapter
from .imports import ImportsAdapter
from .stats import StatsAdapter
from ..utils import print_json_result
from ..utils.query import parse_query_params
from ..utils.results import ResultBuilder

logger = logging.getLogger(__name__)


# Large-but-finite stand-in for "no cap" on overview's --top-bounded sections
# (Languages, Hotspots, Entry points, Components; also the Complex-functions and
# git-log data fetch limits). Keeps every `[:top]`/`min(len(x), top)` call site
# plain int arithmetic instead of needing None-handling threaded through each
# renderer/collector — and a real "-n <huge>" git-log/AST query behaves exactly
# like an uncapped one, bounded by the actual repo/result size either way
# (BACK-1226).
UNLIMITED_TOP = 10**9


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


# ── Data collectors ────────────────────────────────────────────────────────────

def _run_stats(adapter: 'OverviewAdapter', path: Path) -> Dict[str, Any]:
    """Fetch stats and hotspots via StatsAdapter.

    BACK-1042: forwards --exclude/--respect-gitignore as a raw query string
    (not compose()'s **params/urlencode path — nothing downstream in
    parse_query_params URL-decodes, so an urlencoded '*'/',' would reach
    find_analyzable_files still percent-escaped and never match).
    """
    query = 'hotspots=true'
    exclude_patterns = adapter.exclude_patterns
    if exclude_patterns:
        query += f'&exclude={",".join(exclude_patterns)}'
    query += f'&respect_gitignore={"true" if adapter.respect_gitignore else "false"}'
    return adapter.compose(StatsAdapter, str(path), default={}, query=query)


def _run_scope(adapter: 'OverviewAdapter', path: Path) -> Dict[str, Any]:
    """BACK-884: files discovered/analyzed/skipped by language, with
    per-language capability tier — additive 'scope' key in JSON output.
    Shared with architecture.py via capabilities.scope_dict_for_path().

    BACK-1016: routes failures through record_composed_error() (in addition
    to the existing logger.warning) so a crashed census is reflected in
    meta.errors/confidence instead of silently rendering as an empty-but-
    trusted 'scope': {} — the same fix BACK-984 already gave every other
    sibling-adapter site in this file.

    BACK-1042: honors --exclude/--respect-gitignore so the scope census
    agrees with what stats/check actually skipped.
    """
    try:
        return scope_dict_for_path(
            path,
            exclude_patterns=adapter.exclude_patterns,
            respect_gitignore=adapter.respect_gitignore,
        )
    except Exception as exc:
        logger.warning("scope census failed for %s: %s", path, exc)
        adapter.record_composed_error('scope_dict_for_path', path, exc)
        return {}


def _resolve_git_root(path: Path) -> Optional[Path]:
    """Discover the git repo root enclosing *path* (BACK-516).

    ``GitAdapter``/pygit2 walk up to the nearest ancestor ``.git`` unconditionally
    (correct git behavior), so a directory with no ``.git`` of its own — a vendored
    tree, a sample corpus, a submodule checked out without its own ``.git`` — silently
    inherits its enclosing repo's history. Returns the discovered root so callers can
    detect and disclose that mismatch; returns ``None`` if *path* isn't inside a repo
    at all.
    """
    try:
        metadata = GitAdapter(path=str(path)).get_metadata()
        root = metadata.get('path')
        return Path(root).resolve() if root else None
    except Exception:
        return None


def _run_git_log(adapter: 'OverviewAdapter', path: Path, limit: int) -> List[Dict[str, Any]]:
    """Fetch recent commits via GitAdapter.

    BACK-1016: a 13th sibling-adapter-construction site the BACK-984 sweep
    missed — it constructs GitAdapter directly (query is a dict, not the
    canonical query string compose() expects, so it can't route through
    compose() as-is) and previously swallowed a crashed git log into `[]`
    with only a logger.warning, no envelope error. record_composed_error()
    closes that the same way BACK-984 did for every compose()-based site.

    BACK-1225: query type must be 'history', not 'log' -- GitAdapter's
    subpath-scoped dispatch only recognizes the exact string 'history' (see
    adapter.py get_structure()); 'log' fell through to its file-content
    branch and failed with a misdirected error on every subdirectory target
    (i.e. every overview:// call below repo root). At repo root (no subpath)
    this changes nothing: GitAdapter's ref-based branch only ever checked
    query_type for truthiness, never its exact value. The two GitAdapter
    result shapes differ by key -- repo-root's refs.get_ref_structure()
    returns 'history'; a subpath's files.get_file_history() returns
    'commits' -- so both are checked here."""
    try:
        data = GitAdapter(path=str(path), query={'type': 'history', 'limit': str(limit)}).get_structure()
        return data.get('history', data.get('commits', []))
    except Exception as exc:
        logger.warning("git log collection failed for %s: %s", path, exc)
        adapter.record_composed_error('GitAdapter', path, exc)
        return []


def _run_complex_functions(adapter: 'OverviewAdapter', path: Path, limit: int) -> List[Dict[str, Any]]:
    """Fetch top complex functions via AstAdapter."""
    data = adapter.compose(AstAdapter, str(path), default={},
                            query=f'complexity>9&sort=-complexity&limit={limit}')
    return data.get('results', data.get('elements', []))


def _run_imports_analysis(adapter: 'OverviewAdapter', path: Path) -> Dict[str, Any]:
    """Build import graph once and return architectural data for overview.

    Uses ImportsAdapter's private walk/format methods directly (not
    get_structure()) so cannot go through compose() — record the failure
    the same way compose() would (BACK-984).
    """
    try:
        importer = ImportsAdapter(str(path))
        importer._build_graph(path)
        fan_in = importer._format_fan_in()
        entrypoints = importer._format_entrypoints()
        components = importer._format_components()
        circular = importer._format_circular()
        return {
            'fan_in': fan_in.get('entries', []),
            'entrypoints': entrypoints.get('entries', []),
            'components': components.get('components', []),
            'circular_count': circular.get('count', 0),
            # BACK-518 part 2: disclose files the import graph couldn't cover,
            # same signal imports:// itself already gives — otherwise an
            # unsupported-language repo (all fan_in/entrypoints/components
            # empty) renders as a blank Architecture section, which reads as
            # "nothing here" rather than "not analyzed".
            'unsupported_extensions': importer.get_metadata().get('unsupported_extensions', {}),
        }
    except Exception as exc:
        adapter.record_composed_error('ImportsAdapter', path, exc)
        return {'fan_in': [], 'entrypoints': [], 'components': [], 'circular_count': 0, 'unsupported_extensions': {}}


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


# ── Renderers ──────────────────────────────────────────────────────────────────

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
        print(f"  ... and {remaining} more (use --all)")


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
    remaining = len(hotspots) - min(len(hotspots), top)
    if remaining > 0:
        print(f"  ... and {remaining} more (use --all)")


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
            loc = _relpath(loc, base_path)

        icon = '❌' if isinstance(cx, int) and cx >= 20 else '⚠️ '
        lc_str = f"  {lc}L" if lc else ''
        loc_str = f"  {loc}:{line}" if loc else ''
        print(f"  {icon} {name}  cx:{cx}{lc_str}{loc_str}")


def _is_test_file(file_str: str) -> bool:
    """Return True if file looks like a test file."""
    name = Path(file_str).name
    path_norm = file_str.replace('\\', '/')
    return name.startswith('test_') or name.endswith('_test.py') or '/test' in path_norm


def _relpath(file_str: str, base_path: Optional[Path]) -> str:
    """Return path relative to base_path if possible, else the original string.

    BACK-1194: delegates to the shared, resolve()-aware helper — see
    to_relative_display()'s docstring for why the old lexical-only
    relative_to() let absolute paths leak through on relative CLI targets.
    """
    from ..utils.path_utils import to_relative_display
    return to_relative_display(file_str, base_path)


def _relativize_paths(
    complex_fns: List[Dict[str, Any]],
    architecture: Dict[str, Any],
    base_path: Path,
) -> None:
    """Relativize the same file-path fields the text renderer already
    relativizes (via `_relpath`), but in the raw structures the JSON
    output serializes directly — get_structure() never routed through
    the text renderer, so `--format json` leaked absolute host paths
    (analyst's filesystem layout/username) even after BACK-1194 fixed
    the text path. Mutates in place.
    """
    for fn in complex_fns:
        if fn.get('file'):
            fn['file'] = _relpath(fn['file'], base_path)
    for section in ('fan_in', 'entrypoints'):
        for entry in architecture.get(section, []):
            if entry.get('file'):
                entry['file'] = _relpath(entry['file'], base_path)
    for component in architecture.get('components', []):
        if component.get('component'):
            component['component'] = _relpath(component['component'], base_path)
        if component.get('top_bridge'):
            component['top_bridge'] = _relpath(component['top_bridge'], base_path)


def _annotate_provenance(complex_fns: List[Dict[str, Any]], architecture: Dict[str, Any]) -> None:
    """Tag each ranked entry with its provenance classification (BACK-1195):
    'test' / 'vendor' / 'minified' / None (first-party). Live evidence on a
    real corpus: overview://'s top-5 components-by-cohesion and top
    complexity findings were 100% vendored/generated/test code, with the one
    genuine first-party finding ranked below the noise — a reader had no way
    to discount the noise in place without this. Must run AFTER
    `_relativize_paths()` so path fields are already relative to the scan
    root (classification only needs the relative path components, not the
    absolute one). Mutates in place.
    """
    from ..utils.path_utils import classify_path_provenance

    def provenance_for(file_str: Optional[str]) -> Optional[str]:
        if not file_str:
            return None
        rel = Path(file_str)
        return classify_path_provenance(rel.parts[:-1], rel.name)

    for fn in complex_fns:
        fn['provenance'] = provenance_for(fn.get('file'))
    for section in ('fan_in', 'entrypoints'):
        for entry in architecture.get(section, []):
            entry['provenance'] = provenance_for(entry.get('file'))
    for component in architecture.get('components', []):
        component['provenance'] = provenance_for(component.get('component'))


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
    unsupported = arch.get('unsupported_extensions', {})

    if not fan_in and not entrypoints and not components and not unsupported:
        return

    print("\nArchitecture")

    from reveal.adapters.imports import coverage_warning_line, detect_autoload_regime, autoload_regime_warning
    warning = coverage_warning_line(unsupported)
    if warning:
        print(f"  {warning}")

    if base_path is not None:
        regime = detect_autoload_regime(base_path)
        if regime:
            # BACK-1245: same disclosure as architecture://'s text/JSON forms
            # -- this summary view shares the identical fan-in/circular data.
            print(f"  {autoload_regime_warning(regime)}")

    if not fan_in and not entrypoints and not components:
        return

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
        remaining = len(live_eps) - min(len(live_eps), top)
        if remaining > 0:
            print(f"    ... and {remaining} more (use --all)")

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
        remaining = len(components) - min(len(components), top)
        if remaining > 0:
            print(f"    ... and {remaining} more (use --all)")


def _render_git_log(history: List[Dict[str, Any]], foreign_root: Optional[str] = None) -> None:
    if not history:
        return
    print("\nRecent changes")
    if foreign_root:
        print(f"  ⚠ this directory has no .git of its own — history is from the enclosing repo {foreign_root}")
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
    _render_git_log(git_log, report.get('git_foreign_root'))
    # BACK-1261: the JSON documented these and the render dropped them, so a
    # section showing 5 of 97 complex functions looked complete. Printed after
    # the body rather than inline because they describe the report as a whole.
    from ..utils.warning_render import render_meta_warnings
    render_meta_warnings(report, heading="Caveats")
    _render_next_steps()


class OverviewRenderer:
    """Renderer for overview:// results."""

    @staticmethod
    def render_structure(result: Dict[str, Any], format: str = 'text', top: int = 5) -> None:
        if format == 'json':
            print_json_result(result)
            return
        if format in ('typed', 'grep'):
            # BACK-1035: previously fell through to the text renderer below,
            # silently ignoring the requested format (confirmed byte-identical
            # to --format text via diff). overview is an aggregate dashboard,
            # not a line-oriented findings list, so there's no faithful
            # typed/grep rendering to fall back to — fail loud instead of
            # lying about the output shape.
            import sys
            print(
                f"Error: --format {format} is not yet implemented for overview. "
                "Use --format json or --format text instead.",
                file=sys.stderr,
            )
            sys.exit(2)
        _render_overview(result, top)

    @staticmethod
    def render_error(error: Exception) -> None:
        print(f"Error building overview: {error}")


@register_adapter('overview')
@register_renderer(OverviewRenderer)
class OverviewAdapter(ResourceAdapter):
    """Adapter for the one-glance codebase dashboard: languages, quality,
    hotspots, architecture, recent activity."""
    HELP_CLUSTER = 'Code Analysis'

    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907

    def __init__(self, resource: str, query: Optional[str] = None):
        self.path = str(Path(resource).expanduser())
        self.query_params = parse_query_params(query or '', coerce=True)
        self._warn_unknown_query_params(self.query_params)  # BACK-507
        # BACK-1042
        exclude_param = self.query_params.get('exclude')
        self.exclude_patterns: List[str] = (
            [p for p in str(exclude_param).split(',') if p] if exclude_param else []
        )
        self.respect_gitignore: bool = str(self.query_params.get('respect_gitignore', True)).lower() != 'false'

    @staticmethod
    def get_help() -> Dict[str, Any]:
        return {
            'name': 'overview',
            'description': 'One-glance codebase dashboard: languages, quality, hotspots, recent activity.',
            'syntax': 'overview://<path>[?top=5&no_git=true&no_imports=true]',
            'examples': [
                {'uri': 'overview://src', 'description': 'Dashboard for src/'},
                {'uri': 'overview://.?no_git=true', 'description': 'Skip the recent-activity section'},
                {'uri': 'overview://.?top=10', 'description': 'Top 10 items per section'},
            ],
            'features': [
                'Language breakdown, codebase size, quality pulse',
                'Hotspots (via stats://) and complex functions (via ast://)',
                'Architecture summary: entry points, core abstractions, components (via imports://)',
                'Recent git activity (via git://)',
                "complex_functions[]/architecture.{fan_in,entrypoints,components}[] each carry a "
                "'provenance' field: 'test'/'vendor'/'minified'/null (first-party) — BACK-1195, "
                'so a reader can discount vendored/generated/test noise in the ranking in place.',
            ],
            'notes': [
                'Static imports only for the architecture section — dynamically loaded files may appear as entry points.',
                'exclude/respect_gitignore (BACK-1042) apply to the stats/hotspots and scope sections only — '
                'the architecture (imports://) and complex_functions (ast://) sections do not yet honor them.',
                'BACK-1178: the CLI subcommand form (`reveal overview <path> --format '
                'json`) and this URI form intentionally carry different '
                'contract_version/meta envelopes — subcommand-form is frozen at '
                'v1.0 with no meta block (BACK-906, backward-compat guarantee for '
                'existing --format json consumers), URI-form is on v1.1 with a '
                'meta block (confidence/warnings/errors, BACK-885/891). The '
                'underlying data fields are otherwise the same.',
            ],
            'see_also': [
                'reveal overview <path> - CLI subcommand form',
            ],
            'output_formats': ['text', 'json'],
        }

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'overview',
            'description': 'One-glance codebase dashboard (languages, quality, hotspots, architecture, recent activity)',
            'uri_syntax': 'overview://<path>?top=5&no_git=true&no_imports=true&exclude=pat&respect_gitignore=true',
            'query_params': {
                'top': {'type': 'integer', 'description': 'Number of items to show per section', 'examples': ['top=10']},
                'no_git': {'type': 'boolean', 'description': 'Skip the recent git activity section', 'examples': ['no_git=true']},
                'no_imports': {'type': 'boolean', 'description': 'Skip import graph analysis (architecture section)', 'examples': ['no_imports=true']},
                'exclude': {'type': 'string', 'description': 'Comma-separated glob patterns to exclude from the stats/hotspots and scope sections (BACK-1042)', 'examples': ['exclude=dist/*,*.min.js']},
                'respect_gitignore': {'type': 'boolean', 'description': 'Respect .gitignore for the stats/hotspots and scope sections (default: true)', 'examples': ['respect_gitignore=false']},
            },
            'elements': {},
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': [
                {
                    'type': 'overview',
                    'description': 'Stats/hotspots, complex functions, architecture summary, recent git log',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'stats': {'type': 'object'},
                            'git_log': {'type': 'array'},
                            'architecture': {'type': 'object'},
                        },
                    },
                },
            ],
            'example_queries': [
                {'uri': 'overview://src', 'description': 'Dashboard for src/', 'output_type': 'overview'},
            ],
            'notes': [
                'Composed from stats://, git://, ast://, and imports:// — not an independent scan.',
            ],
        }

    def get_structure(self, **kwargs: Any) -> Dict[str, Any]:
        path = Path(self.path)
        top = self.int_param('top', 5)
        no_git = str(self.query_params.get('no_git', False)).lower() == 'true'
        no_imports = str(self.query_params.get('no_imports', False)).lower() == 'true'

        stats = _run_stats(self, path)
        git_log = [] if no_git else _run_git_log(self, path, top)
        git_foreign_root: Optional[Path] = None
        if git_log:
            git_root = _resolve_git_root(path)
            if git_root is not None and git_root != path:
                git_foreign_root = git_root
        complex_fns = _run_complex_functions(self, path, top)
        architecture = {} if no_imports else _run_imports_analysis(self, path)
        _relativize_paths(complex_fns, architecture, path)
        _annotate_provenance(complex_fns, architecture)

        report = {
            'path': str(path),
            'stats': stats,
            'git_log': git_log,
            'git_foreign_root': str(git_foreign_root) if git_foreign_root else None,
            'complex_functions': complex_fns,
            'architecture': architecture,
            'scope': _run_scope(self, path),
        }

        meta = self.composed_meta()
        return ResultBuilder.create(
            result_type='overview',
            source=self.path,
            contract_version=CONTRACT_VERSION,
            data=report,
            warnings=meta.get('warnings') if meta else None,
            errors=meta.get('errors') if meta else None,
            confidence=meta.get('confidence') if meta else None,
        )
