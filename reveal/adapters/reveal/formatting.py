"""Formatting functions for reveal adapter output."""

import json
from typing import Dict, List, Any


def format_output(structure: Dict[str, Any], format_type: str = 'text') -> str:
    """Format reveal structure for display.

    Args:
        structure: Structure dict from get_structure()
        format_type: Output format (text or json)

    Returns:
        Formatted string
    """
    if format_type == 'json':
        return json.dumps(structure, indent=2)

    # Check if this is a config structure
    if 'active_config' in structure and 'sources' in structure:
        return format_config_output(structure)

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
    if structure.get('analyzers'):
        lines.append("## Analyzers\n")
        for analyzer in structure['analyzers']:
            lines.append(f"  • {analyzer['name']:<20} {analyzer['path']}")
        lines.append("")

    # Adapters
    if structure.get('adapters'):
        lines.append("## Adapters\n")
        for adapter in structure['adapters']:
            help_marker = "✓" if adapter['has_help'] else " "
            lines.append(f"  [{help_marker}] {adapter['scheme']+'://':<15} {adapter['class']}")
        lines.append("")

    # Rules
    if structure.get('rules'):
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


def format_metadata_section(meta: Dict[str, Any]) -> List[str]:
    """Format metadata/overview section.

    Args:
        meta: Metadata dict

    Returns:
        List of formatted lines
    """
    lines = ["## Overview\n"]
    lines.append(f"**Project Root**: {meta['project_root']}")
    lines.append(f"**Working Directory**: {meta['working_directory']}")
    lines.append(f"**No-Config Mode**: {meta['no_config_mode']}")
    lines.append(f"**Config Files Found**: {meta['config_files_count']}")
    lines.append(f"**Environment Variables Set**: {meta['env_vars_count']}")
    if meta['custom_config_used']:
        lines.append(f"**Custom Config**: Used (REVEAL_CONFIG)")
    lines.append("")
    return lines


def format_sources_section(sources: Dict[str, Any]) -> List[str]:
    """Format configuration sources section.

    Args:
        sources: Sources dict

    Returns:
        List of formatted lines
    """
    lines = ["## Configuration Sources\n"]

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

    return lines


def format_active_config_section(active: Dict[str, Any]) -> List[str]:
    """Format active configuration section.

    Args:
        active: Active config dict

    Returns:
        List of formatted lines
    """
    lines = ["## Active Configuration\n"]

    # Rules
    if active['rules']:
        lines.append("### Rules")
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

    return lines


def format_config_output(structure: Dict[str, Any]) -> str:
    """Format configuration structure for text display.

    Args:
        structure: Config structure from get_config()

    Returns:
        Formatted text output
    """
    lines = ["# Reveal Configuration\n"]

    # Add sections
    lines.extend(format_metadata_section(structure['metadata']))
    lines.extend(format_sources_section(structure['sources']))
    lines.extend(format_active_config_section(structure['active_config']))

    # Precedence order
    lines.append("## Configuration Precedence\n")
    for order in structure['precedence_order']:
        lines.append(f"  {order}")
    lines.append("")

    lines.append("**Tip**: Use `reveal help://configuration` for complete guide")

    return '\n'.join(lines)
