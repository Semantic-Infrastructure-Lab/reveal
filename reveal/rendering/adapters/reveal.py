"""Renderer for reveal:// internal structure adapter."""

import json
from typing import Any, Dict


def render_reveal_structure(data: Dict[str, Any], output_format: str) -> None:
    """Render reveal:// adapter result.

    Args:
        data: Result from reveal adapter
        output_format: Output format (text, json)
    """
    if output_format == 'json':
        print(json.dumps(data, indent=2))
        return

    # Text format - show structure nicely
    print("Reveal Internal Structure\n")

    # Analyzers
    analyzers = data.get('analyzers', [])
    print(f"Analyzers ({len(analyzers)}):")
    for analyzer in analyzers:
        print(f"  * {analyzer['name']:<20} ({analyzer['path']})")

    # Adapters
    adapters = data.get('adapters', [])
    print(f"\nAdapters ({len(adapters)}):")
    for adapter in adapters:
        help_marker = '*' if adapter.get('has_help') else ' '
        print(f"  {help_marker} {adapter['scheme'] + '://':<15} ({adapter['class']})")

    # Rules
    rules = data.get('rules', [])
    print(f"\nRules ({len(rules)}):")
    # Group by category
    by_category = {}
    for rule in rules:
        category = rule.get('category', 'unknown')
        if category not in by_category:
            by_category[category] = []
        by_category[category].append(rule)

    for category in sorted(by_category.keys()):
        rules_in_cat = by_category[category]
        codes = ', '.join(r['code'] for r in rules_in_cat)
        print(f"  * {category:<15} ({len(rules_in_cat):2}): {codes}")

    # Metadata
    metadata = data.get('metadata', {})
    print(f"\nMetadata:")
    print(f"  Root: {metadata.get('root')}")
    print(f"  Total: {metadata.get('analyzers_count')} analyzers, "
          f"{metadata.get('adapters_count')} adapters, "
          f"{metadata.get('rules_count')} rules")
