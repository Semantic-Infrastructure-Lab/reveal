"""architecture:// adapter - targeted architectural brief for a directory.

Answers: "What do I need to know before editing this code?" Composes imports
graph, complexity data, and cycle analysis into facts + risks + next
commands. Scan/render logic lives here (BACK-901/BACK-957);
`cli/commands/architecture.py` is a thin argparse shim over this adapter
(the `--against <ref>` git-diff branch stays in the CLI shim — it already
delegates to the dedicated `reveal.diff.architecture_diff` module and has
its own contract/tests, so folding it into this adapter would just be
indirection without benefit).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from reveal.capabilities import scope_dict_for_path
from reveal.reveal_types import CONTRACT_VERSION

from .base import ResourceAdapter, register_adapter, register_renderer
from ..utils import print_json_result
from ..utils.query import parse_query_params
from ..utils.results import ResultBuilder

logger = logging.getLogger(__name__)

_COMPLEXITY_ENTRY_THRESHOLD = 20  # entry point complexity that warrants a warning
_FAN_IN_RISK_THRESHOLD = 8        # fan-in count that makes a file load-bearing


def _run_complex_functions(adapter: 'ArchitectureAdapter', path: Path, limit: int) -> List[Dict[str, Any]]:
    from reveal.adapters.ast import AstAdapter
    data = adapter.compose(AstAdapter, str(path), default={},
                            query=f'complexity>9&sort=-complexity&limit={limit}')
    return data.get('results', data.get('elements', []))


def _run_scope(path: Path) -> Dict[str, Any]:
    """BACK-884: files discovered/analyzed/skipped by language, with
    per-language capability tier — additive 'scope' key in JSON output.
    Shared with overview.py via capabilities.scope_dict_for_path()."""
    try:
        return scope_dict_for_path(path)
    except Exception as exc:
        logger.warning("scope census failed for %s: %s", path, exc)
        return {}


def _run_imports_analysis(adapter: 'ArchitectureAdapter', path: Path) -> Dict[str, Any]:
    # Uses ImportsAdapter's private walk/format methods directly (not
    # get_structure()) so cannot go through compose() — record the failure
    # the same way compose() would (BACK-984).
    try:
        from reveal.adapters.imports import ImportsAdapter
        importer = ImportsAdapter(str(path))
        importer._build_graph(path)
        return _format_imports_data(importer, path)
    except Exception as exc:
        adapter.record_composed_error('ImportsAdapter', path, exc)
        return {}


def _format_imports_data(adapter, path: Path) -> Dict[str, Any]:
    fan_in_data = adapter._format_fan_in()
    entrypoints_data = adapter._format_entrypoints()
    components_data = adapter._format_components()
    circular_data = adapter._format_circular()

    all_entries = fan_in_data.get('entries', [])
    raw_eps = entrypoints_data.get('entries', [])
    components = components_data.get('components', [])
    cycle_groups = circular_data.get('cycles', [])

    live_eps = [
        e for e in raw_eps
        if e.get('fan_out', 0) > 0
        and not _is_test_file(e['file'])
        and Path(e['file']).name != '__init__.py'
    ]
    core_abstractions = [e for e in all_entries if e.get('fan_in', 0) > 0]

    return {
        'entry_points': live_eps,
        'core_abstractions': core_abstractions,
        'components': components,
        'circular_groups': cycle_groups,
        # BACK-518 part 2: same coverage disclosure imports:// itself already
        # gives — without it, an unsupported-language repo (e.g. all-Lua) with
        # zero entry points/abstractions renders a blank "Architecture Brief"
        # that reads as "nothing here" rather than "not analyzed".
        'unsupported_extensions': adapter.get_metadata().get('unsupported_extensions', {}),
    }


def _run_combined_analysis(adapter: 'ArchitectureAdapter', path: Path, limit: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Run imports + complexity analysis sharing one walk, one parse per file.

    Running these as two independent full-repo walk+parse passes (the original
    shape) double-parses every file on any repo bigger than the tree-sitter
    parse cache (128 entries) — see BACK-489,
    internal-docs/design/BACK489_ARCHITECTURE_PERF_FINDINGS_2026-07-06.md.
    Piggybacking the AST/complexity collection onto the imports walk's
    per-file callback keeps each file's parse-cache entry warm between the
    two uses instead of it getting evicted by the rest of a large repo.
    """
    structures: List[Dict[str, Any]] = []

    imports_data: Dict[str, Any] = {}
    graph_built = False
    try:
        from reveal.adapters.imports import ImportsAdapter
        importer = ImportsAdapter(str(path))
        # collect_structures=True runs per-file AST analysis in the same
        # (parallelized) walk as import extraction — no second full-repo pass.
        importer._build_graph(path, collect_structures=True)
        structures = importer._structures
        graph_built = True
        imports_data = _format_imports_data(importer, path)
    except Exception as exc:
        adapter.record_composed_error('ImportsAdapter', path, exc)

    if not graph_built:
        # The shared walk never ran, so no structures were collected either —
        # fall back to complexity analysis's own independent walk.
        return _run_complex_functions(adapter, path, limit), imports_data

    try:
        from reveal.adapters.ast import AstAdapter
        # Reuses `structures` from the shared walk above (get_structure()'s
        # extra kwarg), so this can't go through compose() either — same
        # attributed-failure treatment as the ImportsAdapter branch (BACK-984).
        data = AstAdapter(str(path), f'complexity>9&sort=-complexity&limit={limit}').get_structure(structures=structures)
        complex_fns = data.get('results', data.get('elements', []))
    except Exception as exc:
        adapter.record_composed_error('AstAdapter', path, exc)
        complex_fns = []

    return complex_fns, imports_data


def _compute_risks(
    imports_data: Dict[str, Any],
    complex_fns: List[Dict[str, Any]],
    base_path: Path,
) -> List[Dict[str, Any]]:
    risks: List[Dict[str, Any]] = []

    file_max_cx: Dict[str, int] = {}
    for fn in complex_fns:
        f = fn.get('file', '')
        cx = fn.get('complexity', 0)
        if f:
            file_max_cx[f] = max(file_max_cx.get(f, 0), cx)

    for group in imports_data.get('circular_groups', []):
        count = len(group)
        rep = _relpath(group[0], base_path) if group else ''
        risks.append({
            'type': 'circular',
            'severity': 'high' if count > 10 else 'medium',
            'description': f"{count}-file circular group",
            'detail': f"{rep} + {count - 1} more" if count > 1 else rep,
            'file_count': count,
            'representative': group[0] if group else '',
        })

    for ep in imports_data.get('entry_points', []):
        cx = file_max_cx.get(ep['file'], 0)
        if cx >= _COMPLEXITY_ENTRY_THRESHOLD:
            risks.append({
                'type': 'high_complexity_entry',
                'severity': 'medium',
                'description': f"{_relpath(ep['file'], base_path)} — high-complexity entry point",
                'detail': f"fan-out {ep['fan_out']}, cx {cx}",
                'file': ep['file'],
                'complexity': cx,
                'fan_out': ep['fan_out'],
            })

    for abstraction in imports_data.get('core_abstractions', [])[:5]:
        fan_in = abstraction.get('fan_in', 0)
        if fan_in >= _FAN_IN_RISK_THRESHOLD:
            risks.append({
                'type': 'load_bearing',
                'severity': 'low',
                'description': f"{_relpath(abstraction['file'], base_path)} — load-bearing file",
                'detail': f"fan-in {fan_in}",
                'file': abstraction['file'],
                'fan_in': fan_in,
            })

    return risks


def _build_next_commands(
    path: Path,
    risks: List[Dict[str, Any]],
    imports_data: Dict[str, Any],
) -> List[str]:
    cmds: List[str] = []
    abs_path = str(path.resolve())

    if any(r['type'] == 'circular' for r in risks):
        cmds.append(f"reveal 'imports://{abs_path}?circular'")

    cx_entries = [r for r in risks if r['type'] == 'high_complexity_entry']
    if cx_entries:
        worst = max(cx_entries, key=lambda r: r.get('complexity', 0))
        cmds.append(f"reveal {worst['file']} --boundary")

    if imports_data.get('core_abstractions'):
        cmds.append(f"reveal 'ast://{abs_path}?complexity>20'")

    lb = [r for r in risks if r['type'] == 'load_bearing']
    if lb:
        top_lb = max(lb, key=lambda r: r.get('fan_in', 0))
        cmds.append(f"reveal {top_lb['file']}")

    if not cmds:
        cmds.append(f"reveal overview {abs_path}")
        cmds.append(f"reveal {abs_path}")

    return cmds


def _render_entry_points(entry_points: List[Dict], top: int, base_path: Path) -> None:
    if not entry_points:
        return
    print(f"Entry Points  ({len(entry_points)} active)")
    for ep in entry_points[:top]:
        rel = _relpath(ep['file'], base_path)
        print(f"  {rel:<54}  fan-out {ep['fan_out']}")
    print()


def _render_core_abstractions(core: List[Dict], top: int, base_path: Path) -> None:
    ranked = [e for e in core if e.get('fan_in', 0) > 0 and Path(e['file']).name != '__init__.py'][:top]
    if not ranked:
        return
    print("Core Abstractions  (most imported)")
    for e in ranked:
        rel = _relpath(e['file'], base_path)
        print(f"  {rel:<54}  fan-in {e['fan_in']}")
    print()


def _render_components(components: List[Dict], top: int, base_path: Path) -> None:
    if not components:
        return
    print(f"Components  ({len(components)} directories)")
    for c in components[:top]:
        rel = _relpath(c['component'], base_path)
        cohesion = c['cohesion']
        bar = '█' * int(cohesion * 10) + '░' * (10 - int(cohesion * 10))
        print(f"  {rel:<44}  {cohesion:.2f}  {bar}  {c['files']} files")
    print()


def _render_risks(risks: List[Dict]) -> None:
    if not risks:
        return
    print(f"Risks  ({len(risks)} found)")
    for r in risks:
        detail = r.get('detail', '')
        suffix = f"  ({detail})" if detail else ''
        print(f"  ⚠ {r['description']}{suffix}")
    print()


def _render_next_commands(commands: List[str]) -> None:
    if not commands:
        return
    print("Next Commands")
    for cmd in commands:
        print(f"  {cmd}")


def _render_brief(report: Dict[str, Any], top: int, base_path: Path, no_imports: bool = False) -> None:
    path = report['path']
    facts = report['facts']

    print(f"Architecture Brief: {path}\n")

    from reveal.adapters.imports import coverage_warning_line
    warning = coverage_warning_line(report.get('unsupported_extensions', {}))
    if warning:
        print(f"{warning}\n")

    _render_entry_points(facts.get('entry_points', []), top, base_path)
    _render_core_abstractions(facts.get('core_abstractions', []), top, base_path)
    _render_components(facts.get('components', []), top, base_path)
    _render_risks(report.get('risks', []))
    _render_next_commands(report.get('next_commands', []))

    if not no_imports:
        print("\nNote: static imports only — dynamically loaded files (plugins, registries) may appear as entry points.")


def _is_test_file(file_str: str) -> bool:
    p = Path(file_str)
    return p.name.startswith('test_') or '/test/' in file_str or '/tests/' in file_str


def _relpath(file_str: str, base_path: Optional[Path]) -> str:
    if not base_path:
        return file_str
    try:
        return Path(file_str).relative_to(base_path).as_posix()
    except ValueError:
        return file_str


class ArchitectureRenderer:
    """Renderer for architecture:// results."""

    @staticmethod
    def render_structure(result: Dict[str, Any], format: str = 'text',
                          top: int = 5, no_imports: bool = False) -> None:
        if format == 'json':
            print_json_result(result)
            return
        _render_brief(result, top, Path(result['path']), no_imports=no_imports)

    @staticmethod
    def render_error(error: Exception) -> None:
        print(f"Error building architecture brief: {error}")


@register_adapter('architecture')
@register_renderer(ArchitectureRenderer)
class ArchitectureAdapter(ResourceAdapter):
    """Adapter for a targeted architectural brief: entry points, core
    abstractions, risks, and suggested next commands for a directory."""

    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907

    def __init__(self, resource: str, query: Optional[str] = None):
        self.path = str(Path(resource).expanduser())
        self.query_params = parse_query_params(query or '', coerce=True)
        self._warn_unknown_query_params(self.query_params)  # BACK-507

    @staticmethod
    def get_help() -> Dict[str, Any]:
        return {
            'name': 'architecture',
            'description': 'Architectural brief for a directory: entry points, core abstractions, risks, and suggested next commands.',
            'syntax': 'architecture://<path>[?top=5&no_imports=true]',
            'examples': [
                {'uri': 'architecture://src', 'description': 'Brief for a subdirectory'},
                {'uri': 'architecture://.?top=10', 'description': 'Top 10 items per section'},
                {'uri': 'architecture://.?no_imports=true', 'description': 'Skip import graph analysis'},
            ],
            'features': [
                'Entry points and core abstractions (via imports:// fan-in/fan-out)',
                'Circular dependency groups',
                'High-complexity entry points and load-bearing files as risks',
                'Suggested next reveal commands',
            ],
            'notes': [
                'Static imports only — dynamically loaded files (plugins, registries) may appear as entry points.',
                'For a git-ref diff (--against REF), use the CLI subcommand form: reveal architecture <path> --against <ref>.',
            ],
            'see_also': [
                'reveal architecture <path> - CLI subcommand form',
            ],
            'output_formats': ['text', 'json'],
        }

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'architecture',
            'description': 'Targeted architectural brief (entry points, core abstractions, risks, next commands)',
            'uri_syntax': 'architecture://<path>?top=5&no_imports=true',
            'query_params': {
                'top': {'type': 'integer', 'description': 'Number of items to show per section', 'examples': ['top=10']},
                'no_imports': {'type': 'boolean', 'description': 'Skip import graph analysis', 'examples': ['no_imports=true']},
            },
            'elements': {},
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': [
                {
                    'type': 'architecture',
                    'description': 'Facts (entry points/core abstractions/components/cycles), risks, and next commands',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'facts': {'type': 'object'},
                            'risks': {'type': 'array'},
                            'next_commands': {'type': 'array'},
                        },
                    },
                },
            ],
            'example_queries': [
                {'uri': 'architecture://src', 'description': 'Brief for src/', 'output_type': 'architecture'},
            ],
            'notes': [
                'Composed from imports:// (fan-in/fan-out/circular) and ast:// (complexity) — not an independent scan.',
                'The --against <ref> diff mode is CLI-only (reveal.diff.architecture_diff), not part of this URI.',
            ],
        }

    def get_structure(self, **kwargs: Any) -> Dict[str, Any]:
        path = Path(self.path)
        top = int(self.query_params.get('top') or 5)
        no_imports = str(self.query_params.get('no_imports', False)).lower() == 'true'

        if no_imports:
            complex_fns = _run_complex_functions(self, path, top * 4)
            imports_data: Dict[str, Any] = {}
        else:
            complex_fns, imports_data = _run_combined_analysis(self, path, top * 4)

        risks = _compute_risks(imports_data, complex_fns, path)
        next_commands = _build_next_commands(path, risks, imports_data)

        report = {
            'path': str(path),
            'facts': {
                'entry_points': imports_data.get('entry_points', []),
                'core_abstractions': imports_data.get('core_abstractions', []),
                'components': imports_data.get('components', []),
                'circular_groups': imports_data.get('circular_groups', []),
            },
            'risks': risks,
            'next_commands': next_commands,
            'unsupported_extensions': imports_data.get('unsupported_extensions', {}),
            'scope': _run_scope(path),
        }

        meta = self.composed_meta()
        return ResultBuilder.create(
            result_type='architecture',
            source=self.path,
            contract_version=CONTRACT_VERSION,
            data=report,
            warnings=meta.get('warnings') if meta else None,
            errors=meta.get('errors') if meta else None,
            confidence=meta.get('confidence') if meta else None,
        )
