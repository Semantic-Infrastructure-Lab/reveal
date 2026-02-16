"""Help adapter (help://) - Meta-adapter for exploring reveal's capabilities."""

import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from .base import ResourceAdapter, register_adapter, register_renderer, _ADAPTER_REGISTRY


class HelpRenderer:
    """Renderer for help system results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render help topic list.

        Args:
            result: Structure dict from HelpAdapter.get_structure()
            format: Output format ('text', 'json', 'grep')
        """
        from ..rendering import render_help
        render_help(result, format, list_mode=True)

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render specific help topic.

        Args:
            result: Element dict from HelpAdapter.get_element()
            format: Output format ('text', 'json', 'grep')
        """
        from ..rendering import render_help
        render_help(result, format)

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render user-friendly errors."""
        print(f"Error accessing help: {error}", file=sys.stderr)


@register_adapter('help')
@register_renderer(HelpRenderer)
class HelpAdapter(ResourceAdapter):
    """Adapter for exploring reveal's help system via help:// URIs.

    Examples:
        help://                    # List all help topics
        help://ast                 # Get ast:// adapter help
        help://ast/workflows       # Just the workflows section
        help://ast/try-now         # Just the try-now examples
        help://ast/anti-patterns   # Just the anti-patterns
        help://env                 # Get env:// adapter help
        help://python-guide        # Python adapter comprehensive guide
        help://markdown            # Markdown features guide
        help://tricks              # Cool tricks and hidden features
        help://adapters            # List all adapters with help
        help://agent               # Agent usage guide (AGENT_HELP.md)
        help://agent-full          # Full agent guide (AGENT_HELP_FULL.md)

    Agent Introspection (v0.46.0+):
        help://schemas/ssl         # Machine-readable schema for ssl:// adapter
        help://schemas/ast         # Machine-readable schema for ast:// adapter
        help://examples/security   # Query recipes for security analysis
        help://examples/codebase   # Query recipes for codebase exploration
    """

    # Valid section names for help://adapter/section queries
    VALID_SECTIONS = {'workflows', 'try-now', 'anti-patterns'}

    # Static help files (markdown documentation in reveal/docs/)
    STATIC_HELP = {
        'quick-start': 'QUICK_START.md',  # 5-minute quick start guide
        'agent': 'AGENT_HELP.md',
        'agent-full': 'AGENT_HELP.md',  # Alias (full version merged into AGENT_HELP.md)
        'python': 'PYTHON_ADAPTER_GUIDE.md',  # Alias for python-guide
        'python-guide': 'PYTHON_ADAPTER_GUIDE.md',
        'reveal-guide': 'REVEAL_ADAPTER_GUIDE.md',  # Reference implementation
        'markdown': 'MARKDOWN_GUIDE.md',
        'html': 'HTML_GUIDE.md',  # HTML features guide
        'anti-patterns': 'AGENT_HELP.md',  # Merged into AGENT_HELP.md
        'adapter-authoring': 'ADAPTER_AUTHORING_GUIDE.md',
        'tricks': 'RECIPES.md',  # Merged into RECIPES.md (task-based workflows)
        'recipes': 'RECIPES.md',  # Primary name for workflow recipes
        'help': 'HELP_SYSTEM_GUIDE.md',  # Meta-documentation about help system
        'configuration': 'CONFIGURATION_GUIDE.md',  # Configuration system guide
        'config': 'CONFIGURATION_GUIDE.md',  # Alias for configuration
        'codebase-review': 'CODEBASE_REVIEW.md',  # Codebase review workflows
        'output': 'OUTPUT_CONTRACT.md',  # Output format contract
        'schemas': 'SCHEMA_VALIDATION_HELP.md',  # Schema validation guide (v0.29.0+)
        'duplicates': 'DUPLICATE_DETECTION_GUIDE.md',  # Duplicate code detection guide
        'duplicate-detection': 'DUPLICATE_DETECTION_GUIDE.md',  # Alias for duplicates
        'scaffolding': 'SCAFFOLDING_GUIDE.md'  # Component scaffolding system
    }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help about the help system (meta!)."""
        return {
            'name': 'help',
            'description': (
                'Explore reveal help system - '
                'discover adapters, read guides'
            ),
            'syntax': 'help://[topic]',
            'examples': [
                {
                    'uri': 'help://',
                    'description': 'List all available help topics'
                },
                {
                    'uri': 'help://ast',
                    'description': 'Learn about ast:// adapter (query code as database)'
                },
                {
                    'uri': 'help://env',
                    'description': 'Learn about env:// adapter (environment variables)'
                },
                {
                    'uri': 'help://adapters',
                    'description': 'List all URI adapters with descriptions'
                },
                {
                    'uri': 'help://python-guide',
                    'description': (
                        'Python adapter comprehensive guide '
                        '(multi-shot examples, LLM integration)'
                    )
                },
                {
                    'uri': 'help://agent',
                    'description': 'Agent usage patterns (brief guide)'
                },
                {
                    'uri': 'help://agent-full',
                    'description': 'Comprehensive agent guide (all patterns, examples)'
                },
                {
                    'uri': 'help://tricks',
                    'description': 'Cool tricks and hidden features guide'
                }
            ],
            'notes': [
                'Each adapter exposes its own help via get_help() method',
                'Static guides (agent, agent-full) load from markdown files',
                (
                    'New adapters automatically appear in help:// '
                    'when they implement get_help()'
                ),
                (
                    'Alternative: Use --agent-help and --agent-help-full '
                    'flags for llms.txt convention'
                )
            ],
            'see_also': [
                'reveal --agent-help - Brief agent guide (llms.txt)',
                'reveal --agent-help-full - Full agent guide',
                'reveal --list-supported - Supported file types'
            ]
        }

    def __init__(self, topic: Optional[str] = None):
        """Initialize help adapter.

        Args:
            topic: Specific help topic to display (None = list all)
        """
        self.topic = topic
        # Merge auto-discovered guides with manual STATIC_HELP entries
        # STATIC_HELP takes precedence (allows aliases and special mappings)
        self.help_topics = self._discover_and_merge_guides()

    def _discover_and_merge_guides(self) -> Dict[str, str]:
        """Auto-discover guide files and merge with STATIC_HELP.

        Automatically discovers *_GUIDE.md files in reveal/docs/ and makes them
        accessible via help:// URIs. Manual STATIC_HELP entries take precedence,
        allowing for aliases and custom topic names.

        Returns:
            Dict mapping topic names to guide filenames
        """
        discovered = {}

        # Find reveal/docs directory
        docs_dir = Path(__file__).parent.parent / 'docs'

        if docs_dir.exists():
            # Auto-discover *_GUIDE.md files (e.g., AST_ADAPTER_GUIDE.md)
            for guide in docs_dir.glob('*_GUIDE.md'):
                # Convert filename to topic name
                # AST_ADAPTER_GUIDE.md -> ast-adapter
                # QUERY_SYNTAX_GUIDE.md -> query-syntax
                topic = guide.stem.lower().replace('_guide', '').replace('_', '-')
                discovered[topic] = guide.name

            # Also check for *GUIDE.md pattern (without underscore before GUIDE)
            for guide in docs_dir.glob('*GUIDE.md'):
                # Skip if already discovered via *_GUIDE.md pattern
                if guide.name not in discovered.values():
                    # Convert filename to topic name
                    # HTMLGUIDE.md -> html (unlikely but handle it)
                    topic = guide.stem.lower().replace('guide', '').replace('_', '-').strip('-')
                    if topic:  # Only add non-empty topics
                        discovered[topic] = guide.name

        # Merge: discovered guides + STATIC_HELP (STATIC_HELP takes precedence)
        # This allows STATIC_HELP to:
        #   - Define aliases (e.g., 'tricks' -> 'RECIPES.md')
        #   - Override auto-discovered names (e.g., 'python' -> 'PYTHON_ADAPTER_GUIDE.md')
        #   - Reference non-guide files (e.g., 'agent' -> 'AGENT_HELP.md')
        return {**discovered, **self.STATIC_HELP}

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get help structure (list of available topics)."""
        return {
            'type': 'help',
            'available_topics': self._list_topics(),
            'adapters': self._list_adapters(),
            'static_guides': list(self.help_topics.keys())
        }

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get help for a specific topic.

        Args:
            element_name: Topic name (adapter scheme, 'adapters', 'agent', etc.)
                   Can also be 'adapter/section' for section extraction
                   Or 'schemas/adapter' for machine-readable schemas
                   Or 'examples/task' for canonical query recipes

        Returns:
            Help content dict or None if not found
        """
        topic = element_name  # Alias for readability
        # Check for schemas route: help://schemas/ssl
        if topic.startswith('schemas/'):
            adapter_name = topic.split('/', 1)[1]
            return self._get_adapter_schema(adapter_name)

        # Check for examples route: help://examples/security
        if topic.startswith('examples/'):
            task_name = topic.split('/', 1)[1]
            return self._get_example_recipes(task_name)

        # Check for section extraction: help://ast/workflows
        if '/' in topic:
            adapter_name, section = topic.split('/', 1)
            return self._get_adapter_section(adapter_name, section)

        # Check if it's a static guide (includes auto-discovered + manual)
        if topic in self.help_topics:
            return self._load_static_help(topic)

        # Check if it's 'adapters' (list all)
        if topic == 'adapters':
            return self._get_all_adapter_help()

        # Check if it's an adapter scheme
        if topic in _ADAPTER_REGISTRY:
            return self._get_adapter_help(topic)

        return None

    def _validate_section_name(
        self, adapter_name: str, section: str
    ) -> Optional[Dict[str, Any]]:
        """Validate section name is valid.

        Returns:
            Error dict if invalid, None if valid
        """
        if section not in self.VALID_SECTIONS:
            valid_sections = ', '.join(sorted(self.VALID_SECTIONS))
            return {
                'type': 'help_section',
                'adapter': adapter_name,
                'section': section,
                'error': 'Invalid section',
                'message': (
                    f"Unknown section '{section}'. "
                    f"Valid sections: {valid_sections}"
                )
            }
        return None

    def _validate_adapter_exists(
        self, adapter_name: str, section: str
    ) -> Optional[Dict[str, Any]]:
        """Validate adapter exists in registry.

        Returns:
            Error dict if not found, None if exists
        """
        if adapter_name not in _ADAPTER_REGISTRY:
            return {
                'type': 'help_section',
                'adapter': adapter_name,
                'section': section,
                'error': 'Unknown adapter',
                'message': f"No adapter named '{adapter_name}'"
            }
        return None

    def _extract_section_content(
        self, adapter_name: str, section: str, help_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Extract specific section from adapter help.

        Returns:
            Section content dict or error dict
        """
        # Map section names to help dict keys
        section_key_map = {
            'workflows': 'workflows',
            'try-now': 'try_now',
            'anti-patterns': 'anti_patterns',
        }

        key = section_key_map.get(section)
        content = help_data.get(key) if key else None

        if not content:
            return {
                'type': 'help_section',
                'adapter': adapter_name,
                'section': section,
                'error': 'Section not found',
                'message': (
                    f"Adapter '{adapter_name}' does not have "
                    f"a '{section}' section"
                )
            }

        return {
            'type': 'help_section',
            'adapter': adapter_name,
            'section': section,
            'content': content
        }

    def _get_adapter_section(
        self, adapter_name: str, section: str
    ) -> Optional[Dict[str, Any]]:
        """Get a specific section from an adapter's help.

        Args:
            adapter_name: Adapter scheme name (e.g., 'ast')
            section: Section name (e.g., 'workflows', 'try-now')

        Returns:
            Dict with section content or error
        """
        # Validate section name
        error = self._validate_section_name(adapter_name, section)
        if error:
            return error

        # Validate adapter exists
        error = self._validate_adapter_exists(adapter_name, section)
        if error:
            return error

        # Get full adapter help
        help_data = self._get_adapter_help(adapter_name)
        if not help_data or 'error' in help_data:
            return help_data

        # Extract and return section content
        return self._extract_section_content(adapter_name, section, help_data)

    def _list_topics(self) -> List[str]:
        """List all available help topics."""
        topics: List[str] = []

        # Add adapter schemes
        topics.extend(_ADAPTER_REGISTRY.keys())

        # Add meta topics
        topics.append('adapters')

        # Add static guides (auto-discovered + manual)
        topics.extend(self.help_topics.keys())

        return sorted(topics)

    def _get_adapter_description(self, adapter_class: type[Any]) -> str:
        """Get description from adapter's help method.

        Args:
            adapter_class: Adapter class

        Returns:
            Description string or empty string if unavailable
        """
        try:
            help_data = adapter_class.get_help()
            if help_data:
                return str(help_data.get('description', ''))
        except Exception:
            # If get_help() fails, return empty
            pass
        return ''

    def _list_adapters(self) -> List[Dict[str, Any]]:
        """List all registered adapters with basic info."""
        adapters = []
        for scheme, adapter_class in _ADAPTER_REGISTRY.items():
            has_help = (
                hasattr(adapter_class, 'get_help') and
                callable(getattr(adapter_class, 'get_help'))
            )

            info = {
                'scheme': scheme,
                'class': adapter_class.__name__,
                'has_help': has_help
            }

            # Add description if available
            if has_help:
                info['description'] = self._get_adapter_description(adapter_class)

            adapters.append(info)

        return sorted(adapters, key=lambda x: x['scheme'])

    def _get_adapter_help(self, scheme: str) -> Optional[Dict[str, Any]]:
        """Get help for a specific adapter.

        Args:
            scheme: Adapter scheme name

        Returns:
            Help dict or None if adapter has no help
        """
        adapter_class: Optional[type[Any]] = _ADAPTER_REGISTRY.get(scheme)
        if not adapter_class:
            return None

        if not hasattr(adapter_class, 'get_help'):
            return {
                'scheme': scheme,
                'error': 'No help available',
                'message': (
                    f'{adapter_class.__name__} does not provide '
                    f'help documentation'
                )
            }

        try:
            help_data = adapter_class.get_help()
            if help_data:
                help_data['scheme'] = scheme  # Ensure scheme is included
            return help_data  # type: ignore[no-any-return]
        except Exception as e:
            return {
                'scheme': scheme,
                'error': 'Help generation failed',
                'message': str(e)
            }

    def _get_all_adapter_help(self) -> Dict[str, Any]:
        """Get help for all adapters."""
        all_help: Dict[str, Any] = {
            'type': 'adapter_summary',
            'count': len(_ADAPTER_REGISTRY),
            'adapters': {}
        }

        for scheme in _ADAPTER_REGISTRY.keys():
            help_data = self._get_adapter_help(scheme)
            if help_data and 'error' not in help_data:
                example = ''
                if help_data.get('examples'):
                    example = help_data.get('examples', [{}])[0].get('uri', '')

                all_help['adapters'][scheme] = {
                    'description': help_data.get('description', ''),
                    'syntax': help_data.get('syntax', ''),
                    'example': example
                }

        return all_help

    def _load_static_help(self, topic: str) -> Optional[Dict[str, Any]]:
        """Load help from static markdown file.

        Args:
            topic: Topic name ('agent', 'agent-full', 'ast-adapter', etc.)

        Returns:
            Help content dict or None if file not found
        """
        filename = self.help_topics.get(topic)
        if not filename:
            return None

        # Help files are in reveal/docs/ directory
        help_path = Path(__file__).parent.parent / 'docs' / filename

        try:
            with open(help_path, 'r', encoding='utf-8') as f:
                content = f.read()

            return {
                'type': 'static_guide',
                'topic': topic,
                'file': filename,
                'content': content
            }
        except FileNotFoundError:
            return {
                'type': 'static_guide',
                'topic': topic,
                'error': 'File not found',
                'message': f'Could not find {filename}'
            }
        except Exception as e:
            return {
                'type': 'static_guide',
                'topic': topic,
                'error': 'Load failed',
                'message': str(e)
            }

    def _get_adapter_schema(self, adapter_name: str) -> Optional[Dict[str, Any]]:
        """Get machine-readable schema for an adapter.

        Args:
            adapter_name: Adapter scheme name (e.g., 'ssl', 'ast')

        Returns:
            Schema dict or error dict if adapter not found or has no schema
        """
        adapter_class: Optional[type[Any]] = _ADAPTER_REGISTRY.get(adapter_name)
        if not adapter_class:
            return {
                'type': 'adapter_schema',
                'adapter': adapter_name,
                'error': 'Unknown adapter',
                'message': f"No adapter named '{adapter_name}'"
            }

        if not hasattr(adapter_class, 'get_schema'):
            return {
                'type': 'adapter_schema',
                'adapter': adapter_name,
                'error': 'No schema available',
                'message': (
                    f'{adapter_class.__name__} does not provide '
                    f'machine-readable schema'
                )
            }

        try:
            schema_data = adapter_class.get_schema()
            if schema_data:
                schema_data['adapter'] = adapter_name  # Ensure adapter is included
                schema_data['type'] = 'adapter_schema'
            return schema_data  # type: ignore[no-any-return]
        except Exception as e:
            return {
                'type': 'adapter_schema',
                'adapter': adapter_name,
                'error': 'Schema generation failed',
                'message': str(e)
            }

    def _get_example_recipes(self, task_name: str) -> Optional[Dict[str, Any]]:
        """Get canonical query recipes for a specific task.

        Args:
            task_name: Task category (e.g., 'security', 'codebase', 'debugging')

        Returns:
            Recipe dict with example queries or error if task not found
        """
        # Define canonical query recipes for common agent tasks
        recipes = {
            'security': {
                'type': 'query_recipes',
                'task': 'security',
                'description': 'Security analysis and vulnerability detection',
                'recipes': [
                    {
                        'goal': 'Find authentication functions',
                        'query': 'ast://src?name~=auth&kind=function',
                        'description': 'Locate authentication-related code',
                        'output_type': 'ast_query_results'
                    },
                    {
                        'goal': 'Check SSL certificate expiry',
                        'query': 'ssl://example.com --expiring-within=30',
                        'description': 'Find certificates expiring soon',
                        'output_type': 'ssl_certificate'
                    },
                    {
                        'goal': 'Find SQL query construction',
                        'query': 'ast://src?name~=query&complexity>5',
                        'description': 'Locate complex database queries (SQL injection risk)',
                        'output_type': 'ast_query_results'
                    }
                ]
            },
            'codebase': {
                'type': 'query_recipes',
                'task': 'codebase',
                'description': 'Codebase exploration and understanding',
                'recipes': [
                    {
                        'goal': 'Get project overview',
                        'query': 'reveal src/',
                        'description': 'Progressive disclosure: structure first',
                        'output_type': 'reveal_structure'
                    },
                    {
                        'goal': 'Find entry points',
                        'query': 'ast://src?name=main&kind=function',
                        'description': 'Locate main() functions',
                        'output_type': 'ast_query_results'
                    },
                    {
                        'goal': 'List public API',
                        'query': 'ast://src?visibility=public&kind=function',
                        'description': 'Find all public functions',
                        'output_type': 'ast_query_results'
                    },
                    {
                        'goal': 'Find complex code',
                        'query': 'ast://src?complexity>15',
                        'description': 'Locate high-complexity functions',
                        'output_type': 'ast_query_results'
                    }
                ]
            },
            'debugging': {
                'type': 'query_recipes',
                'task': 'debugging',
                'description': 'Debugging and error investigation',
                'recipes': [
                    {
                        'goal': 'Find error handlers',
                        'query': 'ast://src?name~=error&kind=function',
                        'description': 'Locate error handling code',
                        'output_type': 'ast_query_results'
                    },
                    {
                        'goal': 'Check recent changes',
                        'query': 'git://src?since=7days',
                        'description': 'Review changes in last week',
                        'output_type': 'git_log'
                    },
                    {
                        'goal': 'Find large functions',
                        'query': 'ast://src?lines>100&kind=function',
                        'description': 'Locate potentially problematic large functions',
                        'output_type': 'ast_query_results'
                    }
                ]
            },
            'quality': {
                'type': 'query_recipes',
                'task': 'quality',
                'description': 'Code quality and hotspot analysis',
                'recipes': [
                    {
                        'goal': 'Find quality hotspots',
                        'query': 'stats://src --only-failures',
                        'description': 'Show only files with quality issues',
                        'output_type': 'stats_results'
                    },
                    {
                        'goal': 'Check code complexity',
                        'query': 'ast://src?complexity>10',
                        'description': 'High complexity functions',
                        'output_type': 'ast_query_results'
                    },
                    {
                        'goal': 'Find undocumented code',
                        'query': 'ast://src?has_docstring=false&kind=function',
                        'description': 'Functions missing documentation',
                        'output_type': 'ast_query_results'
                    }
                ]
            }
        }

        if task_name not in recipes:
            available = ', '.join(sorted(recipes.keys()))
            return {
                'type': 'query_recipes',
                'task': task_name,
                'error': 'Unknown task',
                'message': f"Unknown task '{task_name}'. Available: {available}",
                'available_tasks': list(recipes.keys())
            }

        return recipes[task_name]
