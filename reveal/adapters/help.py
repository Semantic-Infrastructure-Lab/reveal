"""Help adapter (help://) - Meta-adapter for exploring reveal's capabilities."""

from pathlib import Path
from typing import Dict, List, Any, Optional
from .base import ResourceAdapter, register_adapter, _ADAPTER_REGISTRY


@register_adapter('help')
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
    """

    # Valid section names for help://adapter/section queries
    VALID_SECTIONS = {'workflows', 'try-now', 'anti-patterns'}

    # Static help files (markdown documentation)
    STATIC_HELP = {
        'agent': 'AGENT_HELP.md',
        'agent-full': 'AGENT_HELP_FULL.md',
        'python': 'adapters/PYTHON_ADAPTER_GUIDE.md',  # Alias for python-guide
        'python-guide': 'adapters/PYTHON_ADAPTER_GUIDE.md',
        'reveal-guide': 'REVEAL_ADAPTER_GUIDE.md',  # Reference implementation
        'markdown': 'MARKDOWN_GUIDE.md',
        'anti-patterns': 'ANTI_PATTERNS.md',
        'adapter-authoring': 'adapters/ADAPTER_AUTHORING_GUIDE.md',
        'tricks': 'COOL_TRICKS.md'
    }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help about the help system (meta!)."""
        return {
            'name': 'help',
            'description': 'Explore reveal help system - discover adapters, read guides',
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
                    'description': 'Python adapter comprehensive guide (multi-shot examples, LLM integration)'
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
                'New adapters automatically appear in help:// when they implement get_help()',
                'Alternative: Use --agent-help and --agent-help-full flags for llms.txt convention'
            ],
            'see_also': [
                'reveal --agent-help - Brief agent guide (llms.txt)',
                'reveal --agent-help-full - Full agent guide',
                'reveal --list-supported - Supported file types'
            ]
        }

    def __init__(self, topic: str = None):
        """Initialize help adapter.

        Args:
            topic: Specific help topic to display (None = list all)
        """
        self.topic = topic

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get help structure (list of available topics)."""
        return {
            'type': 'help',
            'available_topics': self._list_topics(),
            'adapters': self._list_adapters(),
            'static_guides': list(self.STATIC_HELP.keys())
        }

    def get_element(self, topic: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get help for a specific topic.

        Args:
            topic: Topic name (adapter scheme, 'adapters', 'agent', etc.)
                   Can also be 'adapter/section' for section extraction

        Returns:
            Help content dict or None if not found
        """
        # Check for section extraction: help://ast/workflows
        if '/' in topic:
            adapter_name, section = topic.split('/', 1)
            return self._get_adapter_section(adapter_name, section)

        # Check if it's a static guide
        if topic in self.STATIC_HELP:
            return self._load_static_help(topic)

        # Check if it's 'adapters' (list all)
        if topic == 'adapters':
            return self._get_all_adapter_help()

        # Check if it's an adapter scheme
        if topic in _ADAPTER_REGISTRY:
            return self._get_adapter_help(topic)

        return None

    def _get_adapter_section(self, adapter_name: str, section: str) -> Optional[Dict[str, Any]]:
        """Get a specific section from an adapter's help.

        Args:
            adapter_name: Adapter scheme name (e.g., 'ast')
            section: Section name (e.g., 'workflows', 'try-now', 'anti-patterns')

        Returns:
            Dict with section content or error
        """
        # Validate section name
        if section not in self.VALID_SECTIONS:
            return {
                'type': 'help_section',
                'adapter': adapter_name,
                'section': section,
                'error': 'Invalid section',
                'message': f"Unknown section '{section}'. Valid sections: {', '.join(sorted(self.VALID_SECTIONS))}"
            }

        # Get full adapter help
        if adapter_name not in _ADAPTER_REGISTRY:
            return {
                'type': 'help_section',
                'adapter': adapter_name,
                'section': section,
                'error': 'Unknown adapter',
                'message': f"No adapter named '{adapter_name}'"
            }

        help_data = self._get_adapter_help(adapter_name)
        if not help_data or 'error' in help_data:
            return help_data

        # Map section names to help dict keys
        section_key_map = {
            'workflows': 'workflows',
            'try-now': 'try_now',
            'anti-patterns': 'anti_patterns',
        }

        key = section_key_map.get(section)
        content = help_data.get(key)

        if not content:
            return {
                'type': 'help_section',
                'adapter': adapter_name,
                'section': section,
                'error': 'Section not found',
                'message': f"Adapter '{adapter_name}' does not have a '{section}' section"
            }

        return {
            'type': 'help_section',
            'adapter': adapter_name,
            'section': section,
            'content': content
        }

    def _list_topics(self) -> List[str]:
        """List all available help topics."""
        topics = []

        # Add adapter schemes
        topics.extend(_ADAPTER_REGISTRY.keys())

        # Add meta topics
        topics.append('adapters')

        # Add static guides
        topics.extend(self.STATIC_HELP.keys())

        return sorted(topics)

    def _list_adapters(self) -> List[Dict[str, Any]]:
        """List all registered adapters with basic info."""
        adapters = []
        for scheme, adapter_class in _ADAPTER_REGISTRY.items():
            info = {
                'scheme': scheme,
                'class': adapter_class.__name__,
                'has_help': hasattr(adapter_class, 'get_help') and
                           callable(getattr(adapter_class, 'get_help'))
            }

            # Try to get description from help
            if info['has_help']:
                try:
                    help_data = adapter_class.get_help()
                    if help_data:
                        info['description'] = help_data.get('description', '')
                except Exception:
                    # If get_help() fails, skip description
                    pass

            adapters.append(info)

        return sorted(adapters, key=lambda x: x['scheme'])

    def _get_adapter_help(self, scheme: str) -> Optional[Dict[str, Any]]:
        """Get help for a specific adapter.

        Args:
            scheme: Adapter scheme name

        Returns:
            Help dict or None if adapter has no help
        """
        adapter_class = _ADAPTER_REGISTRY.get(scheme)
        if not adapter_class:
            return None

        if not hasattr(adapter_class, 'get_help'):
            return {
                'scheme': scheme,
                'error': 'No help available',
                'message': f'{adapter_class.__name__} does not provide help documentation'
            }

        try:
            help_data = adapter_class.get_help()
            if help_data:
                help_data['scheme'] = scheme  # Ensure scheme is included
            return help_data
        except Exception as e:
            return {
                'scheme': scheme,
                'error': 'Help generation failed',
                'message': str(e)
            }

    def _get_all_adapter_help(self) -> Dict[str, Any]:
        """Get help for all adapters."""
        all_help = {
            'type': 'adapter_summary',
            'count': len(_ADAPTER_REGISTRY),
            'adapters': {}
        }

        for scheme in _ADAPTER_REGISTRY.keys():
            help_data = self._get_adapter_help(scheme)
            if help_data and 'error' not in help_data:
                all_help['adapters'][scheme] = {
                    'description': help_data.get('description', ''),
                    'syntax': help_data.get('syntax', ''),
                    'example': help_data.get('examples', [{}])[0].get('uri', '') if help_data.get('examples') else ''
                }

        return all_help

    def _load_static_help(self, topic: str) -> Optional[Dict[str, Any]]:
        """Load help from static markdown file.

        Args:
            topic: Topic name ('agent', 'agent-full')

        Returns:
            Help content dict or None if file not found
        """
        filename = self.STATIC_HELP.get(topic)
        if not filename:
            return None

        # Help files are in reveal/ directory (same as this file's parent)
        help_path = Path(__file__).parent.parent / filename

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
