"""File checking utilities for recursive directory analysis.

This module handles quality checking of files in a directory tree:
- Loading and respecting .gitignore patterns
- Collecting supported files for analysis
- Running quality checks and reporting results
"""

import sys
import os
import logging
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, TYPE_CHECKING

from ..utils.path_utils import (
    ScopeCensus,
    _language_for_path,
    is_skippable_dir,
    tally_files_by_language,
    to_posix,
)

if TYPE_CHECKING:
    from argparse import Namespace

# Minimum files before paying process-pool startup overhead.
# On Linux (fork), startup is cheap; on Windows/macOS (spawn) it's heavier,
# but the break-even is still low for CPU-bound work.
_PARALLEL_THRESHOLD = 4

# Import shared threshold and generated-file detector from checks module.
from reveal.checks import _GROUP_THRESHOLD, _is_generated_file  # noqa: E402
# Single source of truth for severity icons, shared with Detection.__str__ so
# the single-file and directory renderers cannot drift apart (BACK-857).
from reveal.rules.base import SEVERITY_MARKERS  # noqa: E402


def _parallel_worker(packed_args: tuple) -> tuple:
    """Check one file and return results without printing.

    Module-level so it is picklable by multiprocessing.

    Args:
        packed_args: (file_path, directory, select, ignore)

    Returns:
        (file_path, issue_count, detections, status)
    """
    file_path, directory, select, ignore = packed_args
    issue_count, detections, status = check_and_collect_file(file_path, directory, select, ignore)
    return file_path, issue_count, detections, status


def _i002_will_run(select, ignore) -> bool:
    """Return True if I002 is in the effective rule set for the given filters.

    Delegates to the same RuleRegistry resolution the per-file check uses, so
    the preload decision can never drift from what actually runs. In particular
    this honors --select: ``check <dir> --select C901`` must not trigger the
    expensive I002 import-graph build (BACK-338).
    """
    from reveal.rules import RuleRegistry
    rules = RuleRegistry.get_rules(select=select, ignore=ignore)
    return any(r.code == "I002" for r in rules)


def _i002_preload(directory: Path, select, ignore, files: Optional[List[Path]] = None) -> dict:
    """Build the I002 import graph in the main process before spawning workers.

    Returns a plain dict (project_root -> ImportGraph) ready to pickle into
    each worker via the ProcessPoolExecutor initializer.  Workers that receive
    a non-empty cache skip the expensive tree-sitter scan entirely.

    Skips the build entirely (returns {}) when I002 is not in the effective rule
    set — e.g. it is ignored, or --select asks for unrelated rules only.

    BACK-1041: root resolution must start from an actual source file, not the
    bare scan directory. ``_find_project_root`` only climbs *upward* looking
    for markers, so a `directory` that sits above a package boundary (e.g. the
    CLI target is a vendored corpus's parent, with the real `package.json`/
    `.git` one level down inside it) never sees that marker and climbs past it
    to whatever VCS root is further up — which can be a much larger, unrelated
    tree. Each file's own `check()` call resolves its root from the file's own
    path and correctly stops at the nearer marker, so preloading from
    `directory` alone can guess a different (and wrong) root than every
    worker actually ends up using — wasting the preload and logging a
    misleading "likely project-root mis-detection" warning even though the
    real per-file analysis goes on to succeed. Preloading from a real file
    under `directory` keeps the guess consistent with what workers resolve.
    """
    try:
        if not _i002_will_run(select, ignore):
            return {}
        from reveal.rules.imports.I002 import I002, _find_project_root, _graph_cache
        sample = files[0] if files else directory
        root = _find_project_root(sample.resolve())
        I002()._build_import_graph(root)   # populates _graph_cache in main process
        return dict(_graph_cache)          # plain dict is picklable
    except Exception:
        # Documented fallback (see docstring): caller degrades to the old
        # per-worker build behaviour when the shared cache can't be built.
        return {}


def _i002_init_worker(graph_cache: dict) -> None:
    """ProcessPoolExecutor initializer: seed each worker's I002 cache.

    Runs once per worker process, before any files are checked.  Importing
    the module here is safe because each worker is a fresh process.
    """
    if not graph_cache:
        return
    try:
        from reveal.rules.imports.I002 import _graph_cache
        _graph_cache.update(graph_cache)
    except Exception:  # I002 module unavailable in some configs; worker continues without cache
        pass


def _d005_will_run(select, ignore) -> bool:
    """Return True if D005 is in the effective rule set for the given filters.
    Mirrors _i002_will_run's reasoning exactly."""
    from reveal.rules import RuleRegistry
    rules = RuleRegistry.get_rules(select=select, ignore=ignore)
    return any(r.code == "D005" for r in rules)


def _d005_preload(directory: Path, select, ignore, files: Optional[List[Path]] = None) -> dict:
    """Build the D005 cross-file literal index in the main process before
    spawning workers. Mirrors _i002_preload:

    1. Without this, each worker builds its own copy of the index
       independently on first use (no cross-worker sharing) instead of once.
    2. BACK-1051: a capped scan records its skip reason on
       ``reveal.rules.duplicates.D005._project_skip_reasons``, a process-local
       dict. A worker-process build is invisible to the main process that
       renders the final summary, so the disclosure would silently vanish
       under the (default, >=4 files) parallel path — the exact case
       BACK-1051 exists to fix. Building here, in the main process, is what
       makes ``D005.get_scan_disclosures()`` reliable regardless of whether
       the run went parallel or serial.

    Returns a plain dict (project_root -> {canonical_key -> occurrences}) —
    D005's index values are plain dicts/lists/tuples/strings, so this is
    picklable without any extra work, same as I002's ImportGraph return.
    """
    try:
        if not _d005_will_run(select, ignore):
            return {}
        from reveal.rules.duplicates.D005 import D005, _build_index, _find_project_root, _project_index
        sample = files[0] if files else directory
        root = _find_project_root(sample.resolve())
        if root not in _project_index:
            _project_index[root] = _build_index(root, D005())
        return dict(_project_index)
    except Exception:
        # Documented fallback (see docstring): caller degrades to the old
        # per-worker build behaviour when the shared cache can't be built.
        return {}


def _d005_init_worker(project_index: dict) -> None:
    """ProcessPoolExecutor initializer: seed each worker's D005 index cache.
    Mirrors _i002_init_worker."""
    if not project_index:
        return
    try:
        from reveal.rules.duplicates.D005 import _project_index
        _project_index.update(project_index)
    except Exception:  # D005 module unavailable in some configs; worker continues without cache
        pass


def _preload_scan_caches(files: List[Path], directory: Path, select, ignore) -> dict:
    """Preload every scan-capped rule's shared index/graph in the main
    process, returning a dict of {rule_code: cache} for the pool initializer.
    Single call site so a future rule with the same shape (BACK-1051's
    "shared result-envelope contract" direction, see BACK-1093/1086) has one
    place to register, not one more copy-pasted preload/init pair wired by
    hand into every parallel entry point.
    """
    return {
        'I002': _i002_preload(directory, select, ignore, files),
        'D005': _d005_preload(directory, select, ignore, files),
    }


def _init_scan_caches(caches: dict) -> None:
    """ProcessPoolExecutor initializer counterpart to _preload_scan_caches."""
    _i002_init_worker(caches.get('I002', {}))
    _d005_init_worker(caches.get('D005', {}))


def _get_scan_disclosures() -> List[str]:
    """BACK-1051: collect every capped-scan disclosure recorded in this
    process by rules with a shared-index/graph scan ceiling (I002, D005).
    Call only after the check run has completed (serial or parallel) —
    _preload_scan_caches guarantees the main process sees a worker's cap
    hit, not just a serial in-process one. Returns [] when nothing was
    capped, which callers must treat as "confirmed complete", not "unknown".
    """
    disclosures: List[str] = []
    try:
        from reveal.rules.imports.I002 import get_scan_disclosures as i002_disclosures
        disclosures.extend(i002_disclosures())
    except Exception:
        pass
    try:
        from reveal.rules.duplicates.D005 import get_scan_disclosures as d005_disclosures
        disclosures.extend(d005_disclosures())
    except Exception:
        pass
    return disclosures


def _run_parallel(files: List[Path], directory: Path, select, ignore) -> list:
    """Run file checks in parallel, preserving input order in results.

    The I002 import graph and D005 literal index are each built once in the
    main process and injected into every worker via the initializer, so
    workers get a cache hit instead of rebuilding independently (was: 4
    builds for 4 workers → now: 1; see _preload_scan_caches).

    Args:
        files: Already-sorted list of files to check
        directory: Base directory for relative paths
        select: Rule codes to select
        ignore: Rule codes to ignore

    Returns:
        List of (file_path, issue_count, detections, status) in same order as input
    """
    # Benchmark shows 4 workers captures ~74% of max speedup (vs 12 workers at
    # 100%). Beyond 4, marginal gain is <0.5s while fork overhead grows.
    # Capping at 4 leaves remaining cores free and reduces IPC pressure.
    workers = min(4, os.cpu_count() or 4, len(files))
    args_iter = [(f, directory, select, ignore) for f in files]
    caches = _preload_scan_caches(files, directory, select, ignore)
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=_init_scan_caches,
        initargs=(caches,),
    ) as pool:
        return list(pool.map(_parallel_worker, args_iter))


def _run_parallel_streaming(files: List[Path], directory: Path, select, ignore):
    """Run file checks in parallel, yielding results as each future completes.

    Unlike _run_parallel, results are emitted as soon as they are ready rather
    than buffering the entire list before returning.  At most max_workers
    results are held in memory simultaneously.  Output order is non-deterministic
    (completion order), which is acceptable for text output but not JSON.

    Use _run_parallel for JSON output where deterministic ordering matters.

    Args:
        files: Files to check
        directory: Base directory for relative paths
        select: Rule codes to select
        ignore: Rule codes to ignore

    Yields:
        (file_path, issue_count, detections, status) tuples as futures complete
    """
    from concurrent.futures import as_completed
    workers = min(4, os.cpu_count() or 4, len(files))
    args_list = [(f, directory, select, ignore) for f in files]
    caches = _preload_scan_caches(files, directory, select, ignore)
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=_init_scan_caches,
        initargs=(caches,),
    ) as pool:
        futures = {pool.submit(_parallel_worker, args): args[0] for args in args_list}
        for future in as_completed(futures):
            try:
                yield future.result()
            except Exception as e:
                file_path = futures[future]
                logging.warning("check: skipped %s — %s: %s", file_path, type(e).__name__, e)


def _print_grouped_detections(
    detections: list,
    relative: Path,
    no_group: bool = False,
    shown_guidance: Optional[set] = None,
) -> None:
    """Print detections for one file, collapsing rules that repeat excessively.

    When a rule fires >= _GROUP_THRESHOLD times in a single file the first
    occurrence is shown followed by a "+N more" note.  Keeps noisy generated
    configs (e.g. cPanel ea-nginx.conf) from burying genuine findings.

    BACK-1039: that collapsing only helped WITHIN one file — a rule firing
    once each across many files (e.g. B006 60x, one per file) never hit
    _GROUP_THRESHOLD and printed its full suggestion+context block every
    single time (699 lines/32KB observed on one real run vs. 80 for the
    identical --select via --format grep). `shown_guidance`, when passed by
    the caller and shared across the whole run (not just one file), tracks
    which rule codes have already had their full suggestion+context shown
    anywhere — first occurrence run-wide gets the full block, every later
    one (same file or a different one) gets the terse file:line line only.
    `--no-group` still bypasses this, same as the within-file collapsing.

    Args:
        detections: Ordered list of Detection objects for this file
        relative: CWD-relative path used as the source label
        no_group: When True, skip collapsing/guidance-dedup entirely
        shown_guidance: Rule codes whose full guidance has already printed
            somewhere in this run; mutated in place. None = always show
            (matches pre-BACK-1039 per-file-only behavior, e.g. single-file
            check_and_report_file, which has nothing else to dedup against).
    """
    severity_icons = SEVERITY_MARKERS

    def _emit(d, icon: str) -> None:
        print(f"{relative}:{d.line}:{d.column} {icon} {d.rule_code} {d.message}")
        if no_group or shown_guidance is None or d.rule_code not in shown_guidance:
            if shown_guidance is not None:
                shown_guidance.add(d.rule_code)
            if d.suggestion:
                print(f"  💡 {d.suggestion}")
            if d.context:
                print(f"  📝 {d.context}")

    if no_group or len(detections) < _GROUP_THRESHOLD:
        for d in detections:
            _emit(d, severity_icons.get(d.severity, "ℹ️ "))
        return

    # Identify which rule codes exceed the grouping threshold
    by_rule: dict = defaultdict(list)
    for d in detections:
        by_rule[d.rule_code].append(d)
    collapsed = {code for code, grp in by_rule.items() if len(grp) >= _GROUP_THRESHOLD}
    shown_collapsed: set = set()

    for d in detections:
        icon = severity_icons.get(d.severity, "ℹ️ ")
        if d.rule_code not in collapsed:
            _emit(d, icon)
        elif d.rule_code not in shown_collapsed:
            shown_collapsed.add(d.rule_code)
            total = len(by_rule[d.rule_code])
            _emit(d, icon)
            print(f"  ↳ +{total - 1} more {d.rule_code} occurrences hidden — use --no-group to expand")


def load_gitignore_patterns(directory: Path) -> List[str]:
    """Load .gitignore patterns from directory.

    Args:
        directory: Directory containing .gitignore file

    Returns:
        List of gitignore patterns (empty if no .gitignore or on error)
    """
    gitignore_file = directory / '.gitignore'
    if not gitignore_file.exists():
        return []

    try:
        with open(gitignore_file, encoding='utf-8') as f:
            return [
                line.strip() for line in f
                if line.strip() and not line.startswith('#')
            ]
    except Exception:
        return []


def should_skip_file(relative_path: Path, gitignore_patterns: List[str]) -> bool:
    """Check if file should be skipped based on gitignore patterns.

    Args:
        relative_path: File path relative to repository root
        gitignore_patterns: List of gitignore patterns

    Returns:
        True if file should be skipped
    """
    import fnmatch

    path_str = to_posix(relative_path)
    parts = relative_path.parts

    for pattern in gitignore_patterns:
        # Exact fnmatch on full path
        if fnmatch.fnmatch(path_str, pattern):
            return True
        # Directory patterns (trailing /): match any file whose path starts with that dir
        # gitignore's "htmlcov/" means "htmlcov/ and all its contents"
        if pattern.endswith('/'):
            dir_name = pattern.rstrip('/')
            if parts and fnmatch.fnmatch(parts[0], dir_name):
                return True
        # Bare directory name without slash: also treat as directory prefix match
        # e.g. "htmlcov" should match "htmlcov/index.html"
        elif '/' not in pattern and '.' not in pattern and '*' not in pattern:
            if parts and fnmatch.fnmatch(parts[0], pattern):
                return True
    return False


@dataclass
class FileCollectionResult:
    """Result of collect_files_to_check(): survivors plus *why* everything
    else was excluded, so `check --format json` can eventually disclose scope
    (files discovered/skipped, by reason) instead of silently discarding this
    information at the point it's known (BACK-889 / design doc
    BACK884_COVERAGE_CENSUS_UNIFICATION finding #4).
    """

    files: List[Path] = field(default_factory=list)
    skipped_gitignore: int = 0
    skipped_no_analyzer: int = 0
    skipped_dirs: int = 0
    # BACK-1038: files with a recognized code extension but no registered
    # analyzer (e.g. Objective-C, capability_tier=unknown) — a subset of
    # skipped_no_analyzer, broken out by language so to_scope_census() can
    # surface them the same way overview's census_for_path() already does,
    # instead of silently dropping the language from scope.languages.
    no_analyzer_by_language: Dict[str, Dict[str, object]] = field(default_factory=dict)

    def to_scope_census(self) -> ScopeCensus:
        """Build the BACK-884 scope census for this collection: per-language
        breakdown of `.files` (the survivors) plus the skip-reason counts
        already tracked here. `check` is the one BACK-884 target command
        that builds its census from an already-collected file list rather
        than calling `census_for_path` — it has skip-reason data that a
        fresh walk wouldn't.

        BACK-1038: `.files` alone under-reports scope.languages relative to
        overview/architecture, which count any recognized code extension
        regardless of analyzer availability — a target with e.g.
        Objective-C source (extension recognized, no analyzer) would show
        that language in overview's census but not check's, silently
        implying check looked at it. Merge in no_analyzer_by_language so
        both censuses agree on what languages are *present*, even though
        check's `.files` (and thus what it actually ran rules against)
        stays unchanged — capability_tiers_for() will correctly render
        these as 'unknown' tier at the command layer, same as overview.
        """
        counts = tally_files_by_language(self.files)
        per_language = {lang: v['count'] for lang, v in counts.items()}
        language_extensions = {lang: v['ext'] for lang, v in counts.items()}
        for lang, v in self.no_analyzer_by_language.items():
            per_language[lang] = per_language.get(lang, 0) + v['count']
            language_extensions.setdefault(lang, v['ext'])
        return ScopeCensus(
            per_language=per_language,
            language_extensions=language_extensions,
            skipped_gitignore=self.skipped_gitignore,
            skipped_no_analyzer=self.skipped_no_analyzer,
            skipped_dirs=self.skipped_dirs,
        )


def collect_files_to_check(
    directory: Path,
    gitignore_patterns: List[str],
    exclude_patterns: Optional[List[str]] = None,
) -> FileCollectionResult:
    """Collect all supported files in directory tree.

    Args:
        directory: Root directory to scan
        gitignore_patterns: Patterns to skip (from .gitignore, empty if
            --no-gitignore)
        exclude_patterns: Additional user-supplied --exclude patterns
            (BACK-1042); matched with the same semantics as
            gitignore_patterns so a directory pattern like
            "wp-includes/js/dist/*" prunes the whole subtree instead of
            just filtering it out of the final report.

    Returns:
        FileCollectionResult: survivors (`.files`) plus skip-reason counts.
    """
    from ..registry import get_analyzer, get_code_extensions

    code_exts = get_code_extensions()
    files_to_check: List[Path] = []
    skipped_gitignore = 0
    skipped_no_analyzer = 0
    skipped_dirs = 0
    no_analyzer_by_language: Dict[str, Dict[str, object]] = {}
    skip_patterns = list(gitignore_patterns) + list(exclude_patterns or [])

    for root, dirs, files in os.walk(directory):
        # Filter out excluded directories and *.egg-info build artifacts
        root_path = Path(root)
        kept_dirs = []
        for d in dirs:
            if is_skippable_dir(root_path, d) or d.endswith('.egg-info'):
                skipped_dirs += 1
                continue
            if skip_patterns:
                rel_dir = (root_path / d).relative_to(directory)
                # Append a dummy filename so should_skip_file sees parts correctly
                if should_skip_file(rel_dir / '_', skip_patterns):
                    skipped_dirs += 1
                    continue
            kept_dirs.append(d)
        dirs[:] = kept_dirs

        for filename in files:
            file_path = root_path / filename
            relative_path = file_path.relative_to(directory)

            # Skip gitignored/excluded files
            if should_skip_file(relative_path, skip_patterns):
                skipped_gitignore += 1
                continue

            # Check if file has a supported analyzer
            if get_analyzer(str(file_path), allow_fallback=False):
                files_to_check.append(file_path)
            else:
                skipped_no_analyzer += 1
                # BACK-1038: a recognized code extension with no analyzer
                # (e.g. Objective-C) is still a language *present* in the
                # target — track it separately so to_scope_census() can
                # report it (matching overview's un-gated census) without
                # adding the file to files_to_check (rules still can't run
                # on it, that part of the behavior is correct as-is).
                ext = file_path.suffix.lower()
                if ext in code_exts:
                    lang = _language_for_path(file_path)
                    if lang:
                        entry = no_analyzer_by_language.setdefault(lang, {'count': 0, 'ext': ext})
                        entry['count'] += 1

    return FileCollectionResult(
        files=files_to_check,
        skipped_gitignore=skipped_gitignore,
        skipped_no_analyzer=skipped_no_analyzer,
        skipped_dirs=skipped_dirs,
        no_analyzer_by_language=no_analyzer_by_language,
    )


def check_and_report_file(
    file_path: Path,
    directory: Path,
    select: Optional[list[str]],
    ignore: Optional[list[str]],
    no_group: bool = False,
) -> int:
    """Check a single file and report issues.

    Args:
        file_path: Path to file to check
        directory: Base directory for relative paths
        select: Rule codes to select (None = all)
        ignore: Rule codes to ignore
        no_group: Disable collapsing of repeated rule detections

    Returns:
        Number of issues found (0 if no issues or on error)
    """
    from ..registry import get_analyzer
    from ..rules import RuleRegistry

    try:
        analyzer_class = get_analyzer(str(file_path), allow_fallback=False)
        if not analyzer_class:
            return 0

        analyzer = analyzer_class(str(file_path))
        # Always request links so link-checking rules (L001, L002) can reuse
        # this parse instead of creating a second analyzer for each file.
        structure = analyzer.get_structure(extract_links=True)
        content = analyzer.content

        # Skip auto-generated files silently in recursive sweeps
        if _is_generated_file(content):
            return 0

        detections = RuleRegistry.check_file(
            str(file_path), structure, content, select=select, ignore=ignore
        )

        if not detections:
            return 0

        # Always use CWD-relative paths so editor "click to jump" works regardless
        # of where the target argument points (matches ruff/mypy/flake8 behavior).
        cwd = Path.cwd()
        try:
            relative = file_path.relative_to(cwd)
        except ValueError:
            relative = file_path.relative_to(directory)
        issue_count = len(detections)
        print(f"\n{relative}: Found {issue_count} issue{'s' if issue_count != 1 else ''}\n")
        _print_grouped_detections(detections, relative, no_group=no_group)

        return issue_count

    except Exception as e:
        logging.warning("check: skipped %s — %s: %s", file_path, type(e).__name__, e)
        return 0


def check_and_collect_file(
    file_path: Path,
    directory: Path,
    select: Optional[list[str]],
    ignore: Optional[list[str]],
    profile: Optional[dict] = None,
) -> tuple[int, list, dict]:
    """Check a single file and return structured results.

    Args:
        file_path: Path to file to check
        directory: Base directory for relative paths
        select: Rule codes to select (None = all)
        ignore: Rule codes to ignore
        profile: When given, accumulates each rule's wall-clock seconds into
            profile[rule.code] (BACK-540). See RuleRegistry.check_file.

    Returns:
        Tuple of (issue_count, detections_list, status). status is a dict
        with a "status" key ("ok" | "skipped" | "error" | "warning") and,
        when not "ok", a "detail" string; "warning" additionally means the
        file parsed via error-recovery (BACK-1084's structure['_has_errors'])
        so detections may be based on fabricated/partial structure. Present
        so callers can disclose "this file could not be fully checked"
        instead of it reading identically to a genuinely clean file
        (BACK-1083).
    """
    from ..registry import get_analyzer
    from ..rules import RuleRegistry

    try:
        analyzer_class = get_analyzer(str(file_path), allow_fallback=False)
        if not analyzer_class:
            return 0, [], {"status": "skipped", "detail": "no analyzer for this file type"}

        analyzer = analyzer_class(str(file_path))
        # Always request links so link-checking rules (L001, L002) can reuse
        # this parse instead of creating a second analyzer for each file.
        structure = analyzer.get_structure(extract_links=True)
        content = analyzer.content

        # Skip auto-generated files silently in recursive sweeps
        if _is_generated_file(content):
            return 0, [], {"status": "skipped", "detail": "auto-generated file"}

        rule_errors: list = []
        detections = RuleRegistry.check_file(
            str(file_path), structure, content, select=select, ignore=ignore,
            profile=profile, errors=rule_errors,
        )

        status: dict = {"status": "ok"}
        if isinstance(structure, dict) and structure.get('_has_errors'):
            status = {
                "status": "warning",
                "detail": "file did not parse cleanly; results may be incomplete or incorrect",
            }
        if rule_errors:
            status["rule_errors"] = rule_errors

        return len(detections), detections, status

    except Exception as e:
        logging.warning("check: skipped %s — %s: %s", file_path, type(e).__name__, e)
        return 0, [], {"status": "error", "detail": f"{type(e).__name__}: {e}"}


def _build_cli_overrides(args: 'Namespace') -> dict:
    """Build CLI overrides dictionary from args.

    Args:
        args: Parsed arguments

    Returns:
        CLI overrides dict for config system
    """
    cli_overrides = {}
    if args.select or args.ignore:
        rules_override = {}
        if args.select:
            rules_override['select'] = [r.strip() for r in args.select.split(',')]
        if args.ignore:
            rules_override['disable'] = [r.strip() for r in args.ignore.split(',')]
        cli_overrides['rules'] = rules_override
    return cli_overrides


def _handle_no_files_found(directory: Path, output_format: str) -> None:
    """Handle case when no files found to check.

    Args:
        directory: Directory that was checked
        output_format: Output format (json or text)
    """
    import json
    from reveal.utils.results import add_cli_contract_fields
    from reveal.utils.json_utils import attach_provenance

    if output_format == 'json':
        result = {
            "files": [],
            "summary": {
                "files_checked": 0,
                "files_with_issues": 0,
                "total_issues": 0,
                "exit_code": 0
            }
        }
        print(json.dumps(
            attach_provenance(add_cli_contract_fields(result, result_type='check', source=directory, source_type='directory')),
            indent=2,
        ))
    else:
        print(f"No supported files found in {directory}")


_SEVERITY_ORDER = ['low', 'medium', 'high', 'critical']


def _apply_severity_filter(detections: list, severity: Optional[str]) -> list:
    """Filter detections to only those at or above the given severity level."""
    if not severity:
        return detections
    level = severity.lower()
    if level not in _SEVERITY_ORDER:
        return detections
    min_idx = _SEVERITY_ORDER.index(level)
    return [d for d in detections if _SEVERITY_ORDER.index(d.severity.value.lower()) >= min_idx]


def _check_files_json(
    files: List[Path], directory: Path, select: Optional[List[str]], ignore: Optional[List[str]],
    severity: Optional[str] = None,
) -> tuple:
    """Check files and collect JSON results.

    Args:
        files: List of files to check
        directory: Base directory
        select: Rule codes to select
        ignore: Rule codes to ignore
        severity: Minimum severity level to report (low/medium/high/critical)

    Returns:
        Tuple of (total_issues, files_with_issues, file_results, files_errored).
        files_errored counts files whose analyzer/parse pipeline raised
        (BACK-1083) — distinct from files simply skipped (no analyzer for the
        file type), which are not counted as an error.
    """
    total_issues = 0
    files_with_issues = 0
    files_errored = 0
    file_results = []
    sorted_files = sorted(files)

    if len(sorted_files) >= _PARALLEL_THRESHOLD:
        try:
            results = _run_parallel(sorted_files, directory, select, ignore)
        except Exception:
            # Parallel execution itself failed (e.g. pool startup) — fall back to
            # serial, still checking every file in sorted_files, not a smaller set.
            results = [(f, *check_and_collect_file(f, directory, select, ignore)) for f in sorted_files]
    else:
        results = [(f, *check_and_collect_file(f, directory, select, ignore)) for f in sorted_files]

    cwd = Path.cwd()
    for file_path, issue_count, detections, status in results:
        detections = _apply_severity_filter(detections, severity)
        issue_count = len(detections)
        st = status.get("status", "ok")
        if st == "error":
            files_errored += 1
        if issue_count > 0:
            total_issues += issue_count
            files_with_issues += 1
        if issue_count > 0 or st != "ok":
            try:
                rel_path = file_path.relative_to(cwd)
            except ValueError:
                rel_path = file_path.relative_to(directory)
            entry = {
                "file": to_posix(rel_path),
                "issues": issue_count,
                "detections": [
                    {
                        "line": d.line,
                        "column": d.column,
                        "rule_code": d.rule_code,
                        "message": d.message,
                        "severity": d.severity.value,
                        "suggestion": d.suggestion,
                        "context": d.context
                    }
                    for d in detections
                ]
            }
            if st != "ok":
                entry["status"] = st
                if status.get("detail"):
                    entry["detail"] = status["detail"]
            if status.get("rule_errors"):
                entry["rule_errors"] = status["rule_errors"]
            file_results.append(entry)

    return total_issues, files_with_issues, file_results, files_errored


def _check_files_text(
    files: List[Path],
    directory: Path,
    select: Optional[List[str]],
    ignore: Optional[List[str]],
    no_group: bool = False,
    severity: Optional[str] = None,
    limit: int = 50,
) -> tuple:
    """Check files with text output.

    Args:
        files: List of files to check
        directory: Base directory
        select: Rule codes to select
        ignore: Rule codes to ignore
        no_group: Disable collapsing of repeated rule detections
        severity: Minimum severity level to report (low/medium/high/critical)
        limit: Stop printing full per-file detail after this many files-with-
            issues and print a "+N more files" summary footer instead (BACK-539).
            0 (or negative) disables the cap — print every file in full.

    Returns:
        Tuple of (total_issues, files_with_issues, files_errored, files_degraded).
        See _check_files_json for what counts as errored vs. skipped (BACK-1083);
        files_degraded is status == "warning" (parsed via error-recovery).
    """
    total_issues = 0
    files_with_issues = 0
    files_errored = 0
    files_degraded = 0
    hidden_files = 0
    hidden_issues = 0
    sorted_files = sorted(files)

    # Use streaming parallel execution so results are processed as they complete
    # rather than buffering the full result set in memory first.  Non-deterministic
    # output order is acceptable for text mode (matches ruff/flake8 parallel behaviour).
    if len(sorted_files) >= _PARALLEL_THRESHOLD:
        try:
            result_iter = _run_parallel_streaming(sorted_files, directory, select, ignore)
        except Exception:
            # Parallel execution itself failed (e.g. pool startup) — fall back to
            # serial, still checking every file in sorted_files, not a smaller set.
            result_iter = (
                (f, *check_and_collect_file(f, directory, select, ignore))
                for f in sorted_files
            )
    else:
        result_iter = (
            (f, *check_and_collect_file(f, directory, select, ignore))
            for f in sorted_files
        )

    cwd = Path.cwd()
    # BACK-1039: shared run-wide (not per-file) so a rule's full guidance
    # prints once for the whole run — see _print_grouped_detections.
    shown_guidance: set = set()
    for file_path, issue_count, detections, status in result_iter:
        detections = _apply_severity_filter(detections, severity)
        issue_count = len(detections)
        st = status.get("status", "ok")
        if st == "error":
            files_errored += 1
        elif st == "warning":
            files_degraded += 1

        try:
            relative = file_path.relative_to(cwd)
        except ValueError:
            relative = file_path.relative_to(directory)

        if st == "error":
            print(f"\n{relative}: ⚠️  could not be checked — {status.get('detail', 'error')}")
        elif st == "warning":
            print(f"\n{relative}: ⚠️  {status.get('detail', 'file did not parse cleanly')}")
        for err in status.get("rule_errors", []):
            print(f"{relative}: ⚠️  rule {err['rule']} crashed and did not run — {err['error']}")

        if issue_count > 0:
            total_issues += issue_count
            files_with_issues += 1
            if limit > 0 and files_with_issues > limit:
                hidden_files += 1
                hidden_issues += issue_count
                continue
            print(f"\n{relative}: Found {issue_count} issue{'s' if issue_count != 1 else ''}\n")
            _print_grouped_detections(detections, relative, no_group=no_group, shown_guidance=shown_guidance)

    if hidden_files:
        print(
            f"\n… +{hidden_files} more file{'s' if hidden_files != 1 else ''} "
            f"with {hidden_issues} issue{'s' if hidden_issues != 1 else ''} hidden "
            f"(--limit {limit}) — narrow with --select, or raise/disable with --limit N/--limit 0"
        )

    return total_issues, files_with_issues, files_errored, files_degraded


def _print_json_output(
    file_results: List[dict],
    files_checked: int,
    files_with_issues: int,
    total_issues: int,
    source: Path,
    scope: Optional[ScopeCensus] = None,
    select: Optional[List[str]] = None,
    ignore: Optional[List[str]] = None,
    files_errored: int = 0,
    scan_disclosures: Optional[List[str]] = None,
) -> None:
    """Print JSON output with results and summary.

    Args:
        file_results: List of file result dicts
        files_checked: Total files checked
        files_with_issues: Files with issues count
        total_issues: Total issues count
        scope: BACK-884 census (files discovered/analyzed/skipped by reason,
            per-language capability tier) — additive top-level key, omitted
            when not supplied.
        select: Rule select filter actually applied to this run, so
            `scope.unscoped_categories` (BACK-1021) only reports gaps among
            rule categories that actually ran.
        ignore: Rule ignore filter actually applied to this run (see `select`).
        source: Directory that was checked, for the Output Contract envelope
            (BACK-962).
        files_errored: Files whose analyzer/parse pipeline raised (BACK-1083)
            — a subset of files_checked that could not be checked at all;
            individual reasons are on each file_results entry's "detail".
        scan_disclosures: BACK-1051 — one-line skip reasons from any
            scan-capped rule (I002, D005) whose own project/directory-wide
            index build was truncated by a safety ceiling. Distinct from
            files_errored/files_degraded (those are per-file); this is
            rule-wide — e.g. "I002 skipped, tree too large" doesn't map to
            any single file. [] means confirmed complete, not omitted.
    """
    import json
    from reveal.utils.results import add_cli_contract_fields
    from reveal.utils.json_utils import attach_provenance

    files_degraded = sum(1 for fr in file_results if fr.get("status") == "warning")
    result = {
        "files": file_results,
        "summary": {
            "files_checked": files_checked,
            "files_with_issues": files_with_issues,
            "files_errored": files_errored,
            "files_degraded": files_degraded,
            "total_issues": total_issues,
            "exit_code": 1 if total_issues > 0 else 0,
            "scan_disclosures": scan_disclosures or [],
        }
    }
    if scope is not None:
        from ..capabilities import capability_tiers_for
        from ..registry import display_name_for_extension
        from ..rules import RuleRegistry
        from ..rules.coverage import unscoped_rule_categories

        scope_dict = scope.to_scope_dict(
            capability_tiers=capability_tiers_for(scope.language_extensions)
        )
        active_rules = RuleRegistry.get_rules(select, ignore)
        gaps = unscoped_rule_categories(scope.language_extensions.keys(), active_rules)
        for gap in gaps:
            ext = scope.language_extensions.get(gap["language"], "")
            gap["language"] = display_name_for_extension(ext) or gap["language"]
        scope_dict["unscoped_categories"] = gaps
        result["scope"] = scope_dict
    print(json.dumps(
        attach_provenance(add_cli_contract_fields(result, result_type='check', source=source, source_type='directory')),
        indent=2,
    ))


def _print_grep_output(file_results: List[dict]) -> None:
    """Print check results as grep-style lines (BACK-1035).

    Mirrors checks.py's _format_detections_grep shape (file:line:col:rule:message)
    so `reveal check <dir> --format grep` and `reveal check <file> --format grep`
    (the pre-existing single-file path) agree on output shape.
    """
    for entry in file_results:
        file_path = entry["file"]
        for d in entry["detections"]:
            print(f"{file_path}:{d['line']}:{d['column']}:{d['rule_code']}:{d['message']}")


def _print_text_summary(
    files_checked: int, files_with_issues: int, total_issues: int, directory: Path, config,
    files_errored: int = 0, files_degraded: int = 0, scan_disclosures: Optional[List[str]] = None,
) -> None:
    """Print text summary with breadcrumbs.

    Args:
        files_checked: Total files checked
        files_with_issues: Files with issues count
        total_issues: Total issues count
        directory: Directory checked
        config: RevealConfig instance
        files_errored: Files that could not be checked at all (BACK-1083) —
            already individually flagged above; summarized here so the
            "no issues" line can't be misread as "everything was checked".
        files_degraded: Files checked via error-recovery parsing (BACK-1083)
            — rules ran, but against fabricated/partial structure, so their
            results (including "no issues") may be wrong, not just absent.
        scan_disclosures: BACK-1051 — one-line skip reasons from any
            scan-capped rule (I002, D005) whose project-wide index build was
            truncated. See _print_json_output's matching parameter.
    """
    print(f"\n{'='*60}")
    print(f"Checked {files_checked} files")
    if files_errored:
        print(f"⚠️  {files_errored} file{'s' if files_errored != 1 else ''} could not be checked (see warnings above)")
    if files_degraded:
        print(f"⚠️  {files_degraded} file{'s' if files_degraded != 1 else ''} did not parse cleanly — results for {'it' if files_degraded == 1 else 'them'} may be incomplete or incorrect (see warnings above)")
    for reason in (scan_disclosures or []):
        print(f"⚠️  {reason}")
    if total_issues > 0:
        print(f"Found {total_issues} issue{'s' if total_issues != 1 else ''} in {files_with_issues} file{'s' if files_with_issues != 1 else ''}")
    else:
        print("✅ No issues found")

    # Print workflow breadcrumbs
    from ..utils.breadcrumbs import print_breadcrumbs
    print_breadcrumbs(
        'directory-check',
        str(directory),
        config=config,
        total_issues=total_issues,
        files_with_issues=files_with_issues,
        files_checked=files_checked
    )


def handle_recursive_check(directory: Path, args: 'Namespace') -> None:
    """Handle recursive quality checking of a directory.

    Args:
        directory: Directory to check recursively
        args: Parsed arguments
    """
    # Resolve to absolute so all downstream paths are absolute and can be
    # expressed relative to CWD (matching ruff/mypy/flake8 path behavior).
    directory = directory.resolve()

    # Build CLI overrides and initialize config
    cli_overrides = _build_cli_overrides(args)
    from reveal.config import RevealConfig
    config = RevealConfig.get(start_path=directory, cli_overrides=cli_overrides if cli_overrides else None)

    # Collect files to check
    respect_gitignore = getattr(args, 'respect_gitignore', True)
    gitignore_patterns = load_gitignore_patterns(directory) if respect_gitignore else []
    exclude_patterns = getattr(args, 'exclude', None) or []
    collection = collect_files_to_check(directory, gitignore_patterns, exclude_patterns)
    files_to_check = collection.files

    # Handle no files found
    output_format = getattr(args, 'format', 'text')
    if not files_to_check:
        _handle_no_files_found(directory, output_format)
        return

    # Parse select/ignore options
    select = args.select.split(',') if args.select else None
    ignore = args.ignore.split(',') if args.ignore else None
    no_group = getattr(args, 'no_group', False)
    severity = getattr(args, 'severity', None)
    limit = getattr(args, 'limit', 50)

    # Check files based on output format
    if output_format == 'json':
        total_issues, files_with_issues, file_results, files_errored = _check_files_json(
            files_to_check, directory, select, ignore, severity=severity
        )
        _print_json_output(
            file_results, len(files_to_check), files_with_issues, total_issues,
            scope=collection.to_scope_census(), source=directory,
            select=select, ignore=ignore, files_errored=files_errored,
            scan_disclosures=_get_scan_disclosures(),
        )
    elif output_format == 'grep':
        # BACK-1035: this recursive/directory path only ever branched on
        # 'json' vs everything-else-is-text, so --format grep silently
        # rendered identical to text. Single-file `reveal check <file>`
        # already honors grep correctly via checks.py's
        # _format_detections_grep — reuse the same file:line:col:rule:msg
        # shape here, built from the JSON-mode per-file detections.
        total_issues, files_with_issues, file_results, _files_errored = _check_files_json(
            files_to_check, directory, select, ignore, severity=severity
        )
        _print_grep_output(file_results)
        for reason in _get_scan_disclosures():
            # BACK-1051: grep output is meant to stay machine-parseable
            # (file:line:col:rule:message only) — disclose to stderr rather
            # than polluting stdout with a non-conforming line.
            print(f"⚠️  {reason}", file=sys.stderr)
    else:
        if output_format == 'typed':
            # Not implemented for this path (or, as of BACK-1035's
            # follow-up audit, almost anywhere else in the CLI either) —
            # error rather than silently rendering text as if it were typed.
            print(
                "Error: --format typed is not yet implemented for 'reveal check' "
                "on a directory. Use --format json or --format grep instead.",
                file=sys.stderr,
            )
            sys.exit(2)
        total_issues, files_with_issues, files_errored, files_degraded = _check_files_text(
            files_to_check, directory, select, ignore, no_group=no_group, severity=severity, limit=limit
        )
        _print_text_summary(
            len(files_to_check), files_with_issues, total_issues, directory, config,
            files_errored=files_errored, files_degraded=files_degraded,
            scan_disclosures=_get_scan_disclosures(),
        )

    # Exit with appropriate code
    sys.exit(1 if total_issues > 0 else 0)


def handle_profile_rules(directory: Path, args: 'Namespace') -> None:
    """Handle `reveal check <dir> --profile-rules`: a per-rule wall-time
    breakdown of `check`, instead of the normal issue report (BACK-540).

    Filed after BACK-536's I002 investigation burned significant effort on two
    profiling wrong turns (cumulative-vs-self cProfile misread; module-level
    parse/graph-cache contamination comparing *separate* runs). This sidesteps
    both traps by instrumenting a single real pass instead of diffing two runs:
    each rule's check() call is individually timed as it actually executes, so
    a rule's cost lands on whichever file really paid it (e.g. I002 is charged
    for building its import graph on the first file that triggers it) — there
    is no second run and no cache state to contaminate a comparison against.

    Runs serially by design (not through the parallel/streaming path): a
    diagnostic report needs one coherent timing table, not times scattered
    across worker processes that would need re-aggregating.

    Args:
        directory: Directory to check recursively
        args: Parsed arguments
    """
    directory = directory.resolve()

    respect_gitignore = getattr(args, 'respect_gitignore', True)
    gitignore_patterns = load_gitignore_patterns(directory) if respect_gitignore else []
    exclude_patterns = getattr(args, 'exclude', None) or []
    files_to_check = collect_files_to_check(directory, gitignore_patterns, exclude_patterns).files
    if not files_to_check:
        _handle_no_files_found(directory, 'text')
        return

    select = args.select.split(',') if args.select else None
    ignore = args.ignore.split(',') if args.ignore else None

    from reveal.rules import RuleRegistry
    rules_in_scope = RuleRegistry.get_rules(select=select, ignore=ignore)
    rule_message = {r.code: r.message for r in rules_in_scope}

    profile: Dict[str, float] = {}
    total_issues = 0
    start = time.perf_counter()
    for file_path in sorted(files_to_check):
        issue_count, _detections, _status = check_and_collect_file(
            file_path, directory, select, ignore, profile=profile
        )
        total_issues += issue_count
    wall_time = time.perf_counter() - start

    profiled_time = sum(profile.values())
    print(f"\nProfiled {len(files_to_check)} files, {total_issues} issues, {wall_time:.2f}s wall time\n")
    print(f"{'RULE':<8} {'TIME':>10} {'%':>6}  WHAT")
    print("-" * 70)
    for code, seconds in sorted(profile.items(), key=lambda kv: kv[1], reverse=True):
        pct = (seconds / profiled_time * 100) if profiled_time else 0.0
        print(f"{code:<8} {seconds:>9.2f}s {pct:>5.1f}%  {rule_message.get(code, '')}")


# Legacy underscore-prefixed names for backwards compatibility
_load_gitignore_patterns = load_gitignore_patterns
_should_skip_file = should_skip_file
_collect_files_to_check = collect_files_to_check
_check_and_report_file = check_and_report_file
