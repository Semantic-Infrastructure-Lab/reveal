"""reveal review — code quality assessment before a PR merge."""

import argparse
import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, cast


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
        result = subprocess.run(
            ['reveal', f'diff://git://{git_range.replace("..", "/.:git://")}/.', '--format=json'],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            return {'status': 'ok', 'data': data}
    except Exception:
        pass

    # Fallback: use git log to count changed files
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
        result = subprocess.run(
            ['reveal', 'check', str(path), f'--select={select}',
             '--only-failures', '--format=json'],
            capture_output=True, text=True, timeout=60
        )
        if result.stdout.strip():
            data = json.loads(result.stdout)
            return cast(List[Dict[str, Any]], data.get('violations', []))
    except Exception:
        pass
    return []


def _run_hotspots(path: Path) -> List[Dict[str, Any]]:
    """Run hotspot analysis."""
    try:
        result = subprocess.run(
            ['reveal', f'stats://{path}?hotspots=true', '--format=json'],
            capture_output=True, text=True, timeout=30
        )
        if result.stdout.strip():
            data = json.loads(result.stdout)
            hotspots = data.get('hotspots', data.get('files', []))
            return cast(List[Dict[str, Any]], hotspots[:10])  # Top 10
    except Exception:
        pass
    return []


def _run_complexity(path: Path) -> List[Dict[str, Any]]:
    """Run complexity analysis."""
    try:
        result = subprocess.run(
            ['reveal', f'ast://{path}?complexity>10&sort=-complexity&limit=10',
             '--format=json'],
            capture_output=True, text=True, timeout=30
        )
        if result.stdout.strip():
            data = json.loads(result.stdout)
            return cast(List[Dict[str, Any]], data.get('elements', data.get('results', []))[:10])
    except Exception:
        pass
    return []


def _detect_source_root() -> Path:
    """Detect source root from git repo."""
    try:
        result = subprocess.run(['git', 'rev-parse', '--show-toplevel'],
                               capture_output=True, text=True)
        if result.returncode == 0:
            root = Path(result.stdout.strip())
            # Prefer src/ if it exists
            for candidate in ['src', 'lib', 'app']:
                d = root / candidate
                if d.is_dir():
                    return d
            return root
    except Exception:
        pass
    return Path('.')


def _render_report(report: Dict[str, Any], verbose: bool) -> None:
    """Render the review report as text."""
    print()
    print(f"Review: {report['target']}")
    print("━" * 50)

    # Diff section
    diff = report['sections'].get('diff', {})
    if diff and diff.get('status') == 'ok':
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

    # Violations
    violations = report['sections'].get('violations', [])
    if violations:
        by_sev: Dict[str, list] = {}
        for v in violations:
            sev = v.get('severity', 'warning')
            by_sev.setdefault(sev, []).append(v)

        print(f"\nIssues found ({len(violations)}):")
        for sev, items in sorted(by_sev.items(), key=lambda x: {'error': 0, 'warning': 1, 'info': 2}.get(x[0], 3)):
            label = {'error': 'Critical', 'warning': 'Warning', 'info': 'Info'}.get(sev, sev.title())
            print(f"  {label:10} [{len(items)}]  ", end='')
            codes = list(set(i.get('rule', '?') for i in items[:3]))
            print(', '.join(codes) + ('...' if len(items) > 3 else ''))
            if verbose:
                for item in items[:5]:
                    loc = f"{item.get('file', '')}:{item.get('line', '')}"
                    print(f"    {item.get('rule', '')} {loc}: {item.get('message', '')}")
    else:
        print("\nNo violations found ✅")

    # Hotspots
    hotspots = report['sections'].get('hotspots', [])
    if hotspots:
        print("\nHotspots needing attention:")
        for h in hotspots[:5]:
            name = h.get('file', h.get('path', '?'))
            quality = h.get('quality_score', h.get('quality', h.get('score', '?')))
            complexity = h.get('complexity', h.get('max_complexity', ''))
            cx_str = f"  complexity: {complexity}" if complexity else ""
            print(f"  {name:40} quality: {quality}{cx_str}")

    # Complexity
    complex_fns = report['sections'].get('complexity', [])
    if complex_fns:
        print("\nComplex functions:")
        for fn in complex_fns[:5]:
            name = fn.get('name', '?')
            cx = fn.get('complexity', '?')
            loc = fn.get('file', fn.get('path', ''))
            print(f"  {name} (complexity: {cx})  {loc}")

    # Overall recommendation
    violations = report['sections'].get('violations', [])
    critical = sum(1 for v in violations if v.get('severity') in ('error', 'critical'))
    print()
    if critical > 0:
        print(f"Recommendation: Address {critical} critical issue(s) before merge. ❌")
    elif violations:
        print(f"Recommendation: {len(violations)} warning(s) — review before merge. ⚠️")
    else:
        print("Recommendation: No blocking issues. Ready for review. ✅")
    print()
