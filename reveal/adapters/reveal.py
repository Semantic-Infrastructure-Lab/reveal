"""Reveal meta-adapter (reveal://) - Self-inspection and validation."""

import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from .base import ResourceAdapter, register_adapter, register_renderer, _ADAPTER_REGISTRY
from ..rules.validation.utils import find_reveal_root


class RevealRenderer:
    """Renderer for reveal self-inspection results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render reveal structure overview.

        Args:
            result: Structure dict from RevealAdapter.get_structure()
            format: Output format ('text', 'json', 'grep')
        """
        from ..rendering import render_reveal_structure
        render_reveal_structure(result, format)

    @staticmethod
    def render_check(result: dict, format: str = 'text', **kwargs) -> None:
        """Render validation check results.

        Args:
            result: Check result dict with detections
            format: Output format ('text', 'json', 'grep')
            **kwargs: Ignored (for compatibility with other adapters' filter flags)
        """
        from ..main import safe_json_dumps

        detections = result.get('detections', [])
        uri = result.get('file', 'reveal://')

        if format == 'json':
            # Serialize Detection objects to dicts for JSON output
            serialized_result = {
                **result,
                'detections': [d.to_dict() if hasattr(d, 'to_dict') else d for d in detections]
            }
            print(safe_json_dumps(serialized_result))
            return

        if format == 'grep':
            for d in detections:
                print(f"{d.file_path}:{d.line}:{d.column}:{d.rule_code}:{d.message}")
            return

        # Text format
        if not detections:
            print(f"{uri}: ✅ No issues found")
            return

        print(f"{uri}: Found {len(detections)} issues\n")
        for d in sorted(detections, key=lambda x: (x.line, x.column)):
            print(d)
            print()

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render user-friendly errors."""
        print(f"Error inspecting reveal: {error}", file=sys.stderr)


@register_adapter('reveal')
@register_renderer(RevealRenderer)
class RevealAdapter(ResourceAdapter):
    """Adapter for inspecting reveal's own codebase and configuration.

    Examples:
        reveal reveal://                     # Show reveal's structure
        reveal reveal://analyzers            # List all analyzers
        reveal reveal://rules                # List all rules
        reveal reveal:// --check             # Run validation rules
        reveal reveal:// --check --select V  # Only validation rules
        reveal help://reveal                 # Learn about reveal://
    """

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for reveal:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return {
            'adapter': 'reveal',
            'description': 'Self-inspection of reveal\'s own codebase and configuration with validation rules',
            'uri_syntax': 'reveal://[path][/element]',
            'query_params': {},  # No query parameters
            'elements': {
                'config': 'Active configuration with sources and precedence',
                'analyzers': 'List all registered analyzers',
                'rules': 'List all available validation rules',
                'adapters': 'List all registered adapters'
            },
            'cli_flags': [
                '--check',  # Run validation rules
                '--select=<rules>',  # Select specific rules (e.g., V001,V002)
                '--only-failures'  # Show only failed checks
            ],
            'supports_batch': False,
            'supports_advanced': False,
            'validation_rules': {
                'V001': 'Help documentation completeness',
                'V002': 'Analyzer registration validation',
                'V003': 'Feature matrix coverage',
                'V004': 'Test coverage gaps',
                'V005': 'Static help file sync',
                'V006': 'Output format support',
                'V016': 'Output Contract compliance'
            },
            'output_types': [
                {
                    'type': 'reveal_structure',
                    'description': 'Overview of reveal\'s internal structure',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'reveal_structure'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string'},
                            'adapters': {'type': 'array'},
                            'analyzers': {'type': 'array'},
                            'rules': {'type': 'array'}
                        }
                    }
                },
                {
                    'type': 'reveal_check',
                    'description': 'Validation check results',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'reveal_check'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string'},
                            'detections': {'type': 'array'},
                            'passed': {'type': 'integer'},
                            'failed': {'type': 'integer'},
                            'total': {'type': 'integer'}
                        }
                    }
                }
            ],
            'example_queries': [
                {
                    'uri': 'reveal://',
                    'description': 'Show reveal\'s internal structure (analyzers, rules, adapters)',
                    'output_type': 'reveal_structure'
                },
                {
                    'uri': 'reveal://config',
                    'description': 'Show active configuration with full transparency',
                    'element': 'config',
                    'output_type': 'reveal_structure'
                },
                {
                    'uri': 'reveal://analyzers',
                    'description': 'List all registered analyzers',
                    'element': 'analyzers',
                    'output_type': 'reveal_structure'
                },
                {
                    'uri': 'reveal://rules',
                    'description': 'List all available validation rules',
                    'element': 'rules',
                    'output_type': 'reveal_structure'
                },
                {
                    'uri': 'reveal:// --check',
                    'description': 'Run all validation rules (V-series)',
                    'cli_flag': '--check',
                    'output_type': 'reveal_check'
                },
                {
                    'uri': 'reveal:// --check --select V001,V002',
                    'description': 'Run specific validation rules',
                    'cli_flag': '--check --select',
                    'output_type': 'reveal_check'
                },
                {
                    'uri': 'reveal://adapters/reveal.py get_element',
                    'description': 'Extract specific function from reveal\'s source',
                    'output_type': 'code_element'
                }
            ]
        }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for reveal:// adapter."""
        return {
            'name': 'reveal',
            'description': 'Inspect reveal\'s own codebase - validate configuration, check completeness',
            'syntax': 'reveal://[path] [element]',
            'examples': [
                {
                    'uri': 'reveal reveal://',
                    'description': 'Show reveal\'s internal structure (analyzers, rules, adapters)'
                },
                {
                    'uri': 'reveal reveal://config',
                    'description': 'Show active configuration with full transparency (sources, precedence)'
                },
                {
                    'uri': 'reveal reveal://analyzers',
                    'description': 'List all registered analyzers'
                },
                {
                    'uri': 'reveal reveal://rules',
                    'description': 'List all available validation rules'
                },
                {
                    'uri': 'reveal reveal://adapters/reveal.py get_element',
                    'description': 'Extract specific function from reveal\'s source (element extraction)'
                },
                {
                    'uri': 'reveal reveal://analyzers/markdown.py MarkdownAnalyzer',
                    'description': 'Extract class from reveal\'s source'
                },
                {
                    'uri': 'reveal reveal:// --check',
                    'description': 'Run all validation rules (V-series)'
                },
                {
                    'uri': 'reveal reveal:// --check --select V001,V002',
                    'description': 'Run specific validation rules'
                },
            ],
            'features': [
                'Self-inspection of reveal codebase',
                'Element extraction from reveal source files',
                'Validation rules for completeness checks',
                'Analyzer and rule discovery',
                'Configuration validation',
                'Test coverage analysis'
            ],
            'validation_rules': {
                'V001': 'Help documentation completeness (every file type has help)',
                'V002': 'Analyzer registration validation',
                'V003': 'Feature matrix coverage',
                'V004': 'Test coverage gaps',
                'V005': 'Static help file sync',
                'V006': 'Output format support'
            },
            'try_now': [
                "reveal reveal://",
                "reveal reveal://config",
                "reveal reveal:// --check",
                "reveal reveal://analyzers",
            ],
            'workflows': [
                {
                    'name': 'Validate Reveal Configuration',
                    'scenario': 'Before committing changes, ensure reveal is properly configured',
                    'steps': [
                        "reveal reveal:// --check                # Run all validation rules",
                        "reveal reveal:// --check --select V001  # Check help completeness",
                        "reveal reveal://analyzers               # Review registered analyzers",
                    ],
                },
                {
                    'name': 'Extract Reveal Source Code',
                    'scenario': 'Study reveal\'s implementation by extracting specific functions/classes',
                    'steps': [
                        "reveal reveal://analyzers/markdown.py MarkdownAnalyzer  # Extract class",
                        "reveal reveal://rules/links/L001.py _extract_anchors_from_markdown  # Extract function",
                        "reveal reveal://adapters/reveal.py get_element  # Self-referential extraction",
                    ],
                },
                {
                    'name': 'Check Test Coverage',
                    'scenario': 'Added new analyzer, verify tests exist',
                    'steps': [
                        "reveal reveal:// --check --select V004  # Test coverage validation",
                        "reveal reveal://analyzers               # See all analyzers",
                    ],
                },
            ],
            'anti_patterns': [
                {
                    'bad': "grep -r 'register' reveal/analyzers/",
                    'good': "reveal reveal://analyzers",
                    'why': "Shows registered analyzers with their file patterns and metadata",
                },
            ],
            'notes': [
                'Validation rules (V-series) check reveal\'s own codebase for completeness',
                'These rules prevent issues like missing documentation or forgotten test files',
                'Run reveal:// --check as part of CI to catch configuration issues'
            ],
            'output_formats': ['text', 'json'],
            'see_also': [
                'reveal --rules - List all pattern detection rules',
                'reveal help://ast - Query code as database',
                'reveal help:// - List all help topics'
            ]
        }

    def __init__(self, component: Optional[str] = None):
        """Initialize reveal adapter.

        Args:
            component: Optional component to inspect (analyzers, rules, etc.)
        """
        self.component = component
        self.reveal_root = self._find_reveal_root()

    def _find_reveal_root(self) -> Path:
        """Find reveal's root directory using shared utility.

        Delegates to reveal.rules.validation.utils.find_reveal_root for consistent
        path resolution across all reveal components.

        Returns:
            Path to reveal's root directory (never None - falls back to package location)
        """
        # Use shared utility (dev_only=False to include installed package fallback)
        root = find_reveal_root(dev_only=False)

        # Fallback for edge case where utility returns None
        # (should never happen with dev_only=False, but ensures backwards compatibility)
        if root is None:
            root = Path(__file__).parent.parent

        return root

    def get_structure(self, **kwargs: Any) -> Dict[str, Any]:
        """Get reveal's internal structure.

        Returns:
            Dict containing analyzers, adapters, rules, etc.
            Filtered by self.component if specified.
        """
        # Filter by component if specified
        if self.component:
            component = self.component.lower()

            if component == 'analyzers':
                analyzers = self._get_analyzers()
                return {
                    'contract_version': '1.0',
                    'type': 'reveal_structure',
                    'source': str(self.reveal_root),
                    'source_type': 'directory',
                    'analyzers': analyzers,
                    'metadata': {
                        'root': str(self.reveal_root),
                        'analyzers_count': len(analyzers),
                    }
                }
            elif component == 'adapters':
                adapters = self._get_adapters()
                return {
                    'contract_version': '1.0',
                    'type': 'reveal_structure',
                    'source': str(self.reveal_root),
                    'source_type': 'directory',
                    'adapters': adapters,
                    'metadata': {
                        'root': str(self.reveal_root),
                        'adapters_count': len(adapters),
                    }
                }
            elif component == 'rules':
                rules = self._get_rules()
                return {
                    'contract_version': '1.0',
                    'type': 'reveal_structure',
                    'source': str(self.reveal_root),
                    'source_type': 'directory',
                    'rules': rules,
                    'metadata': {
                        'root': str(self.reveal_root),
                        'rules_count': len(rules),
                    }
                }
            elif component == 'config':
                config_data = self._get_config()
                return {
                    'contract_version': '1.0',
                    'type': 'reveal_structure',
                    'source': str(self.reveal_root),
                    'source_type': 'directory',
                    **config_data
                }

        # Default: show everything
        structure = {
            'contract_version': '1.0',
            'type': 'reveal_structure',
            'source': str(self.reveal_root),
            'source_type': 'directory',
            'analyzers': self._get_analyzers(),
            'adapters': self._get_adapters(),
            'rules': self._get_rules(),
            'supported_file_types': self._get_supported_types(),
            'metadata': {
                'root': str(self.reveal_root),
                'analyzers_count': len(self._get_analyzers()),
                'adapters_count': len(self._get_adapters()),
                'rules_count': len(self._get_rules()),
            }
        }

        return structure

    def _get_analyzers(self) -> List[Dict[str, Any]]:
        """Get all registered analyzers."""
        analyzers: List[Dict[str, Any]] = []
        analyzers_dir = self.reveal_root / 'analyzers'

        if not analyzers_dir.exists():
            return analyzers

        for file in analyzers_dir.glob('*.py'):
            if file.stem.startswith('_'):
                continue

            analyzers.append({
                'name': file.stem,
                'path': str(file.relative_to(self.reveal_root)),
                'module': f'reveal.analyzers.{file.stem}'
            })

        return sorted(analyzers, key=lambda x: x['name'])

    def _get_adapters(self) -> List[Dict[str, Any]]:
        """Get all registered adapters from the registry."""
        adapters = []

        for scheme, adapter_class in _ADAPTER_REGISTRY.items():
            adapters.append({
                'scheme': scheme,
                'class': adapter_class.__name__,
                'module': adapter_class.__module__,
                'has_help': hasattr(adapter_class, 'get_help')
            })

        return sorted(adapters, key=lambda x: x['scheme'])

    def _get_rules(self) -> List[Dict[str, Any]]:
        """Get all available rules."""
        rules: List[Dict[str, Any]] = []
        rules_dir = self.reveal_root / 'rules'

        if not rules_dir.exists():
            return rules

        for category_dir in rules_dir.iterdir():
            if not category_dir.is_dir() or category_dir.name.startswith('_'):
                continue

            for rule_file in category_dir.glob('*.py'):
                if rule_file.stem.startswith('_'):
                    continue

                rules.append({
                    'code': rule_file.stem,
                    'category': category_dir.name,
                    'path': str(rule_file.relative_to(self.reveal_root)),
                    'module': f'reveal.rules.{category_dir.name}.{rule_file.stem}'
                })

        return sorted(rules, key=lambda x: x['code'])

    def _get_supported_types(self) -> List[str]:
        """Get list of supported file extensions."""
        # This would ideally query the analyzer registry
        # For now, return a basic list
        types = []

        # Scan analyzer files for @register decorators
        analyzers_dir = self.reveal_root / 'analyzers'
        if analyzers_dir.exists():
            for file in analyzers_dir.glob('*.py'):
                if file.stem.startswith('_'):
                    continue
                # We could parse the file to extract @register patterns
                # For now, just note the analyzer exists
                types.append(file.stem)

        return sorted(types)

    def _get_config(self) -> Dict[str, Any]:
        """Get current configuration with full transparency.

        Returns:
            Dict containing active config, sources, and metadata
        """
        import os
        from ..config import RevealConfig

        # Get current config instance
        config = RevealConfig.get()

        # Extract environment variables
        env_vars = {}
        env_var_names = [
            'REVEAL_NO_CONFIG',
            'REVEAL_CONFIG',
            'REVEAL_RULES_DISABLE',
            'REVEAL_C901_THRESHOLD',
            'REVEAL_C905_MAX_DEPTH',
            'REVEAL_E501_MAX_LENGTH',
            'REVEAL_M101_THRESHOLD',
            'REVEAL_CONFIG_DEBUG'
        ]
        for var in env_var_names:
            value = os.getenv(var)
            if value:
                env_vars[var] = value

        # Discover config files
        project_configs = []
        try:
            discovered = RevealConfig._discover_project_configs(Path.cwd())
            for cfg in discovered:
                if 'path' in cfg:
                    project_configs.append({
                        'path': str(cfg['path']),
                        'root': cfg.get('root', False)
                    })
        except Exception:
            pass

        # Check user and system configs
        user_config_path = RevealConfig._get_user_config_path()
        system_config_path = Path('/etc/reveal/config.yaml')

        custom_config = os.getenv('REVEAL_CONFIG')

        return {
            'active_config': {
                'rules': config._config.get('rules', {}),
                'ignore': config._config.get('ignore', []),
                'root': config._config.get('root', False),
                'overrides': config._config.get('overrides', []),
                'architecture': config._config.get('architecture', {}),
                'adapters': config._config.get('adapters', {}),
            },
            'sources': {
                'env_vars': env_vars,
                'custom_config': custom_config,
                'project_configs': project_configs,
                'user_config': str(user_config_path)
                if user_config_path.exists() else None,
                'system_config': str(system_config_path)
                if system_config_path.exists() else None,
            },
            'metadata': {
                'project_root': str(config.project_root),
                'working_directory': str(Path.cwd()),
                'no_config_mode': os.getenv('REVEAL_NO_CONFIG') == '1',
                'env_vars_count': len(env_vars),
                'config_files_count': len(project_configs),
                'custom_config_used': custom_config is not None,
            },
            'precedence_order': [
                '1. CLI flags (--select, --ignore)',
                '2. Environment variables',
                '3. Custom config file (REVEAL_CONFIG)',
                '4. Project configs (from cwd upward)',
                '5. User config (~/.config/reveal/config.yaml)',
                '6. System config (/etc/reveal/config.yaml)',
                '7. Built-in defaults'
            ]
        }

    def check(self, select: Optional[List[str]] = None, ignore: Optional[List[str]] = None) -> Dict[str, Any]:
        """Run validation rules on reveal itself.

        Args:
            select: Optional list of rule codes to run
            ignore: Optional list of rule codes to ignore

        Returns:
            Dict with detections and metadata
        """
        from ..rules import RuleRegistry

        # V-series rules inspect reveal source directly
        detections = RuleRegistry.check_file("reveal://", None, "", select=select, ignore=ignore)

        return {
            'file': 'reveal://',
            'detections': detections,  # Keep as Detection objects for render_check
            'total': len(detections)
        }

    def get_element(self, element_name: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        """Extract a specific element from a reveal source file.

        Args:
            element_name: Element to extract (e.g., function name) or resource path
            **kwargs: Optional keyword arguments:
                - resource: File path within reveal (e.g., "rules/links/L001.py")
                - args: Command-line arguments

        Returns:
            Dict with success status if successful, None if failed
        """
        from ..file_handler import handle_file

        # For backwards compatibility, support resource as kwarg
        resource = kwargs.get('resource', element_name)
        args = kwargs.get('args')

        if not args:
            # If no args provided, return None (cannot process)
            return None

        # Resolve the file path within reveal
        file_path = self.reveal_root / resource

        if not file_path.exists():
            return None

        # Use regular file processing to extract the element
        # This delegates to the appropriate analyzer (Python, etc.)
        try:
            handle_file(str(file_path), element_name,
                       show_meta=False, output_format=args.format, args=args)
            return {'success': True}
        except Exception:
            return None

    def format_output(self, structure: Dict[str, Any], format_type: str = 'text') -> str:
        """Format reveal structure for display.

        Args:
            structure: Structure dict from get_structure()
            format_type: Output format (text or json)

        Returns:
            Formatted string
        """
        if format_type == 'json':
            import json
            return json.dumps(structure, indent=2)

        # Check if this is a config structure
        if 'active_config' in structure and 'sources' in structure:
            return self._format_config_output(structure)

        # Text format for default reveal structure
        lines = []
        lines.append("# Reveal Internal Structure\n")

        # Metadata
        meta = structure['metadata']
        lines.append(f"**Root**: {meta['root']}")
        lines.append(f"**Analyzers**: {meta['analyzers_count']}")
        lines.append(f"**Adapters**: {meta['adapters_count']}")
        lines.append(f"**Rules**: {meta['rules_count']}\n")

        # Analyzers
        if structure['analyzers']:
            lines.append("## Analyzers\n")
            for analyzer in structure['analyzers']:
                lines.append(f"  • {analyzer['name']:<20} {analyzer['path']}")
            lines.append("")

        # Adapters
        if structure['adapters']:
            lines.append("## Adapters\n")
            for adapter in structure['adapters']:
                help_marker = "✓" if adapter['has_help'] else " "
                lines.append(f"  [{help_marker}] {adapter['scheme']+'://':<15} {adapter['class']}")
            lines.append("")

        # Rules
        if structure['rules']:
            lines.append("## Rules by Category\n")
            by_category: Dict[str, List[Dict[str, Any]]] = {}
            for rule in structure['rules']:
                cat = rule['category']
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append(rule)

            for category, rules in sorted(by_category.items()):
                lines.append(f"### {category.title()}")
                for rule in rules:
                    lines.append(f"  • {rule['code']:<8} {rule['path']}")
                lines.append("")

        return '\n'.join(lines)

    def _format_config_output(self, structure: Dict[str, Any]) -> str:
        """Format configuration structure for text display.

        Args:
            structure: Config structure from _get_config()

        Returns:
            Formatted text output
        """
        lines = []
        lines.append("# Reveal Configuration\n")

        # Metadata section
        meta = structure['metadata']
        lines.append("## Overview\n")
        lines.append(f"**Project Root**: {meta['project_root']}")
        lines.append(f"**Working Directory**: {meta['working_directory']}")
        lines.append(f"**No-Config Mode**: {meta['no_config_mode']}")
        lines.append(f"**Config Files Found**: {meta['config_files_count']}")
        lines.append(f"**Environment Variables Set**: {meta['env_vars_count']}")
        if meta['custom_config_used']:
            lines.append(f"**Custom Config**: Used (REVEAL_CONFIG)")
        lines.append("")

        # Sources section
        sources = structure['sources']
        lines.append("## Configuration Sources\n")

        # Environment variables
        if sources['env_vars']:
            lines.append("### Environment Variables")
            for var, value in sources['env_vars'].items():
                lines.append(f"  • {var} = {value}")
            lines.append("")

        # Custom config
        if sources['custom_config']:
            lines.append("### Custom Config File")
            lines.append(f"  • {sources['custom_config']}")
            lines.append("")

        # Project configs
        if sources['project_configs']:
            lines.append("### Project Configurations")
            for cfg in sources['project_configs']:
                root_marker = " (root)" if cfg.get('root') else ""
                lines.append(f"  • {cfg['path']}{root_marker}")
            lines.append("")

        # User config
        if sources['user_config']:
            lines.append("### User Configuration")
            lines.append(f"  • {sources['user_config']}")
            lines.append("")

        # System config
        if sources['system_config']:
            lines.append("### System Configuration")
            lines.append(f"  • {sources['system_config']}")
            lines.append("")

        # Active configuration
        active = structure['active_config']
        lines.append("## Active Configuration\n")

        # Rules
        if active['rules']:
            lines.append("### Rules")
            import json
            lines.append(f"```yaml\n{json.dumps(active['rules'], indent=2)}\n```")
            lines.append("")

        # Ignore patterns
        if active['ignore']:
            lines.append("### Ignore Patterns")
            for pattern in active['ignore']:
                lines.append(f"  • {pattern}")
            lines.append("")

        # Root flag
        if active['root']:
            lines.append("### Root")
            lines.append("  • root: true (stops config search)")
            lines.append("")

        # Overrides
        if active['overrides']:
            lines.append("### File Overrides")
            lines.append(f"  • {len(active['overrides'])} override(s) defined")
            lines.append("")

        # Precedence order
        lines.append("## Configuration Precedence\n")
        for order in structure['precedence_order']:
            lines.append(f"  {order}")
        lines.append("")

        lines.append("**Tip**: Use `reveal help://configuration` for complete guide")

        return '\n'.join(lines)
