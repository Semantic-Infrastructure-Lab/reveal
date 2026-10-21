"""reveal review — code quality assessment before a PR merge."""

import argparse
import json
import os
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from ..global_flags import add_gitignore_arguments, rule_patterns
from ..routing.ledger import complete
from ..routing.subcommand import emit_subcommand_result
from ...utils.git_range import changed_files as _changed_files, git_range_error as _git_range_error
from ...utils.results import RESULT_CONTROL_WARNINGS, note_truncation, requested_fail_on
from ...utils.warning_render import collect_meta_warnings, render_meta_warnings

# Hotspots and complex functions each list their top this-many (BACK-1543 records the rest).
_SECTION_TOP = 10


def create_review_parser() -> argparse.ArgumentParser:
    """Create parser for reveal review subcommand."""
    from reveal.cli.parser import _build_global_options_parser
    from reveal.cli.invocation import exit_codes_text
    parser = argparse.ArgumentParser(
        prog='reveal review',
        parents=[_build_global_options_parser()],
        description='Retired: use `reveal check --changed RANGE` for the rules and the diff:// adapter '
                    'for structure. This command still answers until the cut release. '
                    'Assess code quality and structural changes before a PR merge. '
                    'A large range can take minutes.\n\n' + exit_codes_text('review'),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  reveal review ./src                 # Review a directory (whole tree)\n"
            "  reveal review main..feature         # PR diff — quality scoped to changed files\n"
            "  reveal review main..feature --format json  # CI/CD gate\n"
            "  reveal review ./src --select B,S    # Focus on bugs and security\n"
            "\n"
            "A git-range review analyzes only the files the diff touched, so cost\n"
            "scales with the PR, not the repository. A directory target reviews the\n"
            "whole tree under that path.\n"
        )
    )
    parser.add_argument(
        'target',
        metavar='PATH|RANGE',
        help='Path to review, or git range like main..feature'
    )
    parser.add_argument(
        '--select',
        type=rule_patterns,
        metavar='RULES',
        default='B,S,I,C,M',
        help='Rule categories (default: B,S,I,C,M)'
    )
    add_gitignore_arguments(parser)
    return parser


# Severities that make a review fail (exit 1, unless analysis was incomplete: exit 3). `check` severities are
# low/medium/high/critical (rules.base.Severity); only N002 emits critical.
BLOCKING_SEVERITIES = ('high', 'critical')


def run_review(args: Namespace) -> None:
    """Run the review workflow."""
    target = args.target
    is_git_range = '..' in target and not Path(target).exists()

    if is_git_range:
        range_error = _git_range_error(target)
        if range_error:
            _exit_invalid_target(target, range_error, args.format)
    elif not Path(target).exists():
        _exit_invalid_target(target, f"path does not exist: {target}", args.format)

    report: Dict[str, Any] = {
        'target': target,
        'is_diff': is_git_range,
        'sections': {},
    }
    errors: List[str] = []

    print(f"Review: {target}", file=sys.stderr)
    print("━" * 40, file=sys.stderr)

    # Step 1: Structural diff (if git range)
    if is_git_range:
        diff_data = _run_diff(target)
        report['sections']['diff'] = diff_data
        report['sections']['complexity_spikes'] = _extract_complexity_spikes(diff_data)

    # Step 2: Determine what to analyze.
    # For a git range, scope the quality pass to the files the diff actually
    # touched — a PR review must not report on (or pay to scan) the whole tree
    # (BACK-538). For a directory target, analyze that directory as asked.
    changed_files: Optional[List[Path]] = None
    path: Optional[Path] = None
    if is_git_range:
        changed_files = _changed_files(target)
        report['scoped_files'] = len(changed_files)
        print(f"  Scoped to {len(changed_files)} changed file(s)", file=sys.stderr)
    else:
        path = Path(target)

    # Step 3: Quality check
    print("  Checking quality rules…", file=sys.stderr)
    scan_disclosures: List[str] = []
    violations = _run_check(path, args.select, files=changed_files, errors=errors,
                            disclosures=scan_disclosures)
    report['sections']['violations'] = violations
    # BACK-1051: `review` is a composite command wrapping `check` — it must
    # propagate a capped-scan disclosure (I002/D005) rather than swallowing
    # it, the concrete symptom that motivated this ticket ("reveal review ."
    # on 20,000+ files produced a silent I002 skip").
    if scan_disclosures:
        report['scan_disclosures'] = scan_disclosures

    # Step 4: Hotspots
    print("  Analyzing hotspots…", file=sys.stderr)
    hotspot_warnings: List[Dict[str, Any]] = []
    _add_top_section(report, 'hotspots', _run_hotspots(path, files=changed_files, warnings=hotspot_warnings),
                     'see all: reveal hotspots <path> --all')
    if hotspot_warnings:
        report.setdefault('meta', {}).setdefault('warnings', []).extend(hotspot_warnings)

    # Step 5: Complexity
    print("  Scanning complexity…", file=sys.stderr)
    complexity_warnings: List[Dict[str, Any]] = []
    _add_top_section(report, 'complexity',
                     _run_complexity(path, files=changed_files, warnings=complexity_warnings),
                     "see all: reveal 'ast://<path>?complexity>10&sort=-complexity'")
    if complexity_warnings:
        report.setdefault('meta', {}).setdefault('warnings', []).extend(complexity_warnings)

    if errors:
        report['errors'] = errors
    report['overall_status'], report['exit_code'] = _review_outcome(
        violations, errors, analysis_incomplete=_lost_analysis(report),
        scan_incomplete=bool(scan_disclosures), fail_on=requested_fail_on(args))

    # Render
    if is_git_range:
        review_source_type = 'git_range'
    else:
        review_source_type = 'file' if path is not None and path.is_file() else 'directory'
    emit_subcommand_result(report, args, name='review', source=target,
                           source_type=review_source_type,
                           render=lambda r: _render_report(r, args.verbose))

    complete(args)  # the exit code is the result: the flag ledger still reports
    sys.exit(report['exit_code'])


def _add_top_section(report: Dict[str, Any], name: str, ranked: List[Dict[str, Any]],
                     hint: str) -> None:
    """Keep the top ``_SECTION_TOP`` of a ranked section and record the cut (BACK-1543).

    ``reveal review --format json`` listed 10 hotspots and 10 complex functions with no
    total, so a reader took them for all there were.
    """
    report['sections'][name] = ranked[:_SECTION_TOP]
    note_truncation(report, name, min(len(ranked), _SECTION_TOP), len(ranked), 'limit', hint=hint)


def _lost_analysis(report: Dict[str, Any]) -> bool:
    """True when hotspot or complexity analysis lost required files or directories."""
    return any(w.get('type') in {'analysis_failed', 'analysis_incomplete'}
               for w in report.get('meta', {}).get('warnings', []))


def _review_outcome(violations: List[Dict[str, Any]], errors: List[str],
                    analysis_incomplete: bool = False,
                    scan_incomplete: bool = False,
                    fail_on: Literal['none', 'findings'] = 'findings') -> tuple:
    """(overall_status, exit_code), D6 precedence (BACK-2051): incomplete/3 when the
    quality pass could not check everything (so an empty violation list is not proof
    of a clean change), a rule-wide scan was capped, skipped or partly unparsed
    (BACK-1824), or the hotspot or complexity step could not analyze every file
    (Scott, 2026-10-07); then fail/1 on a blocking-severity issue, warn/1 on any
    other violation, pass/0. Lost evidence beats a findings gate, and exit 2 stays
    reserved for usage rejection (an invalid target). ``fail_on='none'`` reports the
    findings (status stays fail/warn) without exit 1; it never hides incomplete analysis."""
    from ...utils.results import AnalysisCompleteness, ExecutionFacts, execution_exit_code
    incomplete = bool(errors or analysis_incomplete or scan_incomplete)
    if incomplete:
        status = 'incomplete'
    elif any(v.get('severity') in BLOCKING_SEVERITIES for v in violations):
        status = 'fail'
    else:
        status = 'warn' if violations else 'pass'
    facts = ExecutionFacts(AnalysisCompleteness.INCOMPLETE if incomplete else AnalysisCompleteness.COMPLETE,
                           findings=bool(violations))
    return status, execution_exit_code(facts, fail_on=fail_on)


def _exit_invalid_target(target: str, reason: str, output_format: str) -> None:
    """Usage error: exit 2 like any other invalid invocation, never a review."""
    if output_format == 'json':
        from reveal.utils.results import add_cli_contract_fields
        payload = {'target': target, 'overall_status': 'error', 'exit_code': 2, 'error': reason}
        print(json.dumps(add_cli_contract_fields(
            payload, result_type='review', source=target,
            source_type='git_range' if '..' in target else 'directory',
        ), indent=2))
    print(f"Error: cannot review {target!r}: {reason}", file=sys.stderr)
    sys.exit(2)


def _run_diff(git_range: str) -> Dict[str, Any]:
    """Run diff analysis for a git range."""
    try:
        from reveal.adapters.diff.adapter import DiffAdapter
        resource = f"git://{git_range.replace('..', '/.:git://')}/."
        adapter = DiffAdapter(resource)
        data = adapter.get_structure()
        return {'status': 'ok', 'data': data}
    except Exception as e:  # boundary-ok: broad-except -- any structural-diff failure falls back to the changed-file list and the error text is reported in structural_diff_error
        structural_error = f'{type(e).__name__}: {e}'

    # Fallback: git for changed file list
    try:
        parts = git_range.split('..', 1)
        # --end-of-options: git_range is caller-controlled -- without it, a part
        # starting with '-' is parsed as a git option (e.g. '--output=/path'
        # writes an arbitrary file) instead of a revision.
        result = subprocess.run(
            ['git', 'diff', '--name-only', '--end-of-options', parts[0], parts[1]],
            capture_output=True, text=True, timeout=10, encoding='utf-8', errors='replace'
        )
        files = [f for f in result.stdout.splitlines() if f.strip()]  # boundary-ok: splitlines -- git subprocess stdout
        return {'status': 'ok', 'changed_files': files, 'count': len(files),
                'structural_diff_error': structural_error}
    except Exception:  # boundary-ok: broad-except -- git or a malformed range makes the changed-file fallback unavailable; the status 'unavailable' is what the report shows
        return {'status': 'unavailable'}


def _run_check(path: Optional[Path], select: str,
               files: Optional[List[Path]] = None,
               errors: Optional[List[str]] = None,
               disclosures: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Run quality check and return violations.

    When `files` is given (a diff-scoped review), only those files are checked.
    Otherwise `path` (a directory or single file) is walked as before.
    A check that fails, or files it could not analyze, are appended to `errors`.
    """
    if errors is None:
        errors = []
    try:
        from reveal.cli.file_checker import (
            collect_files_to_check, _check_files_json,
        )
        if files is not None:
            check_files = [f.resolve() for f in files if f.is_file()]
            if not check_files:
                return []
            directory = Path(os.path.commonpath([str(f.parent) for f in check_files]))
        elif path is not None and path.is_dir():
            directory = path.resolve()
            check_files = collect_files_to_check(directory).files
        elif path is not None:
            directory = path.parent.resolve()
            check_files = [path.resolve()]
        else:
            return []
        select_list = select.split(',') if select else None
        _, _, file_results, files_errored, _ = _check_files_json(
            check_files, directory, select_list, None)
        if disclosures is not None:
            from reveal.rules.scan_caches import get_scan_disclosures
            disclosures.extend(get_scan_disclosures(check_files, select_list, None))
        if files_errored:
            errors.append(f"quality check could not analyze {files_errored} file(s)")
        violations: List[Dict[str, Any]] = []
        for fr in file_results:
            for d in fr.get('detections', []):
                violations.append({
                    'file': fr['file'],
                    'line': d.get('line', ''),
                    'rule': d.get('rule_code', ''),
                    'severity': d.get('severity', 'medium'),
                    'message': d.get('message', ''),
                })
        return violations
    except Exception as e:  # boundary-ok: broad-except -- the lint pass runs arbitrary rules; failure is printed and appended to the report's errors
        print(f"Warning: lint check failed, skipping: {e}", file=sys.stderr)
        errors.append(f"quality check failed: {e}")
        return []


def _run_hotspots(path: Optional[Path],
                  files: Optional[List[Path]] = None,
                  warnings: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Run hotspot analysis.

    When `files` is given (a diff-scoped review), rank only those files by their
    own churn×complexity score instead of scanning the whole tree.

    stats:// reports a file it could not analyze (a raising analyzer, or a pool
    worker that died, BACK-1718) through a meta warning and leaves it out of the
    ranking, and a single-file target through its ``error``. Both are appended to
    `warnings`, as overview:// and hotspots:// fold them, so a lost file is
    named instead of silently missing from the list (BACK-1738).
    """
    if warnings is None:
        warnings = []
    try:
        from reveal.adapters.stats.adapter import StatsAdapter
        targets = files if files is not None else ([path] if path is not None else [])
        hotspots: List[Dict[str, Any]] = []
        for target in targets:
            try:
                adapter = StatsAdapter(str(target), 'hotspots=true&top=0')  # all: cut once, above
                data = adapter.get_structure(hotspots=True)
                if data.get('error'):
                    warnings.append({'type': 'analysis_failed', 'count': 1,
                                     'message': f"hotspots: {target}: {data['error']}"})
                    continue
                warnings.extend({**w, 'message': f"hotspots: {w.get('message', '')}"}
                                for w in collect_meta_warnings(data)
                                if w.get('type') not in RESULT_CONTROL_WARNINGS)
                found = data.get('hotspots', data.get('files', [])) or []
                hotspots.extend(_as_hotspot(h) for h in found)
            except Exception as e:  # boundary-ok: broad-except -- one target's hotspot analysis failure is printed and recorded as an analysis_failed warning, the other targets still run
                print(f"Warning: hotspot analysis failed for {target}, skipping: {e}", file=sys.stderr)
                warnings.append(_analysis_failed('hotspots', target, e))
                continue
        hotspots = [h for h in hotspots if not _is_perfect_quality(h)]
        hotspots.sort(key=_hotspot_score, reverse=True)
        return hotspots
    except Exception as e:  # boundary-ok: broad-except -- the hotspot section runs the stats adapter; failure is printed, recorded as an analysis_failed warning, and the section is empty
        print(f"Warning: hotspot analysis failed, skipping: {e}", file=sys.stderr)
        warnings.append(_analysis_failed('hotspots', None, e))
        return []


def _as_hotspot(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten a per-file stats entry (a single-file target returns `files`,
    with `quality`/`complexity` as dicts) into the directory `hotspots` shape."""
    quality = entry.get('quality')
    if not isinstance(quality, dict):
        return entry
    complexity = entry.get('complexity')
    return {
        'file': entry.get('file', '?'),
        'quality_score': quality.get('score'),
        'max_complexity': complexity.get('max') if isinstance(complexity, dict) else complexity,
        'local_check_issues': quality.get('local_check_issues', 0),
    }


def _is_perfect_quality(h: Dict[str, Any]) -> bool:
    score = h.get('quality_score')
    return isinstance(score, (int, float)) and score >= 100


def _hotspot_score(h: Dict[str, Any]) -> float:
    """Best-available ranking score for a hotspot entry (higher = worse)."""
    for key in ('hotspot_score', 'score', 'churn', 'complexity'):
        val = h.get(key)
        if isinstance(val, (int, float)):
            return float(val)
    quality = h.get('quality_score')
    if isinstance(quality, (int, float)):
        return 100.0 - float(quality)
    return 0.0


def _analysis_failed(step: str, target: Optional[Path], error: BaseException) -> Dict[str, Any]:
    """The ``analysis_failed`` caveat for a review step that raised on *target* (the
    whole step when None): its results are missing, which the report must say (BACK-1852)."""
    where = f"{step}: {target}" if target is not None else step
    return {'type': 'analysis_failed', 'count': 1,
            'message': f"{where}: {type(error).__name__}: {error}"}


def _run_complexity(path: Optional[Path],
                    files: Optional[List[Path]] = None,
                    warnings: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Run complexity analysis.

    When `files` is given (a diff-scoped review), only those files' functions are
    considered, then merged and ranked globally. A target whose analysis raised is
    appended to `warnings` as an analysis_failed caveat, as `_run_hotspots` does.
    """
    if warnings is None:
        warnings = []
    try:
        from reveal.adapters.ast.adapter import AstAdapter
        targets = files if files is not None else ([path] if path is not None else [])
        results: List[Dict[str, Any]] = []
        for target in targets:
            try:
                # limit=1000000 as ast's --all: no auto-cap, so the section's total is real.
                adapter = AstAdapter(str(target), 'complexity>10&sort=-complexity&limit=1000000')
                data = adapter.get_structure()
                # A file ast:// could not analyze is missing from `found` (BACK-1856).
                warnings.extend({**w, 'message': f"complexity: {w.get('message', '')}"}
                                for w in collect_meta_warnings(data)
                                if w.get('type') == 'analysis_failed')
                found = data.get('results', data.get('elements', [])) or []
                results.extend(found)
            except Exception as e:  # boundary-ok: broad-except -- one target's complexity analysis failure is printed and recorded as an analysis_failed warning, the other targets still run
                print(f"Warning: complexity analysis failed for {target}, skipping: {e}", file=sys.stderr)
                warnings.append(_analysis_failed('complexity', target, e))
                continue
        results.sort(key=lambda r: r.get('complexity', 0) or 0, reverse=True)
        return results
    except Exception as e:  # boundary-ok: broad-except -- the complexity section runs the ast adapter; failure is printed, recorded as an analysis_failed warning, and the section is empty
        print(f"Warning: complexity analysis failed, skipping: {e}", file=sys.stderr)
        warnings.append(_analysis_failed('complexity', None, e))
        return []


def _extract_complexity_spikes(diff_data: Dict[str, Any], threshold: int = 5) -> List[Dict[str, Any]]:
    """Extract functions whose complexity increased beyond threshold.

    Args:
        diff_data: Diff section data from _run_diff (has 'data' key with full diff result)
        threshold: Minimum complexity_delta to flag (default 5)

    Returns:
        List of dicts with name, complexity_before, complexity_after, complexity_delta
    """
    spikes = []
    data = diff_data.get('data', {})
    functions = data.get('diff', {}).get('functions', [])
    for fn in functions:
        delta = fn.get('complexity_delta')
        if delta is not None and delta > threshold:
            spikes.append({
                'name': fn.get('name', '?'),
                'complexity_before': fn.get('complexity_before'),
                'complexity_after': fn.get('complexity_after'),
                'complexity_delta': delta,
            })
    spikes.sort(key=lambda x: x['complexity_delta'], reverse=True)
    return spikes


def _render_diff_section(diff: Dict[str, Any]) -> None:
    if not diff or diff.get('status') != 'ok':
        return
    summary = (diff.get('data') or {}).get('summary')
    if summary is not None:
        _render_structural_summary(summary)
        return
    # git --name-only fallback (the diff adapter failed)
    changed = diff.get('changed_files', [])
    count = diff.get('count', len(changed))
    print(f"\nStructural changes: {count} files modified")
    if changed and len(changed) <= 10:
        for f in changed:
            print(f"  {f}")
    elif count > 10:
        for f in changed[:5]:
            print(f"  {f}")
        print(f"  ... and {count - 5} more")


def _render_structural_summary(summary: Dict[str, Any]) -> None:
    """The diff adapter's summary: {functions|classes: {added, removed,
    modified}, imports: {added, removed}}, then every other category diff://
    compared (interfaces, structs, ...; BACK-1732), in the order it lists them."""
    parts = []
    for kind, counts in summary.items():
        counts = counts or {}
        changes = [f"{sign}{counts[key]}" for key, sign in
                   (('added', '+'), ('removed', '-'), ('modified', '~')) if counts.get(key)]
        if changes:
            parts.append(f"{kind} {' '.join(changes)}")
    print(f"\nStructural changes: {', '.join(parts) if parts else 'none'}")


_SEVERITY_ORDER = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}


def _render_violations_section(violations: list, verbose: bool,
                               scan_incomplete: bool = False) -> None:
    if not violations:
        print("\nNo violations found in the scanned population ⚠️" if scan_incomplete
              else "\nNo violations found ✅")
        return
    by_sev: Dict[str, list] = {}
    for v in violations:
        by_sev.setdefault(v.get('severity', 'medium'), []).append(v)

    print(f"\nIssues found ({len(violations)}):")
    for sev, items in sorted(by_sev.items(), key=lambda x: _SEVERITY_ORDER.get(x[0], 4)):
        label = sev.title()
        codes = sorted(set(i.get('rule', '?') for i in items[:3]))
        print(f"  {label:10} [{len(items)}]  " + ', '.join(codes) + ('...' if len(items) > 3 else ''))
        if verbose:
            for item in items[:5]:
                loc = f"{item.get('file', '')}:{item.get('line', '')}"
                print(f"    {item.get('rule', '')} {loc}: {item.get('message', '')}")


def _render_complexity_spikes_section(spikes: list) -> None:
    if not spikes:
        return
    print(f"\nComplexity spikes (delta > 5): {len(spikes)} function(s)")
    for fn in spikes[:10]:
        before = fn.get('complexity_before', 0) or 0
        after = fn.get('complexity_after', 0) or 0
        delta = fn.get('complexity_delta', 0)
        print(f"  {fn.get('name', '?'):40}  {before} → {after}  (+{delta})")


def _render_hotspots_section(hotspots: list) -> None:
    if not hotspots:
        return
    print("\nHotspots needing attention:")
    for h in hotspots[:5]:
        name = h.get('file', h.get('path', '?'))
        quality = h.get('quality_score', h.get('quality', h.get('score', '?')))
        if isinstance(quality, (int, float)):
            quality = f"{quality:g}/100"
        complexity = h.get('max_complexity', h.get('complexity', ''))
        if not complexity:
            complexity = (h.get('details') or {}).get('complexity', '')
        cx_str = f"  complexity: {complexity}" if complexity else ""
        print(f"  {name:40} quality: {quality}{cx_str}")


def _render_complexity_section(complex_fns: list) -> None:
    if not complex_fns:
        return
    print("\nComplex functions:")
    for fn in complex_fns[:5]:
        loc = fn.get('file', fn.get('path', ''))
        print(f"  {fn.get('name', '?')} (complexity: {fn.get('complexity', '?')})  {loc}")


def _render_recommendation(violations: list, errors: Optional[List[str]] = None,
                           analysis_incomplete: bool = False,
                           scan_incomplete: bool = False) -> None:
    blocking = sum(1 for v in violations if v.get('severity') in BLOCKING_SEVERITIES)
    print()
    if blocking > 0:
        print(f"Recommendation: Address {blocking} high/critical issue(s) before merge. ❌")
    elif errors:
        for e in errors:
            print(f"⚠️  {e}")
        print("Recommendation: Review incomplete — the quality check did not cover every file. ⚠️")
    elif analysis_incomplete:
        print("Recommendation: Review incomplete — the hotspot or complexity analysis is missing "
              "the targets named under Caveats. ⚠️")
    elif scan_incomplete:
        print("Recommendation: Review incomplete — a project-wide scan was capped, skipped or "
              "partly unparsed (see the warnings above). ⚠️")
    elif violations:
        print(f"Recommendation: {len(violations)} warning(s) — review before merge. ⚠️")
    else:
        print("Recommendation: No blocking issues. Ready for review. ✅")
    print()


def _render_report(report: Dict[str, Any], verbose: bool) -> None:
    """Render the review report as text."""
    sections = report['sections']
    print()
    print(f"Review: {report['target']}")
    print("━" * 50)
    if 'scoped_files' in report:
        print(f"\nChanged files checked: {report['scoped_files']}")
    _render_diff_section(sections.get('diff', {}))
    _render_complexity_spikes_section(sections.get('complexity_spikes', []))
    violations = sections.get('violations', [])
    scan_incomplete = bool(report.get('scan_disclosures'))
    _render_violations_section(violations, verbose, scan_incomplete)
    _render_hotspots_section(sections.get('hotspots', []))
    _render_complexity_section(sections.get('complexity', []))
    render_meta_warnings(report, heading="Caveats:")
    for reason in report.get('scan_disclosures', []):
        print(f"⚠️  {reason}")
    _render_recommendation(violations, report.get('errors'), _lost_analysis(report),
                           scan_incomplete)
