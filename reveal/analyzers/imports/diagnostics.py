"""Shared disclosures carried by complete import analysis artifacts."""
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

from .types import ImportAnalysis
from ...reveal_types import PathFailure, WarningEntry
from ...utils.parallel import worker_lost_warning as _worker_lost_warning
from ...utils.path_utils import to_posix, to_relative_display

def worker_lost_warning(lost_files: List[str], base: Optional[Path] = None) -> Optional[WarningEntry]:
    """One meta warning for the files a dead pool worker took down before they were
    parsed (BACK-1753): not a parse error, and a file with no import extractor loses
    its structure the same way (BACK-1752)."""
    return cast(Optional[WarningEntry], _worker_lost_warning(
        lost_files, "their imports and structure are missing, so results can under-report", base))


def parse_failure_warning(failed_files: List[str], base: Optional[Path] = None) -> Optional[WarningEntry]:
    """One meta warning for the files tree-sitter parsed with errors (BACK-1598).

    The per-file extractor only sets ``parse_failed``; every command that builds
    an import graph discloses the set once, through this, rather than one log
    line per file per extraction pass (364 stderr lines on a cold `reveal
    overview` of Redis src/, none on a warm one, and never in the result).
    """
    if not failed_files:
        return None
    shown = [to_relative_display(f, base) if base else to_posix(f) for f in sorted(failed_files)[:5]]
    more = f" and {len(failed_files) - len(shown)} more" if len(failed_files) > len(shown) else ''
    return {
        'type': 'partial_parse',
        'count': len(failed_files),
        'files': shown,
        'message': (
            f"{len(failed_files)} file(s) parsed with errors -- their imports may be incomplete, "
            f"so import-graph results can under-report: {', '.join(shown)}{more}"
        ),
    }


def file_loss_warnings(analysis: ImportAnalysis, base: Optional[Path] = None, *,
                       spell: Optional[Callable[[Optional[str]], Optional[str]]] = None) -> List[WarningEntry]:
    """The per-file facts of one import build, each under its own cause (BACK-2190).

    ``files_failed`` holds three different things, and the user's next step differs: a file
    tree-sitter recovered with ERROR nodes (``partial_parse``: its recovered imports are edges), a
    file never parsed because it could not be read (``analysis_failed``, named by the OSError type:
    no tree, its imports are missing) and a file a dead pool worker took (``worker_lost``).
    ``spell`` names each file as the answer does (imports' ``_path_display``) instead of ``base``."""
    from ...utils.path_utils import analysis_skipped_warning
    name = _spelled(spell)
    if spell is not None:
        base = None
    lost = set(analysis.files_lost)
    partial: List[str] = []
    unread: List[Tuple[str, str]] = []
    for path in analysis.files_failed:
        if path in lost:
            continue
        extraction = analysis.extractions.get(path)
        parse = (extraction.diagnostics.get('parse') or {}) if extraction is not None else {}
        read_error = extraction.read_error if extraction is not None else None
        # Only a file whose tree was never built is unreadable (status 'unavailable', or an OSError);
        # a failed file with no such record is a parse failure, as it was before BACK-2190.
        if read_error or parse.get('status') == 'unavailable':
            unread.append((name(path), f'{read_error}: {parse.get("reason", "")}' if read_error
                           else str(parse.get('reason') or 'not parsed')))
        else:
            partial.append(name(path))
    warnings = [parse_failure_warning(partial, base), worker_lost_warning([name(p) for p in lost], base),
                analysis_skipped_warning(unread, base, 'analysis is incomplete; its imports are missing from the '
                                                       'import graph')]
    return [w for w in warnings if w]


def _spelled(spell: Optional[Callable[[Optional[str]], Optional[str]]]) -> Callable[[Any], str]:
    """``str`` of a path, or the answer's spelling of it when the caller passes one."""
    if spell is None:
        return str
    return lambda path: spell(str(path)) or str(path)


def integrity_warnings(analysis: ImportAnalysis, base: Optional[Path] = None, *,
                       spell: Optional[Callable[[Optional[str]], Optional[str]]] = None) -> List[WarningEntry]:
    """The graph's disclosures, for the commands that build it through _build_graph
    rather than get_structure (overview, architecture): files parsed with errors
    (parse_failure_warning) and files a dead pool worker took down
    (worker_lost_warning), each under its own cause. Paths are relative to ``base``, or
    spelled by ``spell`` (imports' own answers, BACK-2185) when one is given."""
    from ...utils.path_utils import analysis_skipped_warning, traversal_failed_warning
    name = _spelled(spell)
    if spell is not None:
        base = None
    traversal = [PathFailure(name(path) if path else path, cause)
                 for path, cause in getattr(analysis.graph, 'traversal_failures', ())]
    structure_failures = [(name(path), cause) for path, cause in analysis.structure_failures]
    warnings = [traversal_failed_warning(traversal, base),
                *file_loss_warnings(analysis, base, spell=spell),
                analysis_skipped_warning(
                    structure_failures, base,
                    "analysis is incomplete; some functions and classes may be missing from the complexity and structure results")]
    return [w for w in warnings if w]
