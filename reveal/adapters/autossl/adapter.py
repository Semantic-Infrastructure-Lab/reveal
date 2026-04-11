"""AutoSSL adapter — inspect cPanel AutoSSL run logs (autossl://).

URI scheme: autossl://[TIMESTAMP]

    autossl://                  List available runs
    autossl://latest            Parse most recent run
    autossl://2026-03-03T23:26:01Z  Parse specific run

All operations are filesystem-based; must be run as root (or with read
access to /var/cpanel/logs/autossl/).

Examples:
    reveal autossl://               # List recent runs
    reveal autossl://latest         # Latest run summary
    reveal autossl://latest --format=json | jq '.users[0].domains[:5]'
"""

from typing import Any, Dict, Optional

from ..base import ResourceAdapter, register_adapter, register_renderer
from .parser import AUTOSSL_LOG_DIR, list_runs, parse_run
from .renderer import AutosslRenderer

_FAILURE_STATUSES = {'incomplete', 'defective', 'dcv_failed', 'unknown'}


def _get_error_code_taxonomy() -> dict:
    """Return the AutoSSL error code reference (autossl://error-codes)."""
    return {
        'type': 'autossl_error_codes',
        'title': 'cPanel AutoSSL Error Code Reference',
        'openssl_defect_codes': [
            {
                'code': 'DEPTH_ZERO_SELF_SIGNED_CERT',
                'meaning': 'Leaf certificate is self-signed (not issued by a CA)',
                'cause': 'Server is using a cPanel self-signed fallback cert',
                'fix': 'AutoSSL should replace it automatically; if stuck, check DCV impediments',
            },
            {
                'code': 'SELF_SIGNED_CERT_IN_CHAIN',
                'meaning': 'A certificate in the chain is self-signed',
                'cause': 'Intermediate cert is missing or the chain includes a root in the wrong position',
                'fix': 'Re-run AutoSSL; if persistent, check the domain\'s cert chain with: reveal ssl://DOMAIN --advanced',
            },
            {
                'code': 'CERT_HAS_EXPIRED',
                'meaning': 'Certificate has passed its notAfter date',
                'cause': 'AutoSSL failed to renew before expiry',
                'fix': 'Check DCV impediments for the domain; fix DNS/HTTP challenge accessibility',
            },
            {
                'code': 'UNABLE_TO_GET_ISSUER_CERT_LOCALLY',
                'meaning': 'Issuer cert not found in local trust store',
                'cause': 'Incomplete chain or missing intermediate cert',
                'fix': 'Usually resolves on next AutoSSL cycle; check with reveal ssl://DOMAIN --advanced',
            },
            {
                'code': 'CERTIFICATE_VERIFY_FAILED',
                'meaning': 'Certificate failed trust chain verification',
                'cause': 'General chain validation error — often an intermediate missing',
                'fix': 'Check live cert with: reveal ssl://DOMAIN --advanced',
            },
        ],
        'dcv_impediment_codes': [
            {
                'code': 'TOTAL_DCV_FAILURE',
                'meaning': 'Every domain in the certificate failed DCV — no renewal possible',
                'cause': 'DNS not pointing to this server, or HTTP challenge path blocked',
                'fix': (
                    'Verify DNS A record points to this server. '
                    'Check ACME challenge path: reveal nginx://DOMAIN --validate-nginx-acme'
                ),
            },
            {
                'code': 'NO_UNSECURED_DOMAIN_PASSED_DCV',
                'meaning': 'No unsecured domain passed DCV — partial failure',
                'cause': 'All domains in the cert failed DCV; at least one must pass for renewal',
                'fix': 'Fix the primary domain DCV first; subdomains inherit the cert',
            },
            {
                'code': 'DNS_RESOLVES_TO_ANOTHER_SERVER',
                'meaning': 'Domain\'s DNS A/AAAA record points to a different server',
                'cause': 'Domain migrated away or DNS not updated; AutoSSL skips externally-hosted domains',
                'fix': (
                    'Update DNS to point to this server, or remove the domain from cPanel. '
                    'Check with: reveal domain://DOMAIN'
                ),
            },
            {
                'code': 'DOMAIN_NOT_IN_CPANEL',
                'meaning': 'Domain not found in cPanel user account',
                'cause': 'Domain was removed from the account but cert still references it',
                'fix': 'Re-add the domain to cPanel or remove it from the SSL cert',
            },
        ],
        'tls_status_values': {
            'ok': 'Certificate valid; AutoSSL satisfied (no renewal needed)',
            'incomplete': 'No renewal triggered — existing cert is still valid and not near expiry',
            'defective': 'Certificate has a problem (expired, self-signed, chain error)',
        },
        'next_steps': [
            'reveal autossl://latest --only-failures     # Show only domains with errors',
            'reveal autossl://latest --format=json | jq \'.users[].domains[] | select(.tls_status=="defective")\'',
            'reveal domain://DOMAIN                      # Check DNS for a failing domain',
            'reveal nginx://DOMAIN --validate-nginx-acme # Verify ACME challenge path',
            'reveal ssl://DOMAIN --advanced              # Inspect live cert chain',
        ],
    }


def _apply_autossl_filters(result: Dict[str, Any], only_failures: bool = False,
                            summary: bool = False,
                            user: Optional[str] = None) -> Dict[str, Any]:
    """Apply --only-failures, --summary, and --user filters to a parsed autossl run.

    Args:
        result: Parsed autossl_run dict from parse_run()
        only_failures: Drop ok domains; drop users with no remaining failures.
        summary: Return only run-level header + summary counts, no per-user detail.
        user: Filter to a single named user (case-sensitive).

    Returns:
        Filtered copy of result.
    """
    users = list(result.get('users', []))

    # Filter to single user
    if user is not None:
        users = [u for u in users if u.get('username') == user]
        if not users:
            available = [u.get('username', '?') for u in result.get('users', [])]
            raise ValueError(
                f"User '{user}' not found in this AutoSSL run. "
                f"Available users: {', '.join(available) if available else '(none)'}"
            )

    # Filter to failures only
    if only_failures:
        filtered_users = []
        for u in users:
            failing_domains = [
                d for d in u.get('domains', [])
                if d.get('tls_status') not in (None, 'ok')
            ]
            if failing_domains:
                filtered_users.append({**u, 'domains': failing_domains,
                                        'domain_count': len(failing_domains)})
        users = filtered_users

    result = dict(result)
    result['users'] = users
    result['user_count'] = len(users)
    result['domain_count'] = sum(u['domain_count'] for u in users)

    # Summary mode: strip per-user detail
    if summary:
        result = {k: v for k, v in result.items() if k != 'users'}
        result['user_count'] = len(users)
        result['domain_count'] = sum(u.get('domain_count', 0) for u in users)

    return result


@register_adapter('autossl')
@register_renderer(AutosslRenderer)
class AutosslAdapter(ResourceAdapter):
    """Adapter for inspecting cPanel AutoSSL run logs via autossl:// URIs.

    Usage:
        reveal autossl://               # List available run timestamps
        reveal autossl://latest         # Parse most recent run
        reveal autossl://TIMESTAMP      # Parse a specific run
    """

    def __init__(self, connection_string: str = ""):
        if not connection_string:
            raise TypeError("AutosslAdapter requires a connection string: autossl://[TIMESTAMP]")

        self.connection_string = connection_string
        self.timestamp: Optional[str] = None  # None → list runs
        self.domain: Optional[str] = None     # set → domain history mode
        self._parse_connection_string(connection_string)

    def _parse_connection_string(self, uri: str) -> None:
        if not uri.startswith('autossl://'):
            raise ValueError(f"Invalid autossl:// URI: {uri}")
        rest = uri[len('autossl://'):].strip('/')
        if rest == '':
            self.timestamp = None
        elif rest == 'latest':
            self.timestamp = 'latest'
        elif '.' in rest:
            # Domains always contain dots; timestamps (YYYY-MM-DD...) do not
            self.domain = rest
        else:
            self.timestamp = rest

    def get_structure(self, only_failures: bool = False, summary: bool = False,
                      user: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        """Return run list or parsed run data.

        Args:
            only_failures: When True, omit domains with tls_status='ok'; drop
                users with no remaining failures.
            summary: When True, strip per-user/domain detail — return only the
                top-level run header and summary counts.
            user: When set, filter to only the named user (case-sensitive).
        """
        if self.domain is not None:
            show_all = kwargs.get('all', False)
            return self._domain_history_structure(self.domain, show_all=show_all)
        if self.timestamp is None:
            return self._list_runs_structure()
        if self.timestamp == 'error-codes':
            return _get_error_code_taxonomy()
        result = self._parse_run_structure(self.timestamp)
        if result.get('error'):
            return result
        return _apply_autossl_filters(result, only_failures=only_failures,
                                      summary=summary, user=user)

    def _list_runs_structure(self) -> Dict[str, Any]:
        runs = list_runs()
        next_steps = ['reveal autossl://latest    # Parse most recent run']
        if runs:
            next_steps.append(
                f'reveal autossl://{runs[0]}    # Parse this specific run'
            )
        return {
            'contract_version': '1.0',
            'type': 'autossl_runs',
            'log_dir': AUTOSSL_LOG_DIR,
            'run_count': len(runs),
            'runs': runs,
            'next_steps': next_steps,
        }

    def _parse_run_structure(self, timestamp: str) -> Dict[str, Any]:
        if timestamp == 'latest':
            runs = list_runs()
            if not runs:
                raise ValueError(
                    f"No AutoSSL runs found in {AUTOSSL_LOG_DIR}. "
                    "Is this a cPanel server?"
                )
            timestamp = runs[0]
        return parse_run(timestamp)

    def _domain_history_structure(self, domain: str, show_all: bool = False) -> Dict[str, Any]:
        """Search all runs for a specific domain and return its full history."""
        _ROW_LIMIT = 20
        runs = list_runs()
        history = []
        for timestamp in runs:
            result = parse_run(timestamp)
            if result.get('error'):
                continue
            for user in result.get('users', []):
                for d in user.get('domains', []):
                    if d['domain'] == domain:
                        history.append({
                            'run_timestamp': timestamp,
                            'run_start': result.get('run_start'),
                            'username': user['username'],
                            'tls_status': d['tls_status'],
                            'cert_expiry_days': d.get('cert_expiry_days'),
                            'defect_codes': d.get('defect_codes', []),
                            'impediments': d.get('impediments', []),
                            'detail': d.get('detail', ''),
                        })
        ok_count = sum(1 for h in history if h['tls_status'] == 'ok')
        defective_count = sum(1 for h in history if h['tls_status'] == 'defective')
        incomplete_count = sum(1 for h in history if h['tls_status'] == 'incomplete')
        dcv_failed_count = sum(
            1 for h in history if not h['tls_status'] and h.get('impediments')
        )
        total_run_count = len(history)
        oldest_run_timestamp = history[-1]['run_timestamp'] if history else None
        truncated = (not show_all) and (total_run_count > _ROW_LIMIT)
        if truncated:
            history = history[:_ROW_LIMIT]
        return {
            'contract_version': '1.0',
            'type': 'autossl_domain_history',
            'domain': domain,
            'run_count': total_run_count,
            'truncated': truncated,
            'oldest_run_timestamp': oldest_run_timestamp,
            'summary': {
                'ok': ok_count,
                'defective': defective_count,
                'incomplete': incomplete_count,
                'dcv_failed': dcv_failed_count,
            },
            'history': history,
            'next_steps': [
                'reveal autossl://latest    # Latest full run',
                'reveal autossl://          # List all runs',
            ],
        }

    def get_element(self, element_name: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return None

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Machine-readable schema for AI agent integration."""
        return {
            'adapter': 'autossl',
            'description': 'Inspect cPanel AutoSSL run logs — per-domain TLS outcomes, DCV failures',
            'uri_syntax': 'autossl://[TIMESTAMP|DOMAIN]',
            'query_params': {},
            'elements': {},
            'cli_flags': ['--format=json', '--only-failures', '--user=USERNAME', '--summary', '--all'],
            'supports_batch': False,
            'output_types': [
                {
                    'type': 'autossl_runs',
                    'description': 'List of available AutoSSL run timestamps',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'type': {'type': 'string', 'const': 'autossl_runs'},
                            'run_count': {'type': 'integer'},
                            'runs': {'type': 'array', 'items': {'type': 'string'}},
                        },
                    },
                },
                {
                    'type': 'autossl_run',
                    'description': 'Parsed AutoSSL run — per-user/domain TLS outcomes',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'type': {'type': 'string', 'const': 'autossl_run'},
                            'run_timestamp': {'type': 'string'},
                            'provider': {'type': 'string'},
                            'domain_count': {'type': 'integer'},
                            'summary': {
                                'type': 'object',
                                'description': 'Counts keyed by tls_status: ok/incomplete/defective',
                            },
                            'users': {
                                'type': 'array',
                                'items': {
                                    'type': 'object',
                                    'properties': {
                                        'username': {'type': 'string'},
                                        'domain_count': {'type': 'integer'},
                                        'domains': {
                                            'type': 'array',
                                            'items': {
                                                'type': 'object',
                                                'properties': {
                                                    'domain': {'type': 'string'},
                                                    'tls_status': {
                                                        'type': 'string',
                                                        'enum': ['ok', 'incomplete', 'defective'],
                                                    },
                                                    'cert_expiry_days': {'type': ['number', 'null']},
                                                    'detail': {
                                                        'type': 'string',
                                                        'description': 'Synthesized summary: defect codes + impediment codes (e.g. "CERT_HAS_EXPIRED, DCV:TOTAL_DCV_FAILURE")',
                                                    },
                                                    'defect_codes': {'type': 'array', 'items': {'type': 'string'}},
                                                    'impediments': {'type': 'array'},
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
                {
                    'type': 'autossl_domain_history',
                    'description': 'TLS history for a specific domain across all runs',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'type': {'type': 'string', 'const': 'autossl_domain_history'},
                            'domain': {'type': 'string'},
                            'run_count': {'type': 'integer'},
                            'summary': {
                                'type': 'object',
                                'description': 'Counts by tls_status across all runs: ok/defective/incomplete',
                            },
                            'history': {
                                'type': 'array',
                                'items': {
                                    'type': 'object',
                                    'properties': {
                                        'run_timestamp': {'type': 'string'},
                                        'run_start': {'type': ['string', 'null']},
                                        'username': {'type': 'string'},
                                        'tls_status': {'type': 'string'},
                                        'cert_expiry_days': {'type': ['number', 'null']},
                                        'defect_codes': {'type': 'array', 'items': {'type': 'string'}},
                                        'impediments': {'type': 'array'},
                                        'detail': {'type': 'string'},
                                    },
                                },
                            },
                        },
                    },
                },
            ],
            'example_queries': [
                {
                    'uri': 'reveal autossl://',
                    'description': 'List all available AutoSSL run timestamps on this server',
                    'output_type': 'autossl_runs',
                },
                {
                    'uri': 'reveal autossl://2024-01-15_03-00-00',
                    'description': 'Inspect a specific AutoSSL run — per-user/domain TLS outcomes',
                    'output_type': 'autossl_run',
                },
                {
                    'uri': "reveal autossl:// --format=json | jq '.runs[-1]'",
                    'description': 'Get timestamp of the most recent AutoSSL run',
                    'output_type': 'autossl_runs',
                },
                {
                    'uri': "reveal autossl://$(reveal autossl:// --format=json | jq -r '.runs[-1]')",
                    'description': 'Inspect the most recent AutoSSL run directly',
                    'output_type': 'autossl_run',
                },
                {
                    'uri': 'reveal autossl://app.example.com',
                    'description': 'Domain history — TLS status for one domain across all runs',
                    'output_type': 'autossl_domain_history',
                },
            ],
            'notes': [
                'Reads /var/cpanel/logs/autossl/ directly — no WHM API or credentials required',
                'Timestamps are in YYYY-MM-DD_HH-MM-SS format matching log filenames',
                'tls_status values: ok (cert valid), incomplete (pending), defective (failed)',
                'defect_codes explain why AutoSSL failed: DCV_ERROR, RATE_LIMIT, etc.',
                'Only available on cPanel servers — adapter errors cleanly on non-cPanel systems',
            ],
        }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        return {
            'name': 'autossl',
            'description': "Inspect cPanel AutoSSL run logs — per-domain TLS outcomes, DCV failures",
            'stability': 'beta',
            'syntax': 'autossl://[TIMESTAMP|DOMAIN]',
            'features': [
                'Filesystem-based — no WHM API or credentials required',
                'Lists all available run timestamps',
                'Parses NDJSON log: per-user, per-domain TLS status',
                'TLS outcomes: ok / incomplete / defective',
                'Defect codes extracted (e.g. SELF_SIGNED_CERT, CERT_HAS_EXPIRED)',
                'DCV impediment codes (TOTAL_DCV_FAILURE, NO_UNSECURED_DOMAIN_PASSED_DCV)',
                'Summary by user + overall counts',
                'Filter to one user with --user=USERNAME',
                'Filter to failures only with --only-failures',
                'Domain history: autossl://DOMAIN shows status across all runs',
                'JSON output for scripting and filtering',
            ],
            'examples': [
                {
                    'uri': 'autossl://',
                    'description': 'List available run timestamps (newest first)',
                },
                {
                    'uri': 'autossl://latest',
                    'description': 'Parse most recent AutoSSL run — per-user/domain summary',
                },
                {
                    'uri': 'autossl://2026-03-03T23:26:01Z',
                    'description': 'Parse a specific AutoSSL run by timestamp',
                },
                {
                    'uri': 'autossl://latest --only-failures',
                    'description': 'Show only domains with errors (defective/incomplete) — hides ok domains',
                },
                {
                    'uri': 'autossl://latest --user=sociamonials',
                    'description': 'Filter to a single cPanel user — avoids 800-domain output on shared hosts',
                },
                {
                    'uri': 'autossl://latest --user=sociamonials --only-failures',
                    'description': 'One user, failures only — the most focused diagnostic view',
                },
                {
                    'uri': "autossl://latest --format=json | jq '[.users[].domains[] | select(.tls_status==\"defective\")]'",
                    'description': 'Extract all defective domains as JSON',
                },
                {
                    'uri': 'autossl://app.example.com',
                    'description': 'Domain history — TLS status across all runs (is this always failing?)',
                },
            ],
            'tls_status_values': {
                'ok': 'Certificate valid and AutoSSL satisfied',
                'incomplete': 'No cert renewal triggered (existing cert still valid)',
                'defective': 'Certificate has a problem (expired, self-signed, chain error)',
            },
            'impediment_codes': {
                'TOTAL_DCV_FAILURE': 'Every domain in the cert failed DCV — no renewal possible',
                'NO_UNSECURED_DOMAIN_PASSED_DCV': 'No unsecured domain passed DCV — partial failure',
            },
            'notes': [
                'Must run as root or with read access to /var/cpanel/logs/autossl/',
                'Runs approximately every 3 hours; logs retained ~30 days',
                'Use --format=json for machine-readable output and jq filtering',
                f'Log directory: {AUTOSSL_LOG_DIR}',
            ],
            'see_also': [
                'reveal cpanel://USERNAME/ssl  - Disk cert health per domain',
                'reveal cpanel://USERNAME      - cPanel user overview',
                'reveal ssl://DOMAIN           - Live TLS cert inspection',
            ],
        }
