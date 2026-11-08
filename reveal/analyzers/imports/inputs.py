"""Explicit import scan inputs and shared discovery/extractor boundaries."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import LanguageExtractor
from .file_index import discover_import_files
from .packages import EMPTY_PACKAGES, PackageModel
from .types import ImportGraph, ImportStatement
from ...reveal_types import PathFailure
from ...utils.path_utils import HiddenTally, failure_of, under_directory

@dataclass(frozen=True)
class ScanScope:
    root: Path
    extensions: frozenset
    lowercase_extensions: frozenset = frozenset()
    cap: Optional[int] = None
    # The file or directory the request is about when the walk is wider than it (depends
    # walks from the project root): what is left to analyze is judged there (BACK-2075).
    focus: Optional[Path] = None
    # A focused build (BACK-2565): the walk, the file index and the project inputs still cover
    # the root, but only files at the focus are resolved, and a file outside it is extracted only
    # when its language indexes declarations project-wide (resolution.indexes_project_declarations).
    # For a consumer that reads only the focus's own imports (calls' callee bindings), never for a
    # view that needs edges INTO the focus (importers, rank, cycles).
    focus_only: bool = False


@dataclass(frozen=True)
class ImportFileSet:
    candidates: Tuple[Path, ...]
    index: Dict[str, List[Path]]
    capped: bool = False
    traversal_failures: Tuple[PathFailure, ...] = ()
    # Entries the walk hid, by actionable cause (``HiddenTally``; BACK-2065).
    # With a focus, the causes at the focus once the walk kept files elsewhere.
    hidden: Dict[str, int] = field(default_factory=dict)
    # Graph files at the scope's focus (all of them without one): what ``hidden`` is judged against.
    analyzed: int = 0


@dataclass(frozen=True)
class ResolutionContext:
    base_path: Path
    search_paths: Tuple[Path, ...]
    file_index: Dict[str, List[Path]]
    packages: PackageModel = EMPTY_PACKAGES  # the scan's package model (BACK-2559)


def discover(scope: ScanScope) -> ImportFileSet:
    def accepts(path: Path) -> bool:
        return path.suffix in scope.extensions or path.suffix.lower() in scope.lowercase_extensions
    if scope.root.is_file():
        kept = (scope.root,) if accepts(scope.root) else ()
        return ImportFileSet(kept, {}, analyzed=len(kept))
    failures: List[PathFailure] = []

    def on_error(error: OSError) -> None:
        failures.append(failure_of(error))

    hidden = HiddenTally(scope.focus)
    candidates, index, capped = discover_import_files(scope.root, accepts, cap=scope.cap, on_error=on_error,
                                                      on_hidden=hidden)
    focus = scope.focus
    if focus is None:
        return ImportFileSet(tuple(candidates), index, capped, tuple(failures), dict(hidden), len(candidates))
    in_focus = under_directory(focus)
    analyzed = sum(1 for c in candidates if in_focus(c))
    # A walk that kept nothing at all says everything it hid; one that kept files elsewhere
    # says only what hides the focus, so an ignored sibling is not blamed for an empty one.
    return ImportFileSet(tuple(candidates), index, capped, tuple(failures),
                         dict(hidden if not candidates else hidden.at_focus), analyzed)


def resolve_primary(stmt: ImportStatement, extractor: LanguageExtractor, context: ResolutionContext) -> Optional[Path]:
    kwargs: Dict[str, Any] = {'search_paths': list(context.search_paths)}
    if getattr(extractor, 'spec', None) is not None:
        kwargs['file_index'] = context.file_index
        kwargs['packages'] = context.packages
    return extractor.resolve_import(stmt, context.base_path, **kwargs)


def resolve_targets(stmt: ImportStatement, extractor: LanguageExtractor, context: ResolutionContext) -> List[Path]:
    if getattr(extractor, 'spec', None) is not None:
        primary = resolve_primary(stmt, extractor, context)
        return [primary] if primary else []
    return extractor.resolve_import_targets(stmt, context.base_path, search_paths=list(context.search_paths),
                                            packages=context.packages)


def mark_structural(graph: ImportGraph, extractor: LanguageExtractor, from_file: Path, to_file: Path) -> None:
    """Record an edge the importing language calls its module layout (BACK-2129)."""
    if extractor.is_structural_edge(from_file, to_file):
        graph.structural_edges.add((from_file, to_file))

