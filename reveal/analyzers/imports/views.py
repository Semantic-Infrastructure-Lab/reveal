"""Shared import graph projections, independent of query parsing and resource adapters."""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import resolution, service
from .base import extension_detects_unused
from .types import ImportAnalysis, ImportGraph, LAZY_INCLUDE, LAZY_EXCLUDE
from ...conventions import conventions_for_path, same_package_families
from ...utils.path_utils import is_test_path, to_posix, to_relative_display

_AUTOLOAD_REGIMES: Tuple[Tuple[str, str, str], ...] = (
    # (manifest filename, content substring to require (empty = presence-only), framework label)
    ('Gemfile', "gem 'rails'", 'Ruby on Rails'),
    ('Gemfile', 'gem "rails"', 'Ruby on Rails'),
    ('manage.py', '', 'Django'),
    ('artisan', '', 'Laravel'),
)


_AUTOLOAD_REGIME_MAX_WALK_UP = 6


COHESION_DECLINED_REASON = 'same-package visibility'
COHESION_DECLINED_RULE = (
    'cohesion n/a (' + COHESION_DECLINED_REASON + '): a component with more than half its files in ' + ', '.join(same_package_families())
    + ' is not scored, because files of one package or module use each other without an import, so internal imports '
    'would read ~0 whatever the structure; other languages keep their number')


def _unused_not_checked(scanned_files) -> Dict[str, int]:
    tally: Dict[str, int] = {}
    for fp in scanned_files:
        if not extension_detects_unused(fp.suffix):
            ext = fp.suffix.lower()
            tally[ext] = tally.get(ext, 0) + 1
    return dict(sorted(tally.items()))


def detect_autoload_regime(path: Path) -> Optional[Dict[str, str]]:
    """Return {'framework': ..., 'evidence': ...} if `path` -- or an ancestor,
    up to _AUTOLOAD_REGIME_MAX_WALK_UP levels up -- looks like a
    convention-autoloading project's root; None otherwise. See
    _AUTOLOAD_REGIMES for what's covered.

    Walks upward because a real invocation typically targets a subdirectory
    (`imports://app/models`, `architecture://src/entities`), not the project
    root where Gemfile/manage.py/artisan actually live -- checking only the
    exact queried path would silently miss the common case (confirmed: the
    due-diligence recipe this was filed against runs adapters against
    subdirectories routinely). Crossing into an unrelated enclosing project
    is possible but low-cost (an extra, still-true disclosure line) compared
    to the silent miss this fixes.
    """
    try:
        base = (path if path.is_dir() else path.parent).resolve()
    except OSError:
        return None
    seen_frameworks: set = set()
    current = base
    for _ in range(_AUTOLOAD_REGIME_MAX_WALK_UP):
        for filename, needle, framework in _AUTOLOAD_REGIMES:
            if framework in seen_frameworks:
                continue
            candidate = current / filename
            if not candidate.is_file():
                continue
            if not needle:
                seen_frameworks.add(framework)
                continue
            try:
                if needle in candidate.read_text(errors='ignore', encoding='utf-8'):
                    seen_frameworks.add(framework)
            except OSError:
                continue
        if seen_frameworks:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    if not seen_frameworks:
        return None
    framework = sorted(seen_frameworks)[0]
    evidence = next(f"{fn} ({framework.split()[-1].lower()} marker)" for fn, _, fw in _AUTOLOAD_REGIMES if fw == framework)
    return {'framework': framework, 'evidence': evidence}


def _component_cohesion(internal: int, total: int, files) -> Optional[float]:
    """internal / (internal + outgoing), or None where the component's language makes it meaningless."""
    if _cohesion_declined(files):
        return None
    return internal / total if total > 0 else 0.0


def _cohesion_fields(cohesion: Optional[float]) -> Dict[str, Any]:
    """The row's cohesion, rounded, or its decline: ``cohesion: None`` and ``cohesion_reason``."""
    if cohesion is None:
        return {'cohesion': None, 'cohesion_reason': COHESION_DECLINED_REASON}
    return {'cohesion': round(cohesion, 3)}


def _cohesion_declined(files) -> bool:
    """Whether a component's files are mostly (strictly more than half) in a same-package-visibility language."""
    same = sum(1 for f in files if conventions_for_path(str(f)).same_package_visibility)
    return 2 * same > len(files)

@dataclass(frozen=True)
class ImportView:
    """Domain rows/counts for one artifact and explicit presentation scope.

    Graphs are shared read-only. Request choices select views without entering build keys.
    The adapter owns URI validation, envelopes and display-path conversion.
    """
    analysis: ImportAnalysis
    target: Optional[Path]
    scan: Optional[resolution.ScanRoot]
    cap: Optional[int]
    lazy: Optional[str] = None
    tests: str = 'include'
    scope: str = 'path'
    top: Optional[int] = None

    def _lazy_mode(self, default: str) -> Tuple[str, bool]:
        return (default, True) if self.lazy is None else (self.lazy, False)

    def _tests_excluded(self) -> bool:
        return self.tests == 'exclude'

    def _scope_is_root(self) -> bool:
        return self.scope == 'root'


    def _graph(self) -> ImportGraph:
        if self.analysis.graph is None:
            raise ValueError('Import analysis requires a built graph before presentation')
        return self.analysis.graph

    def _edges(self, default: str) -> ImportGraph:
        """The graph view an edge-derived answer counts: &lazy, else the view's default, then
        &scan-root containment (BACK-2251: an edge to a file outside the scan root is not counted), then
        &tests=exclude (importers under a test path dropped, ``path_utils.is_test_path``)."""
        view = self._graph().edge_view(self._lazy_mode(default)[0])
        if self.scan is not None:
            view = view.within_root(self.scan.root)
        return view.without_test_importers() if self._tests_excluded() else view

    def outside_root_edge_count(self) -> int:
        """The edges the answer left out because their target is outside the scan root (BACK-2251)."""
        return self._graph().outside_root_edges(self.scan.root) if self.scan is not None else 0

    def _base_dir(self) -> Path:
        target = self.target or Path('.').resolve()
        return target if target.is_dir() else target.parent

    def _in_scope(self, path: Path) -> bool:
        """Whether ``path`` is a row of this answer: every file under the scan root when the requested
        path is the scan root, else the requested file or files under the requested directory."""
        target = self.target
        if target is None or self.scan is None:
            return True
        if self.scan.source == 'path' or self.scan.root == target:
            return resolution.path_is_under(path, self.scan.root)
        return path == target or (target.is_dir() and resolution.path_is_under(path, target))

    def _resolved_at(self, cycles: bool = False) -> service.ResolvedAt:
        scan = self.scan or resolution.ScanRoot(self.target or Path('.').resolve(), 'path')
        return service.ResolvedAt(
            root=to_posix(os.path.relpath(scan.root, self._base_dir())), root_source=scan.source,
            scope=self.scope, tests=self.tests,
            gated=resolution.IMPORT_RECALL_GATED, cycles=cycles,
            outside_root=self._graph().outside_root_edges(scan.root))

    def _edge_rule(self, default: str, subject: str, *, tests_counted: bool = True,
                   cycles: bool = False) -> Dict[str, Any]:
        """The rule (JSON and text) of an answer counted on ``self._edges(default)``."""
        lazy, lazy_default = self._lazy_mode(default)
        return service.edge_rule(
            self._graph(), lazy, lazy_default=lazy_default, subject=subject,
            scope='scan_root' if self._scope_is_root() else 'scanned_path',
            tests_counted=tests_counted and not self._tests_excluded(),
            resolved_at=self._resolved_at(cycles), counted=self._edges(default))

    def _row_files(self, graph: ImportGraph) -> set:
        """The files an answer has rows for: every scanned file and every edge target (which may
        live outside the parse corpus), whichever view, so a row never vanishes with &lazy or
        &tests; under scope=root only those under the requested path."""
        files = self.analysis.scanned_files | set(graph.files.keys()) | set(self._graph().reverse_deps.keys())
        return {f for f in files if self._in_scope(f)}

    def _cycle_groups(self, graph: ImportGraph) -> List[List[Path]]:
        """Cycle groups of ``graph`` that hold a row of this answer (all of each group is shown)."""
        return [group for group in graph.find_cycle_groups() if any(self._in_scope(f) for f in group)]

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about import analysis."""
        if not self.analysis.graph:
            return {'status': 'not_analyzed'}

        in_scope = [imports for f, imports in self.analysis.graph.files.items() if self._in_scope(f)]
        return {
            'total_imports': sum(len(imports) for imports in in_scope),
            'total_files': len(in_scope),
            # Files actually scanned with a working extractor — distinct from
            # total_files (files that happen to have >=1 import statement).
            # A file with a supported language but zero imports (common in
            # older procedural PHP/Ruby, found via real WordPress source
            # during the BACK-431 feature-breadth pass) legitimately has
            # total_files == 0 despite being fully, correctly analyzed; the
            # text renderer needs this count to tell "clean" from "unchecked."
            'scanned_files': sum(1 for f in self.analysis.scanned_files if self._in_scope(f)),
            # Cycles leave function-level imports out unless &lazy says otherwise (BACK-2077).
            'has_cycles': len(self._cycle_groups(self._edges(LAZY_EXCLUDE))) > 0,
            'cycles_lazy': self._lazy_mode(LAZY_EXCLUDE)[0],
            'analyzer': 'imports',
            # Recognized code files whose language has no import extractor yet.
            'unsupported_extensions': dict(sorted(self.analysis.unsupported_extensions.items())),
            # BACK-1398: scanned files whose language has an import extractor but
            # no unused-import detection -- their 0 unused is "not checked".
            'unused_not_checked_extensions': _unused_not_checked(self.analysis.scanned_files),
            # Files with a supported language that tree-sitter could not parse
            # (BACK-982) -- included in scanned_files but their imports/symbols
            # are incomplete, not confirmed-empty; has_cycles can under-report
            # when a cycle runs through one of these. Sorted+capped for stable,
            # bounded JSON/text output; the count alone (below) is exact.
            'extraction_diagnostics': {
                to_relative_display(fp, self.target): artifact.diagnostics
                for fp, artifact in self.analysis.extractions.items() if artifact.diagnostics
            },
            # files_failed is every file whose imports may be incomplete; files_lost is
            # the subset a dead pool worker took down before it was parsed (BACK-1753).
            'files_failed_count': len(self.analysis.files_failed),
            'files_failed': sorted(str(fp) for fp in self.analysis.files_failed)[:50],
            'files_lost_count': len(self.analysis.files_lost),
            'files_lost': sorted(str(fp) for fp in self.analysis.files_lost)[:50],
            # BACK-1245: None on every corpus except a detected convention-
            # autoloading framework (Rails/Django/Laravel) -- see
            # detect_autoload_regime()/autoload_regime_warning() above.
            'autoload_regime': detect_autoload_regime(self.target) if self.target else None,
            # BACK-1054: the one file cap the walk ran under (&max_files) and what it kept.
            'scan_budget': self._scan_budget_dict(),
        }

    def _scan_budget_dict(self) -> Dict[str, Any]:
        record = self.analysis.resolution
        accounting = record.scan_accounting if record is not None else None
        return {'scope': accounting.scope if accounting else 'source_candidates',
                'limit': self.cap,
                'total': accounting.total if accounting else None,
                'returned': accounting.returned if accounting else None,
                'exact': accounting.exact if accounting else None,
                'capped': bool(record.capped) if record is not None else False}

    def fan_in(self) -> Dict[str, Any]:
        """Rank files by fan-in (number of other files that import them).

        High fan-in = core abstractions (base classes, shared utils).
        Zero fan-in = entry points or dead code.
        """
        if not self.analysis.graph:
            return {'entries': [], 'total': 0}

        top = self.top

        graph = self._edges(LAZY_INCLUDE)
        # Union: all scanned files + files that appear as import targets (may live outside scan
        # root); every edge's target, whichever view, so a row never vanishes with &lazy.
        all_files = self._row_files(graph)
        entries: List[Dict[str, Any]] = sorted(
            [
                {
                    'file': str(f),
                    'fan_in': len(graph.reverse_deps.get(f, set())),
                    'fan_out': len(graph.dependencies.get(f, set())),
                }
                for f in all_files
            ],
            key=lambda e: (-e['fan_in'], -e['fan_out'], e['file']),
        )

        total = len(entries)
        if top and top > 0:  # a negative slice would drop the tail, not cap
            entries = entries[:top]

        return {
            'entries': entries, 'total': total,
            'edge_rule': self._edge_rule(LAZY_INCLUDE, 'fan-in and fan-out count static imports between'),
        }

    def entrypoints(self) -> Dict[str, Any]:
        """Return files with fan-in=0 — nothing imports them.

        These are unambiguously entry points (CLIs, test runners, scripts) or dead code.
        Sorted by fan-out descending: high fan-out = likely real entry point; low = likely dead code.

        BACK-1263: importers under a test root do not count toward fan-in here.
        The heuristic's own definition ("no one imports this" = "execution
        starts here") is falsified by the single most common non-caller
        importer, the test suite: a production entry point imported by its own
        tests (`from myapp.worker import main`) has fan-in > 0 and drops off
        the list, while leaf test files nothing imports flood the top sorted by
        fan-out, looking like a confident answer. Measured on a conventional
        src/ + tests/ layout: both real __main__-guarded entry points excluded,
        3 of the 4 reported were test files. A test importing a module is
        evidence that module is *testable*, not that something calls it.
        """
        if not self.analysis.graph:
            return {'entries': [], 'total_scanned': 0}

        graph = self._edges(LAZY_INCLUDE)

        def _non_test_fan_in(f) -> int:
            return sum(
                1 for importer in graph.reverse_deps.get(f, set())
                if not is_test_path(importer)
            )

        all_files = self._row_files(graph)
        candidates = [f for f in all_files if _non_test_fan_in(f) == 0]
        entries: List[Dict[str, Any]] = sorted(
            [
                {
                    'file': str(f),
                    'fan_out': len(graph.dependencies.get(f, set())),
                    # Kept visible rather than filtered out: a test file with
                    # no importers genuinely has fan-in 0, and dropping it
                    # silently would trade one wrong answer for another.
                    'is_test': is_test_path(f),
                    'test_only_importers': len(
                        graph.reverse_deps.get(f, set())
                    ),
                }
                for f in candidates
            ],
            # Non-test files first: a production entry point is what the caller
            # asked for, and previously could not appear at all.
            key=lambda e: (e['is_test'], -e['fan_out'], e['file']),
        )

        response: Dict[str, Any] = {
            'entries': entries, 'total_scanned': len(all_files),
            'edge_rule': self._edge_rule(LAZY_INCLUDE, 'fan-in counts static imports between',
                                         tests_counted=False),
        }
        test_share = sum(1 for e in entries if e['is_test'])
        if entries and test_share:
            meta = response.setdefault('metadata', {})
            meta.setdefault('warnings', []).append({
                'type': 'test_files_in_entrypoints',
                'message': (
                    f'{test_share} of {len(entries)} entry points are test files '
                    f'(is_test=true). Nothing imports a leaf test file, so it '
                    f'satisfies the fan-in=0 definition without being a place '
                    f'execution starts.'
                ),
            })
        return response

    def components(self) -> Dict[str, Any]:
        """Score each directory as a component using import graph cohesion.

        Groups scanned files by immediate parent directory. For each directory:
        - internal: import edges where both source and target are in this directory
        - outgoing: import edges leaving this directory
        - incoming: import edges arriving from outside this directory
        - cohesion: internal / (internal + outgoing) — fraction of imports that stay local
        - top_bridge: file in this directory with most outgoing cross-boundary edges

        High cohesion = well-encapsulated component.
        Low cohesion = files import heavily outside — may not be a real component.
        """
        from collections import defaultdict

        if not self.analysis.graph:
            return {'components': [], 'total': 0}

        graph = self._edges(LAZY_INCLUDE)
        # Group scanned files by immediate parent — only analyze files within the scan root
        dir_files: dict = defaultdict(set)
        for f in self.analysis.scanned_files:
            if self._in_scope(f):
                dir_files[f.parent].add(f)

        components = []
        for directory, file_set in dir_files.items():
            # BACK-1246: compare resolved (canonical, absolute) forms, not the
            # raw Path objects in file_set. Some per-language resolvers (e.g.
            # javascript.py's _resolve_target_path) return absolute dependency
            # targets while _scanned_files keeps whatever path style the CLI
            # invocation used (often relative) -- an unresolved `dep in
            # file_set` check then never matches for that language, silently
            # zeroing internal/cohesion for every component. Resolving both
            # sides here (comparison-only; `directory`/`file_set` below still
            # use the original style for display) fixes it regardless of
            # which side happens to be absolute.
            resolved_file_set = {f.resolve() for f in file_set}
            internal = 0
            outgoing = 0
            incoming = 0
            bridge_counts: dict = defaultdict(int)

            for f in file_set:
                for dep in graph.dependencies.get(f, set()):
                    if dep.resolve() in resolved_file_set:
                        internal += 1
                    else:
                        outgoing += 1
                        bridge_counts[f] += 1
                for src in graph.reverse_deps.get(f, set()):
                    if src.resolve() not in resolved_file_set:
                        incoming += 1

            total_out = internal + outgoing
            cohesion = _component_cohesion(internal, total_out, file_set)
            # BACK-1243: break ties deterministically -- max() over a dict
            # with equal-count keys otherwise depends on hash-seed-salted
            # dict iteration order (PYTHONHASHSEED), varying top_bridge
            # between runs on identical input. Sort by (count, path string)
            # so the highest count wins and ties resolve to the same file
            # every time.
            top_bridge = (
                str(max(bridge_counts.items(), key=lambda kv: (kv[1], str(kv[0])))[0])
                if bridge_counts else None
            )

            component = {
                'component': str(directory),
                'files': len(file_set),
                'internal': internal,
                'outgoing': outgoing,
                'incoming': incoming,
                **_cohesion_fields(cohesion),
                'top_bridge': top_bridge,
            }
            components.append(component)

        # Sort: measured cohesion descending (best-structured first), files descending as tiebreak.
        # A declined component has no number to rank by: it follows every measured one (never sorted as 0.00).
        components.sort(key=lambda c: (c['cohesion'] is None, -(c['cohesion'] or 0.0), -c['files'], c['component']))

        extra = {'cohesion_rule': COHESION_DECLINED_RULE} if any(c['cohesion'] is None for c in components) else {}
        return {
            'components': components, 'total': len(components), **extra,
            'edge_rule': self._edge_rule(LAZY_INCLUDE, 'internal, outgoing and incoming count static imports between'),
        }

    def circular(self) -> Dict[str, Any]:
        """Format circular dependency groups (one entry per SCC, not per simple path)."""
        if not self.analysis.graph:
            return {'cycles': []}

        graph = self._edges(LAZY_EXCLUDE)
        groups = self._cycle_groups(graph)
        cycle_paths = [
            [str(p) for p in graph.find_cycle_path(group)]
            for group in groups
        ]

        return {
            'cycles': [[str(p) for p in group] for group in groups],
            'cycle_paths': cycle_paths, 'count': len(groups),
            'edge_rule': self._edge_rule(LAZY_EXCLUDE, 'cycles use static imports between', cycles=True),
        }
