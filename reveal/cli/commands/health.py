"""reveal health — unified health check across resources."""

import argparse
import sys
from argparse import Namespace
from pathlib import Path
from typing import List


def create_health_parser() -> argparse.ArgumentParser:
    """Create parser for reveal health subcommand."""
    from reveal.cli.parser import _build_global_options_parser
    parser = argparse.ArgumentParser(
        prog='reveal health',
        parents=[_build_global_options_parser()],
        description='Unified health check across code, SSL, databases, and DNS.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  reveal health ./src                  # Code quality health\n"
            "  reveal health ssl://example.com      # SSL certificate health\n"
            "  reveal health mysql://prod/mydb      # Database health\n"
            "  reveal health domain://example.com   # DNS + registration health\n"
            "  reveal health ./src ssl://example.com  # Multiple resources\n"
            "\n"
            "Exit codes: 0=all pass, 1=warnings present, 2=failures present\n"
            "\n"
            "Adapter-specific help:\n"
            "  reveal help://ssl      reveal help://mysql\n"
            "  reveal help://domain   reveal help://nginx\n"
        )
    )
    parser.add_argument(
        'targets',
        nargs='*',
        metavar='TARGET',
        help='Paths or URIs to check (e.g., ./src, ssl://example.com, mysql://host/db)'
    )
    parser.add_argument(
        '--select',
        metavar='RULES',
        help='Rule categories to check (e.g., B,S,I,C)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        dest='health_all',
        help='Check all resources detectable in context (current dir + configured targets)'
    )
    return parser


def _detect_targets() -> List[str]:
    """Detect health check targets from context.

    Priority:
    1. `health.targets` in .reveal.yaml (user-configured)
    2. Known source directories (src/, lib/, app/, or a top-level Python package)
    3. Current directory (fallback)
    """
    # 1. Check .reveal.yaml for configured targets
    try:
        from reveal.config import get_config
        config = get_config(Path('.'))
        health_targets = config.get('health', {}).get('targets', [])
        if health_targets:
            return [str(t) for t in health_targets]
    except Exception:
        pass

    # 2. Look for common source directories
    _SOURCE_DIRS = ['src', 'lib', 'app']
    for name in _SOURCE_DIRS:
        if Path(name).is_dir():
            return [name]

    # 2b. Top-level Python package (dir with __init__.py, not tests/docs)
    _SKIP = {'tests', 'test', 'docs', 'doc', 'vendor', 'node_modules', '.git'}
    for d in sorted(Path('.').iterdir()):
        if d.is_dir() and d.name not in _SKIP and not d.name.startswith('.'):
            if (d / '__init__.py').exists():
                return [str(d)]

    # 3. Fallback
    return ['.']


def run_health(args: Namespace) -> None:
    """Run unified health check across all specified targets."""
    targets = args.targets
    if getattr(args, 'health_all', False):
        targets = _detect_targets()
    elif not targets:
        _print_usage_and_exit()

    overall_exit = 0
    results = []

    for target in targets:
        exit_code, summary = _check_target(target, args)
        results.append({'target': target, 'exit_code': exit_code, 'summary': summary})
        if exit_code > overall_exit:
            overall_exit = exit_code

    if args.format == 'json':
        import json
        print(json.dumps({'results': results, 'overall_exit': overall_exit}, indent=2))
    else:
        _render_results(results)

    sys.exit(overall_exit)


def _check_target(target: str, args: Namespace):
    """Route a target to the appropriate health check."""
    # URI-based routing
    if '://' in target:
        scheme = target.split('://')[0]
        return _check_uri(scheme, target, args)

    # Local path routing
    path = Path(target)
    if path.exists():
        if path.suffix.lower() in ('.conf',):
            return _check_nginx(path, args)
        return _check_code(path, args)

    print(f"  ⚠  {target}: not found", file=sys.stderr)
    return 1, f"not found: {target}"


def _check_code(path: Path, args: Namespace):
    """Run code quality health check."""
    import subprocess
    select = getattr(args, 'select', None) or 'B,S,I,C'
    cmd = ['reveal', 'check', str(path), f'--select={select}', '--only-failures', '--format=json']
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout.strip()

    try:
        import json
        data = json.loads(output) if output else {}
        violations = data.get('total_violations', 0)
        critical = sum(1 for v in data.get('violations', []) if v.get('severity') == 'error')
        if critical > 0:
            return 2, f"code: {violations} violations ({critical} critical)"
        elif violations > 0:
            return 1, f"code: {violations} violations"
        else:
            return 0, "code: healthy"
    except Exception:
        if result.returncode != 0:
            return 1, "code: check failed"
        return 0, "code: healthy"


def _check_uri(scheme: str, uri: str, args: Namespace):
    """Run URI-adapter health check."""
    import subprocess

    _URI_FLAGS = {
        'ssl': ['--check', '--advanced'],
        'mysql': ['--check', '--advanced'],
        'domain': ['--check'],
        'stats': [],
    }
    flags = _URI_FLAGS.get(scheme, [])
    cmd = ['reveal', uri] + flags + ['--only-failures']

    result = subprocess.run(cmd, capture_output=True, text=True)
    combined = (result.stdout + result.stderr).strip()

    if result.returncode == 2:
        return 2, f"{scheme}: critical failure"
    elif result.returncode == 1:
        lines = [l for l in combined.splitlines() if l.strip()]
        summary = lines[0] if lines else "warning"
        return 1, f"{scheme}: {summary}"
    else:
        return 0, f"{scheme}: healthy"


def _check_nginx(path: Path, args: Namespace):
    """Run nginx config health check."""
    import subprocess
    result = subprocess.run(['reveal', str(path), '--check', '--only-failures'],
                           capture_output=True, text=True)
    if result.returncode != 0 or result.stdout.strip():
        return 1, f"nginx: violations found"
    return 0, "nginx: healthy"


def _render_results(results: list) -> None:
    """Render health check results to stdout."""
    print()
    for r in results:
        exit_code = r['exit_code']
        icon = '✅' if exit_code == 0 else '⚠️ ' if exit_code == 1 else '❌'
        print(f"  {icon}  {r['target']}")
        print(f"       {r['summary']}")
    print()

    overall = max((r['exit_code'] for r in results), default=0)
    if overall == 0:
        print("Health: PASS")
    elif overall == 1:
        print("Health: WARN — review warnings above")
    else:
        print("Health: FAIL — critical issues found")
    print()


def _print_usage_and_exit() -> None:
    print("Usage: reveal health <target> [target ...]", file=sys.stderr)
    print("", file=sys.stderr)
    print("Examples:", file=sys.stderr)
    print("  reveal health ./src", file=sys.stderr)
    print("  reveal health ssl://example.com", file=sys.stderr)
    print("  reveal health mysql://host/db", file=sys.stderr)
    sys.exit(1)
