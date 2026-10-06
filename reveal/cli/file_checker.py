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
from ..logging_setup import worker_bootstrap
from ..utils.parallel import pool_worker_count
from ..utils.results import note_truncation
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, TYPE_CHECKING

from ..utils.path_utils import (
    ScopeCensus,
    _language_for_path,
    as_spelled,
    _walk_code_files,
    tally_files_by_language,
    to_posix,
)

if TYPE_CHECKING:
    from argparse import Namespace

# Minimum files before paying process-pool startup overhead.
# On Linux (fork), startup is cheap; on Windows/macOS (spawn) it's heavier,
# but the break-even is still low for CPU-bound work.
_PARALLEL_THRESHOLD = 4

# Import shared threshold, generated-file detector and the rule-set/capability
# disclosure helpers (shared with single-file check, BACK-1466) from checks.
from reveal.checks import (  # noqa: E402
    _GROUP_THRESHOLD,
    _is_generated_file,
    capability_disclosures,
)
# The rules' project-wide indexes, built once here and seeded into every pool
# worker (BACK-1051); shared with stats://'s pool.
from reveal.rules.scan_caches import (  # noqa: E402
    get_scan_disclosures,
    init_scan_caches,
    preload_scan_caches,
)
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


def _pool_size(n_files: int) -> int:
    """Workers for check's pool over *n_files*: REVEAL_MAX_WORKERS when set
    (BACK-1436, the reader stats:// and imports:// use), else up to 4 -- a
    benchmark showed 4 workers capture ~74% of the max speedup (vs 12 workers at
    100%); beyond 4 the marginal gain is <0.5s while fork overhead and IPC
    pressure grow. Never more workers than files."""
    return min(pool_worker_count(min(4, os.cpu_count() or 4)), n_files)


def _check_worker_count(n_files: int) -> int:
    """1 = check the files serially in this process, without a pool: below
    _PARALLEL_THRESHOLD pool startup costs more than it saves, and
    REVEAL_MAX_WORKERS=1 asks for the serial path."""
    if n_files < _PARALLEL_THRESHOLD:
        return 1
    return _pool_size(n_files)


def _run_parallel(files: List[Path], directory: Path, select, ignore) -> list:
    """Run file checks in parallel, preserving input order in results.

    The I002 import graph and D005 literal index are each built once in the
    main process and injected into every worker via the initializer, so
    workers get a cache hit instead of rebuilding independently (was: 4
    builds for 4 workers → now: 1; see rules/scan_caches.py).

    Args:
        files: Already-sorted list of files to check
        directory: Base directory for relative paths
        select: Rule codes to select
        ignore: Rule codes to ignore

    Returns:
        List of (file_path, issue_count, detections, status) in same order as input
    """
    workers = _pool_size(len(files))
    args_iter = [(f, directory, select, ignore) for f in files]
    caches = preload_scan_caches(files, directory, select, ignore)
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=worker_bootstrap,
        initargs=(init_scan_caches, (caches,)),
    ) as pool:
        return list(pool.map(_parallel_worker, args_iter))


def _run_parallel_streaming(files: List[Path], directory: Path, select, ignore):
    """Run file checks in parallel, yielding results as each future completes.

    Unlike _run_parallel, results are emitted as soon as they are ready rather
    than buffering the entire list before returning, so at most max_workers
    results are held in memory simultaneously during execution. Yield order is
    completion order (non-deterministic) -- callers that need a stable
    processing order (e.g. the text report's --limit cutoff, BACK-1243)
    must buffer and re-sort before acting on it; this generator itself makes
    no ordering guarantee.

    Use _run_parallel for JSON output where deterministic ordering matters.

    Args:
        files: Files to check
        directory: Base directory for relative paths
        select: Rule codes to select
        ignore: Rule codes to ignore

    Yields:
        (file_path, issue_count, detections, status) tuples as futures complete;
        a future that failed (a dead worker breaks the pool and fails every
        pending one) yields ``status: error`` for its file instead of dropping it
    """
    from concurrent.futures import as_completed
    workers = _pool_size(len(files))
    args_list = [(f, directory, select, ignore) for f in files]
    caches = preload_scan_caches(files, directory, select, ignore)
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=worker_bootstrap,
        initargs=(init_scan_caches, (caches,)),
    ) as pool:
        futures = {pool.submit(_parallel_worker, args): args[0] for args in args_list}
        for future in as_completed(futures):
            try:
                yield future.result()
            except Exception as e:
                # A lost file (its worker died, BrokenProcessPool) is an errored file:
                # it stays in the report, counts in files_errored and exits 3
                # (BACK-1681). The report line is the one disclosure.
                yield (futures[future], 0, [],
                       {"status": "error", "detail": f"{type(e).__name__}: {e}"})


def _print_grouped_detections(
    detections: list,
    relative: str,
    no_group: bool = False,
    shown_guidance: Optional[set] = None,
    no_snippets: bool = False,
    max_snippet_chars: Optional[int] = None,
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
        no_snippets: Omit the 📝 code-excerpt line (BACK-1182).
        max_snippet_chars: Truncate the excerpt to N chars instead of
            omitting it (BACK-1181). Ignored when no_snippets.
    """
    severity_icons = SEVERITY_MARKERS

    def _emit(d, icon: str) -> None:
        print(f"{relative}:{d.line}:{d.column} {icon} {d.rule_code} {d.message}")
        if no_group or shown_guidance is None or d.rule_code not in shown_guidance:
            if shown_guidance is not None:
                shown_guidance.add(d.rule_code)
            if d.suggestion:
                print(f"  💡 {d.suggestion}")
            context = d.context
            if context and max_snippet_chars is not None and len(context) > max_snippet_chars:
                context = context[:max_snippet_chars] + '…'
            if context and not no_snippets:
                print(f"  📝 {context}")

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


def _cwd_relative(file_path: Path, directory: Path, cwd: Optional[Path] = None) -> str:
    """The path check prints for a file: relative to the cwd, so an editor's "click to
    jump" works wherever the target points (ruff/mypy/flake8 do the same), else relative
    to the checked directory. '/' on every OS (BACK-1586): the text, grep and JSON
    renders all print this one spelling."""
    try:
        return to_posix(file_path.relative_to(cwd or Path.cwd()))
    except ValueError:
        return to_posix(file_path.relative_to(directory))


def should_skip_file(relative_path: Path, gitignore_patterns: List[str]) -> bool:
    """True if *relative_path* matches an ``--exclude`` / REVEAL_IGNORE pattern.

    Patterns are gitignore syntax (BACK-1576, ``utils.gitignore.PatternSet``): a bare name
    matches at any depth, a pattern with a slash is anchored at the root *relative_path*
    is relative to, and a file under a matched directory is matched. Callers asking about a
    directory pass a synthetic child (``rel / '_'``).
    """
    from ..utils.gitignore import pattern_set
    return pattern_set(tuple(gitignore_patterns)).matches(to_posix(relative_path))


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
    respect_gitignore: Optional[bool] = None,
    exclude_patterns: Optional[List[str]] = None,
) -> FileCollectionResult:
    """Collect all supported files in directory tree.

    Args:
        directory: Root directory to scan
        respect_gitignore: skip what git ignores (BACK-1485, via
            utils/gitignore.py: tracked files are never skipped); None
            follows the process switch (--no-gitignore)
        exclude_patterns: Additional user-supplied --exclude patterns
            (BACK-1042), gitignore syntax (BACK-1576); a directory pattern
            like "wp-includes/js/dist/*" prunes the whole subtree instead of
            just filtering it out of the final report.

    Returns:
        FileCollectionResult: survivors (`.files`) plus skip-reason counts.
    """
    from ..registry import get_analyzer, get_code_extensions

    code_exts = get_code_extensions()
    files_to_check: List[Path] = []
    skipped = {True: 0, False: 0}  # is_dir -> count, whatever the cause
    skipped_no_analyzer = 0
    no_analyzer_by_language: Dict[str, Dict[str, object]] = {}

    def count_hidden(_path: Path, is_dir: bool, _cause: str) -> None:
        skipped[is_dir] += 1

    # The shared walker (BACK-1577): noise dirs, what git ignores, REVEAL_IGNORE and
    # --exclude are the seam's, so check sees the files ast:// and stats:// see.
    for file_path in _walk_code_files(directory, exclude_patterns, respect_gitignore,
                                      on_hidden=count_hidden):
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
        skipped_gitignore=skipped[False],
        skipped_no_analyzer=skipped_no_analyzer,
        skipped_dirs=skipped[True],
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

        relative = _cwd_relative(file_path, directory)
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
        from ..checks import structure_parse_degraded
        if structure_parse_degraded(structure):
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


def _no_files_message(directory) -> str:
    return f"No supported files found in {to_posix(directory)}"


def _handle_no_files_found(directory: Path, args: 'Namespace') -> None:
    """Answer a directory with nothing to check: an empty result, through the
    subcommand seam like every other check result (BACK-1545)."""
    from .routing.subcommand import emit_subcommand_result
    result = {
        "files": [],
        "summary": {
            "files_checked": 0,
            "files_with_issues": 0,
            "total_issues": 0,
            "exit_code": 0
        }
    }
    emit_subcommand_result(result, args, name='check', source=directory,
                           render=lambda _result: print(_no_files_message(directory)))


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


def check_exit_code(
    total_issues: int, files_errored: int = 0, files_degraded: int = 0,
    exit_zero: bool = False,
) -> int:
    """Compute `reveal check`'s process exit code (BACK-1099's contract).

    0 = clean: ran to completion, zero issues, every file parsed and every
        rule ran without raising.
    1 = issues found: ran to completion, no degraded/errored files, but at
        least one rule violation was reported.
    3 = incomplete scan: one or more files could not be checked at all
        (files_errored -- analyzer/parse pipeline raised) or were checked
        against a degraded/error-recovery parse (files_degraded) or a rule
        itself raised. Takes priority over 1 even when issues were also
        found, because a degraded scan means the issue *count* itself may
        be wrong or incomplete -- see
        internal-docs/design/EXIT_CODE_CONTRACT.md.

    (2 is reserved for usage/invocation errors -- bad args, unsupported
    path -- raised directly by the CLI layer before a scan starts, not
    computed here.)

    exit_zero (BACK-1186): once the scan itself completed (this function
    was reached at all -- a real usage error still exits 2 upstream of
    here), always return 0 regardless of findings or degraded files. "Were
    there issues" stays fully recorded in the JSON/text summary; this only
    changes the process exit code, matching how every other reveal adapter
    (overview://, hotspots://, ...) already behaves -- makes `check` safe
    to drop into a `set -e` / CI pipeline without the caller needing to
    know this one adapter's special exit-code convention.
    """
    if exit_zero:
        return 0
    if files_errored or files_degraded:
        return 3
    return 1 if total_issues > 0 else 0


def _build_file_entry(
    rel_path: str,
    issue_count: int,
    rendered: list,
    status: dict,
    no_snippets: bool = False,
    max_snippet_chars: Optional[int] = None,
) -> dict:
    """Build one `files[]` entry for check's JSON report.

    Extracted from _check_files_json (BACK-1248) so the text render path can
    produce the byte-identical per-file shape for --also-json instead of the
    artifact drifting from what --format json emits.
    """
    entry = {
        "file": rel_path,
        "issues": issue_count,
        "detections": [
            {
                "line": d.line,
                "column": d.column,
                "rule_code": d.rule_code,
                "message": d.message,
                "severity": d.severity.value,
                "suggestion": d.suggestion,
                **({} if no_snippets else {
                    "context": (
                        d.context[:max_snippet_chars] + '…'
                        if max_snippet_chars is not None and d.context
                        and len(d.context) > max_snippet_chars
                        else d.context
                    )
                }),
            }
            for d in rendered
        ]
    }
    st = status.get("status", "ok")
    if st != "ok":
        entry["status"] = st
        if status.get("detail"):
            entry["detail"] = status["detail"]
    if status.get("rule_errors"):
        entry["rule_errors"] = status["rule_errors"]
    return entry


class _ItemBudget:
    """--max-items: a running cap on rendered detections across the whole scan
    (BACK-1181), not per file. Each render (text, JSON, --also-json) holds its own.
    """

    def __init__(self, max_items: Optional[int]):
        self.remaining = max_items
        self.truncated = False
        self.offered = 0   # detections the render reached
        self.shown = 0     # of those, the ones it kept

    def take(self, detections: list) -> list:
        """The part of *detections* the budget still allows; the rest is cut."""
        rendered = detections
        if self.remaining is not None:
            rendered = detections[:max(self.remaining, 0)]
            self.remaining -= len(rendered)
        if len(rendered) < len(detections):
            self.truncated = True
        self.offered += len(detections)
        self.shown += len(rendered)
        return rendered

    def note_cut(self, result: dict) -> None:
        """Record the cut on *result* the way every other result records one
        (note_truncation, BACK-1545): JSON gets a ``meta.warnings`` entry and the
        subcommand seam prints ``⚠ Truncated ...`` after a text render. Nothing is
        recorded when nothing was cut."""
        note_truncation(result, 'detections', self.shown, self.offered, cause='max_items')


@dataclass
class _CheckedFile:
    """One file's check result after the --severity filter: the plain data every
    render of a directory check is built from (BACK-1534)."""

    relative: str
    detections: list
    status: dict

    @property
    def state(self) -> str:
        return str(self.status.get("status", "ok"))

    @property
    def reportable(self) -> bool:
        """Has issues or a non-ok status, so it gets a JSON ``files[]`` entry."""
        return bool(self.detections) or self.state != "ok"


@dataclass
class _CheckTally:
    """The summary counts, and the inputs to check_exit_code()."""

    total_issues: int = 0
    files_with_issues: int = 0
    files_errored: int = 0
    files_degraded: int = 0

    def add(self, checked: _CheckedFile) -> None:
        if checked.state == "error":
            self.files_errored += 1
        elif checked.state == "warning":
            self.files_degraded += 1
        if checked.detections:
            self.total_issues += len(checked.detections)
            self.files_with_issues += 1


def _filter_results(results, directory: Path, severity: Optional[str]) -> List[_CheckedFile]:
    """Apply --severity to each (file_path, issue_count, detections, status) result.
    A file's issue count is its filtered detections, so the summary and exit code
    agree with what is shown."""
    cwd = Path.cwd()
    return [
        _CheckedFile(_cwd_relative(file_path, directory, cwd),
                     _apply_severity_filter(detections, severity), status)
        for file_path, _issue_count, detections, status in results
    ]


def _tally(checked_files: List[_CheckedFile]) -> _CheckTally:
    tally = _CheckTally()
    for checked in checked_files:
        tally.add(checked)
    return tally


def _json_file_entries(
    checked_files: List[_CheckedFile],
    max_items: Optional[int] = None,
    no_snippets: bool = False,
    max_snippet_chars: Optional[int] = None,
) -> tuple:
    """The JSON report's ``files[]`` and the --max-items budget that cut it.
    Shared by --format json/grep and text's --also-json (BACK-1248), so the
    artifact is the document --format json prints."""
    budget = _ItemBudget(max_items)
    entries = [
        _build_file_entry(
            checked.relative, len(checked.detections), budget.take(checked.detections),
            checked.status, no_snippets=no_snippets, max_snippet_chars=max_snippet_chars,
        )
        for checked in checked_files if checked.reportable
    ]
    return entries, budget


def _check_files_json(
    files: List[Path], directory: Path, select: Optional[List[str]], ignore: Optional[List[str]],
    severity: Optional[str] = None,
    no_snippets: bool = False,
    max_snippet_chars: Optional[int] = None,
    max_items: Optional[int] = None,
) -> tuple:
    """Check files and collect JSON results.

    Args:
        files: List of files to check
        directory: Base directory
        select: Rule codes to select
        ignore: Rule codes to ignore
        severity: Minimum severity level to report (low/medium/high/critical)
        no_snippets: Omit each detection's `context` (code excerpt) field
            (BACK-1182).
        max_snippet_chars: Truncate each detection's `context` to N chars
            instead of omitting it (BACK-1181). Ignored when no_snippets.
        max_items: Cap the total number of rendered detections across the
            whole scan (BACK-1181) -- a running budget, not per-file. Files
            still report their true `issues` count and contribute fully to
            total_issues/exit-code computation; only the emitted `detections` arrays
            are truncated once the budget is exhausted.

    Returns:
        Tuple of (total_issues, files_with_issues, file_results, files_errored,
        items_truncated). files_errored counts files whose analyzer/parse
        pipeline raised (BACK-1083) — distinct from files simply skipped (no
        analyzer for the file type), which are not counted as an error.
        items_truncated is True when max_items cut off some detections.
    """
    checked_files = _check_json(files, directory, select, ignore, severity)
    tally = _tally(checked_files)
    file_results, budget = _json_file_entries(
        checked_files, max_items, no_snippets=no_snippets, max_snippet_chars=max_snippet_chars,
    )
    return tally.total_issues, tally.files_with_issues, file_results, tally.files_errored, budget.truncated


def _check_json(files: List[Path], directory: Path, select, ignore,
                severity: Optional[str]) -> List[_CheckedFile]:
    """Run the JSON/grep path's checks (an order-preserving pool map, or serially)
    and apply --severity."""
    sorted_files = sorted(files)

    if _check_worker_count(len(sorted_files)) > 1:
        try:
            results = _run_parallel(sorted_files, directory, select, ignore)
        except Exception:
            # Parallel execution itself failed (e.g. pool startup) — fall back to
            # serial, still checking every file in sorted_files, not a smaller set.
            results = [(f, *check_and_collect_file(f, directory, select, ignore)) for f in sorted_files]
    else:
        results = [(f, *check_and_collect_file(f, directory, select, ignore)) for f in sorted_files]
    return _filter_results(results, directory, severity)


def _results_in_sorted_order(sorted_files: List[Path], directory: Path, select, ignore) -> list:
    """Run the text path's checks; (file_path, issue_count, detections, status) per
    file, in ``sorted_files`` order.

    Uses streaming parallel execution so workers run concurrently rather than
    buffering the full result set before any of them start. Completion order is
    non-deterministic, so results are gathered by file and returned in the stable
    input order (BACK-1243): the ``--limit`` cutoff decides which files get full
    detail vs. get folded into the "N more files hidden" footer, and on completion
    order that decision (and the hidden-count total) varied run to run on
    byte-identical input. Every file is in the result: one whose worker died is an
    errored file (BACK-1681).
    """
    results_by_file: dict = {}
    if _check_worker_count(len(sorted_files)) > 1:
        try:
            for file_path, *rest in _run_parallel_streaming(sorted_files, directory, select, ignore):
                results_by_file[file_path] = tuple(rest)
        except Exception as e:
            # The pool itself failed (e.g. startup) -- the generator raises when
            # iterated, not when created. Check what it did not deliver serially.
            logging.warning("check: parallel run failed (%s: %s); checking the rest serially",
                            type(e).__name__, e)
    for f in sorted_files:
        if f not in results_by_file:
            results_by_file[f] = check_and_collect_file(f, directory, select, ignore)
    return [(f, *results_by_file[f]) for f in sorted_files]


@dataclass
class _TextFileBlock:
    """One file in the text report. ``shown`` is what prints under its
    "Found N issues" header; None = no header (no issues, or past --limit)."""

    checked: _CheckedFile
    shown: Optional[list] = None


@dataclass
class _TextReport:
    """The text report as plain data, before printing (BACK-1534; the print half
    is what BACK-916's single rendering layer takes over). ``budget`` is the
    --max-items cut of what the text prints; ``checked_files`` feed --also-json."""

    blocks: List[_TextFileBlock]
    tally: _CheckTally
    budget: _ItemBudget
    checked_files: List[_CheckedFile]
    hidden_files: int = 0
    hidden_issues: int = 0


def _build_text_report(
    checked_files: List[_CheckedFile], limit: int, max_items: Optional[int],
) -> _TextReport:
    """Apply --limit (files with issues shown in full) and --max-items (detections
    shown across the run). Both only shorten what prints: every file still counts.
    The budget only reaches the files --limit lets print, so its cut counts those;
    the rest are --limit's footer to disclose."""
    budget = _ItemBudget(max_items)
    report = _TextReport(blocks=[], tally=_CheckTally(), budget=budget, checked_files=checked_files)
    for checked in checked_files:
        report.tally.add(checked)
        block = _TextFileBlock(checked)
        if checked.detections:
            if limit > 0 and report.tally.files_with_issues > limit:
                report.hidden_files += 1
                report.hidden_issues += len(checked.detections)
            else:
                block.shown = budget.take(checked.detections)
        report.blocks.append(block)
    return report


def _print_file_status(checked: _CheckedFile) -> None:
    """A file that could not be checked, parsed degraded, or had a rule crash."""
    relative = checked.relative
    if checked.state == "error":
        print(f"\n{relative}: ⚠️  could not be checked — {checked.status.get('detail', 'error')}")
    elif checked.state == "warning":
        print(f"\n{relative}: ⚠️  {checked.status.get('detail', 'file did not parse cleanly')}")
    for err in checked.status.get("rule_errors", []):
        print(f"{relative}: ⚠️  rule {err['rule']} crashed and did not run — {err['error']}")


def _print_text_report(
    report: _TextReport,
    limit: int,
    no_group: bool = False,
    no_snippets: bool = False,
    max_snippet_chars: Optional[int] = None,
) -> None:
    """Print the per-file blocks and the --limit footer. The --max-items cut is the
    subcommand seam's to print, once, after the render (BACK-1545)."""
    # BACK-1039: shared run-wide (not per-file) so a rule's full guidance
    # prints once for the whole run — see _print_grouped_detections.
    shown_guidance: set = set()
    for block in report.blocks:
        _print_file_status(block.checked)
        if block.shown is None:
            continue
        relative = block.checked.relative
        issue_count = len(block.checked.detections)
        print(f"\n{relative}: Found {issue_count} issue{'s' if issue_count != 1 else ''}\n")
        _print_grouped_detections(
            block.shown, relative, no_group=no_group, shown_guidance=shown_guidance,
            no_snippets=no_snippets, max_snippet_chars=max_snippet_chars,
        )

    hidden_files, hidden_issues = report.hidden_files, report.hidden_issues
    if hidden_files:
        print(
            f"\n… +{hidden_files} more file{'s' if hidden_files != 1 else ''} "
            f"with {hidden_issues} issue{'s' if hidden_issues != 1 else ''} hidden "
            f"(--limit {limit}) — narrow with --select, or raise/disable with --limit N/--limit 0"
        )


def _check_text(
    files: List[Path],
    directory: Path,
    select: Optional[List[str]],
    ignore: Optional[List[str]],
    severity: Optional[str] = None,
    limit: int = 50,
    max_items: Optional[int] = None,
) -> _TextReport:
    """Check files for the text report: run, filter, build the report as data.
    Printing it is the render's job (_print_text_report), called by the
    subcommand seam.

    Args:
        files: List of files to check
        directory: Base directory
        select: Rule codes to select
        ignore: Rule codes to ignore
        severity: Minimum severity level to report (low/medium/high/critical)
        limit: Stop printing full per-file detail after this many files-with-
            issues and print a "+N more files" summary footer instead (BACK-539).
            0 (or negative) disables the cap — print every file in full.
        max_items: Cap the total number of rendered detections across the
            whole scan (BACK-1181) -- a running budget, not per-file (see
            _check_files_json).

    The report's ``checked_files`` give --also-json its `files[]` (BACK-1248),
    built with their own max_items budget and without `limit`, because `limit`
    is a print-density cap on the human report -- letting it truncate the
    machine artifact would make --also-json's content depend on a flag that
    exists only to shorten terminal output. See _check_files_json for what
    counts as errored vs. skipped (BACK-1083); files_degraded is status ==
    "warning" (parsed via error-recovery).
    """
    results = _results_in_sorted_order(sorted(files), directory, select, ignore)
    return _build_text_report(_filter_results(results, directory, severity), limit, max_items)


def _check_report(
    tally: _CheckTally,
    files_checked: int,
    budget: _ItemBudget,
    file_results: Optional[List[dict]] = None,
    scope: Optional[ScopeCensus] = None,
    select: Optional[List[str]] = None,
    ignore: Optional[List[str]] = None,
    scan_disclosures: Optional[List[str]] = None,
    exit_zero: bool = False,
) -> dict:
    """check's result as plain data; the subcommand seam (emit_subcommand_result /
    subcommand_json) adds the Output Contract envelope (BACK-1545).

    Args:
        tally: The summary counts. files_errored are files whose analyzer/parse
            pipeline raised (BACK-1083) — a subset of files_checked that could not
            be checked at all; individual reasons are on each file_results entry's
            "detail". files_degraded parsed via error recovery.
        files_checked: Total files checked
        budget: The --max-items budget the answer was cut with. Its cut is a
            ``note_truncation`` (``meta.warnings``); ``summary.items_truncated``
            stays for compatibility (BACK-1181).
        file_results: The ``files[]`` entries. None for the text report's result,
            whose per-file blocks are printed from _TextReport: it carries the
            summary and the cut the text printed under.
        scope: BACK-884 census (files discovered/analyzed/skipped by reason,
            per-language capability tier) — additive top-level key, omitted
            when not supplied.
        select: Rule select filter actually applied to this run, so
            `scope.unscoped_categories` (BACK-1021) only reports gaps among
            rule categories that actually ran.
        ignore: Rule ignore filter actually applied to this run (see `select`).
        scan_disclosures: BACK-1051 — one-line skip reasons from any
            scan-capped rule (I002, D005, T006) whose own project/directory-wide
            index build was truncated by a safety ceiling. Distinct from
            files_errored/files_degraded (those are per-file); this is
            rule-wide — e.g. "I002 skipped, tree too large" doesn't map to
            any single file. [] means confirmed complete, not omitted.
    """
    result: dict = {}
    if file_results is not None:
        result["files"] = file_results
    result["summary"] = {
        "files_checked": files_checked,
        "files_with_issues": tally.files_with_issues,
        "files_errored": tally.files_errored,
        "files_degraded": tally.files_degraded,
        "total_issues": tally.total_issues,
        "exit_code": check_exit_code(
            tally.total_issues, tally.files_errored, tally.files_degraded, exit_zero=exit_zero),
        "scan_disclosures": scan_disclosures or [],
        "items_truncated": budget.truncated,
    }
    if scope is not None:
        result["scope"] = _scope_dict(scope, select, ignore)
    budget.note_cut(result)
    return result


def _scope_dict(scope: ScopeCensus, select, ignore) -> dict:
    """The JSON report's ``scope`` block, with the rule categories no analyzer covers
    for the languages present (BACK-1021)."""
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
    return scope_dict


def _write_also_json_report(path: str, result: dict, source: str) -> None:
    """BACK-1248: write check's JSON report to *path* alongside a text/grep
    render on stdout, so one invocation produces both the human report and the
    machine artifact -- the document --format json prints (subcommand_json).

    Previously --also-json was wired only for the uri:// render paths and this
    subcommand merely warned that the flag did nothing, which left consumers
    dispatching `check` twice over the same tree. A write failure is reported
    on stderr and does not change the exit code -- the check itself succeeded,
    and its exit code is the answer the caller is branching on.
    """
    from .routing.subcommand import subcommand_json
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(subcommand_json(result, name='check', source=source))
    except OSError as e:
        print(f"Warning: --also-json could not write {path}: {e}", file=sys.stderr)


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
            truncated. See _check_report's matching parameter.
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

    The result leaves through the subcommand seam like every other ``reveal
    <name>`` (emit_subcommand_result, BACK-1545): JSON gets its envelope there,
    text and grep are rendered by it, and a --max-items cut is printed once after
    the render. The exit code stays check's own (EXIT_CODE_CONTRACT, BACK-1099):
    0 clean, 1 issues found, 2 usage error, 3 scan incomplete.

    Args:
        directory: Directory to check recursively
        args: Parsed arguments
    """
    # Resolve to absolute so all downstream paths are absolute and can be
    # expressed relative to CWD (matching ruff/mypy/flake8 path behavior).
    named = directory
    directory = directory.resolve()
    shown = as_spelled(directory, named)  # the envelope names it as the user did (BACK-1366)

    # Build CLI overrides and initialize config
    cli_overrides = _build_cli_overrides(args)
    from reveal.config import RevealConfig
    config = RevealConfig.get(start_path=directory, cli_overrides=cli_overrides if cli_overrides else None)

    # Collect files to check
    respect_gitignore = getattr(args, 'respect_gitignore', True) is not False
    exclude_patterns = getattr(args, 'exclude', None) or []
    collection = collect_files_to_check(directory, respect_gitignore, exclude_patterns)
    files_to_check = collection.files

    output_format = getattr(args, 'format', 'text')
    if not files_to_check:
        _handle_no_files_found(Path(shown), args)
        return
    if output_format == 'typed':
        # Not implemented for this path (or, as of BACK-1035's follow-up audit,
        # almost anywhere else in the CLI either) — error rather than silently
        # rendering text as if it were typed.
        print(
            "Error: --format typed is not yet implemented for 'reveal check' "
            "on a directory. Use --format json or --format grep instead.",
            file=sys.stderr,
        )
        sys.exit(2)

    if output_format in ('json', 'grep'):
        tally, result, render, artifact = _json_or_grep_check(files_to_check, directory, collection, args)
    else:
        tally, result, render, artifact = _text_check(files_to_check, directory, collection, config, args)

    from .routing.subcommand import emit_subcommand_result
    emit_subcommand_result(result, args, name='check', source=shown, render=render)
    if artifact is not None:
        _write_also_json_report(args.also_json, artifact, shown)

    # Exit with appropriate code (BACK-1099: distinguish "clean" from
    # "issues found" from "scan incomplete" -- files_errored/files_degraded
    # previously fed only the disclosure text/JSON summary, never the
    # actual process exit code, so a directory containing an unparseable
    # file exited 0 identically to an all-clean directory).
    from .routing.ledger import complete
    complete(args)  # the exit code is the result: the flag ledger still reports
    sys.exit(check_exit_code(
        tally.total_issues, tally.files_errored, tally.files_degraded,
        exit_zero=getattr(args, 'exit_zero', False),
    ))


def _rule_filters(args: 'Namespace') -> tuple:
    """--select/--ignore as rule-code lists (None when not given)."""
    select = args.select.split(',') if args.select else None
    ignore = args.ignore.split(',') if args.ignore else None
    return select, ignore


def _scan_disclosures(files: List[Path], select, ignore) -> List[str]:
    """Everything the run could not fully check, rule-wide: a capped scan
    (BACK-1051) and rules a language skips (BACK-1466). Read after the scan --
    the caps are recorded by it. [] claims the scan was complete."""
    return get_scan_disclosures() + capability_disclosures(files, select, ignore)


def _report_for(files: List[Path], collection: 'FileCollectionResult', args: 'Namespace',
                select, ignore, disclosures: List[str]):
    """_check_report with this run's arguments, so --format json and both
    --also-json writers describe the run the same way (BACK-1248): same scope,
    same scan disclosures, same exit_zero."""
    def report(tally: _CheckTally, budget: _ItemBudget, file_results: Optional[List[dict]] = None) -> dict:
        return _check_report(
            tally, len(files), budget, file_results,
            scope=collection.to_scope_census() if file_results is not None else None,
            select=select, ignore=ignore, scan_disclosures=disclosures,
            exit_zero=getattr(args, 'exit_zero', False),
        )
    return report


def _json_or_grep_check(files: List[Path], directory: Path, collection: 'FileCollectionResult',
                        args: 'Namespace') -> tuple:
    """Run check for --format json or grep: (tally, result, render, --also-json result).

    BACK-1035: --format grep renders file:line:col:rule:message, the shape the
    single-file ``reveal check <file> --format grep`` prints, from the JSON
    result's per-file detections. It never applied --max-items or the snippet
    flags, and its --also-json artifact is that same result.
    """
    select, ignore = _rule_filters(args)
    severity = getattr(args, 'severity', None)
    checked = _check_json(files, directory, select, ignore, severity)
    tally = _tally(checked)
    if args.format == 'json':
        file_results, budget = _json_file_entries(
            checked, getattr(args, 'max_items', None),
            no_snippets=getattr(args, 'no_snippets', False),
            max_snippet_chars=getattr(args, 'max_snippet_chars', None),
        )
    else:
        file_results, budget = _json_file_entries(checked)
    disclosures = _scan_disclosures(files, select, ignore)
    result = _report_for(files, collection, args, select, ignore, disclosures)(tally, budget, file_results)

    def render_grep(_result: dict) -> None:
        _print_grep_output(file_results)
        for reason in disclosures:
            # BACK-1051: grep output is meant to stay machine-parseable
            # (file:line:col:rule:message only) — disclose to stderr rather
            # than polluting stdout with a non-conforming line.
            print(f"⚠️  {reason}", file=sys.stderr)

    artifact = result if args.format == 'grep' and getattr(args, 'also_json', None) else None
    return tally, result, render_grep, artifact


def _text_check(files: List[Path], directory: Path, collection: 'FileCollectionResult', config,
                args: 'Namespace') -> tuple:
    """Run check for the text report: (tally, result, render, --also-json result).

    The text result carries the summary and the --max-items cut of what the text
    prints; its per-file blocks are printed from the _TextReport. --also-json gets
    the --format json document, with its own budget over every file (BACK-1248).
    """
    select, ignore = _rule_filters(args)
    no_group = getattr(args, 'no_group', False)
    no_snippets = getattr(args, 'no_snippets', False)
    max_snippet_chars = getattr(args, 'max_snippet_chars', None)
    max_items = getattr(args, 'max_items', None)
    limit = getattr(args, 'limit', None)
    if limit is None:  # --limit not typed (parser default is None; URI targets share the flag)
        limit = 50
    text = _check_text(files, directory, select, ignore, getattr(args, 'severity', None), limit, max_items)
    tally = text.tally
    disclosures = _scan_disclosures(files, select, ignore)
    report = _report_for(files, collection, args, select, ignore, disclosures)
    result = report(tally, text.budget)

    artifact = None
    if getattr(args, 'also_json', None):
        entries, budget = _json_file_entries(
            text.checked_files, max_items, no_snippets=no_snippets, max_snippet_chars=max_snippet_chars,
        )
        artifact = report(tally, budget, entries)

    def render_text(_result: dict) -> None:
        _print_text_report(text, limit, no_group=no_group,
                           no_snippets=no_snippets, max_snippet_chars=max_snippet_chars)
        _print_text_summary(
            len(files), tally.files_with_issues, tally.total_issues, directory, config,
            files_errored=tally.files_errored, files_degraded=tally.files_degraded,
            scan_disclosures=disclosures,
        )

    return tally, result, render_text, artifact


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

    respect_gitignore = getattr(args, 'respect_gitignore', True) is not False
    exclude_patterns = getattr(args, 'exclude', None) or []
    files_to_check = collect_files_to_check(directory, respect_gitignore, exclude_patterns).files
    if not files_to_check:
        print(_no_files_message(directory))
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
_should_skip_file = should_skip_file
_collect_files_to_check = collect_files_to_check
_check_and_report_file = check_and_report_file
