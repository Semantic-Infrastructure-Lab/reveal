"""Renderer for reveal:// internal structure adapter."""

from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Union

from reveal.utils import print_json_result


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _file_outcome_line(entry: Dict[str, Any], selected: bool, said: Sequence[str] = ()) -> str:
    """One rule's per-file outcome line for a check on files, or '' when it has nothing to say.

    A rule that was unavailable (or crashed) on any file always speaks: its "no findings" is not a
    pass. What it was not applicable to speaks only when the run *selected* rules (--select), where
    the list is short by construction; the default view would otherwise print the ~50 rules aimed at
    other targets (AGENT_DEVELOPER_GUIDELINES item 8). JSON carries every rule either way. A reason
    the output already printed in full (*said*: the scan disclosures, which a rule-wide scan loss
    reports under the same words) is not printed a second time."""
    files = entry["files"]
    parts = []
    if files["unavailable"]:
        parts.append(f"unavailable on {_plural(files['unavailable'], 'file')}")
    if files["failed"]:
        parts.append(f"crashed on {_plural(files['failed'], 'file')}")
    if not parts and not (selected and (files["skipped"] or entry.get("subjects", {}).get("skipped"))):
        return ""
    if files["run"]:
        parts.append(f"ran on {_plural(files['run'], 'file')}")
    if selected and files["skipped"]:
        parts.append(f"not applicable to {files['skipped']}")
    if selected and entry.get("subjects", {}).get("skipped"):
        parts.append(f"{_plural(entry['subjects']['skipped'], 'item')} within not applicable")
    repeated = any(entry["reason"] in line for line in said)
    reason = f": {entry['reason']}" if entry["reason"] and not repeated else ""
    return f"  {entry['rule']} {', '.join(parts)}{reason}"


def _render_flat_coverage(coverage: Dict[str, Any]) -> None:
    """The reveal:// self-check's ledger: one entry per rule, every unavailable one and its
    subject details in full."""
    print(coverage["scope"])
    for entry in coverage.get("rules", []):
        if entry["status"] == "unavailable":
            print(f"  {entry['rule']} unavailable: {entry['reason']}")
        for subject in entry.get("subjects", []):
            if subject["status"] != "run" and subject["subject"]:
                print(f"    {subject['subject']} {subject['status']}: {subject['reason']}")


def render_check_coverage(coverage: Optional[Dict[str, Any]], selected: bool = True,
                          said: Sequence[str] = ()) -> None:
    """Print a check's ``coverage`` block: the reveal:// self-check's flat ledger in full, or a
    file / directory check's per-rule aggregate (``selected``: --select named the rules; see
    ``_file_outcome_line``). Nothing prints when a file check has nothing to disclose."""
    if not coverage:
        return
    flat = "files_covered" not in coverage
    lines = [] if flat else [ln for ln in (_file_outcome_line(e, selected, said) for e in coverage["rules"]) if ln]
    if not flat and not lines:
        return
    print(f"Checks: {coverage['run']} run, {coverage['skipped']} skipped, {coverage['failed']} failed, "
          f"{coverage.get('unavailable', 0)} unavailable")
    if flat:
        _render_flat_coverage(coverage)
    for line in lines:
        print(line)


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
    _render_optional_section("Could Not Load (settings not applied)", [
        f"{failure['path']}: {failure['reason']}" for failure in sources.get('load_failures', [])
    ])
    _render_optional_section("Other REVEAL_* Variables (set, not read by the config loader)",
                             sources.get('other_env_vars'))


def _render_config_active_rules(rules: Dict[str, Any]) -> None:
    """Render active rules configuration."""
    if not rules:
        return

    print("  Rules:")
    # Show disabled and selected rules
    if 'disable' in rules:
        print(f"    Disabled: {', '.join(rules['disable'])}")
    if 'select' in rules:
        print(f"    Selected: {', '.join(rules['select'])}")
    # Show rule configs
    for rule_code, rule_config in rules.items():
        if rule_code not in ('disable', 'select') and isinstance(rule_config, dict):
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
        print_json_result(data)
        return
    if 'error' in data:
        return  # the router prints it (BACK-1553); an empty structure view under it misleads

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
