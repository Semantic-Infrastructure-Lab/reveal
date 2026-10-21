"""reveal health — unified health check across resources."""

import logging
import argparse
import sys
from argparse import Namespace
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional
from ...utils.query_control import ScanBudget, BudgetAccounting
from ...utils.results import (AnalysisCompleteness, ExecutionFacts, execution_exit_code, outcome_of,
                              requested_fail_on)
from ..global_flags import add_gitignore_arguments, rule_patterns
from ..routing.ledger import complete
from ..routing.subcommand import emit_subcommand_result

logger = logging.getLogger(__name__)


def create_health_parser() -> argparse.ArgumentParser:
    """Create parser for reveal health subcommand."""
    from reveal.cli.parser import _build_global_options_parser
    from reveal.cli.invocation import exit_codes_text
    parser = argparse.ArgumentParser(
        prog='reveal health',
        parents=[_build_global_options_parser()],
        description='Ops health check across SSL, databases, DNS and nginx (code quality: reveal check).',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  reveal health ./src                  # Code quality health\n"
            "  reveal health ssl://example.com      # SSL certificate health\n"
            "  reveal health mysql://prod           # MySQL server health\n"
            "  reveal health domain://example.com   # DNS + registration health\n"
            "  reveal health ./src ssl://example.com  # Multiple resources\n"
            "\n"
            + exit_codes_text('health') + "\n"
            "A target a check does not apply to is shown but never fails the run.\n"
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


# What one target's check established (BACK-2051). A numeric child exit code does not say which:
# a child exiting 2 may carry a real domain verdict (an expired certificate) or may have crashed.
#   healthy        completed, nothing adverse
#   finding        completed with a negative domain verdict (violations, failing checks)
#   not_applicable the check does not apply to this target
#   unavailable    the target could not be reached or read
#   incomplete     usable but partial or capped evidence
#   failed         the check could not produce its answer
HEALTH_VERDICTS = ('healthy', 'finding', 'not_applicable', 'unavailable', 'incomplete', 'failed')

# A producer that names no verdict gets one from its legacy outcome; an unknown outcome is never clean.
_OUTCOME_VERDICTS = {'not_applicable': 'not_applicable', 'partial': 'incomplete',
                     'skipped': 'incomplete', 'failed': 'failed'}


@dataclass(frozen=True)
class HealthResult:
    """One target's status and source accounting, carried to both output formats."""
    exit_code: int
    summary: str
    outcome: str = 'ok'
    scan_budget: Optional[dict] = None
    verdict: Optional[str] = None

    def __post_init__(self) -> None:
        if self.verdict is None:
            derived = ('finding' if self.exit_code else 'healthy') if self.outcome == 'ok' \
                else _OUTCOME_VERDICTS.get(self.outcome, 'failed')
            object.__setattr__(self, 'verdict', derived)
        elif self.verdict not in HEALTH_VERDICTS:
            raise ValueError(f'unknown health verdict: {self.verdict}')


def run_health(args: Namespace) -> None:
    """Run unified health check across all specified targets."""
    targets = args.targets
    if getattr(args, 'health_all', False):
        targets = _detect_targets()
    elif not targets:
        _print_usage_and_exit()

    results = []
    checked = []

    if any(_is_code_target(t) for t in targets):
        from ..invocation import retirement_note
        retirement_note('target:health.code')

    for target in targets:
        try:
            result = _check_target(target, args)
        except Exception as exc:  # boundary-ok: broad-except -- one target's failure becomes a failed HealthResult (exit 2, 'error: ...') in the summary; it must not end the other targets
            # Visible via the 'summary' field appended to results below.
            result = HealthResult(2, f"error: {exc}", "failed")
        results.append({'target': target, **asdict(result)})
        checked.append(result)
    overall_exit = _overall_exit(checked, requested_fail_on(args))

    emit_subcommand_result({'results': results, 'overall_exit': overall_exit}, args,
                           name='health', source=','.join(targets), source_type='multi',
                           render=lambda report: _render_results(report['results']))

    complete(args)  # the exit code is the result: the flag ledger still reports
    sys.exit(overall_exit)


# Verdicts that mean the requested check did not complete (D6: required analysis failed or is incomplete).
_LOST_VERDICTS = ('unavailable', 'incomplete', 'failed')


def _overall_exit(results: List[HealthResult], fail_on) -> int:
    """The process code from the targets' verdicts (BACK-2051, D6), never the maximum of their
    legacy severity codes: 3 when any check was lost, else 1 when a finding matches the gate, else 0.
    A target the check does not apply to is disclosed but never fails the run."""
    lost = [r for r in results if r.verdict in _LOST_VERDICTS]
    state = (AnalysisCompleteness.FAILED if len(lost) == len(results) else AnalysisCompleteness.INCOMPLETE) \
        if lost else AnalysisCompleteness.COMPLETE
    facts = ExecutionFacts(state, findings=any(r.verdict == 'finding' for r in results))
    return execution_exit_code(facts, fail_on=fail_on)


def _is_code_target(target: str) -> bool:
    """A local path that is not an ops target (a URI, an nginx .conf, a missing path): check's, not health's."""
    if '://' in target:
        return False
    path = Path(target)
    return path.exists() and path.suffix.lower() not in ('.conf',)


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
            unreadable = 'cannot read' in summary
            return HealthResult(code, summary, 'failed' if unreadable else 'ok',
                                verdict='unavailable' if unreadable else None)
        return _check_code(path, args)

    print(f"  ⚠  {target}: not found", file=sys.stderr)
    return HealthResult(1, f"not found: {target}", "failed", verdict='unavailable')


# Maximum supported files before health bails and tells the user to run reveal check directly.
# At this scale, capture_output=True in the subprocess double-buffers all output in the parent
# process which can exhaust RAM on machines with limited swap.
_HEALTH_MAX_FILES = 5000


def _reveal_child(*argv: str) -> tuple:
    """Command and env for a child `reveal` that runs this process's interpreter and imports (BACK-2125).

    A bare 'reveal' resolves through PATH, which can be another venv or version. The parent's
    sys.path goes on PYTHONPATH so the child sees the same package and dependencies even when
    HOME or the cwd differ (a source checkout that is not installed, a user site).
    """
    import os
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join(entry for entry in sys.path if entry)
    return [sys.executable, '-m', 'reveal', *argv], env


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
    cmd, env = _reveal_child('check', str(path), f'--select={select}', '--only-failures', '--format=json')
    if not gitignore_enabled():
        cmd.append('--no-gitignore')
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                            encoding='utf-8', errors='replace', env=env)
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
    capped = bool(report.disclosures)
    accounting = {**accounting, 'preflight_files': accounting['total'],
                  'total': max(accounting['total'], report.checked),
                  'returned': report.checked, 'exact': accounting['exact'] and not changed and not capped,
                  'analyzed_files': report.checked - report.errors,
                  'failed_files': report.errors, 'degraded_files': report.degraded}
    if report.errors or returncode < 0:
        return HealthResult(2, f'code: check failed ({report.errors} errored files, exit {returncode})',
                            'failed', accounting)
    incomplete = _incomplete_code_result(data, report, accounting, changed, returncode)
    if incomplete is not None:
        return incomplete
    if returncode >= 2:
        return HealthResult(2, f'code: check failed (exit {returncode})', 'failed', accounting)
    return _completed_code_result(report, returncode, accounting)


def _completed_code_result(report: CodeReport, returncode: int, accounting: dict) -> HealthResult:
    """A complete scan: healthy, or a finding whose summary carries any capability note."""
    high = sum(1 for d in report.detections if d.get('severity') == 'high')
    critical = sum(1 for d in report.detections if d.get('severity') == 'critical')
    notes = f" — {'; '.join(str(d) for d in report.disclosures)}" if report.disclosures else ''
    if high or critical:
        return HealthResult(2, f'code: {report.total} violations ({high} high, {critical} critical){notes}', 'ok', accounting)
    if report.total:
        return HealthResult(1, f'code: {report.total} violations{notes}', 'ok', accounting)
    if returncode:
        return HealthResult(2, f'code: check failed (exit {returncode})', 'failed', accounting)
    return HealthResult(0, f'code: healthy{notes}', 'ok', accounting)


def _incomplete_code_result(data: dict, report: CodeReport, accounting: dict,
                            changed: bool, returncode: int) -> Optional[HealthResult]:
    """Retain child scope disclosures before judging violation severity. Disclosures count as
    lost evidence only when the child itself exited 3 (a capped or lost scan); a language-capability
    note leaves check at exit 0 or 1 and stays a note on the summary."""
    meta = data.get('meta') or {}
    if not isinstance(meta, dict):
        raise ValueError('invalid check metadata')
    if report.checked == 0:
        return HealthResult(1, 'code: no applicable files were checked', 'not_applicable', accounting)
    if changed or report.degraded or (report.disclosures and returncode == 3) or meta.get('errors') or meta.get('warnings'):
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
    cmd, env = _reveal_child(uri, *flags, '--only-failures', '--format=json')

    # Hard outer ceiling independent of what any individual adapter promises
    # internally -- this is the one health-check path reachable straight from
    # MCP's reveal_health(target) for network-facing targets (ssl/mysql/domain
    # today, whatever's added tomorrow), so a hung remote host can't block the
    # call forever. Mirrors _check_code's timeout=120 below.
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, encoding='utf-8', errors='replace',
                                env=env)
    except subprocess.TimeoutExpired:
        return HealthResult(2, f"{scheme}: timed out", 'failed')
    return _uri_health_result(scheme, result.returncode, result.stdout, result.stderr)


def _child_reason(stderr: Optional[str], first: bool = False) -> str:
    """One of the child's own stderr lines as ``: reason`` ('' when it said nothing): the
    last by default (a traceback ends on its cause), the first for a CLI error message."""
    text = stderr if isinstance(stderr, str) else ''
    lines = [line.strip() for line in text.splitlines() if line.strip()]  # boundary-ok: splitlines -- child stderr, not file content
    return f': {lines[0 if first else -1][:200]}' if lines else ''


def _failing_check_result(scheme: str, output: str) -> Optional[HealthResult]:
    """A completed health-check answer whose own verdict is ``failure`` (an expired certificate,
    a refused connection, a domain that does not resolve) is a finding about the target,
    however the child's exit code reads. None when the child printed anything else."""
    import json
    try:
        data = json.loads(output)
    except (ValueError, TypeError):
        return None
    if not (isinstance(data, dict) and isinstance(data.get('checks'), list) and data.get('status') == 'failure'):
        return None
    failing = sum(1 for c in data['checks'] if isinstance(c, dict) and c.get('status') == 'failure')
    return HealthResult(2, f"{scheme}: checks failed" + (f" ({failing} failing)" if failing else ""),
                        'ok', verdict='finding')


def _completed_uri_result(scheme: str, returncode: int, output: str) -> HealthResult:
    """Judge a child that exited 0 or 1 by its parsed answer; ValueError/TypeError mean malformed."""
    import json
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
    reported = data.get('exit_code')
    if type(reported) is int and reported >= 2:
        # The answer itself says it failed, whatever the process exit code was.
        return HealthResult(2, f"{scheme}: critical failure (reported exit {reported})", 'failed')
    if meta.get('errors') or meta.get('warnings') or data.get('warnings'):
        return HealthResult(1, f"{scheme}: incomplete or warning result", 'partial')
    if returncode:
        # A completed answer whose findings set the exit code is not partial.
        return HealthResult(1, f"{scheme}: warnings found", 'ok')
    return HealthResult(0, f"{scheme}: healthy", 'ok')


def _uri_health_result(scheme: str, returncode: int, output: str,
                       stderr: Optional[str] = None) -> HealthResult:
    """A failed child is failed; a partial or unavailable answer cannot be clean."""
    verdict = _failing_check_result(scheme, output) if returncode >= 0 else None
    if verdict is not None:
        return verdict
    if returncode < 0 or returncode >= 2:
        return HealthResult(2, f"{scheme}: critical failure (exit {returncode}{_child_reason(stderr)})",
                            'failed')
    try:
        return _completed_uri_result(scheme, returncode, output)
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


def _row_verdict(row: dict) -> str:
    """A rendered row's verdict; rows from before the verdict field derive it the way HealthResult does."""
    return row.get('verdict') or str(HealthResult(row['exit_code'], '', row.get('outcome', 'ok')).verdict)


def _icon(row: dict) -> str:
    verdict = _row_verdict(row)
    if verdict == 'healthy':
        return '✅'
    if verdict == 'not_applicable':
        return '➖'
    if verdict in ('finding', 'incomplete'):
        return '⚠️ ' if row['exit_code'] < 2 else '❌'
    return '❌'


def _render_results(results: list) -> None:
    """Render health check results to stdout."""
    print()
    for r in results:
        icon = _icon(r)
        print(f"  {icon}  {r['target']}")
        print(f"       {r['summary']}")
        budget = r.get('scan_budget')
        if budget:
            total = str(budget['total']) if budget['exact'] else f"at least {budget['total']}"
            print(f"       Scan: {total} candidate files, {budget['analyzed_files']} analyzed; limit {budget['limit']}")
    print()

    verdicts = [_row_verdict(r) for r in results]
    severity = max((r['exit_code'] for r, v in zip(results, verdicts) if v == 'finding'), default=0)
    if any(v in _LOST_VERDICTS for v in verdicts):
        print("Health: INCOMPLETE — some checks failed or could not complete (see above)")
    elif severity >= 2:
        print("Health: FAIL — see failed checks above")
    elif severity == 1:
        print("Health: WARN — review warnings above")
    else:
        print("Health: PASS")
    print()


def _print_usage_and_exit() -> None:
    print("Usage: reveal health <target> [target ...]", file=sys.stderr)
    print("", file=sys.stderr)
    print("Examples:", file=sys.stderr)
    print("  reveal health ./src", file=sys.stderr)
    print("  reveal health ssl://example.com", file=sys.stderr)
    print("  reveal health mysql://host", file=sys.stderr)
    sys.exit(2)
