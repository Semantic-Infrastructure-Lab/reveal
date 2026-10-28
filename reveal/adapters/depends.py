"""depends:// adapter — Inverse module dependency graph.

Answer "what depends on this module?" by inverting the import graph.

A retired spelling (BACK-1054 slice S6, Q8): the graph is the one imports:// engine's build
(``service.analyze``, under depends' own scan root, file cap and extension family) and the
answer keeps depends' shapes, warnings and exit code (0 on a partial answer, BACK-2181) until the
cut; ``imports://<path>?importers`` is the replacement.

Usage:
    reveal depends://src/utils.py          # Who imports utils.py?
    reveal depends://src/models/           # Who imports anything in models/?
    reveal 'depends://src?top=20'          # Most-imported files
    reveal 'depends://src?format=dot'      # GraphViz output
"""

from ..utils.query_control import ScanBudget

import os
from pathlib import Path
from typing import Dict, Any, Optional
from reveal.reveal_types import CONTRACT_VERSION

from .base import ResourceAdapter, register_adapter, register_renderer
from ..analyzers.imports.diagnostics import parse_failure_warning, worker_lost_warning
from ..utils import print_json_result
from ..analyzers.imports import ImportGraph, ImportStatement
from ..analyzers.imports.types import ImportAnalysis
from ..analyzers.imports.base import get_extractor, get_all_extensions, get_supported_languages
from ..analyzers.imports.generic import CImportExtractor, CppImportExtractor
from ..analyzers.imports import resolution
from ..analyzers.imports import service as import_analysis
from ..analyzers.imports.types import LAZY_INCLUDE
from ..utils.query import parse_query_params
from ..utils.results import ResultBuilder, note_truncation, note_warning
from ..utils.path_utils import (
    traversal_failed_warning,
    resolve_project_root,
    to_relative_display,
    _PACKAGE_ROOT_MARKERS,
    _VCS_ROOT_MARKERS,
    _has_package_marker,
    _has_vcs_marker,
)

# BACK-612: the marker sets and per-tier predicates now live in
# reveal.utils.path_utils (the single home shared with config/I002/D005) —
# imported above. Kept here: the back-compat union alias
# (`_PROJECT_ROOT_MARKERS`, "is there ANY marker in this one dir") and the
# `_has_project_marker` helper the depends tests import.
_PROJECT_ROOT_MARKERS = _PACKAGE_ROOT_MARKERS + _VCS_ROOT_MARKERS

# BACK-675: C and C++ share one #include header namespace and the same
# preprocessor-style resolver (_resolve_include), but the extractor registry
# gives '.h' to CImportExtractor alone (CppImportExtractor's extensions
# deliberately omit '.h' to avoid a duplicate-registration conflict with C).
# Most C++ headers are named '.h', not '.hpp' -- so scoping a '.h' target's
# scan to CImportExtractor's own extensions {'.c', '.h'} (BACK-525 layer 4)
# silently drops every .cpp/.cc/.cxx/.hpp file from the parse corpus, and
# depends:// can never see a .cpp file as an importer of its own header.
_C_CPP_FAMILY_EXTENSIONS = frozenset(CImportExtractor.extensions | CppImportExtractor.extensions)
_C_CPP_LANGUAGES = frozenset({CImportExtractor.language_name, CppImportExtractor.language_name})


def scan_extensions_for(target_path: Path) -> Optional[frozenset]:
    """The parse-corpus extension family depends:// scans for one file target.

    BACK-525 layer 4: only the target's own extractor family can satisfy
    resolve_import's extension-qualified lookup; BACK-675 widens C/C++ to the
    shared header family. ``None`` (an unsupported file) scans every extension.
    The recall gate (scripts/recall_gate.py) reads the same choice.
    """
    target_extractor = get_extractor(target_path)
    if target_extractor is None:
        return None
    if target_extractor.language_name in _C_CPP_LANGUAGES:
        return _C_CPP_FAMILY_EXTENSIONS
    return frozenset(target_extractor.extensions)



def _has_project_marker(directory: Path) -> bool:
    """True if *directory* holds a depends:// project-root marker (package or
    VCS, union of both tiers). A missing marker is a hang, not a cosmetic gap
    (BACK-515); the tiers decide *which* marker gets promoted (BACK-525). Both
    predicates now live in path_utils (BACK-612); kept here for the tests."""
    return _has_package_marker(directory) or _has_vcs_marker(directory)


def _resolve_project_root(
    target_path: Path, root_override: Optional[Path] = None
) -> Optional[Path]:
    """Resolve depends://'s scan root via the shared, ceiling-bounded resolver
    (BACK-612): tier -1 ``?root=`` override → tier 0 ``.reveal.yaml root:true``
    → tier 1 package marker → tier 2 VCS root. Returns ``None`` if nothing
    matches before the hard ceiling — ``get_structure`` then applies depends://'s
    own inferred-project fallback (BACK-525 layer 3), which is why the shared
    resolver's ``python_init_chain`` tier is left off here.
    """
    return resolve_project_root(target_path, root_override=root_override)

_SCHEMA_QUERY_PARAMS = {
    'top': {
        'type': 'integer',
        'description': 'Limit to the N most-imported files',
        'examples': ["depends://src?top=10"],
    },
    'format': {
        'type': 'string',
        'description': 'Output format: text (default) or dot (GraphViz)',
        'examples': ["depends://src?format=dot"],
    },
    'root': {
        'type': 'string',
        'description': (
            'Pin the scan root to DIR for this invocation (highest precedence — '
            'beats .reveal.yaml root:true, package, and VCS markers). Resolved '
            'relative to cwd; must be a directory containing the target and is '
            'refused if it is a filesystem/home/system root. Use it when the '
            'auto-detected root climbs too high — e.g. a marker-less C/C++ tree '
            'nested under a larger ancestor .git repo.'
        ),
        'examples': ["depends://src/server.c?root=src"],
    },
    'verbose': {
        'type': 'flag',
        'description': "Directory targets: list each module's importers under its row (a file target already shows one row per import). Same as the CLI --verbose",
        'examples': ['depends://src?verbose'],
    },
}

_SCHEMA_OUTPUT_TYPES = [
    {
        'type': 'module_dependents',
        'description': 'List of files that import the target module(s)',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'module_dependents'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'target': {'type': 'string'},
                'dependents': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'file': {'type': 'string'},
                            'line': {'type': 'integer'},
                            'module': {'type': 'string'},
                            'names': {'type': 'array', 'items': {'type': 'string'}},
                            'type': {'type': 'string'},
                            'is_relative': {'type': 'boolean'},
                            'alias': {'type': 'string'},
                        },
                    },
                },
                'count': {'type': 'integer'},
                'edge_rule': {'type': 'object'},
            },
        },
    },
    {
        'type': 'dependency_summary',
        'description': 'Most-imported modules in a directory',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'dependency_summary'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'modules': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'module': {'type': 'string'},
                            'dependent_count': {'type': 'integer'},
                            'dependents': {'type': 'array', 'items': {'type': 'string'}},
                        },
                    },
                },
                'edge_rule': {'type': 'object'},
            },
        },
    },
]

_SCHEMA_EXAMPLE_QUERIES = [
    {
        'uri': 'depends://src/utils.py',
        'description': 'Show all files that import utils.py',
        'output_type': 'module_dependents',
    },
    {
        'uri': 'depends://src/models/',
        'description': 'Show everything that imports any module in models/',
        'output_type': 'dependency_summary',
    },
    {
        'uri': "depends://src?top=10",
        'description': 'The 10 most-imported modules in src (high coupling candidates)',
        'output_type': 'dependency_summary',
    },
    {
        'uri': "depends://src?format=dot",
        'description': 'Full reverse dependency graph in GraphViz DOT format',
        'output_type': 'dependency_summary',
    },
    {
        'uri': "depends://project/src/main.c?root=project",
        'description': (
            'Pin the scan root when auto-detection over-climbs (e.g. a Makefile '
            'C project nested under a larger ancestor .git)'
        ),
        'output_type': 'module_dependents',
    },
]

_SCHEMA_NOTES = [
    'Inverts the import graph built by imports:// — same language support, same resolution',
    'Dynamic imports (importlib.import_module, __import__) are not tracked',
    'TYPE_CHECKING-only imports are excluded from edges (intentional)',
    'Function-level imports are importers like any other; edge_rule (and a Rule: line in text) states the rule. depends:// takes no &lazy: imports://<dir>?rank=fan-in&lazy=exclude is the load-time view',
    'Results are conservative: false negatives possible, never false positives',
    'Use ?top=N on a directory to find high-coupling modules (many dependents = high impact if changed)',
    'Use depends://file.py to do impact analysis before refactoring a module',
    'Not deps:// (one character apart) — depends:// answers "who imports this '
    'one module" for a single target; deps:// is a whole-tree dependency dashboard',
    'Scan root: ?root=DIR > .reveal.yaml root:true > package marker > VCS root > inferred subtree',
    "BACK-1093: some languages (Ruby, Zig, Dart, GDScript, Lua) have no real "
    "True/False intra-project classification at all -- an unresolved import from one "
    "of them never trips the BACK-547 honest-decline caveat, so 'high' confidence on "
    "a scan dominated by them is disclosed via a dedicated known_limits entry rather "
    "than silently absent.",
]


class DependsRenderer:
    """Renderer for depends:// results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text', verbose: bool = False, resource: str = '.') -> None:
        # ?format=dot is a URI output override (as on imports:// and calls://): it wins over
        # --format, so the private routing field never reaches JSON (BACK-2282).
        if result.get('_format') == 'dot':
            DependsRenderer._render_dot(result)
            return
        if format == 'json':
            print_json_result(result)
            return

        # verbose from query (?verbose) takes precedence over caller arg (BACK-1379)
        verbose = result.get('verbose', verbose)

        result_type = result.get('type')
        if result_type == 'module_dependents':
            DependsRenderer._render_dependents(result, verbose)
        elif result_type == 'dependency_summary':
            DependsRenderer._render_summary(result, verbose, resource)
        else:
            print_json_result(result)

    @staticmethod
    def _render_edge_rule(result: dict) -> None:
        """The counting rule, as the JSON states it (BACK-2077)."""
        for line in import_analysis.edge_rule_lines(result):
            print(f"  {line}\n")

    @staticmethod
    def _has_traversal_loss(result: dict) -> bool:
        return any(entry.get('type') == 'analysis_incomplete' and entry.get('unit') == 'directories'
                   for entry in result.get('meta', {}).get('warnings', []))

    @staticmethod
    def _render_dependents(result: dict, verbose: bool) -> None:
        target = result.get('target', 'unknown')
        dependents = result.get('dependents', [])
        count = result.get('count', 0)

        print(f"\n{'='*60}")
        print(f"Dependents of: {target}")
        print(f"{'='*60}\n")

        warning = result.get('warning')
        if warning:
            print(f"{warning}\n")
        DependsRenderer._render_edge_rule(result)

        # BACK-557: convention-autoload coverage caveat prints for both empty
        # and positive results (a positive count is still a lower bound here).
        autoload_note = result.get('autoload_note')
        if autoload_note:
            print(f"{autoload_note}\n")

        if not dependents:
            if result.get('undercount_possible'):
                # BACK-547: the caveat (⚠) already printed above; do not assert
                # the confident "nothing imports this module" that contradicts it.
                print("  No dependents resolved — but see the ⚠ above: this may be incomplete.")
            else:
                print("  No dependents found (nothing imports this module)")
            same_module_note = result.get('same_module_note')
            if same_module_note:
                print()
                print(same_module_note)
            print()
            print("ℹ Import-graph analysis — dynamic imports not followed.")
            return

        shown = f" (showing {len(dependents)})" if len(dependents) < count else ''
        observed = " observed" if DependsRenderer._has_traversal_loss(result) else ""
        print(f"  {count}{observed} file(s) import this module{shown}:\n")
        for dep in dependents:
            file_path = dep.get('file', '')
            line = dep.get('line', 0)
            names = dep.get('names', [])
            import_type = dep.get('type', '')
            alias = dep.get('alias')

            if import_type == 'star_import':
                what = '*'
            elif names:
                what = ', '.join(names[:5])
                if len(names) > 5:
                    what += f', … (+{len(names) - 5} more)'
            else:
                what = dep.get('module', '')

            alias_str = f' as {alias}' if alias else ''
            print(f"  {file_path}:{line}  ← {what}{alias_str}")

        # Each importing statement is already its own row, so --verbose adds nothing
        # here; no Tip recommends it (BACK-2213 lane C B2).
        print()
        print("ℹ Import-graph analysis — dynamic imports not followed.")
        print()

    @staticmethod
    def _render_summary(result: dict, verbose: bool, resource: str) -> None:
        modules = result.get('modules', [])
        source = result.get('source', resource)

        print(f"\n{'='*60}")
        print(f"Reverse Dependency Summary: {source}")
        print(f"{'='*60}\n")

        warning = result.get('warning')
        if warning:
            print(f"{warning}\n")
        DependsRenderer._render_edge_rule(result)

        if not modules:
            if result.get('undercount_possible'):
                print("  No internal imports resolved — but see the ⚠ above: this may be incomplete.")
            else:
                print("  No internal imports found.")
            print()
            print("ℹ Import-graph analysis — dynamic imports not followed.")
            return

        total = sum(m['dependent_count'] for m in modules)
        total_modules = result.get('total_modules', len(modules))
        if DependsRenderer._has_traversal_loss(result):
            print(f"  {len(modules)} of {total_modules} observed module(s) imported internally "
                  f"({total} observed import edges shown); ranking is among observed modules\n")
        elif len(modules) < total_modules:
            print(f"  Top {len(modules)} of {total_modules} module(s) imported internally "
                  f"({total} import edges shown)\n")
        else:
            print(f"  {len(modules)} module(s) imported internally ({total} total import edges)\n")

        for m in modules:
            count = m['dependent_count']
            mod = m['module']
            bar = '█' * min(count, 20)
            print(f"  {count:3d}  {bar}  {mod}")
            if verbose:
                for dep in m.get('dependents', []):
                    print(f"         ← {dep}")

        print()
        print(f"  Tip: reveal depends://<module>  for full importer list")
        print()
        print("ℹ Import-graph analysis — dynamic imports not followed.")
        print()

    @staticmethod
    def _render_dot(result: dict) -> None:
        modules = result.get('modules', [])
        print('digraph depends {')
        if DependsRenderer._has_traversal_loss(result):
            for line in result.get('warning', '').splitlines():  # boundary-ok: splitlines -- generated warning text, not file content; each line must be a DOT comment
                print(f'  // {line}')
        print('  rankdir=LR;')
        print('  node [shape=box fontname="monospace" fontsize=10];')
        for m in modules:
            target = m['module'].replace('"', '\\"')
            for dep in m.get('dependents', []):
                src = dep.replace('"', '\\"')
                print(f'  "{src}" -> "{target}";')
        print('}')

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        if format == 'json':
            print_json_result(result)
            return
        DependsRenderer._render_dependents(result, verbose=True)


@register_adapter('depends')
@register_renderer(DependsRenderer)
class DependsAdapter(ResourceAdapter):
    """Inverse module dependency graph — who imports this module?

    Builds the same import graph as imports:// but queries it in reverse:
    given a target module (or directory), returns the set of files that
    depend on it.
    """
    HELP_CLUSTER = 'Code Analysis'

    # BACK-524: bound the tree-sitter-parsed file set so a scan_root that
    # resolves to a genuinely huge (but marker-legit) ancestor repo degrades
    # to a warned, partial result instead of an unbounded parse — the residual
    # class BACK-515's marker fix couldn't close (a file with no marker above
    # it at all, or a future depends://-supported language whose marker isn't
    # in _PROJECT_ROOT_MARKERS yet). Counts only extractor-supported files
    # (what's actually expensive to parse), not every file os.walk visits.
    _SCAN_FILE_CAP = 5000

    # BACK-557: convention-autoloading coverage caveat. When a
    # `convention_autoloaded` language (Ruby/Rails-Zeitwerk) dominates the scan
    # and the fraction of its files carrying ANY import/require statement falls
    # below this threshold, statement-based analysis structurally undercounts
    # (most intra-app edges are bare constant references with no statement).
    # Threshold grounded in the real Discourse corpus: convention-loaded trees
    # cluster ≤10% require-density (app/ 4.7%, db/ 1.8%, plugins/ 8.9%,
    # spec/ 10.2%) while explicit-require Ruby sits far higher (config/ 32%,
    # script/ 87%); 15% lands in the empirical gap. Min file count avoids
    # firing on tiny toy trees where the ratio is noise.
    _AUTOLOAD_DENSITY_THRESHOLD = 0.15
    _AUTOLOAD_MIN_FILES = 20
    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907
    RESOURCE_IS_PATH = True  # a nonexistent path is an error, not an empty result (BACK-1321)
    # BACK-1379: render_structure() already has a real verbose branch (below) but
    # handle_uri never forwards a verbose= kwarg through the URI path (only
    # ACCEPTS_TOP renderers get kwargs forwarded, and this isn't one) -- so
    # --verbose was a silent no-op on depends://. Same fix as imports:// (BACK-1361):
    # declare the flag, read it back out of the query in get_structure(), and have
    # render_structure prefer result['verbose'] over its own kwarg default.
    CLI_QUERY_FLAGS = {'verbose': 'verbose', 'limit': 'top={value}', 'respect_gitignore': 'respect_gitignore=false'}  # top= caps the module / dependents list (BACK-1496)
    BUDGET_LIST_FIELD = ('modules', 'dependents')  # directory summary / single-file mode (BACK-1497)

    def __init__(self, resource: str = '', query: Optional[str] = None):
        """Initialize depends adapter.

        Args:
            resource: File or directory to find dependents for
            query: Query string (e.g., 'top=10', 'format=dot')
        """
        path = resource or '.'
        # What the cascade resolved (analyzers/imports/resolution.py, BACK-1054); empty until
        # _build_graph runs. Everything below it is this presenter's own request state.
        self._resolution = resolution.ProjectResolution()
        self._analysis = ImportAnalysis()
        # What this request's walk hid at the target (BACK-2065): the engine's, judged by this walk.
        self._scope_hidden: Optional[Dict[str, Any]] = None
        self._target_path: Optional[Path] = Path(path).resolve() if path else None
        self._query_params = parse_query_params(query or '')
        self._warn_unknown_query_params(self._query_params)  # BACK-507
        self._scan_root: Optional[Path] = None
        self._scan_budget = ScanBudget(self._SCAN_FILE_CAP)
        self._root_inferred = False
        # BACK-610: the validated ?root= override actually in effect (None when
        # not passed or rejected), plus a one-line reason when a passed ?root=
        # was rejected (surfaced via _warnings so the fallback isn't silent).
        self._root_override_used: Optional[Path] = None
        self._root_override_rejected: Optional[str] = None

    @property
    def _graph(self) -> Optional[ImportGraph]:
        return self._resolution.graph

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Build import graph and return reverse-dependency view.

        Returns:
            - module_dependents if target is a specific file
            - dependency_summary if target is a directory
        """
        target_path = self._target_path or Path('.').resolve()

        if not target_path.exists():
            return {'error': f"Path not found: {target_path}"}

        # For a specific file target: scan from project root so ALL importers
        # (not just siblings) are discovered.
        # For a directory target: same — scan from project root so files outside
        # the directory that import into it are visible.
        #
        # BACK-498: when no project marker exists above a *file* target, falling
        # back straight to the file's own parent directory is too narrow for
        # package/namespace-resolved languages (Java, Kotlin, Swift, PHP) — a
        # dependent commonly lives in a sibling package directory
        # (src/main/java/com/example/{util,app}/...), not the same folder. Widen
        # to the nearest conventional source root ('src', the Maven/Gradle/iOS/
        # Composer convention that all four affected languages share) when one
        # exists above the file; only fall back to the bare parent dir if even
        # that isn't found.
        # BACK-525 layers 1-3 and BACK-610's ?root=, in the owner the imports:// climb shares
        # (resolution.choose_scan_root): a validated override, the ceiling-bounded marker
        # climb, else the inferred subtree (tsserver's model: no marker before the ceiling,
        # so scope to the target's own subtree and say so).
        choice = resolution.choose_scan_root(target_path, self._query_params.get('root'))
        self._root_override_used = choice.override_used
        self._root_override_rejected = choice.override_rejected
        self._root_inferred = choice.inferred
        project_root = choice.root
        self._target_path = target_path
        # BACK-525 layer 4: for a single-file target, only files in its own
        # extractor's `extensions` family (e.g. C's .c+.h) can ever satisfy
        # resolve_import's extension-qualified lookup (verified read-only,
        # gate G1) — parsing every other supported language's files under
        # scan_root just to build the dependency graph is pure waste. A
        # directory target may span languages, so it stays unscoped.
        scan_extensions = scan_extensions_for(target_path) if target_path.is_file() else None
        self._build_graph(project_root, scan_extensions=scan_extensions)

        fmt = self._query_params.get('format', 'text')
        if not isinstance(fmt, str):
            fmt = 'text'
        top_n_raw = self._query_params.get('top')
        top_n = int(top_n_raw) if top_n_raw else None
        if top_n is not None and top_n < 1:
            top_n = None  # 0 / negative = no cap (a negative slice would drop the tail)

        if target_path.is_file():
            result = self._format_file_dependents(target_path, top_n=top_n)
        else:
            result = self._format_directory_summary(target_path, top_n=top_n, fmt=fmt)
        # BACK-1379: carry ?verbose through the result dict since handle_uri
        # doesn't forward a verbose= render kwarg for this renderer.
        if 'verbose' in self._query_params or kwargs.get('verbose', False):
            result['verbose'] = True
        return result

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get dependents for a specific module by name.

        Args:
            element_name: File name (e.g., 'utils.py')
        """
        if not self._graph:
            return None

        for file_path in self._graph.reverse_deps:
            if file_path.name == element_name:
                return self._format_file_dependents(file_path)

        return None

    def get_metadata(self) -> Dict[str, Any]:
        if not self._graph:
            return {'status': 'not_analyzed'}
        resolved = self._resolution
        accounting = resolved.scan_accounting
        return {
            'total_files_scanned': self._graph.get_file_count(),
            'total_import_edges': sum(len(v) for v in self._graph.reverse_deps.values()),
            'analyzer': 'depends',
            'scan_capped': resolved.capped,
            'scan_budget': {'scope': accounting.scope,
                            'limit': self._scan_budget.limit,
                            'total': accounting.total,
                            'returned': accounting.returned,
                            'exact': accounting.exact},
            'root_inferred': self._root_inferred,
            'zeitwerk_edges_inferred': resolved.zeitwerk_edges,
            'php_constants_indexed': resolved.constants_indexed,
            'php_constants_ambiguous': resolved.constants_ambiguous,
        }

    # ── Graph building (the cascade lives in analyzers/imports/resolution.py) ──

    def _build_graph(self, scan_root: Path, scan_extensions: Optional[frozenset] = None) -> None:
        """Build the import graph of scan_root through the one imports:// engine (BACK-1054 S6).

        The engine (``service.analyze``: its walk, per-file extraction, cascade and caches)
        resolves at ``scan_root`` (passed as ``root``, the climb's own choice), under depends' file
        cap (``_SCAN_FILE_CAP`` as ``max_files``) and over depends' extension family.

        ``scan_extensions`` (BACK-525 layer 4): when given, restricts the *parse corpus* (``files``
        — what actually gets tree-sitter'd for import statements) to this extension set, the
        target's own extractor family (e.g. C's ``.c``/``.h``). This is where the cost lives, so
        it's where the win is; ``file_index`` (the resolution basename map) stays
        extension-agnostic regardless, since it needs to hold non-source-extension include targets
        too (BACK-491: ``.inc``/``.tcc``). A basename lookup only ever matches a file whose name is
        extension-qualified to the *importing* language (verified read-only, gate G1), so a file
        outside the target's family could never satisfy a resolution anyway — narrowing the parse
        corpus to it is correct-by-construction, not a heuristic, and dissolves the file-count
        cap's non-determinism for single-language targets (``None`` — directory targets, which may
        span languages — stays unscoped across every supported extension, the pre-BACK-525 shape).
        The walk keeps only that family, so recognized code without an extractor is not counted
        against the cap either (depends' pre-S6 build).
        """
        supported_exts = scan_extensions if scan_extensions is not None else frozenset(get_all_extensions())
        self._scan_root = scan_root
        self._scan_budget = ScanBudget(self._SCAN_FILE_CAP)
        target = self._target_path or scan_root
        built = import_analysis.analyze(import_analysis.ScanScope(
            scan_root, supported_exts, cap=self._SCAN_FILE_CAP,
            focus=None if scan_root == target else target))
        self._analysis = built.analysis
        self._resolution = self._analysis.resolution or resolution.ProjectResolution()
        from ..utils.path_utils import hidden_entries_warning
        warning = hidden_entries_warning(built.files.hidden, built.files.analyzed)
        self._scope_hidden = dict(warning) if warning else None

    def _build_meta(self) -> Dict[str, Any]:
        known_limits = [
            'dynamic imports (importlib, __import__) not followed',
            'conditional imports may not reflect runtime state',
            'TYPE_CHECKING-only imports are excluded',
        ]
        resolved = self._resolution
        if resolved.traversal_failures:
            known_limits.append(
                'required directory enumeration failed; missing file population is unknown; '
                'dependency observations may be incomplete or undercounted')
        if resolved.capped:
            known_limits.append(
                f'scan capped at {self._SCAN_FILE_CAP:,} files — BACK-524, results may be partial')
        if self._root_inferred:
            known_limits.append(
                "no project marker found above the target before the scan-root ceiling — "
                "BACK-525, scope inferred from the target's own directory")
        if resolved.unresolved_intra > 0:
            known_limits.append(
                f'{resolved.unresolved_intra} intra-project import(s) did not resolve to a file — '
                'BACK-547, dependents may be undercounted (a negative is a lower bound)')
        if self._convention_autoload_note():
            known_limits.append(
                f'{resolved.autoload_with_imports}/{resolved.autoload_total} Ruby files declare any '
                'require — BACK-557, convention-based autoloading (Zeitwerk) suspected, '
                'require-based dependents may significantly undercount (positive results too)')
        if resolved.unclassifiable_languages:
            langs = ', '.join(sorted(resolved.unclassifiable_languages))
            known_limits.append(
                f'no intra-project import classification for: {langs} — BACK-1093, '
                "depends:// cannot distinguish an unresolved import that points inside "
                "this project from one that's correctly external for these languages, "
                "so 'high' confidence here does not cover them"
            )
        return {
            'analysis_kind': 'import-graph',
            # Known required discovery loss also reduces confidence, independently
            # of whether any surviving import could be classified as unresolved.
            # BACK-547: a graph with unresolved intra-project imports is not a
            # high-confidence source for a blast-radius negative. BACK-1093:
            # unclassifiable-language imports are a distinct, disclosed-but-
            # not-scored risk (see known_limits above) — deliberately not
            # folded into this binary confidence value, since "how much
            # residual risk" for a whole language is a bigger judgment call
            # than this per-scan flag should make unilaterally.
            'confidence': 'reduced' if resolved.traversal_failures or resolved.unresolved_intra > 0 else 'high',
            'known_limits': known_limits,
        }

    def _edge_rule(self) -> Dict[str, Any]:
        """depends:// counts every edge; the load-time view is imports://'s &lazy=exclude."""
        assert self._graph is not None
        return import_analysis.edge_rule(
            self._graph, LAZY_INCLUDE, lazy_default=True,
            subject='importers are files whose static imports resolve here, among',
            scope='scan_root',
            hint="depends:// takes no &lazy; imports://<dir>?rank=fan-in&lazy=exclude counts load-time edges only")

    def _scan_cap_warning(self) -> str:
        """BACK-524: one-line disclosure when _build_graph stopped early.

        Mirrors imports.py's coverage_warning_line — a partial graph must say
        so, not present itself as complete (same principle as BACK-518 part 2).

        BACK-610: the advice is now honest for the case that actually breaks.
        The old wording ("Scope depends:// to a narrower path") is *impossible*
        for a single-file target — you can't narrow a single file, and the real
        cause is the scan root climbing above the file's project (an ancestor
        .git). For a file target, name the levers that actually fix it: ``?root=``
        or a ``.reveal.yaml root:true`` marker. If a ``?root=`` was already in
        effect and the cap still fired, the pinned root is genuinely over the cap,
        so don't loop back to advice they already followed.
        """
        if not self._resolution.capped:
            return ''
        root = self._scan_root
        base = (
            f"⚠ Scan capped at {self._SCAN_FILE_CAP:,} files under {root} — "
            "results may be incomplete."
        )
        if self._root_override_used is not None:
            return f"{base} This pinned ?root= exceeds the scan cap even as scoped."
        if self._target_path is not None and self._target_path.is_file():
            return (
                f"{base} Can't narrow a single-file target — the scan root climbed "
                "above this file's project. Pin it with depends://…?root=DIR or a "
                "'.reveal.yaml' containing 'root: true' at the project root."
            )
        return (
            f"{base} Scope depends:// to a narrower path, or pin the root with "
            "?root=DIR (or a '.reveal.yaml' with 'root: true')."
        )

    def _root_override_warning(self) -> str:
        """BACK-610: one-line disclosure when a passed ``?root=`` was rejected
        and validation fell back to auto-detection — so the silent fallback
        doesn't hand back a scope the user didn't ask for without saying why."""
        if not self._root_override_rejected:
            return ''
        return (
            f"⚠ {self._root_override_rejected} — ignored, using the auto-detected "
            "scan root instead."
        )

    def _root_inferred_warning(self) -> str:
        """BACK-525 layer 3: one-line disclosure when no project marker was
        found above the target before the scan-root ceiling, so the scan was
        scoped to the target's own directory instead of climbing further."""
        if not self._root_inferred:
            return ''
        root = self._scan_root
        return (
            f"⚠ Couldn't determine this file's project boundary — scanning only "
            f"{root}. Pass an explicit root or cd into the project for full coverage."
        )

    def _honest_decline_warning(self) -> str:
        """BACK-547 honest-decline: one-line disclosure when the scan contained
        intra-project imports that did not resolve to a file edge, so a
        blast-radius negative here is a lower bound, not a proof of "nothing
        imports this". Only intra-project misses count — external (stdlib/dep)
        imports are correctly edge-less and never trigger this."""
        n = self._resolution.unresolved_intra
        if n <= 0:
            return ''
        eg = ''
        if self._resolution.unresolved_examples:
            _importer, stmt = self._resolution.unresolved_examples[0]
            eg = f" (e.g. '{stmt.module_name}')"
        return (
            f"⚠ {n} intra-project import{'s' if n != 1 else ''} in this scan did not "
            f"resolve to a file{eg} — dependents may be undercounted, or those targets "
            "lie outside the scanned scope. Treat blast-radius negatives here as a lower bound."
        )

    def _same_module_note(self, target: Path) -> str:
        """BACK-560/567: unconditional informational note framing what a Swift
        file's dependent list does and doesn't mean. Two distinct truths:

        1. **Same-module (same-target) references are invisible** (BACK-560) —
           Swift compiles a target together, so a sibling file uses this file's
           declarations with no `import` statement to extract. Not an
           undercount from failed resolution; a class of edge that has no
           syntax at all. Deliberately NOT the ⚠ honest-decline signal (keyed
           on _unresolved_intra, which never increments here — nothing was
           extracted to fail).

        2. **Cross-module dependents shown are module-level** (BACK-567) — an
           `import Foo` names the whole module Foo, so every file importing
           this file's module is listed as a dependent, whether or not it uses
           *this specific file*. The count is an honest ceiling at Swift's
           import granularity (the module), not file-precise like Java's."""
        extractor = get_extractor(target)
        spec = getattr(extractor, 'spec', None)
        if not getattr(spec, 'same_module_undetectable', False):
            return ''
        return (
            "ℹ This is a Swift file. Swift's import granularity is the module/target, "
            "not the file, so this list is module-level: (1) same-module siblings use "
            "this file's declarations with NO `import` statement, so they can never "
            "appear here (not a failed resolution — a class of edge with no syntax); "
            "(2) any dependent shown imports this file's whole module, not necessarily "
            "this specific file. Treat the count as an import-granularity ceiling, not "
            "a file-precise dependent set."
        )

    def _convention_autoload_note(self) -> str:
        """BACK-557: project-level coverage caveat for a convention-autoloaded
        language (Ruby/Rails-Zeitwerk). Fires when that language dominates the
        scan and require-statement density is below threshold — most intra-app
        edges are bare constant references with no statement to extract, so
        depends:// structurally undercounts. Unlike the ⚠ honest-decline (which
        is keyed on failed *resolution* of an extracted import and only fires on
        empty results), this fires on positive results too: a non-empty answer
        is still a lower bound when 90%+ of edges were never expressible as a
        require in the first place. Returns '' when the signal doesn't apply."""
        total = self._resolution.autoload_total
        if total < self._AUTOLOAD_MIN_FILES:
            return ''
        density = self._resolution.autoload_with_imports / total
        if density >= self._AUTOLOAD_DENSITY_THRESHOLD:
            return ''
        return (
            f"ℹ Only {density:.0%} of the {total} Ruby files scanned declare any "
            "require/require_relative — convention-based autoloading (Rails/Zeitwerk maps file "
            "paths to constant names, resolving bare references like `Topic` with no statement) "
            "is likely. depends:// only sees require-based edges, so intra-project dependents "
            "here may be significantly undercounted regardless of the count shown."
        )

    def _traversal_warning(self) -> Optional[Dict[str, Any]]:
        warning = traversal_failed_warning(self._resolution.traversal_failures, self._scan_root)
        return dict(warning) if warning else None

    def _parse_warning(self) -> Optional[Dict[str, Any]]:
        """Files parsed with errors (BACK-1598), as a structured warning beside the ``warning``
        line: the engine's verdict on them is exit 3 (D6), depends' is exit 0, so a JSON reader
        finds the partial answer here (BACK-2181)."""
        warning = parse_failure_warning(self._resolution.files_failed, self._scan_root)
        return dict(warning) if warning else None

    def _lost_warning(self) -> Optional[Dict[str, Any]]:
        """Files a dead pool worker took down before they were parsed: the engine extracts in a
        process pool on a large tree, and a lost file has no imports, so it is disclosed, never a
        silent gap (its importers' edges are missing too)."""
        warning = worker_lost_warning([str(fp) for fp in self._analysis.files_lost], self._scan_root)
        return dict(warning) if warning else None

    def _undercount_possible(self, empty: bool) -> bool:
        return (bool(self._resolution.traversal_failures) or bool(self._analysis.files_lost)
                or (empty and self._resolution.unresolved_intra > 0))

    def _warnings(self, include_honest_decline: bool = False) -> str:
        """Join active disclosures (scan cap, inferred root, and — only when the
        result is empty — honest-decline) into one warning string, in priority
        order. The honest-decline ⚠ is gated to the empty/negative case (the
        DD-killer BACK-542 signature): on a *positive* result the same
        intra-project-miss count is disclosed via _meta.known_limits instead, so
        a corpus with a few unresolved imports doesn't append a caveat to every
        confident, non-empty answer (that would be the cry-wolf failure honest-
        decline is meant to prevent)."""
        partial = self._parse_warning()
        traversal = self._traversal_warning()
        lost = self._lost_warning()
        parts = [
            self._root_override_warning(),
            self._scan_cap_warning(),
            self._root_inferred_warning(),
            f"⚠️  {partial['message']}" if partial else '',
            f"⚠️  {traversal['message']}" if traversal else '',
            f"⚠️  {self._scope_hidden['message']}" if self._scope_hidden else '',
            f"⚠️  {lost['message']}" if lost else '',
        ]
        if include_honest_decline:
            parts.append(self._honest_decline_warning())
        return '\n'.join(w for w in parts if w)

    # ── Formatters ─────────────────────────────────────────────────────────

    def _format_file_dependents(self, target: Path, top_n: Optional[int] = None) -> Dict[str, Any]:
        """Format all files that import `target`."""
        if not self._graph:
            return {'error': 'Graph not built'}

        # BACK-553 (a package-granularity language, Go, resolves an import to the package
        # DIRECTORY, so importers of the file's directory count) and BACK-542 (the exact statement
        # behind each edge, correct even when one statement resolves to several targets): the one
        # listing imports://?importers=FILE presents too (resolution.file_importers, BACK-1054 S6).
        # Every cascade edge records its statement; an edge without one lists as 'unknown'.
        dependents = []
        for importer, _edge, stmt in resolution.file_importers(
                self._graph, self._resolution.edge_statements, target):
            if stmt is not None:
                dependents.append(_format_import_stmt(stmt))
            else:
                dependents.append({'file': str(importer), 'line': 0, 'module': '', 'names': [], 'type': 'unknown',
                                   'is_relative': False, 'alias': None})

        # BACK-1214: each dependent's 'file' came from _format_import_stmt's
        # str(stmt.file_path)/str(importer), always absolute -- never
        # relativized. Same confidentiality gap as BACK-1212/BACK-1213.
        # BACK-1462: so is 'module' when the extractor resolved it to a path
        # (PHP require/include carries the resolved absolute include path).
        for dep in dependents:
            if dep.get('file'):
                dep['file'] = to_relative_display(dep['file'], self._scan_root)
            if dep.get('module') and os.path.isabs(dep['module']):
                dep['module'] = to_relative_display(dep['module'], self._scan_root)

        shown = dependents[:top_n] if top_n else dependents
        result = ResultBuilder.create(
            result_type='module_dependents',
            source=to_relative_display(str(self._target_path), self._scan_root),
            contract_version=CONTRACT_VERSION,
            source_type='file',
            data={
                'target': to_relative_display(str(target), self._scan_root),
                'dependents': shown,
                'count': len(dependents),  # the total, also when top= shows fewer (BACK-1496)
                'edge_rule': self._edge_rule(),
                'metadata': self.get_metadata(),
                '_meta': self._build_meta(),
            },
        )
        note_truncation(result, 'dependents', len(shown), len(dependents), 'limit', hint='raise ?top=N')
        # Required directory loss qualifies positives too; the prior unresolved-
        # import policy still qualifies only empty answers (BACK-547).
        empty = not dependents
        note_warning(result, self._traversal_warning())
        note_warning(result, self._scope_hidden)
        note_warning(result, self._parse_warning())
        note_warning(result, self._lost_warning())
        result['undercount_possible'] = self._undercount_possible(empty)
        warnings = self._warnings(include_honest_decline=empty)
        if warnings:
            result['warning'] = warnings
        if empty:
            note = self._same_module_note(target)
            if note:
                result['same_module_note'] = note
        autoload_note = self._convention_autoload_note()
        if autoload_note:
            result['autoload_note'] = autoload_note
        return result

    def _format_directory_summary(self, directory: Path, top_n: Optional[int], fmt: str) -> Dict[str, Any]:
        """Format most-imported modules in directory, sorted by dependent count."""
        if not self._graph:
            return {'error': 'Graph not built'}

        # Only include modules that live inside the directory
        modules = []
        for target, importers in self._graph.reverse_deps.items():
            if not resolution.path_is_under(target, directory):
                continue
            # BACK-1214: 'module' and every 'dependents' entry are absolute
            # paths from the import graph -- never relativized. Same
            # confidentiality gap as BACK-1212/BACK-1213.
            modules.append({
                'module': to_relative_display(str(target), self._scan_root),
                'dependent_count': len(importers),
                'dependents': sorted(to_relative_display(str(p), self._scan_root) for p in importers),
            })

        modules.sort(key=lambda m: m['dependent_count'], reverse=True)
        total_modules = len(modules)

        if top_n:
            modules = modules[:top_n]

        data: Dict[str, Any] = {
            'modules': modules,
            'total_modules': total_modules,
            'edge_rule': self._edge_rule(),
            'metadata': self.get_metadata(),
            '_meta': self._build_meta(),
        }
        if fmt == 'dot':
            # Renderer routing only, set for the one value it acts on; text and JSON never
            # carry it (BACK-2282).
            data['_format'] = 'dot'
        result = ResultBuilder.create(
            result_type='dependency_summary',
            source=to_relative_display(str(self._target_path), self._scan_root),
            contract_version=CONTRACT_VERSION,
            source_type='directory',
            data=data,
        )
        # total_modules stays for JSON readers; the marker is what every renderer and the
        # router read as a cut (BACK-1543).
        note_truncation(result, 'modules', len(modules), total_modules, 'limit', hint='raise ?top=N')
        empty = not modules
        note_warning(result, self._traversal_warning())
        note_warning(result, self._scope_hidden)
        note_warning(result, self._parse_warning())
        note_warning(result, self._lost_warning())
        result['undercount_possible'] = self._undercount_possible(empty)
        warnings = self._warnings(include_honest_decline=empty)
        if warnings:
            result['warning'] = warnings
        autoload_note = self._convention_autoload_note()
        if autoload_note:
            result['autoload_note'] = autoload_note
        return result

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'depends',
            'description': 'Inverse module dependency graph — who imports this module?',
            'uri_syntax': 'depends://<path>[?query]',
            'query_params': _SCHEMA_QUERY_PARAMS,
            'elements': {},
            'cli_flags': ['--verbose'],
            'supports_batch': False,
            'supports_advanced': False,
            'supported_languages': get_supported_languages(),
            'output_types': _SCHEMA_OUTPUT_TYPES,
            'example_queries': _SCHEMA_EXAMPLE_QUERIES,
            'notes': _SCHEMA_NOTES,
        }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        return {
            'name': 'depends',
            'description': 'Inverse module dependency graph — who imports this module?',
            'syntax': 'depends://<path>[?<query>]',
            'examples': _SCHEMA_EXAMPLE_QUERIES,
            'notes': _SCHEMA_NOTES,
            'supported_languages': get_supported_languages(),
            'see_also': [
                'reveal help://calls - Function-level call graph (depends:// is module-level)',
            ],
        }


# ── Helpers ────────────────────────────────────────────────────────────────

def _format_import_stmt(stmt: ImportStatement) -> Dict[str, Any]:
    return {
        'file': str(stmt.file_path),
        'line': stmt.line_number,
        'module': stmt.module_name,
        'names': stmt.imported_names,
        'type': stmt.import_type,
        'is_relative': stmt.is_relative,
        'alias': stmt.alias,
    }
