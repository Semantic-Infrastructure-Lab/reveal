"""Import analysis service: scope/files and resolution before adapter presentation.

Discovery stays in the shared file-index walker. This module owns graph assembly
and extractor resolution dispatch, rather than loading a resource adapter in the
analysis layer. The public analyze operation owns extraction/cache orchestration over that resolver.
The project-wide fallback cascade depends:// answers from is ``resolution.py``.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from .base import get_extractor, get_all_extensions
from . import build_cache, extraction as file_extraction, resolution
from ...core import disk_cache
from ...utils.exclusions import active_exclusions
from ...utils.gitignore import gitignore_enabled
from .inputs import (ScanScope, ImportFileSet, ResolutionContext, discover, resolve_primary,
                     resolve_targets, mark_structural)
from .types import LAZY_EXCLUDE, LAZY_INCLUDE, LAZY_MODES, LAZY_ONLY, ImportAnalysis, ImportGraph, ImportStatement
from ...registry import language_for_extension, get_code_extensions


DEFAULT_FILE_CAP = 20000


def path_scope(root: Path, *, cap: Optional[int] = DEFAULT_FILE_CAP,
               focus: Optional[Path] = None) -> ScanScope:
    """The standard multi-language build scope, including unsupported-code coverage."""
    return ScanScope(root, frozenset(get_all_extensions()), get_code_extensions(), cap, focus)


@dataclass(frozen=True)
class ImportBuild:
    """One analysis plus fresh discovery and optional, uncached structure observations."""
    analysis: ImportAnalysis
    files: ImportFileSet
    structures: List[Dict[str, Any]] = field(default_factory=list)


def analyze(scope: ScanScope, *, on_file_processed: Optional[Callable[[Path], None]] = None,
            structure_reader: Optional[file_extraction.StructureReader] = None) -> ImportBuild:
    """Discover, extract and resolve one explicit build scope through the existing resolver.

    Callbacks disable graph reuse. Structures live only on this returned build, never in
    the shared analysis cache. Discovery runs even on a cache hit to retain fresh disclosures.
    """
    files = discover(scope)
    candidates = list(files.candidates)
    focus = scope.focus
    if focus is not None and focus.is_file() and focus not in candidates and (
            focus.suffix in scope.extensions or focus.suffix.lower() in scope.lowercase_extensions):
        candidates.append(focus)
    key = build_cache._graph_cache_key(candidates, files.index, scope.root, files.traversal_failures,
                                       scope.cap, scope.extensions) if (structure_reader is None and
                                       on_file_processed is None) else None
    variant = (key, active_exclusions(), gitignore_enabled())
    cached = build_cache._cached_graph(scope.root, key, variant)
    if cached is not None:
        return ImportBuild(cached, files)
    analysis = ImportAnalysis()
    structures: List[Dict[str, Any]] = []
    resolver = resolution.ProjectResolver(cap=scope.cap, focus=focus)
    resolver.result.scan_root = scope.root
    resolver.record_discovery(files)
    parse_corpus = [fp for fp in candidates if fp.suffix in scope.extensions]
    inputs = resolver.prepare(parse_corpus, scope.root)
    entries: Dict[Path, resolution.FileEntry] = {}
    _process_extracted_files(analysis, structures, candidates, structure_reader, on_file_processed,
                             scope.extensions, scope.lowercase_extensions, inputs, entries)
    resolved = resolver.resolve_entries(scope.root, [fp for fp in parse_corpus if fp in entries],
                                        files.index, entries, inputs)
    analysis.graph = resolved.graph
    analysis.resolution = resolved
    if key is not None and analysis.cacheable and not resolved.traversal_failures:
        disk_cache.put(build_cache._ADAPTER_IMPORT_GRAPH_NAMESPACE, key, analysis)
    if key is not None and not resolved.traversal_failures:
        build_cache._remember_graph(scope.root, variant, analysis)
    return ImportBuild(analysis, files, structures)


def _process_extracted_files(
    analysis: ImportAnalysis,
    collected: List[Dict[str, Any]],
    candidates: List[Path],
    structure_reader: Optional[file_extraction.StructureReader],
    on_file_processed: Optional[Callable[[Path], None]],
    supported_exts: frozenset,
    code_exts: frozenset,
    inputs: Optional[resolution.ResolutionInputs] = None,
    entries: Optional[Dict[Path, resolution.FileEntry]] = None,
) -> List[ImportStatement]:
    """Run per-file extraction (parallel on large repos, else serial),
    consumed in candidate order so assembly is deterministic. Populates the analysis
    artifact and optional structure list and returns the collected import statements; with the cascade's
    *inputs*, each extracted file's ``FileEntry`` lands in *entries*.
    """
    files: List[Path] = []
    all_imports: List[ImportStatement] = []
    structures: List[Dict[str, Any]] = []
    unextractable: Dict[str, int] = {}
    failed_files: List[Path] = []
    lost_files: List[Path] = []
    structure_failures: List[Tuple[str, str]] = []

    for fp, imports, symbols, structure, extraction, structure_failure in file_extraction.recording_entries(
            file_extraction.extract_files(candidates, structure_reader, inputs), entries):
        if extraction is not None and extraction.worker_lost:
            # Lost before its extractor ran, so "no import extractor" is unknown for
            # it: failed either way, never silently unsupported (BACK-1752).
            if fp.suffix in supported_exts:
                files.append(fp)
                analysis.extractions[fp] = extraction
            failed_files.append(fp)
            lost_files.append(fp)
        elif fp.suffix in supported_exts:
            files.append(fp)
            if imports is not None:
                analysis.symbols_by_file[fp] = symbols
                all_imports.extend(imports)
            if extraction is not None:
                analysis.extractions[fp] = extraction
                if extraction.parse_failed:
                    failed_files.append(fp)
        else:
            ext = fp.suffix.lower()
            if ext in code_exts:
                unextractable[ext] = unextractable.get(ext, 0) + 1
        if structure_reader is not None and structure:
            structures.append(structure)
        if structure_failure:
            structure_failures.append((str(fp), structure_failure))
        if on_file_processed:
            on_file_processed(fp)

    analysis.scanned_files = set(files)
    analysis.unsupported_extensions = unextractable
    collected.extend(structures)
    analysis.files_failed = failed_files
    analysis.files_lost = lost_files
    analysis.structure_failures = structure_failures
    return all_imports


def _build_namespace_index(
    files_and_extractors: List[Tuple[Path, Any]]
) -> Dict[str, List[Path]]:
    """namespace -> [declaring files], for languages where a qualified
    import names a namespace rather than one type (C#, BACK-544).

    Built only from extractors whose spec opts in
    (``resolve_namespaces``), so this is a no-op scan for trees with no
    such language present.
    """
    namespace_index: Dict[str, List[Path]] = {}
    for file_path, extractor in files_and_extractors:
        if not getattr(getattr(extractor, 'spec', None), 'resolve_namespaces', False):
            continue
        for ns in getattr(extractor, 'extract_namespaces')(file_path):
            namespace_index.setdefault(ns, []).append(file_path)
    return namespace_index


def resolve_graph(scope: ScanScope, files: ImportFileSet, analysis: ImportAnalysis) -> ImportAnalysis:
    """Resolve each file's imports to dependency edges (language-specific)."""
    if analysis.graph is None:
        raise ValueError('Import analysis requires an extracted graph before resolution')
    analysis.graph.traversal_failures = list(files.traversal_failures)
    target_path, file_index = scope.root, files.index
    # BACK-554: the namespace index (below) must be built from every
    # scanned file (`analysis.scanned_files`), not just `analysis.graph.files`
    # (files that themselves emitted >=1 import statement). A C# leaf
    # file with zero local `using` directives — the common shape for a
    # file that relies purely on a project-wide C# 10 `global using`, or
    # simply a class that imports nothing — never appears in
    # `analysis.graph.files` (ImportGraph.from_imports only registers files
    # present in the imports list), so its own `namespace X.Y` was
    # silently invisible to the namespace fan-out that resolves edges
    # *to* it: every C# file with no local usings was structurally
    # unreachable via `using`-of-a-namespace, regardless of how many
    # other files declared `using X.Y;`.
    files_and_extractors = [
        (fp, get_extractor(fp)) for fp in analysis.scanned_files
    ]
    namespace_index = _build_namespace_index(files_and_extractors)

    for file_path, extractor in files_and_extractors:
        # BACK-554: file_path may be a zero-import file (present now that
        # files_and_extractors is sourced from analysis.scanned_files, not
        # analysis.graph.files) — nothing to resolve *from*, but it still
        # needed to enter the namespace_index above so edges *to* it work.
        imports = analysis.graph.files.get(file_path, [])
        if not extractor:
            continue

        base_path = file_path.parent
        # Pass project root as an extra search path so absolute intra-project
        # imports resolve (e.g., `from db.session import X` from `api/routes.py`
        # finds `db/session.py` under the project root, not just under `api/`).
        # BACK-621: always include target_path even when it equals base_path
        # — GDScript's `project_relative_prefix` (`res://`) resolver never
        # falls back to base_path (project-root-relative, not file-relative),
        # so skipping target_path here left a root-level importer's `res://`
        # imports unresolvable with no search path at all. Harmless duplicate
        # root for every other resolver, which already tries base_path first.
        extra_paths = [target_path] if target_path.is_dir() else []
        # BACK-491/487/488: every generic (spec-based) extractor shares the
        # `resolve_import(..., file_index=...)` signature and benefits from the
        # prebuilt basename index — C/C++ include full-suffix matching and the
        # Java/PHP/Ruby/Swift/Kotlin dotted-name lookup alike. Bespoke
        # extractors (python/js/go/rust) have no `spec` and keep the 3-arg
        # signature, so gate the index-passing on spec presence.
        for stmt in imports:
            # TYPE_CHECKING imports never run, so they are no edge in any view. A
            # function-body (deferred/lazy) import (scope 'local', BACK-2076; a class
            # body, decorated or not, is 'module') is an edge, tagged with its scope
            # (BACK-2077): it runs only after every top-level import finished, so it
            # is the standard way to *break* a load-time cycle, and the cycle views
            # (imports:// ?circular, I002, which resolves here too, BACK-1723) leave it
            # out through ImportGraph.edge_view (BACK-445: registry.py's lazy
            # `from .analyzers.nginx import ...` exists "to avoid circular import").
            if stmt.is_type_checking:
                continue

            # BACK-1723: every file the statement loads, not only the primary
            # one -- `from pkg import b` (b a submodule) runs pkg/b.py at
            # startup, so it is a cycle edge; depends:// already used targets.
            # Skip self-references (e.g., logging.py importing stdlib logging
            # should not create logging.py → logging.py dependency)
            targets = [t for t in resolve_targets(
                stmt, extractor, ResolutionContext(base_path, tuple(extra_paths), file_index))
                if t != file_path]
            if targets:
                for resolved in targets:
                    analysis.graph.add_dependency(file_path, resolved, stmt.scope)
                    mark_structural(analysis.graph, extractor, file_path, resolved)
                analysis.graph.resolved_paths[stmt.module_name] = targets[0]
                # BACK-1193: carry the resolution onto the statement itself
                # (not just the module-name-keyed graph index) so per-import
                # consumers like deps:// can classify on resolution truth
                # instead of re-guessing from the raw module string.
                stmt.resolved_path = targets[0]
                continue

            # BACK-544: the single-file dotted match above only catches a
            # namespace that coincidentally names one matching file. The
            # common case — a namespace declared across several files —
            # needs the namespace index instead, fanning out to every
            # declaring file (skipping the importing file itself).
            if namespace_index and getattr(getattr(extractor, 'spec', None), 'resolve_namespaces', False):
                for target in getattr(extractor, 'resolve_namespace_targets')(stmt, namespace_index):
                    if target != file_path:
                        analysis.graph.add_dependency(file_path, target, stmt.scope)
                        mark_structural(analysis.graph, extractor, file_path, target)
                        stmt.resolved_path = target  # BACK-1193: any in-tree target proves intra-project

    return analysis


_LAZY_PHRASES = {
    LAZY_INCLUDE: 'function-level (lazy) imports included',
    LAZY_EXCLUDE: 'function-level (lazy) imports excluded',
    LAZY_ONLY: 'only function-level (lazy) imports',
}


@dataclass(frozen=True)
class ResolvedAt:
    """Where an imports:// answer was resolved and which rows it shows (BACK-1054), for its rule.

    ``root`` is the scan root as displayed (relative to the requested path), ``root_source``
    one of ``resolution.ROOT_SOURCES``, ``scope`` the request's ``&scope`` (``root``: rows under
    the requested path, edges from anywhere under the root; ``path``: the requested path is the
    root), ``tests`` its ``&tests``. ``gated`` names the languages a recall oracle scores; edges
    from any other language are named as not gated. ``cycles`` marks a cycle view, which leaves
    module and convention edges out. ``outside_root`` counts the edges whose target lies outside
    the scan root, which no count includes (BACK-2251).
    """
    root: str
    root_source: str
    scope: str
    tests: str
    gated: frozenset
    cycles: bool = False
    outside_root: int = 0


_VIA_ORDER = ('direct', 'constant', 'namespace', 'member', 'module', 'convention')


def _outside_root_note(at: ResolvedAt) -> str:
    """The sentence naming the edges no count includes because their target lies outside the scan root."""
    return f' {at.outside_root} edge(s) resolve outside the scan root, not counted.' if at.outside_root else ''


def _resolution_fields(graph: ImportGraph, at: ResolvedAt) -> Tuple[Dict[str, Any], str]:
    """The rule fields and text an answer resolved through the cascade adds: its root, scope and
    tests choice, how many counted edges each cascade stage found, and the ungated languages."""
    via: Dict[str, int] = {}
    ungated: Dict[str, int] = {}
    for src, targets in graph.dependencies.items():
        language = language_for_extension(src.suffix.lower()) or src.suffix
        for dst in targets:
            tags = graph.edge_via.get((src, dst)) or {'direct'}
            first = next(tag for tag in _VIA_ORDER if tag in tags)
            via[first] = via.get(first, 0) + 1
            if language not in at.gated:
                ungated[language] = ungated.get(language, 0) + 1
    via = {tag: via[tag] for tag in _VIA_ORDER if tag in via}
    fields = {'root': at.root, 'root_source': at.root_source, 'scope_param': at.scope, 'tests_param': at.tests,
              'via': via, 'ungated_languages': sorted(ungated), 'ungated_edges': sum(ungated.values()),
              'outside_root_edges': at.outside_root}
    rows = 'rows are files under the requested path' if at.scope == 'root' else 'the requested path is the scan root'
    text = f' Resolved at the scan root {at.root} ({at.root_source.replace("_", " ")}); {rows}'
    if via:
        text += '; edges by stage: ' + ', '.join(f'{tag} {n}' for tag, n in via.items())
    if at.cycles:
        text += '; module and convention edges never close a cycle'
    text += '.' + _outside_root_note(at)
    if ungated:
        text += (f' Not gated (no recall oracle measures them): {", ".join(sorted(ungated))}, '
                 f'{sum(ungated.values())} edge(s); treat those counts as unmeasured.')
    return fields, text


def edge_rule(graph: ImportGraph, lazy: str, *, lazy_default: bool, subject: str,
              scope: str, tests_counted: bool = True, hint: Optional[str] = None,
              resolved_at: Optional[ResolvedAt] = None, counted: Optional[ImportGraph] = None) -> Dict[str, Any]:
    """The counting rule of an edge-derived answer, for its JSON and its text (BACK-2077).

    ``lazy`` is the LAZY_MODES value the answer used and ``lazy_default`` whether the
    request left it to the view's default. ``subject`` names what is counted, ``scope``
    which files an edge may join ('scanned_path' or 'scan_root'). ``hint`` replaces the
    default pointer at the other ``&lazy`` values. Edges from languages whose extractor
    records no import scope are named: every view counts them as load-time. ``resolved_at``
    (imports://) adds where the answer was resolved and its stage and gating counts over
    ``counted``, the view the answer counts (the graph itself when not given).
    """
    unclassified = graph.unclassified_edges()
    languages = sorted({language_for_extension(src.suffix.lower()) or src.suffix
                        for src, _target in unclassified})
    where = 'files under the scanned path' if scope == 'scanned_path' else 'files under the scan root'
    tests = ', tests included' if tests_counted else ', importers under a test path not counted'
    source = 'default' if lazy_default else f'&lazy={lazy}'
    if hint is None:
        hint = _RULE_HINT.get()
    if hint is None:
        hint = 'other views: ' + ', '.join(f'&lazy={mode}' for mode in LAZY_MODES if mode != lazy)
    text = (f'Rule: {subject} {where}{tests}; TYPE_CHECKING imports excluded; '
            f'{_LAZY_PHRASES[lazy]} ({source}); {hint}.')
    if unclassified:
        text += (f' Import scope is not recorded for {", ".join(languages)}: '
                 f'{len(unclassified)} edge(s) count as load-time under every &lazy value.')
    rule = {
        'lazy': lazy,
        'lazy_default': lazy_default,
        'type_checking': 'excluded',
        'tests': 'included' if tests_counted else 'importers_not_counted',
        'scope': scope,
        'unclassified_edges': len(unclassified),
        'unclassified_languages': languages,
    }
    # A command composing imports answers (inside composed_rules) takes no &scope, &tests or &root
    # and keeps the rule it printed before: the resolution fields are imports://'s own.
    if resolved_at is not None and _RULE_HINT.get() is None:
        fields, more = _resolution_fields(graph if counted is None else counted, resolved_at)
        rule.update(fields)
        text += more
    rule['text'] = text
    return rule


def _counting_view(rule: Dict[str, Any]) -> Tuple[Any, Any, Any]:
    """What makes two rules count different edges (the subject only names what is counted)."""
    return rule['lazy'], rule['tests'], rule['scope']


def fold_edge_rules(rules: Dict[str, Optional[Dict[str, Any]]], headline: str) -> Dict[str, Any]:
    """The rule fields of one answer made of several edge-derived sections (BACK-2087).

    ``rules`` maps each section to the ``edge_rule`` its formatter returned. ``headline`` is
    the section whose rule the answer leads with; a section that counts different edges
    (another ``&lazy`` view, tests not counted) keeps its own rule under ``edge_rule_sections``,
    so no number is read under a rule it was not counted by. An answer with no headline rule
    counted no edge and returns nothing.
    """
    head = rules.get(headline)
    if not head:
        return {}
    sections = {name: rule for name, rule in rules.items()
                if name != headline and rule and _counting_view(rule) != _counting_view(head)}
    return {'edge_rule': head, **({'edge_rule_sections': sections} if sections else {})}


def composed_rule_hint(noun: str) -> str:
    """The ``hint`` of a rule printed by a command that takes no ``&lazy`` itself (the default
    hint would point at a parameter that command rejects)."""
    return f'{noun} takes no &lazy; imports:// answers the same counts with &lazy=include|exclude|only'


_RULE_HINT: ContextVar[Optional[str]] = ContextVar('edge_rule_hint', default=None)


@contextmanager
def composed_rules(noun: str) -> Iterator[None]:
    """Rules built inside this block point at ``imports://``'s views, not at an ``&lazy`` that
    ``noun`` rejects: for a command that composes imports answers (BACK-2087). The scope ends with
    the block, so no later request reads it."""
    token = _RULE_HINT.set(composed_rule_hint(noun))
    try:
        yield
    finally:
        _RULE_HINT.reset(token)


def architecture_edge_rules(fan_in: Dict[str, Any], entrypoints: Dict[str, Any],
                            components: Dict[str, Any], circular: Dict[str, Any]) -> Dict[str, Any]:
    """``fold_edge_rules`` for the four imports answers architecture, overview and the
    architecture comparison are made of; fan-in leads, because its rule is the default one."""
    return fold_edge_rules({'fan_in': fan_in.get('edge_rule'), 'entry_points': entrypoints.get('edge_rule'),
                            'components': components.get('edge_rule'), 'cycles': circular.get('edge_rule')},
                           'fan_in')


def edge_rule_lines(result: Dict[str, Any]) -> List[str]:
    """The text lines that state an answer's counting rule: the one renderer of ``edge_rule``.

    Every consumer of the edge-derived graph prints through this (imports, depends and the
    commands that rank by the same edges), so the JSON objects and the text cannot drift.
    A section's rule is labelled with the section it governs.
    """
    rule = result.get('edge_rule')
    if not rule:
        return []
    lines = [rule['text']]
    for name, section in (result.get('edge_rule_sections') or {}).items():
        lines.append(section['text'].replace('Rule:', f"Rule ({name.replace('_', ' ')}):", 1))
    return lines
