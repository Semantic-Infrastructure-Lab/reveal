"""Renderer for reveal:// internal structure adapter."""

import json
from collections import defaultdict
from typing import Any, Dict, List, Union


def _render_optional_section(title: str, items: Union[str, List, Dict, None], indent: int = 1) -> None:
    """Render an optional configuration section if items exist.

    Args:
        title: Section title
        items: Items to render (string, list, or dict)
        indent: Indentation level
    """
    if not items:
        return

    prefix = "  " * indent
    print(f"{prefix}{title}:")

    if isinstance(items, str):
        print(f"{prefix}  * {items}")
    elif isinstance(items, dict):
        for key, value in items.items():
            print(f"{prefix}  * {key} = {value}")
    elif isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                # Handle project configs with root marker
                path = item.get('path', str(item))
                marker = " (root)" if item.get('root') else ""
                print(f"{prefix}  * {path}{marker}")
            else:
                print(f"{prefix}  * {item}")

    print()


def _render_config_overview(meta: Dict[str, Any]) -> None:
    """Render config overview section."""
    print("Overview:")
    print(f"  Project Root: {meta['project_root']}")
    print(f"  Working Directory: {meta['working_directory']}")
    print(f"  No-Config Mode: {meta['no_config_mode']}")
    print(f"  Config Files Found: {meta['config_files_count']}")
    print(f"  Environment Variables Set: {meta['env_vars_count']}")
    if meta['custom_config_used']:
        print("  Custom Config: Used (REVEAL_CONFIG)")
    print()


def _render_config_sources(sources: Dict[str, Any]) -> None:
    """Render configuration sources section."""
    print("Configuration Sources:\n")

    # Render each source section using helper
    _render_optional_section("Environment Variables", sources.get('env_vars'))
    _render_optional_section("Custom Config File", sources.get('custom_config'))
    _render_optional_section("Project Configurations", sources.get('project_configs'))
    _render_optional_section("User Configuration", sources.get('user_config'))
    _render_optional_section("System Configuration", sources.get('system_config'))


def _render_config_active_rules(rules: Dict[str, Any]) -> None:
    """Render active rules configuration."""
    if not rules:
        return

    print("  Rules:")
    # Show disabled rules
    if 'disable' in rules:
        print(f"    Disabled: {', '.join(rules['disable'])}")
    # Show rule configs
    for rule_code, rule_config in rules.items():
        if rule_code != 'disable' and isinstance(rule_config, dict):
            print(f"    {rule_code}:")
            for key, value in rule_config.items():
                print(f"      {key}: {value}")
    print()


def _render_config_active_settings(active: Dict[str, Any]) -> None:
    """Render active configuration settings."""
    print("Active Configuration:\n")

    _render_config_active_rules(active['rules'])

    # Ignore patterns
    if active['ignore']:
        print("  Ignore Patterns:")
        for pattern in active['ignore']:
            print(f"    * {pattern}")
        print()

    # Root flag
    if active['root']:
        print("  Root:")
        print("    * root: true (stops config search)")
        print()

    # Overrides
    if active['overrides']:
        print("  File Overrides:")
        print(f"    * {len(active['overrides'])} override(s) defined")
        print()


def _render_config_precedence(precedence_order: list) -> None:
    """Render configuration precedence order."""
    print("Configuration Precedence:\n")
    for order in precedence_order:
        print(f"  {order}")
    print()


def _render_config_structure(data: Dict[str, Any]) -> None:
    """Render reveal://config structure.

    Args:
        data: Config structure from reveal adapter
    """
    print("Reveal Configuration\n")

    _render_config_overview(data['metadata'])
    _render_config_sources(data['sources'])
    _render_config_active_settings(data['active_config'])
    _render_config_precedence(data['precedence_order'])

    print("Tip: Use 'reveal help://configuration' for complete guide")


def _render_analyzers_section(data: Dict[str, Any]) -> None:
    """Render analyzers section of reveal structure."""
    if 'analyzers' not in data:
        return

    analyzers = data['analyzers']
    print(f"Analyzers ({len(analyzers)}):")
    for analyzer in analyzers:
        print(f"  * {analyzer['name']:<20} ({analyzer['path']})")
    if 'adapters' in data or 'rules' in data:
        print()


def _render_adapters_section(data: Dict[str, Any]) -> None:
    """Render adapters section of reveal structure."""
    if 'adapters' not in data:
        return

    adapters = data['adapters']
    print(f"Adapters ({len(adapters)}):")
    for adapter in adapters:
        help_marker = '*' if adapter.get('has_help') else ' '
        print(f"  {help_marker} {adapter['scheme'] + '://':<15} ({adapter['class']})")
    if 'rules' in data:
        print()


def _render_rules_section(data: Dict[str, Any]) -> None:
    """Render rules section of reveal structure."""
    if 'rules' not in data:
        return

    rules = data['rules']
    print(f"Rules ({len(rules)}):")

    # Group by category using defaultdict
    by_category = defaultdict(list)
    for rule in rules:
        category = rule.get('category', 'unknown')
        by_category[category].append(rule)

    for category in sorted(by_category.keys()):
        rules_in_cat = by_category[category]
        codes = ', '.join(r['code'] for r in rules_in_cat)
        print(f"  * {category:<15} ({len(rules_in_cat):2}): {codes}")


def _render_metadata_section(data: Dict[str, Any]) -> None:
    """Render metadata section of reveal structure."""
    metadata = data.get('metadata', {})
    print("\nMetadata:")
    print(f"  Root: {metadata.get('root')}")

    # Build total summary dynamically
    total_parts = []
    if metadata.get('analyzers_count') is not None:
        total_parts.append(f"{metadata['analyzers_count']} analyzers")
    if metadata.get('adapters_count') is not None:
        total_parts.append(f"{metadata['adapters_count']} adapters")
    if metadata.get('rules_count') is not None:
        total_parts.append(f"{metadata['rules_count']} rules")

    if total_parts:
        print(f"  Total: {', '.join(total_parts)}")


def render_reveal_structure(data: Dict[str, Any], output_format: str) -> None:
    """Render reveal:// adapter result.

    Args:
        data: Result from reveal adapter
        output_format: Output format (text, json)
    """
    if output_format == 'json':
        print(json.dumps(data, indent=2))
        return

    # Check if this is a config structure
    if 'active_config' in data and 'sources' in data:
        _render_config_structure(data)
        return

    # Text format - show structure nicely
    print("Reveal Internal Structure\n")

    _render_analyzers_section(data)
    _render_adapters_section(data)
    _render_rules_section(data)
    _render_metadata_section(data)
