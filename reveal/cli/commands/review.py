"""reveal review — code quality assessment before a PR merge."""

import argparse
import json
import os
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List, Optional


def create_review_parser() -> argparse.ArgumentParser:
    """Create parser for reveal review subcommand."""
    from reveal.cli.parser import _build_global_options_parser
    parser = argparse.ArgumentParser(
        prog='reveal review',
        parents=[_build_global_options_parser()],
        description='Assess code quality and structural changes before a PR merge.',
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
        metavar='RULES',
        default='B,S,I,C,M',
        help='Rule categories (default: B,S,I,C,M)'
    )
    return parser


def run_review(args: Namespace) -> None:
    """Run the review workflow."""
    target = args.target
    is_git_range = '..' in target and not Path(target).exists()

    report: Dict[str, Any] = {
        'target': target,
        'is_diff': is_git_range,
        'sections': {},
    }

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
    violations = _run_check(path, args.select, files=changed_files)
    report['sections']['violations'] = violations

    # Step 4: Hotspots
    print("  Analyzing hotspots…", file=sys.stderr)
    hotspots = _run_hotspots(path, files=changed_files)
    report['sections']['hotspots'] = hotspots

    # Step 5: Complexity
    print("  Scanning complexity…", file=sys.stderr)
    complexity = _run_complexity(path, files=changed_files)
    report['sections']['complexity'] = complexity

    # Render
    if args.format == 'json':
        print(json.dumps(report, indent=2, default=str))
    else:
        _render_report(report, args.verbose)

    # Exit code: 0=clean, 1=warnings, 2=critical
    critical = sum(1 for v in violations if v.get('severity') in ('error', 'critical'))
    sys.exit(2 if critical > 0 else (1 if violations else 0))


def _run_diff(git_range: str) -> Dict[str, Any]:
    """Run diff analysis for a git range."""
    try:
        from reveal.adapters.diff.adapter import DiffAdapter
        resource = f"git://{git_range.replace('..', '/.:git://')}/."
        adapter = DiffAdapter(resource)
        data = adapter.get_structure()
        return {'status': 'ok', 'data': data}
    except Exception:
        pass

    # Fallback: git for changed file list
    try:
        parts = git_range.split('..', 1)
        result = subprocess.run(
            ['git', 'diff', '--name-only', parts[0], parts[1]],
            capture_output=True, text=True, timeout=10
        )
        files = [f for f in result.stdout.splitlines() if f.strip()]
        return {'status': 'ok', 'changed_files': files, 'count': len(files)}
    except Exception:
        return {'status': 'unavailable'}


def _run_check(path: Optional[Path], select: str,
               files: Optional[List[Path]] = None) -> List[Dict[str, Any]]:
    """Run quality check and return violations.

    When `files` is given (a diff-scoped review), only those files are checked.
    Otherwise `path` (a directory or single file) is walked as before.
    """
    try:
        from reveal.cli.file_checker import (
            collect_files_to_check, load_gitignore_patterns, _check_files_json,
        )
        if files is not None:
            check_files = [f.resolve() for f in files if f.is_file()]
            if not check_files:
                return []
            directory = Path(os.path.commonpath([str(f.parent) for f in check_files]))
        elif path is not None and path.is_dir():
            directory = path.resolve()
            gitignore_patterns = load_gitignore_patterns(directory)
            check_files = collect_files_to_check(directory, gitignore_patterns)
        elif path is not None:
            directory = path.parent.resolve()
            check_files = [path.resolve()]
        else:
            return []
        select_list = select.split(',') if select else None
        _, _, file_results = _check_files_json(check_files, directory, select_list, None)
        violations: List[Dict[str, Any]] = []
        for fr in file_results:
            for d in fr.get('detections', []):
                violations.append({
                    'file': fr['file'],
                    'line': d.get('line', ''),
                    'rule': d.get('rule_code', ''),
                    'severity': d.get('severity', 'warning'),
                    'message': d.get('message', ''),
                })
        return violations
    except Exception:
        return []


def _run_hotspots(path: Optional[Path],
                  files: Optional[List[Path]] = None) -> List[Dict[str, Any]]:
    """Run hotspot analysis.

    When `files` is given (a diff-scoped review), rank only those files by their
    own churn×complexity score instead of scanning the whole tree.
    """
    try:
        from reveal.adapters.stats.adapter import StatsAdapter
        targets = files if files is not None else ([path] if path is not None else [])
        hotspots: List[Dict[str, Any]] = []
        for target in targets:
            try:
                adapter = StatsAdapter(str(target), 'hotspots=true')
                data = adapter.get_structure(hotspots=True)
                found = data.get('hotspots', data.get('files', [])) or []
                hotspots.extend(found)
            except Exception:
                continue
        hotspots.sort(key=_hotspot_score, reverse=True)
        return hotspots[:10]
    except Exception:
        return []


def _hotspot_score(h: Dict[str, Any]) -> float:
    """Best-available ranking score for a hotspot entry (higher = worse)."""
    for key in ('hotspot_score', 'score', 'churn', 'complexity'):
        val = h.get(key)
        if isinstance(val, (int, float)):
            return float(val)
    return 0.0


def _run_complexity(path: Optional[Path],
                    files: Optional[List[Path]] = None) -> List[Dict[str, Any]]:
    """Run complexity analysis.

    When `files` is given (a diff-scoped review), only those files' functions are
    considered, then merged and ranked globally.
    """
    try:
        from reveal.adapters.ast.adapter import AstAdapter
        targets = files if files is not None else ([path] if path is not None else [])
        results: List[Dict[str, Any]] = []
        for target in targets:
            try:
                adapter = AstAdapter(str(target), 'complexity>10&sort=-complexity&limit=10')
                data = adapter.get_structure()
                found = data.get('results', data.get('elements', [])) or []
                results.extend(found)
            except Exception:
                continue
        results.sort(key=lambda r: r.get('complexity', 0) or 0, reverse=True)
        return results[:10]
    except Exception:
        return []


def _changed_files(git_range: str) -> List[Path]:
    """Absolute paths of files changed in a git range that still exist on disk.

    Deleted files are omitted (nothing to quality-check). Names are resolved
    against the git top-level so `review` works from any subdirectory. Replaces
    the old whole-tree `_detect_source_root()` walk (BACK-538).
    """
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-only', git_range],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []
        toplevel = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True, timeout=10,
        )
        root = Path(toplevel.stdout.strip()) if toplevel.returncode == 0 else Path.cwd()
        files: List[Path] = []
        for name in result.stdout.splitlines():
            name = name.strip()
            if not name:
                continue
            candidate = root / name
            if candidate.is_file():
                files.append(candidate.resolve())
        return files
    except Exception:
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


def _render_violations_section(violations: list, verbose: bool) -> None:
    if not violations:
        print("\nNo violations found ✅")
        return
    by_sev: Dict[str, list] = {}
    for v in violations:
        by_sev.setdefault(v.get('severity', 'warning'), []).append(v)

    print(f"\nIssues found ({len(violations)}):")
    _sev_order = {'error': 0, 'warning': 1, 'info': 2}
    for sev, items in sorted(by_sev.items(), key=lambda x: _sev_order.get(x[0], 3)):
        label = {'error': 'Critical', 'warning': 'Warning', 'info': 'Info'}.get(sev, sev.title())
        codes = list(set(i.get('rule', '?') for i in items[:3]))
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
        complexity = h.get('complexity', h.get('max_complexity', ''))
        cx_str = f"  complexity: {complexity}" if complexity else ""
        print(f"  {name:40} quality: {quality}{cx_str}")


def _render_complexity_section(complex_fns: list) -> None:
    if not complex_fns:
        return
    print("\nComplex functions:")
    for fn in complex_fns[:5]:
        loc = fn.get('file', fn.get('path', ''))
        print(f"  {fn.get('name', '?')} (complexity: {fn.get('complexity', '?')})  {loc}")


def _render_recommendation(violations: list) -> None:
    critical = sum(1 for v in violations if v.get('severity') in ('error', 'critical'))
    print()
    if critical > 0:
        print(f"Recommendation: Address {critical} critical issue(s) before merge. ❌")
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
    _render_diff_section(sections.get('diff', {}))
    _render_complexity_spikes_section(sections.get('complexity_spikes', []))
    violations = sections.get('violations', [])
    _render_violations_section(violations, verbose)
    _render_hotspots_section(sections.get('hotspots', []))
    _render_complexity_section(sections.get('complexity', []))
    _render_recommendation(violations)
