"""Reveal meta-adapter (reveal://) - Self-inspection and validation."""

from pathlib import Path
from typing import Dict, List, Any, Optional
from .base import ResourceAdapter, register_adapter, _ADAPTER_REGISTRY


@register_adapter('reveal')
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
        """Find reveal's root directory.

        Priority:
        1. REVEAL_DEV_ROOT environment variable (explicit override)
        2. Git checkout in CWD or parent directories (prefer development)
        3. Installed package location (fallback)
        """
        import os

        # 1. Explicit override via environment
        env_root = os.getenv('REVEAL_DEV_ROOT')
        if env_root:
            dev_root = Path(env_root)
            if (dev_root / 'analyzers').exists() and (dev_root / 'rules').exists():
                return dev_root

        # 2. Search from CWD for git checkout (prefer development over installed)
        cwd = Path.cwd()
        for _ in range(10):  # Search up to 10 levels
            # Check for reveal git checkout patterns
            reveal_dir = cwd / 'reveal'
            if (reveal_dir / 'analyzers').exists() and (reveal_dir / 'rules').exists():
                # Verify it's a git checkout by checking for pyproject.toml in parent
                if (cwd / 'pyproject.toml').exists():
                    return reveal_dir
            cwd = cwd.parent
            if cwd == cwd.parent:  # Reached root
                break

        # 3. Fallback to installed package location
        installed = Path(__file__).parent.parent
        if (installed / 'analyzers').exists() and (installed / 'rules').exists():
            return installed

        # Last resort
        return Path(__file__).parent.parent

    def get_structure(self) -> Dict[str, Any]:
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
                    'analyzers': analyzers,
                    'metadata': {
                        'root': str(self.reveal_root),
                        'analyzers_count': len(analyzers),
                    }
                }
            elif component == 'adapters':
                adapters = self._get_adapters()
                return {
                    'adapters': adapters,
                    'metadata': {
                        'root': str(self.reveal_root),
                        'adapters_count': len(adapters),
                    }
                }
            elif component == 'rules':
                rules = self._get_rules()
                return {
                    'rules': rules,
                    'metadata': {
                        'root': str(self.reveal_root),
                        'rules_count': len(rules),
                    }
                }

        # Default: show everything
        structure = {
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
        analyzers = []
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
        rules = []
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

    def get_element(self, resource: str, element_name: str, args) -> Optional[bool]:
        """Extract a specific element from a reveal source file.

        Args:
            resource: File path within reveal (e.g., "rules/links/L001.py")
            element_name: Element to extract (e.g., function name)
            args: Command-line arguments

        Returns:
            True if successful (output is printed), None if failed
        """
        from ..cli.routing import handle_file

        # Resolve the file path within reveal
        file_path = self.reveal_root / resource

        if not file_path.exists():
            return None

        # Use regular file processing to extract the element
        # This delegates to the appropriate analyzer (Python, etc.)
        try:
            handle_file(str(file_path), element_name,
                       show_meta=False, output_format=args.format, args=args)
            return True
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

        # Text format
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
            by_category = {}
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
