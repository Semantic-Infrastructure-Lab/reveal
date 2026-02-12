"""Environment variable adapter (env://)."""

import os
import sys
from typing import Dict, Any, Optional
from .base import ResourceAdapter, register_adapter, register_renderer


class EnvRenderer:
    """Renderer for environment variable results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render all environment variables.

        Args:
            result: Structure dict from EnvAdapter.get_structure()
            format: Output format ('text', 'json', 'grep')
        """
        from ..rendering import render_env_structure
        render_env_structure(result, format)

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render specific environment variable.

        Args:
            result: Element dict from EnvAdapter.get_element()
            format: Output format ('text', 'json', 'grep')
        """
        from ..rendering import render_env_variable
        render_env_variable(result, format)

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render user-friendly errors."""
        print(f"Error accessing environment: {error}", file=sys.stderr)


@register_adapter('env')
@register_renderer(EnvRenderer)
class EnvAdapter(ResourceAdapter):
    """Adapter for exploring environment variables via env:// URIs."""

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for env:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return {
            'adapter': 'env',
            'description': 'Environment variable inspection with auto-categorization and sensitive value redaction',
            'uri_syntax': 'env://[variable_name]',
            'query_params': {},  # No query parameters
            'elements': {},  # Variable names are not fixed elements
            'cli_flags': [],
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': [
                {
                    'type': 'environment',
                    'description': 'All environment variables categorized by type',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'environment'},
                            'source': {'type': 'string', 'const': 'system'},
                            'source_type': {'type': 'string', 'const': 'runtime'},
                            'total_count': {'type': 'integer'},
                            'categories': {
                                'type': 'object',
                                'properties': {
                                    'System': {'type': 'array'},
                                    'Python': {'type': 'array'},
                                    'Node': {'type': 'array'},
                                    'Application': {'type': 'array'},
                                    'Custom': {'type': 'array'}
                                }
                            }
                        }
                    },
                    'example': {
                        'contract_version': '1.0',
                        'type': 'environment',
                        'source': 'system',
                        'source_type': 'runtime',
                        'total_count': 42,
                        'categories': {
                            'System': [
                                {'name': 'PATH', 'value': '/usr/local/bin:/usr/bin', 'sensitive': False, 'length': 25},
                                {'name': 'HOME', 'value': '/home/user', 'sensitive': False, 'length': 10}
                            ],
                            'Python': [
                                {'name': 'PYTHONPATH', 'value': '/opt/python', 'sensitive': False, 'length': 11}
                            ]
                        }
                    }
                },
                {
                    'type': 'env_variable',
                    'description': 'Specific environment variable details',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'name': {'type': 'string'},
                            'value': {'type': 'string'},
                            'category': {'type': 'string', 'enum': ['System', 'Python', 'Node', 'Application', 'Custom']},
                            'sensitive': {'type': 'boolean'},
                            'length': {'type': 'integer'}
                        }
                    }
                }
            ],
            'example_queries': [
                {
                    'uri': 'env://',
                    'description': 'List all environment variables grouped by category',
                    'output_type': 'environment'
                },
                {
                    'uri': 'env://PATH',
                    'description': 'Get PATH variable value and metadata',
                    'output_type': 'env_variable'
                },
                {
                    'uri': 'env://DATABASE_URL',
                    'description': 'Get database URL (sensitive values automatically redacted)',
                    'output_type': 'env_variable'
                }
            ],
            'security_features': [
                'Automatic sensitive value redaction',
                'Pattern-based detection: PASSWORD, SECRET, TOKEN, KEY, CREDENTIAL, API_KEY, AUTH',
                'Redacted values shown as ***'
            ]
        }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for env:// adapter."""
        return {
            'name': 'env',
            'description': 'Explore environment variables - view all vars or get specific value',
            'syntax': 'env://[variable_name]',
            'examples': [
                {
                    'uri': 'env://',
                    'description': 'List all environment variables (grouped by category)'
                },
                {
                    'uri': 'env://PATH',
                    'description': 'Get value of PATH variable'
                },
                {
                    'uri': 'env://DATABASE_URL',
                    'description': 'Get database connection string (sensitive values hidden)'
                },
                {
                    'uri': 'env:// --format=json',
                    'description': 'JSON output for scripting'
                },
                {
                    'uri': "env:// --format=json | jq '.categories.Python'",
                    'description': 'Filter Python-related variables with jq'
                }
            ],
            'features': [
                'Auto-categorizes variables (System, Python, Node, Application, Custom)',
                'Redacts sensitive values (passwords, tokens, API keys)',
                'Shows variable metadata (category, length, sensitivity)',
                'Supports JSON and grep output formats'
            ],
            'categories': {
                'System': 'PATH, HOME, SHELL, USER, etc.',
                'Python': 'PYTHON*, VIRTUAL*, PYTHONPATH',
                'Node': 'NODE*, NPM*, NVM*',
                'Application': 'APP_*, DATABASE_*, REDIS_*, API_*',
                'Custom': 'Everything else'
            },
            # Executable examples
            'try_now': [
                "reveal env://",
                "reveal env://PATH",
                "reveal env://HOME",
            ],
            # Scenario-based workflow patterns
            'workflows': [
                {
                    'name': 'Audit Environment for Secrets',
                    'scenario': 'Need to check what sensitive data is exposed',
                    'steps': [
                        "reveal env://                    # See all vars (sensitive redacted)",
                        "reveal env:// --format=json | jq '[.categories[] | .[] | select(.sensitive==true)]'",
                    ],
                },
                {
                    'name': 'Debug Python Environment',
                    'scenario': 'Python not finding packages or using wrong interpreter',
                    'steps': [
                        "reveal env://VIRTUAL_ENV         # Is venv active?",
                        "reveal env://PYTHONPATH          # Extra import paths?",
                        "reveal python://venv             # More detailed venv info",
                    ],
                },
            ],
            # What NOT to do
            'anti_patterns': [
                {
                    'bad': "env | grep -i password",
                    'good': "reveal env://",
                    'why': "Automatically redacts sensitive values, prevents accidental exposure in logs",
                },
                {
                    'bad': "echo $DATABASE_URL",
                    'good': "reveal env://DATABASE_URL",
                    'why': "Redacts sensitive values, shows metadata (category, length)",
                },
            ],
            'notes': [
                'Sensitive values are automatically redacted (shown as ***)',
                'Patterns that trigger redaction: PASSWORD, SECRET, TOKEN, KEY, CREDENTIAL, API_KEY, AUTH',
                'Use show_secrets parameter (not exposed via CLI) to reveal sensitive values in code'
            ],
            'output_formats': ['text', 'json', 'grep'],
            'see_also': [
                'reveal help://python - Python runtime inspection',
                'reveal help://tricks - Power user workflows',
                'reveal ast:// - Code structure analysis'
            ]
        }

    SENSITIVE_PATTERNS = [
        'PASSWORD', 'SECRET', 'TOKEN', 'KEY', 'CREDENTIAL',
        'API_KEY', 'AUTH', 'PRIVATE', 'PASSPHRASE'
    ]

    SYSTEM_VARS = {
        # Unix/Linux/macOS
        'PATH', 'HOME', 'SHELL', 'USER', 'LANG', 'PWD',
        'LOGNAME', 'TERM', 'DISPLAY', 'EDITOR', 'PAGER',
        # Windows equivalents and system variables
        'USERPROFILE', 'USERNAME', 'COMSPEC', 'SYSTEMROOT',
        'WINDIR', 'TEMP', 'TMP', 'OS', 'PROCESSOR_ARCHITECTURE',
        'PATHEXT', 'COMPUTERNAME', 'HOMEDRIVE', 'HOMEPATH',
        'LOCALAPPDATA', 'APPDATA', 'PROGRAMFILES'
    }

    def __init__(self):
        """Initialize the environment adapter."""
        self.variables = dict(os.environ)

    def get_structure(self, show_secrets: bool = False, **kwargs: Any) -> Dict[str, Any]:
        """Get all environment variables, grouped by category.

        Args:
            show_secrets: If True, show actual values of sensitive variables

        Returns:
            Dict containing categorized environment variables
        """
        categorized: Dict[str, list] = {
            'System': [],
            'Python': [],
            'Node': [],
            'Application': [],
            'Custom': []
        }

        for name, value in sorted(self.variables.items()):
            category = self._categorize(name)
            var_info = {
                'name': name,
                'value': self._maybe_redact(name, value, show_secrets),
                'sensitive': self._is_sensitive(name),
                'length': len(value)
            }
            categorized[category].append(var_info)

        # Remove empty categories
        categorized = {k: v for k, v in categorized.items() if v}

        return {
            'contract_version': '1.0',
            'type': 'environment',
            'source': 'system',
            'source_type': 'runtime',
            'total_count': len(self.variables),
            'categories': categorized
        }

    def get_element(self, element_name: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        """Get details about a specific environment variable.

        Args:
            element_name: Name of the environment variable
            **kwargs: Optional keyword arguments:
                - show_secrets: If True, show actual value even if sensitive (default: False)

        Returns:
            Dict with variable details, or None if not found
        """
        show_secrets = kwargs.get('show_secrets', False)

        if element_name not in self.variables:
            return None

        value = self.variables[element_name]
        return {
            'name': element_name,
            'value': self._maybe_redact(element_name, value, show_secrets),
            'category': self._categorize(element_name),
            'sensitive': self._is_sensitive(element_name),
            'length': len(value),
            'raw_value': value if show_secrets else None
        }

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about the environment.

        Returns:
            Dict with environment metadata
        """
        sensitive_count = sum(1 for name in self.variables if self._is_sensitive(name))

        return {
            'type': 'environment',
            'total_variables': len(self.variables),
            'sensitive_variables': sensitive_count,
            'categories': self._get_category_counts()
        }

    def _is_sensitive(self, name: str) -> bool:
        """Check if variable name suggests sensitive data.

        Args:
            name: Variable name to check

        Returns:
            True if name matches sensitive patterns
        """
        upper_name = name.upper()
        return any(pattern in upper_name for pattern in self.SENSITIVE_PATTERNS)

    def _maybe_redact(self, name: str, value: str, show_secrets: bool) -> str:
        """Redact sensitive values unless show_secrets=True.

        Args:
            name: Variable name
            value: Variable value
            show_secrets: Whether to show actual value

        Returns:
            Original value or redacted string
        """
        if not show_secrets and self._is_sensitive(name):
            return '***'
        return value

    def _categorize(self, name: str) -> str:
        """Categorize variable by name pattern.

        Args:
            name: Variable name

        Returns:
            Category name
        """
        # System variables
        if name in self.SYSTEM_VARS:
            return 'System'

        # Python-related
        if name.startswith('PYTHON') or name.startswith('VIRTUAL') or name == 'PYTHONPATH':
            return 'Python'

        # Node/NPM-related
        if name.startswith('NODE') or name.startswith('NPM') or name.startswith('NVM'):
            return 'Node'

        # Application-specific (common patterns)
        if any(name.startswith(prefix) for prefix in ['APP_', 'DATABASE_', 'REDIS_', 'API_']):
            return 'Application'

        # Everything else
        return 'Custom'

    def _get_category_counts(self) -> Dict[str, int]:
        """Get count of variables per category.

        Returns:
            Dict mapping category to count
        """
        counts = {}
        for name in self.variables:
            category = self._categorize(name)
            counts[category] = counts.get(category, 0) + 1
        return counts
