"""File handling operations.

This module is separate from cli.routing to avoid circular dependencies with adapters.
"""

import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace


def _get_analyzer_or_exit(path: str, allow_fallback: bool):
    """Get analyzer for path or exit with error.

    Args:
        path: File path
        allow_fallback: Whether to allow fallback analyzers

    Returns:
        Analyzer instance

    Exits:
        With error code 1 if no analyzer found
    """
    from .registry import get_analyzer, get_all_analyzers
    from .errors import AnalyzerNotFoundError

    analyzer_class = get_analyzer(path, allow_fallback=allow_fallback)
    if not analyzer_class:
        # Find similar extensions for suggestions
        ext = Path(path).suffix
        similar_exts = None
        if ext:
            analyzers = get_all_analyzers()
            similar_exts = [e for e in analyzers.keys()
                          if ext.lower() in e.lower() or e.lower() in ext.lower()]

        # Create detailed error with suggestions
        error = AnalyzerNotFoundError(
            path=path,
            allow_fallback=allow_fallback,
            similar_extensions=similar_exts
        )

        print(str(error), file=sys.stderr)
        sys.exit(1)

    return analyzer_class(path)


def _build_file_cli_overrides(args: Optional['Namespace']) -> dict:
    """Build CLI overrides dictionary from args.

    Args:
        args: Argument namespace

    Returns:
        CLI overrides dict
    """
    cli_overrides = {}
    if args and getattr(args, 'no_breadcrumbs', False):
        cli_overrides['display'] = {'breadcrumbs': False}
    return cli_overrides


def _handle_domain_extraction(analyzer) -> None:
    """Handle domain extraction from analyzer.

    Args:
        analyzer: Analyzer instance

    Exits:
        With error code 1 if domain extraction not supported
    """
    if hasattr(analyzer, 'extract_ssl_domains'):
        domains = analyzer.extract_ssl_domains()
        for domain in domains:
            print(f"ssl://{domain}")
    else:
        print(f"Error: --extract domains not supported for {type(analyzer).__name__}", file=sys.stderr)
        print("This option is available for nginx config files.", file=sys.stderr)
        sys.exit(1)


def _handle_acme_roots_extraction(analyzer) -> None:
    """Print ACME challenge root paths and nobody ACL status (N4)."""
    if not hasattr(analyzer, 'extract_acme_roots'):
        print(f"Error: --extract acme-roots not supported for {type(analyzer).__name__}",
              file=sys.stderr)
        print("This option is available for nginx config files.", file=sys.stderr)
        sys.exit(1)

    rows = analyzer.extract_acme_roots()
    if not rows:
        print("No ACME challenge location blocks found.")
        return

    col_domain = max(len(r['domain']) for r in rows)
    col_path = max(len(r['acme_path']) for r in rows)

    header = (f"  {'domain':<{col_domain}}  {'acme root path':<{col_path}}  acl status")
    print(header)
    print("  " + "-" * (len(header) - 2))

    for r in rows:
        status = r['acl_status']
        if status == 'ok':
            icon = "✅"
            detail = "nobody:read OK"
        elif status == 'denied':
            failing = r.get('acl_failing_path') or ''
            detail = f"❌ DENIED  ({r['acl_message']})"
            icon = ""
        elif status == 'not_found':
            icon = "⚠️ "
            detail = f"path not found: {r['acme_path']}"
        else:
            icon = "❓"
            detail = r['acl_message']

        print(f"  {r['domain']:<{col_domain}}  {r['acme_path']:<{col_path}}  {icon} {detail}")


def _handle_check_acl(analyzer) -> None:
    """Print nobody ACL status for all root directives in config (N1)."""
    if not hasattr(analyzer, 'extract_docroot_acl'):
        print(f"Error: --check-acl not supported for {type(analyzer).__name__}",
              file=sys.stderr)
        print("This option is available for nginx config files.", file=sys.stderr)
        sys.exit(1)

    rows = analyzer.extract_docroot_acl()
    if not rows:
        print("No root directives found.")
        return

    failures = [r for r in rows if r['acl_status'] != 'ok']
    passes = [r for r in rows if r['acl_status'] == 'ok']

    col_root = max(len(r['root']) for r in rows)
    col_domain = max(len(r['domain']) for r in rows)

    if failures:
        print(f"❌ ACL failures ({len(failures)}):")
        for r in failures:
            msg = r['acl_message']
            print(f"  {r['root']:<{col_root}}  ({r['domain']})  {msg}")
        print()

    if passes:
        print(f"✅ OK ({len(passes)}):")
        for r in passes:
            print(f"  {r['root']:<{col_root}}  ({r['domain']})")
        print()

    exit_code = 2 if failures else 0
    if failures:
        sys.exit(exit_code)


def _handle_validate_nginx_acme(analyzer) -> None:
    """Full ACME pipeline audit: acme root + ACL + live SSL per domain (--validate-nginx-acme)."""
    if not hasattr(analyzer, 'extract_acme_roots'):
        print(f"Error: --validate-nginx-acme not supported for {type(analyzer).__name__}",
              file=sys.stderr)
        print("This option is available for nginx config files.", file=sys.stderr)
        sys.exit(1)

    from .adapters.ssl.certificate import check_ssl_health

    rows = analyzer.extract_acme_roots()
    if not rows:
        print("No ACME challenge location blocks found.")
        return

    # Fetch live SSL for each domain
    results = []
    for r in rows:
        domain = r['domain']
        try:
            ssl_result = check_ssl_health(domain, warn_days=30, critical_days=7)
            ssl_status = ssl_result.get('status', 'unknown')
            leaf = ssl_result.get('leaf', {})
            ssl_days = leaf.get('days_until_expiry')
            ssl_not_after = leaf.get('not_after', '')
        except Exception as exc:
            ssl_status = 'error'
            ssl_days = None
            ssl_not_after = str(exc)[:60]
        results.append({**r, 'ssl_status': ssl_status, 'ssl_days': ssl_days,
                        'ssl_not_after': ssl_not_after})

    col_domain = max(len(r['domain']) for r in results)
    col_path = max(len(r['acme_path']) for r in results)

    # Header
    header = (f"  {'domain':<{col_domain}}  {'acme root path':<{col_path}}"
              f"  {'acl':<14}  ssl status")
    print(header)
    print("  " + "─" * (len(header) - 2))

    has_failures = False
    for r in results:
        acl_status = r['acl_status']
        if acl_status == 'ok':
            acl_col = "✅ ACL ok"
        elif acl_status == 'denied':
            acl_col = "❌ ACL DENIED"
            has_failures = True
        else:
            acl_col = f"⚠️  ACL {acl_status}"

        ssl_status = r['ssl_status']
        if ssl_status == 'healthy':
            days = r['ssl_days']
            ssl_col = f"✅ {days}d"
            if r['ssl_not_after']:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(r['ssl_not_after'].replace('Z', '+00:00'))
                    ssl_col += f"  ({dt.strftime('%b %d, %Y')})"
                except (ValueError, TypeError):
                    pass
        elif ssl_status in ('warning', 'critical'):
            days = r['ssl_days']
            ssl_col = f"⚠️  expires in {days}d"
        elif ssl_status == 'expired':
            days = abs(r['ssl_days'] or 0)
            ssl_col = f"❌ EXPIRED {days} days ago"
            has_failures = True
        elif ssl_status == 'error':
            ssl_col = f"❌ {r['ssl_not_after']}"
            has_failures = True
        else:
            ssl_col = ssl_status

        print(f"  {r['domain']:<{col_domain}}  {r['acme_path']:<{col_path}}"
              f"  {acl_col:<14}  {ssl_col}")

    if has_failures:
        sys.exit(2)


def _handle_check_conflicts(analyzer) -> None:
    """Detect nginx location prefix overlaps and regex/prefix conflicts (N2)."""
    if not hasattr(analyzer, 'detect_location_conflicts'):
        print(f"Error: --check-conflicts not supported for {type(analyzer).__name__}",
              file=sys.stderr)
        print("This option is available for nginx config files.", file=sys.stderr)
        sys.exit(1)

    conflicts = analyzer.detect_location_conflicts()
    if not conflicts:
        print("✅ No location conflicts detected.")
        return

    warnings = [c for c in conflicts if c['severity'] == 'warning']
    infos = [c for c in conflicts if c['severity'] == 'info']

    if warnings:
        print(f"⚠️  Conflicts ({len(warnings)}):")
        for c in warnings:
            print(f"\n  [{c['server']}]")
            print(f"    {c['location_a']['path']}  (line {c['location_a']['line']})")
            print(f"    {c['location_b']['path']}  (line {c['location_b']['line']})")
            print(f"    → {c['note']}")
        print()

    if infos:
        print(f"ℹ️  Prefix overlaps ({len(infos)}):")
        for c in infos:
            print(f"\n  [{c['server']}]")
            print(f"    {c['location_a']['path']}  (line {c['location_a']['line']})")
            print(f"    {c['location_b']['path']}  (line {c['location_b']['line']})")
            print(f"    → {c['note']}")
        print()

    if warnings:
        sys.exit(2)


def _handle_extract_option(analyzer, extract_type: str) -> None:
    """Handle --extract option with validation.

    Args:
        analyzer: Analyzer instance
        extract_type: Type to extract (e.g., 'domains', 'acme-roots')

    Exits:
        With error code 1 if extract type unknown
    """
    if extract_type == 'domains':
        _handle_domain_extraction(analyzer)
    elif extract_type == 'acme-roots':
        _handle_acme_roots_extraction(analyzer)
    else:
        print(f"Error: Unknown extract type '{extract_type}'", file=sys.stderr)
        print("Supported types: domains, acme-roots (for nginx configs)", file=sys.stderr)
        sys.exit(1)


def handle_file(path: str, element: Optional[str], show_meta: bool,
                output_format: str, args: Optional['Namespace'] = None) -> None:
    """Handle file analysis.

    Args:
        path: File path
        element: Optional element to extract
        show_meta: Whether to show metadata only
        output_format: Output format ('text', 'json', 'grep')
        args: Full argument namespace (for filter options)
    """
    from .display import show_structure, show_metadata, extract_element
    from .config import RevealConfig

    # Get analyzer
    allow_fallback = not getattr(args, 'no_fallback', False) if args else True
    analyzer = _get_analyzer_or_exit(path, allow_fallback)

    # Load config with CLI overrides
    cli_overrides = _build_file_cli_overrides(args)
    config = RevealConfig.get(
        start_path=Path(path).parent if Path(path).is_file() else Path(path),
        cli_overrides=cli_overrides if cli_overrides else None
    )

    # Route to appropriate handler based on flags
    if show_meta:
        show_metadata(analyzer, output_format, config=config)
        return

    if args and getattr(args, 'extract', None):
        _handle_extract_option(analyzer, args.extract.lower())
        return

    if args and getattr(args, 'check_acl', False):
        _handle_check_acl(analyzer)
        return

    if args and getattr(args, 'validate_nginx_acme', False):
        _handle_validate_nginx_acme(analyzer)
        return

    if args and getattr(args, 'check_conflicts', False):
        _handle_check_conflicts(analyzer)
        return

    if args and getattr(args, 'validate_schema', None):
        from .checks import run_schema_validation
        run_schema_validation(analyzer, path, args.validate_schema, output_format, args)
        return

    if args and getattr(args, 'check', False):
        from .checks import run_pattern_detection
        run_pattern_detection(analyzer, path, output_format, args, config=config)
        return

    if element:
        extract_element(analyzer, element, output_format, config=config)
        return

    show_structure(analyzer, output_format, args, config=config)
