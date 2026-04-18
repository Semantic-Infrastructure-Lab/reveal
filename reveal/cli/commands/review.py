"""reveal review — code quality assessment before a PR merge."""

import argparse
import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List, cast


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
            "  reveal review ./src                 # Review a directory\n"
            "  reveal review main..feature         # PR diff (git range syntax)\n"
            "  reveal review main..feature --format json  # CI/CD gate\n"
            "  reveal review ./src --select B,S    # Focus on bugs and security\n"
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

    # Step 2: Determine the path to analyze
    if is_git_range:
        # Use the working tree for quality analysis
        path = _detect_source_root()
    else:
        path = Path(target)

    # Step 3: Quality check
    violations = _run_check(path, args.select)
    report['sections']['violations'] = violations

    # Step 4: Hotspots
    hotspots = _run_hotspots(path)
    report['sections']['hotspots'] = hotspots

    # Step 5: Complexity
    complexity = _run_complexity(path)
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


def _run_check(path: Path, select: str) -> List[Dict[str, Any]]:
    """Run quality check and return violations."""
    try:
        from reveal.cli.file_checker import (
            collect_files_to_check, load_gitignore_patterns, _check_files_json,
        )
        if path.is_dir():
            directory = path.resolve()
            gitignore_patterns = load_gitignore_patterns(directory)
            files = collect_files_to_check(directory, gitignore_patterns)
        else:
            directory = path.parent.resolve()
            files = [path.resolve()]
        select_list = select.split(',') if select else None
        _, _, file_results = _check_files_json(files, directory, select_list, None)
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


def _run_hotspots(path: Path) -> List[Dict[str, Any]]:
    """Run hotspot analysis."""
    try:
        from reveal.adapters.stats.adapter import StatsAdapter
        adapter = StatsAdapter(str(path), 'hotspots=true')
        data = adapter.get_structure(hotspots=True)
        hotspots = data.get('hotspots', data.get('files', []))
        return cast(List[Dict[str, Any]], hotspots[:10])
    except Exception:
        return []


def _run_complexity(path: Path) -> List[Dict[str, Any]]:
    """Run complexity analysis."""
    try:
        from reveal.adapters.ast.adapter import AstAdapter
        adapter = AstAdapter(str(path), 'complexity>10&sort=-complexity&limit=10')
        data = adapter.get_structure()
        return cast(List[Dict[str, Any]], data.get('results', data.get('elements', []))[:10])
    except Exception:
        return []


def _detect_source_root() -> Path:
    """Detect source root from git repo."""
    try:
        result = subprocess.run(['git', 'rev-parse', '--show-toplevel'],
                               capture_output=True, text=True)
        if result.returncode == 0:
            root = Path(result.stdout.strip())
            subdir = next((root / c for c in ['src', 'lib', 'app'] if (root / c).is_dir()), None)
            return subdir if subdir else root
        return Path('.')
    except Exception:
        return Path('.')


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
