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
        self._parse_connection_string(connection_string)

    def _parse_connection_string(self, uri: str) -> None:
        if not uri.startswith('autossl://'):
            raise ValueError(f"Invalid autossl:// URI: {uri}")
        rest = uri[len('autossl://'):].strip('/')
        if rest == '':
            self.timestamp = None
        elif rest == 'latest':
            self.timestamp = 'latest'
        else:
            self.timestamp = rest

    def get_structure(self, **kwargs: Any) -> Dict[str, Any]:
        """Return run list or parsed run data."""
        if self.timestamp is None:
            return self._list_runs_structure()
        return self._parse_run_structure(self.timestamp)

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

    def get_element(self, element_name: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return None

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Machine-readable schema for AI agent integration."""
        return {
            'adapter': 'autossl',
            'description': 'Inspect cPanel AutoSSL run logs — per-domain TLS outcomes, DCV failures',
            'uri_syntax': 'autossl://[TIMESTAMP]',
            'query_params': {},
            'elements': {},
            'cli_flags': ['--format=json'],
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
            'syntax': 'autossl://[TIMESTAMP]',
            'features': [
                'Filesystem-based — no WHM API or credentials required',
                'Lists all available run timestamps',
                'Parses NDJSON log: per-user, per-domain TLS status',
                'TLS outcomes: ok / incomplete / defective',
                'Defect codes extracted (e.g. SELF_SIGNED_CERT, CERT_HAS_EXPIRED)',
                'DCV impediment codes (TOTAL_DCV_FAILURE, NO_UNSECURED_DOMAIN_PASSED_DCV)',
                'Summary by user + overall counts',
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
                    'uri': "autossl://latest --format=json | jq '[.users[].domains[] | select(.tls_status==\"defective\")]'",
                    'description': 'Extract all defective domains as JSON',
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
