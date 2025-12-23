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

    # Analyzers (only if present in filtered data)
    if 'analyzers' in data:
        analyzers = data['analyzers']
        print(f"Analyzers ({len(analyzers)}):")
        for analyzer in analyzers:
            print(f"  * {analyzer['name']:<20} ({analyzer['path']})")
        if 'adapters' in data or 'rules' in data:
            print()

    # Adapters (only if present in filtered data)
    if 'adapters' in data:
        adapters = data['adapters']
        print(f"Adapters ({len(adapters)}):")
        for adapter in adapters:
            help_marker = '*' if adapter.get('has_help') else ' '
            print(f"  {help_marker} {adapter['scheme'] + '://':<15} ({adapter['class']})")
        if 'rules' in data:
            print()

    # Rules (only if present in filtered data)
    if 'rules' in data:
        rules = data['rules']
        print(f"Rules ({len(rules)}):")
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
