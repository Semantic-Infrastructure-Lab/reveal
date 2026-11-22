"""Environment variable adapter (env://)."""

import os
import re
from typing import Dict, Any, Optional, Tuple
from .base import ResourceAdapter, Stability, register_adapter, register_renderer
from ..errors import RequestValidationError
from ..utils.query_binding import bind_declared_params
from ..utils.query_parser import ParamSpec, QueryParams, ResourceSpec, legacy_check, param_schema
from ..utils.results import AnalysisCompleteness, ResultBuilder, result_execution_facts
from reveal.reveal_types import CONTRACT_VERSION

_SCHEMA_OUTPUT_TYPES = [
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
            'contract_version': CONTRACT_VERSION,
            'type': 'environment',
            'source': 'system',
            'source_type': 'runtime',
            'total_count': 42,
            'categories': {
                'System': [
                    {'name': 'PATH', 'value': '/usr/local/bin:/usr/bin', 'sensitive': False, 'length': 23},
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
]

_SCHEMA_EXAMPLE_QUERIES = [
    {
        'uri': 'env://',
        'description': 'All environment variables grouped by category (System, Python, Node, Application, Custom)',
        'output_type': 'environment'
    },
    {
        'uri': 'env://PATH',
        'description': 'Get specific variable value, category, and sensitivity flag',
        'output_type': 'env_variable'
    },
    {
        'uri': 'env://DATABASE_URL',
        'description': 'Sensitive variable — value automatically redacted to ***',
        'output_type': 'env_variable'
    },
    {
        'uri': 'env:// --format=json',
        'description': 'Machine-readable: vars grouped under their category key, each with a sensitive flag',
        'output_type': 'environment'
    },
    {
        'uri': "env:// --format=json | jq '.categories.Application'",
        'description': 'Extract just Application-category variables',
        'output_type': 'environment'
    }
]

_SCHEMA_NOTES = [
    'Sensitive values are auto-redacted: a name holding PASSWORD, PASSWD, PGPASSWORD, SECRET, TOKEN, KEY, CREDENTIAL, AUTH, PRIVATE, PASSPHRASE, DATABASE_URL, DSN, CONNECTION_STRING or CONNSTR as a whole _-delimited word (plural too, any case) or ending in _PWD, or a value that is a URL with user:password@ or carries a password=/pwd= parameter',
    'Redacted values shown as *** on every output (text, JSON, the Python API, MCP): no control discloses them',
    'env:// groups all vars by category: System, Python, Node, Application, Custom',
    'env://VAR_NAME returns the single variable with sensitivity classification',
    '--format=json exposes per-variable sensitive flag for programmatic filtering',
]

_SCHEMA_SECURITY_FEATURES = [
    'Automatic sensitive value redaction',
    'Name-based detection: PASSWORD, PASSWD, PGPASSWORD, SECRET, TOKEN, KEY, CREDENTIAL, API_KEY, AUTH, PRIVATE, PASSPHRASE, DATABASE_URL, DSN, CONNECTION_STRING, CONNSTR (whole _-delimited words, plural too) and a _PWD suffix',
    'Value-based detection: a URL with embedded user:password@ credentials or a password=/pwd= parameter, whatever the name',
    'Redacted values shown as ***'
]


# env takes no control: the resource is the variable (BACK-2626), so an undeclared keyword or URI key is an invalid
# request. --check/--lint never changed an env answer: an inert legacy modifier with its note (BACK-2708).
PARAM_SPECS: Tuple[ParamSpec, ...] = (legacy_check(),)


class EnvRenderer:
    """Renderer for environment variable results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render the listing, or the one variable a resource names (``reveal env NAME``).

        Args:
            result: Structure dict from EnvAdapter.get_structure()
            format: Output format ('text', 'json', 'grep')
        """
        from ..rendering import render_env_structure, render_env_variable
        if result.get('type') == EnvAdapter.ELEMENT_RESULT_TYPE:
            render_env_variable(result, format)
            return
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


@register_adapter('env')
@register_renderer(EnvRenderer)
class EnvAdapter(ResourceAdapter):
    """Adapter for exploring environment variables via env:// URIs.

    Usage:
        reveal env              # every variable, grouped by category (or env://)
        reveal env PATH         # one variable (or env://PATH)
    """
    HELP_CLUSTER = 'Data & Config'
    ELEMENT_RESULT_TYPE = 'env_variable'  # its schema's element type (BACK-1591)

    STABILITY = Stability.STABLE
    LEGACY_INIT = False
    CANONICAL_EMPTY_RESOURCE = ''
    # The declaration `reveal env` and env:// are both generated from (D20, BACK-2626): the resource is the variable,
    # and env takes no control. Secret values are redacted on every output; no control discloses them (BACK-2752).
    BOUND_QUERY_CALL = True
    PARAM_SPECS: tuple = PARAM_SPECS
    RESOURCE_SPEC = ResourceSpec(name='variable', cli_default='', uri_default='', walks=False, filesystem=False)
    RESULT_TYPE = 'environment'
    DEFAULT_FAIL_ON = 'none'
    FINDINGS_POLICIES = ('none',)

    @classmethod
    def uri_execution_facts(cls, resource):
        """The listing and the variable share D6: a variable that is not set is an invalid request (exit 2)."""
        return cls.execution_facts

    @classmethod
    def uri_result_type(cls, resource):
        return cls.ELEMENT_RESULT_TYPE if resource.partition('?')[0] else cls.RESULT_TYPE

    @classmethod
    def result_type_at(cls, params, resource):
        """The answer the resource picks: the variable it names, else the listing."""
        return cls.uri_result_type(resource)

    @staticmethod
    def execution_facts(result):
        return result_execution_facts(result, completeness=AnalysisCompleteness.COMPLETE)

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for env:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return {
            'adapter': 'env',
            'description': 'Environment variable inspection with auto-categorization and sensitive value redaction',
            'uri_syntax': 'env://[NAME] (reveal env [NAME])',
            'query_params': param_schema(PARAM_SPECS),
            'resource': EnvAdapter.RESOURCE_SPEC.schema(),
            'elements': {},
            'cli_flags': [],
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': _SCHEMA_OUTPUT_TYPES,
            'example_queries': _SCHEMA_EXAMPLE_QUERIES,
            'notes': _SCHEMA_NOTES,
            'security_features': _SCHEMA_SECURITY_FEATURES,
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
                'Names that trigger redaction: PASSWORD, SECRET, TOKEN, KEY, CREDENTIAL, API_KEY, AUTH, PRIVATE, PASSPHRASE, DATABASE_URL, DSN (whole _-delimited words, plural too); also any value that is a URL with user:password@',
                'Secret values are never disclosed — redaction is enforced at all output layers'
            ],
            'output_formats': ['text', 'json', 'grep'],
            'see_also': [
                'reveal help://tricks - Power user workflows',
                'reveal ast:// - Code structure analysis'
            ]
        }

    SENSITIVE_PATTERNS = [
        'PASSWORD', 'PASSWD', 'PGPASSWORD', 'SECRET', 'TOKEN', 'KEY', 'CREDENTIAL',
        'API_KEY', 'AUTH', 'PRIVATE', 'PASSPHRASE',
        'DATABASE_URL', 'DSN', 'CONNECTION_STRING', 'CONNSTR'
    ]

    # Compiled regex: each pattern must appear as a whole word in the var name
    # (delimited by _ or start/end of string, since env var names use _ not spaces).
    # PWD is a secret only as a suffix (MYSQL_PWD): a bare PWD is the working directory.
    _SENSITIVE_RE = re.compile(
        '|'.join(
            [r'(?:^|_)' + p + r'S?(?:_|$)' for p in SENSITIVE_PATTERNS]
            + [r'_PWD(?:_|$)']
        )
    )

    # A secret in the value, whatever the name: scheme://user:password@host (scheme may carry a
    # sub-scheme, jdbc:mysql://), optionally quoted or space-prefixed; a password= / pwd= URL
    # parameter; or a Password=/Pwd= key in an ADO/ODBC style connection string.
    _URL_CREDENTIALS_RE = re.compile(r'^[\s"\']*[A-Za-z][A-Za-z0-9+.:-]*://[^/\s:@]*:[^/\s@]+@')
    _CREDENTIAL_PARAM_RE = re.compile(r'(?:^|[?&;\s])(?:password|passwd|pwd)\s*=\s*[^&;\s]', re.IGNORECASE)

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

    def __init__(self, resource: str = '', query: Optional[str] = None, *,
                 params: Optional[Dict[str, Any]] = None):
        """Initialize the environment adapter.

        Args:
            resource: The variable env://NAME (``reveal env NAME``) names, or '' for the listing.
            query: The URI query, bound through the declaration: env takes no control, so any key is an invalid request
            params: Already-bound or typed controls, in place of *query*
        """
        if params is not None:
            self.query_params = params if isinstance(params, QueryParams) else bind_declared_params(
                PARAM_SPECS, params, transport='typed')
        else:
            self.query_params = bind_declared_params(PARAM_SPECS, query or '', transport='uri')
        self.resource = resource
        self.variables = dict(os.environ)

    def get_structure(self) -> Dict[str, Any]:
        """Every environment variable grouped by category, or the one variable the resource names; sensitive values
        are redacted.

        Returns:
            Dict containing categorized environment variables, or the variable the resource names
        """
        if self.resource:
            return self._variable_answer(self.resource)
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
                'value': self._redacted(name, value),
                'sensitive': self._is_sensitive(name, value),
                'length': len(value)
            }
            categorized[category].append(var_info)

        # Remove empty categories
        categorized = {k: v for k, v in categorized.items() if v}

        return ResultBuilder.create(
            result_type='environment',
            source='system',
            source_type='runtime',
            contract_version=CONTRACT_VERSION,
            data={
                'total_count': len(self.variables),
                'categories': categorized,
            }
        )

    def _variable_answer(self, name: str) -> Dict[str, Any]:
        """The answer env://NAME (``reveal env NAME``) gives on every transport: the one variable. A name that is not set
        is an invalid request (rule 9, BACK-2626)."""
        variable = self.get_element(name)
        if variable is None:
            raise RequestValidationError(f"Element '{name}' not found")
        return dict(ResultBuilder.create(result_type=self.ELEMENT_RESULT_TYPE, source=f'env://{name}',
                                         source_type='runtime', contract_version=CONTRACT_VERSION, data=variable))

    def get_element(self, element_name: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        """Get details about a specific environment variable; a sensitive value is redacted.

        Args:
            element_name: Name of the environment variable

        Returns:
            Dict with variable details, or None if not found
        """
        if element_name not in self.variables:
            return None

        value = self.variables[element_name]
        return {
            'name': element_name,
            'value': self._redacted(element_name, value),
            'category': self._categorize(element_name),
            'sensitive': self._is_sensitive(element_name, value),
            'length': len(value),
            'raw_value': None,  # always null: no output discloses a value (ENV_ADAPTER_GUIDE, BACK-2752)
        }

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about the environment.

        Returns:
            Dict with environment metadata
        """
        sensitive_count = sum(1 for name, val in self.variables.items() if self._is_sensitive(name, val))

        return {
            'type': 'environment',
            'total_variables': len(self.variables),
            'sensitive_variables': sensitive_count,
            'categories': self._get_category_counts()
        }

    def _is_sensitive(self, name: str, value: Optional[str] = None) -> bool:
        """Check if a variable holds sensitive data, by name or by value.

        Args:
            name: Variable name to check
            value: Variable value; a URL with embedded user:password counts

        Returns:
            True if the name matches sensitive patterns or the value embeds credentials
        """
        if self._SENSITIVE_RE.search(name.upper()):
            return True
        return bool(value and (self._URL_CREDENTIALS_RE.match(value)
                               or self._CREDENTIAL_PARAM_RE.search(value)))

    def _redacted(self, name: str, value: str) -> str:
        """The value as every output shows it: ``***`` for a sensitive variable, else the value.

        Args:
            name: Variable name
            value: Variable value

        Returns:
            Original value or redacted string
        """
        if self._is_sensitive(name, value):
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
        counts: Dict[str, int] = {}
        for name in self.variables:
            category = self._categorize(name)
            counts[category] = counts.get(category, 0) + 1
        return counts
