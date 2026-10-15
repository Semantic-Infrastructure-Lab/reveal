"""reveal health — unified health check across resources."""

import logging
import argparse
import sys
from argparse import Namespace
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional
from ...utils.query_control import ScanBudget, BudgetAccounting
from ...utils.results import outcome_of
from ..global_flags import add_gitignore_arguments, rule_patterns
from ..routing.ledger import complete
from ..routing.subcommand import emit_subcommand_result

logger = logging.getLogger(__name__)


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
            "  reveal health mysql://prod           # MySQL server health\n"
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
        help='Paths or URIs to check (e.g., ./src, ssl://example.com, mysql://host)'
    )
    parser.add_argument(
        '--select',
        type=rule_patterns,
        metavar='RULES',
        help='Rule categories to check (e.g., B,S,I,C)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        dest='health_all',
        help='Check all resources detectable in context (current dir + configured targets)'
    )
    add_gitignore_arguments(parser)
    return parser


def _detect_targets() -> List[str]:
    """Detect health check targets from context.

    Priority:
    1. `health.targets` in .reveal.yaml (user-configured)
    2. Known source directories (src/, lib/, app/, or a top-level Python package)
    3. Current directory (fallback)
    """
    # 1. Check .reveal.yaml for configured targets under `health.targets`
    from reveal.config import get_config
    raw: dict = get_config(Path('.'))._config  # get_config reports a file it can't load
    try:
        health_targets = raw.get('health', {}).get('targets', [])
        if health_targets:
            return [str(t) for t in health_targets]
    except (AttributeError, TypeError) as e:  # `health:` or its `targets:` has the wrong shape
        logger.warning(".reveal.yaml health.targets ignored (%s); detecting targets instead", e)

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


@dataclass(frozen=True)
class HealthResult:
    """One target's status and source accounting, carried to both output formats."""
    exit_code: int
    summary: str
    outcome: str = 'ok'
    scan_budget: Optional[dict] = None


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
        try:
            result = _check_target(target, args)
        except Exception as exc:
            # Visible via the 'summary' field appended to results below.
            result = HealthResult(2, f"error: {exc}", "failed")
        results.append({'target': target, **asdict(result)})
        overall_exit = max(overall_exit, result.exit_code)

    emit_subcommand_result({'results': results, 'overall_exit': overall_exit}, args,
                           name='health', source=','.join(targets), source_type='multi',
                           render=lambda report: _render_results(report['results']))

    complete(args)  # the exit code is the result: the flag ledger still reports
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
            code, summary = _check_nginx(path, args)
            return HealthResult(code, summary, 'failed' if 'cannot read' in summary else 'ok')
        return _check_code(path, args)

    print(f"  ⚠  {target}: not found", file=sys.stderr)
    return HealthResult(1, f"not found: {target}", "failed")


# Maximum supported files before health bails and tells the user to run reveal check directly.
# At this scale, capture_output=True in the subprocess double-buffers all output in the parent
# process which can exhaust RAM on machines with limited swap.
_HEALTH_MAX_FILES = 5000


def _check_code(path: Path, args: Namespace) -> HealthResult:
    """Use the same scan policy and the actual check result shapes."""
    import subprocess
    import json
    from reveal.cli.file_checker import collect_files_to_check
    from reveal.utils.gitignore import gitignore_enabled
    budget = ScanBudget(_HEALTH_MAX_FILES)
    count = len(collect_files_to_check(path.resolve()).files) if path.is_dir() else 1
    skipped = count > _HEALTH_MAX_FILES
    accounting = {**asdict(BudgetAccounting('scan', count, 0 if skipped else count)), 'limit': budget.limit,
                  'analyzed_files': 0, 'skipped': skipped}
    if skipped:
        return HealthResult(1,
            f"code: skipped — {count} files exceeds health check limit "
            f"({_HEALTH_MAX_FILES}). Use `reveal check {path}` directly.", 'skipped', accounting)
    select = getattr(args, 'select', None) or 'B,S,I,C'
    cmd = ['reveal', 'check', str(path), f'--select={select}', '--only-failures', '--format=json']
    if not gitignore_enabled():
        cmd.append('--no-gitignore')
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                            encoding='utf-8', errors='replace')
    try:
        data = json.loads(result.stdout)
        return _code_result(data, result.returncode, accounting)
    except (ValueError, TypeError, KeyError) as exc:
        if result.returncode != 0:
            # A checker that died (signal, traceback) produced no answer: FAIL, like the
            # same death inside a parsed answer and like a dead URI child (BACK-1828).
            return HealthResult(2, f'code: check failed (exit {result.returncode}'
                                   f'{_child_reason(result.stderr)})', 'failed', accounting)
        return HealthResult(2, f'code: could not parse check results ({exc})',
                            'failed', accounting)


@dataclass(frozen=True)
class CodeReport:
    total: int
    checked: int
    errors: int
    degraded: int
    detections: list
    disclosures: list


def _read_code_report(data: dict, candidates: int) -> CodeReport:
    """Normalize the two current check envelopes; reject unknown or malformed shapes."""
    summary = data.get('summary')
    if isinstance(summary, dict):
        total = summary['total_issues']
        files = data.get('files', [])
        if not isinstance(files, list) or not all(isinstance(f, dict) for f in files):
            raise ValueError('invalid file results')
        entries = [d for file in files for d in file.get('detections', [])]
        report = CodeReport(total, summary.get('files_checked', candidates),
                            summary.get('files_errored', 0), summary.get('files_degraded', 0),
                            entries, summary.get('scan_disclosures', []))
    else:
        report = CodeReport(data['total'], 1, int(bool(data.get('errors'))),
                            int(bool(data.get('warning'))), data['detections'],
                            data.get('scan_disclosures', []))
    counts = (report.total, report.checked, report.errors, report.degraded)
    if not all(type(n) is int and n >= 0 for n in counts):
        raise ValueError('invalid check counts')
    if (not isinstance(report.detections, list)
            or not all(isinstance(d, dict) for d in report.detections)
            or not isinstance(report.disclosures, list) or report.errors > report.checked):
        raise ValueError('invalid detections, disclosures or failed-file count')
    return report


def _code_result(data: dict, returncode: int, accounting: dict) -> HealthResult:
    """Interpret a validated answer before allowing a clean health result."""
    if not isinstance(data, dict):
        raise ValueError('check result is not an object')
    if outcome_of(data) == 'failed':
        return HealthResult(2, f"code: check failed ({data['error']})", 'failed', accounting)
    if outcome_of(data) == 'not_applicable':
        return HealthResult(1, 'code: check not applicable', 'not_applicable', accounting)
    report = _read_code_report(data, accounting['total'])
    changed = report.checked != accounting['returned']
    accounting = {**accounting, 'preflight_files': accounting['total'],
                  'total': max(accounting['total'], report.checked),
                  'returned': report.checked, 'exact': accounting['exact'] and not changed,
                  'analyzed_files': report.checked - report.errors,
                  'failed_files': report.errors, 'degraded_files': report.degraded}
    if report.errors or returncode < 0:
        return HealthResult(2, f'code: check failed ({report.errors} errored files, exit {returncode})',
                            'failed', accounting)
    incomplete = _incomplete_code_result(data, report, accounting, changed)
    if incomplete is not None:
        return incomplete
    if returncode >= 2:
        return HealthResult(2, f'code: check failed (exit {returncode})', 'failed', accounting)
    high = sum(1 for d in report.detections if d.get('severity') == 'high')
    critical = sum(1 for d in report.detections if d.get('severity') == 'critical')
    if high or critical:
        return HealthResult(2, f'code: {report.total} violations ({high} high, {critical} critical)', 'ok', accounting)
    if report.total:
        return HealthResult(1, f'code: {report.total} violations', 'ok', accounting)
    if returncode:
        return HealthResult(2, f'code: check failed (exit {returncode})', 'failed', accounting)
    return HealthResult(0, 'code: healthy', 'ok', accounting)


def _incomplete_code_result(data: dict, report: CodeReport, accounting: dict,
                            changed: bool) -> Optional[HealthResult]:
    """Retain child scope disclosures before judging violation severity."""
    meta = data.get('meta') or {}
    if not isinstance(meta, dict):
        raise ValueError('invalid check metadata')
    if report.checked == 0:
        return HealthResult(1, 'code: no applicable files were checked', 'not_applicable', accounting)
    if changed or report.degraded or report.disclosures or meta.get('errors') or meta.get('warnings'):
        notices = [*report.disclosures, *(['file population changed between preflight and check'] if changed else [])]
        detail = '; '.join(str(d) for d in notices)
        return HealthResult(1, f'code: incomplete check ({report.total} violations, {report.degraded} degraded files)'
                            + (f' — {detail}' if detail else ''), 'partial', accounting)
    return None


def _check_uri(scheme: str, uri: str, args: Namespace) -> HealthResult:
    """Run URI-adapter health check."""
    import subprocess

    _URI_FLAGS: dict[str, list[str]] = {
        'ssl': ['--check', '--advanced'],
        'mysql': ['--check', '--advanced'],
        'domain': ['--check'],
        'stats': [],
    }
    flags = _URI_FLAGS.get(scheme, [])
    cmd = ['reveal', uri] + flags + ['--only-failures', '--format=json']

    # Hard outer ceiling independent of what any individual adapter promises
    # internally -- this is the one health-check path reachable straight from
    # MCP's reveal_health(target) for network-facing targets (ssl/mysql/domain
    # today, whatever's added tomorrow), so a hung remote host can't block the
    # call forever. Mirrors _check_code's timeout=120 below.
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, encoding='utf-8', errors='replace')
    except subprocess.TimeoutExpired:
        return HealthResult(2, f"{scheme}: timed out", 'failed')
    return _uri_health_result(scheme, result.returncode, result.stdout, result.stderr)


def _child_reason(stderr: Optional[str], first: bool = False) -> str:
    """One of the child's own stderr lines as ``: reason`` ('' when it said nothing): the
    last by default (a traceback ends on its cause), the first for a CLI error message."""
    text = stderr if isinstance(stderr, str) else ''
    lines = [line.strip() for line in text.splitlines() if line.strip()]  # boundary-ok: splitlines -- child stderr, not file content
    return f': {lines[0 if first else -1][:200]}' if lines else ''


def _uri_health_result(scheme: str, returncode: int, output: str,
                       stderr: Optional[str] = None) -> HealthResult:
    """A failed child is failed; a partial or unavailable answer cannot be clean."""
    import json
    if returncode < 0 or returncode >= 2:
        return HealthResult(2, f"{scheme}: critical failure (exit {returncode}{_child_reason(stderr)})",
                            'failed')
    try:
        data = json.loads(output)
        if not isinstance(data, dict):
            raise ValueError('expected an object')
        outcome = outcome_of(data)
        if outcome == 'failed':
            return HealthResult(1, f"{scheme}: {data['error']}", 'failed')
        if outcome == 'not_applicable':
            return HealthResult(1, f"{scheme}: not applicable", 'not_applicable')
        meta = data.get('meta') or {}
        if not isinstance(meta, dict):
            raise ValueError('invalid metadata')
        if meta.get('errors') or meta.get('warnings') or data.get('warnings'):
            return HealthResult(1, f"{scheme}: incomplete or warning result", 'partial')
        if returncode:
            # A completed answer whose findings set the exit code is not partial.
            return HealthResult(1, f"{scheme}: warnings found", 'ok')
        return HealthResult(0, f"{scheme}: healthy", 'ok')
    except (ValueError, TypeError):
        return HealthResult(2, f"{scheme}: malformed check results (exit {returncode}"
                               f"{_child_reason(stderr, first=True)})", 'failed')


def _check_nginx(path: Path, args: Namespace):
    """Run nginx config health check via direct rule API (no subprocess)."""
    from reveal.rules import RuleRegistry

    try:
        content = path.read_text(errors='replace', encoding='utf-8')
    except OSError as exc:
        return 1, f"nginx: cannot read {path}: {exc}"

    file_path = str(path)
    detections = RuleRegistry.check_file(file_path, None, content, select=['N'])

    if detections:
        return 1, f"nginx: {len(detections)} violation(s)"
    return 0, "nginx: healthy"


def _render_results(results: list) -> None:
    """Render health check results to stdout."""
    print()
    for r in results:
        exit_code = r['exit_code']
        icon = '✅' if exit_code == 0 else '⚠️ ' if exit_code == 1 else '❌'
        print(f"  {icon}  {r['target']}")
        print(f"       {r['summary']}")
        budget = r.get('scan_budget')
        if budget:
            total = str(budget['total']) if budget['exact'] else f"at least {budget['total']}"
            print(f"       Scan: {total} candidate files, {budget['analyzed_files']} analyzed; limit {budget['limit']}")
    print()

    overall = max((r['exit_code'] for r in results), default=0)
    if overall == 0:
        print("Health: PASS")
    elif overall == 1:
        print("Health: WARN — review warnings above")
    else:
        print("Health: FAIL — see failed checks above")
    print()


def _print_usage_and_exit() -> None:
    print("Usage: reveal health <target> [target ...]", file=sys.stderr)
    print("", file=sys.stderr)
    print("Examples:", file=sys.stderr)
    print("  reveal health ./src", file=sys.stderr)
    print("  reveal health ssl://example.com", file=sys.stderr)
    print("  reveal health mysql://host", file=sys.stderr)
    sys.exit(1)
