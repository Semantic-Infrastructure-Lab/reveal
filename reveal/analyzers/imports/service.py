"""Import analysis service: scope/files and resolution before adapter presentation.

Discovery stays in the shared file-index walker. This module owns graph assembly
and extractor resolution dispatch, rather than loading a resource adapter in the
analysis layer. Extraction/cache ownership remains with existing callers in this pilot.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import LanguageExtractor, get_extractor
from .file_index import discover_import_files
from .types import ImportAnalysis, ImportStatement


@dataclass(frozen=True)
class ScanScope:
    root: Path
    extensions: frozenset
    lowercase_extensions: frozenset = frozenset()
    cap: Optional[int] = None


@dataclass(frozen=True)
class ImportFileSet:
    candidates: Tuple[Path, ...]
    index: Dict[str, List[Path]]
    capped: bool = False


@dataclass(frozen=True)
class ResolutionContext:
    base_path: Path
    search_paths: Tuple[Path, ...]
    file_index: Dict[str, List[Path]]


def discover(scope: ScanScope) -> ImportFileSet:
    def accepts(path: Path) -> bool:
        return path.suffix in scope.extensions or path.suffix.lower() in scope.lowercase_extensions
    if scope.root.is_file():
        return ImportFileSet((scope.root,) if accepts(scope.root) else (), {})
    candidates, index, capped = discover_import_files(scope.root, accepts, cap=scope.cap)
    return ImportFileSet(tuple(candidates), index, capped)


def resolve_primary(stmt: ImportStatement, extractor: LanguageExtractor, context: ResolutionContext) -> Optional[Path]:
    kwargs: Dict[str, Any] = {'search_paths': list(context.search_paths)}
    if getattr(extractor, 'spec', None) is not None:
        kwargs['file_index'] = context.file_index
    return extractor.resolve_import(stmt, context.base_path, **kwargs)


def resolve_targets(stmt: ImportStatement, extractor: LanguageExtractor, context: ResolutionContext) -> List[Path]:
    if getattr(extractor, 'spec', None) is not None:
        primary = resolve_primary(stmt, extractor, context)
        return [primary] if primary else []
    return extractor.resolve_import_targets(stmt, context.base_path, search_paths=list(context.search_paths))


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
            # BACK-445: skip imports that can't cause a circular ImportError
            # at startup — matching the I002 circular-import rule's definition
            # (rules/imports/I002.py:_resolve_graph_dependencies):
            #   - TYPE_CHECKING imports never run at runtime
            #   - function-body (deferred/lazy) imports run only after all
            #     top-level code has finished importing — they are the
            #     standard pattern used to *break* cycles, so counting them
            #     as cycle edges reports phantom cycles (e.g. registry.py's
            #     lazy `from .analyzers.nginx import ...`, whose own comment
            #     says it exists "to avoid circular import").
            if stmt.is_type_checking or stmt.is_in_function:
                continue

            resolved = resolve_primary(
                stmt, extractor, ResolutionContext(base_path, tuple(extra_paths), file_index))
            # Skip self-references (e.g., logging.py importing stdlib logging
            # should not create logging.py → logging.py dependency)
            if resolved and resolved != file_path:
                analysis.graph.add_dependency(file_path, resolved)
                analysis.graph.resolved_paths[stmt.module_name] = resolved
                # BACK-1193: carry the resolution onto the statement itself
                # (not just the module-name-keyed graph index) so per-import
                # consumers like deps:// can classify on resolution truth
                # instead of re-guessing from the raw module string.
                stmt.resolved_path = resolved
                continue

            # BACK-544: the single-file dotted match above only catches a
            # namespace that coincidentally names one matching file. The
            # common case — a namespace declared across several files —
            # needs the namespace index instead, fanning out to every
            # declaring file (skipping the importing file itself).
            if namespace_index and getattr(getattr(extractor, 'spec', None), 'resolve_namespaces', False):
                for target in getattr(extractor, 'resolve_namespace_targets')(stmt, namespace_index):
                    if target != file_path:
                        analysis.graph.add_dependency(file_path, target)
                        stmt.resolved_path = target  # BACK-1193: any in-tree target proves intra-project

    return analysis
