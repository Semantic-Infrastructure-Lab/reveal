"""overview:// adapter - one-glance codebase dashboard.

Scan/render logic lives here (BACK-901/BACK-958); `cli/commands/overview.py`
is a thin argparse shim over this adapter, matching the URI/adapter contract
every other capability follows.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from reveal.capabilities import scope_dict_for_path
from reveal.errors import NotApplicableError
from reveal.reveal_types import CONTRACT_VERSION

from .ast import AstAdapter
from .base import ResourceAdapter, register_adapter, register_renderer
from .git import GitAdapter
from .imports import ImportsAdapter
from .stats import StatsAdapter
from ..utils.exclusions import exclusion_scope
from ..utils.gitignore import respect_gitignore_param
from ..utils.path_utils import as_spelled, display_name_for_path
from ..utils.query import parse_query_params
from ..rendering.adapters.overview import (  # noqa: F401 -- the render helpers are re-exported
    OverviewRenderer,
    _NON_CODE_EXT_LABELS,
    _age_label,
    _is_test_file,
    _language_breakdown,
    _relpath,
    _render_architecture,
    _render_codebase_stats,
    _render_complex_functions,
    _render_git_log,
    _render_hotspots,
    _render_language_breakdown,
    _render_next_steps,
    _render_overview,
    _render_quality_pulse,
)
from ..utils.query_parser import join_exclude_patterns, split_exclude_param
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


# ── Data collectors ────────────────────────────────────────────────────────────

def _run_stats(adapter: 'OverviewAdapter', path: Path, top: int) -> Dict[str, Any]:
    """Fetch stats and the top ``top`` hotspots via StatsAdapter.

    BACK-1042: forwards --exclude/--respect-gitignore as a raw query string
    (not compose()'s **params/urlencode path — nothing downstream in
    parse_query_params URL-decodes, so an urlencoded '*' would reach
    find_analyzable_files still percent-escaped and never match). ',', '&', '='
    and '%' inside a pattern are escaped by join_exclude_patterns (BACK-1380).

    BACK-1543: ``?top=N`` is forwarded, and stats' cut is restated as this report's
    ``hotspots``. Before, stats kept its own top 10 and dropped the total, so
    ``?top=2`` still listed 5 and "... and 5 more" counted against that hidden 10.
    """
    query = f'hotspots=true&top={top}'
    exclude_patterns = adapter.exclude_patterns
    if exclude_patterns:
        query += f'&exclude={join_exclude_patterns(exclude_patterns)}'
    query += f'&respect_gitignore={"true" if adapter.respect_gitignore else "false"}'
    stats = adapter.compose(StatsAdapter, str(path), default={}, query=query,
                            cut_as=('hotspots', 'raise ?top=N'))
    # Each file's language as the scope census names it, while the file can be
    # read (`.h` is sniffed for C++); the text census counted by extension alone
    # and contradicted the JSON scope (BACK-1428).
    for entry in stats.get('files') or []:
        entry['language'] = display_name_for_path(path / entry['file'] if path.is_dir() else path)
    return stats


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
    except (ImportError, OSError, ValueError, NotApplicableError):  # absent/unavailable git
        return None


def _run_git_log(adapter: 'OverviewAdapter', path: Path, limit: int) -> List[Dict[str, Any]]:
    """Fetch the newest ``limit`` commits via GitAdapter, and restate its cut as ``git_log``.

    BACK-1547: through ``compose`` like the other sections. It had constructed GitAdapter
    directly with a dict query (BACK-1016), so git's cut never reached this report and
    ``?top=1`` showed one commit as the whole log. GitAdapter takes ``compose``'s
    ``(resource, query-string)`` call, since it moves a query string passed as its ``ref``
    into its query. A crashed git log is still an attributed composed error, not ``[]``.

    BACK-1225: the query type is 'history', which GitAdapter's subpath dispatch recognizes
    ('log' fell through to its file-content branch on every subdirectory target). The two
    result shapes differ by key: repo-root's ``refs.get_ref_structure()`` returns
    'history', a subpath's ``files.get_file_history()`` returns 'commits', so both are read.
    """
    data = adapter.compose(GitAdapter, str(path), default={},
                           query=f'type=history&limit={limit}',
                           cut_as=('git_log', 'raise ?top=N'))
    return data.get('history', data.get('commits', []))


def _run_complex_functions(adapter: 'OverviewAdapter', path: Path, limit: int) -> List[Dict[str, Any]]:
    """Fetch top complex functions via AstAdapter."""
    data = adapter.compose(AstAdapter, str(path), default={},
                            query=f'complexity>9&sort=-complexity&limit={limit}',
                            cut_as=('complex_functions', 'raise ?top=N'))
    return data.get('results', data.get('elements', []))


def _run_imports_analysis(adapter: 'OverviewAdapter', path: Path) -> Dict[str, Any]:
    """Build import graph once and return architectural data for overview.

    Uses ImportsAdapter's private walk/format methods directly (not
    get_structure()) so cannot go through compose() — record the failure
    the same way compose() would (BACK-984).
    """
    try:
        importer = ImportsAdapter(str(path))
        # BACK-1495: this call bypasses compose(), so --exclude has to be scoped here.
        with exclusion_scope(path if path.is_dir() else path.parent, adapter.exclude_patterns):
            importer._build_graph(path)
        warnings = importer.integrity_warnings(path)  # BACK-1598, BACK-1753
        if warnings:
            adapter.fold_meta({'warnings': warnings})
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


@register_adapter('overview')
@register_renderer(OverviewRenderer)
class OverviewAdapter(ResourceAdapter):
    """Adapter for the one-glance codebase dashboard: languages, quality,
    hotspots, architecture, recent activity."""
    HELP_CLUSTER = 'Code Analysis'

    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907
    RESOURCE_IS_PATH = True  # a nonexistent path is an error, not an empty result (BACK-1321)
    # --no-gitignore (BACK-1202). --all lifts ?top=N for the data, not only the render
    # (BACK-1543): overview://X --all printed "showing 5 of 387" complex functions.
    CLI_QUERY_FLAGS = {'all': 'top=1000000', 'respect_gitignore': 'respect_gitignore=false'}

    def __init__(self, resource: str, query: Optional[str] = None):
        self.path = str(Path(resource).expanduser())
        self.query_params = parse_query_params(query or '', coerce=True)
        self._warn_unknown_query_params(self.query_params)  # BACK-507
        # BACK-1042
        exclude_param = self.query_params.get('exclude')
        self.exclude_patterns: List[str] = (
            split_exclude_param(exclude_param)
        )
        self.respect_gitignore: bool = respect_gitignore_param(self.query_params)

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
                '?exclude= (BACK-1042) applies to the stats/hotspots and scope sections only — '
                'the architecture (imports://) and complex_functions (ast://) sections do not yet honor it.',
                'Every section skips what git ignores (tracked files are never skipped); '
                'respect_gitignore=false / --no-gitignore includes it everywhere (BACK-1386).',
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

        stats = _run_stats(self, path, top)
        git_log = [] if no_git else _run_git_log(self, path, top)
        git_foreign_root: Optional[Path] = None
        if git_log:
            git_root = _resolve_git_root(path)
            # Compare resolved: 'overview://.' at a repo root is not foreign to itself.
            if git_root is not None and git_root.resolve() != path.resolve():
                git_foreign_root = git_root
        complex_fns = _run_complex_functions(self, path, top)
        architecture = {} if no_imports else _run_imports_analysis(self, path)
        _relativize_paths(complex_fns, architecture, path)
        _annotate_provenance(complex_fns, architecture)

        report: Dict[str, Any] = {
            'path': str(path),
            'stats': stats,
            'git_log': git_log,
            'git_foreign_root': as_spelled(git_foreign_root, path) if git_foreign_root else None,
            'complex_functions': complex_fns,
            'architecture': architecture,
            'scope': _run_scope(self, path),
        }

        meta = self.composed_meta()
        return ResultBuilder.create(
            result_type='overview',
            source=self.path,
            contract_version=CONTRACT_VERSION,
            scope=report.pop('scope'),
            data=report,
            warnings=meta.get('warnings') if meta else None,
            errors=meta.get('errors') if meta else None,
            confidence=meta.get('confidence') if meta else None,
        )
