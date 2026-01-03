"""Renderer for help:// documentation adapter."""

import sys
from typing import Any, Dict

from reveal.utils import safe_json_dumps


def _render_help_breadcrumbs(scheme: str, data: Dict[str, Any]) -> None:
    """Render breadcrumbs after help output.

    Args:
        scheme: Adapter scheme name (e.g., 'ast', 'python')
        data: Help data dict
    """
    if not scheme:
        return

    print("---")
    print()

    # Related adapters - suggest complementary tools
    related = {
        'ast': ['python', 'env'],
        'python': ['ast', 'env'],
        'env': ['python'],
        'json': ['ast'],
        'help': ['ast', 'python'],
    }

    related_adapters = related.get(scheme, [])
    if related_adapters:
        print("## Next Steps")
        print(f"  -> reveal help://{related_adapters[0]}  # Related adapter")
        if len(related_adapters) > 1:
            print(f"  -> reveal help://{related_adapters[1]}  # Another option")
        print("  -> reveal .                   # Start exploring your code")
        print()

    # Point to deeper content
    print("## Go Deeper")
    print("  -> reveal help://tricks         # Power user workflows")
    print("  -> reveal help://anti-patterns  # Common mistakes to avoid")
    print()


def _render_help_list_mode(data: Dict[str, Any]) -> None:
    """Render help system topic list (reveal help://)."""
    print("# Reveal Help System")
    print("**Purpose:** Progressive, explorable documentation")
    print("**Usage:** reveal help://<topic>")
    print()
    print("---")
    print()

    # Group topics
    adapters = [a for a in data.get('adapters', []) if a.get('has_help')]
    static = data.get('static_guides', [])

    # DYNAMIC CONTENT
    print("## 📦 DYNAMIC CONTENT (Runtime Discovery)")
    print()

    if adapters:
        print("### URI Adapters ({} registered)".format(len(adapters)))
        print("Source: Live adapter registry")
        print("Updates: Automatic when new adapters added")
        print()
        for adapter in adapters:
            scheme = adapter['scheme']
            desc = adapter.get('description', 'No description')
            print(f"  {scheme}://      - {desc}")
            print(f"               Details: reveal help://{scheme}")
        print()

    # STATIC CONTENT
    print("## 📄 STATIC GUIDES (Markdown Files)")
    print("Source: reveal/ and reveal/adapters/ directories")
    print("Location: Bundled with installation")
    print()

    if static:
        # Organize static guides by category
        ai_guides = ['agent', 'agent-full']
        feature_guides = ['python-guide', 'markdown', 'reveal-guide', 'html', 'configuration', 'schemas']
        best_practices = ['anti-patterns', 'tricks']
        dev_guides = ['adapter-authoring', 'help', 'release']

        # Map topics to their files for source attribution
        from reveal.adapters.help import HelpAdapter
        static_help_map = HelpAdapter.STATIC_HELP

        # AI Agent Guides
        print("### For AI Agents")
        for topic in [t for t in ai_guides if t in static]:
            file = static_help_map.get(topic, 'unknown')
            token_estimate = {
                'agent': '~2,200',
                'agent-full': '~12,000'
            }.get(topic, '~1,500')

            alias = ''
            if topic == 'agent':
                alias = '\n                     Alias: --agent-help flag'
            elif topic == 'agent-full':
                alias = '\n                     Alias: --agent-help-full flag'

            print(f"  {topic:16} - {_get_guide_description(topic)}")
            print(f"                     File: {file}")
            print(f"                     Token cost: {token_estimate}{alias}")
        print()

        # Feature Guides
        if any(t in static for t in feature_guides):
            print("### Feature Guides")
            for topic in [t for t in feature_guides if t in static]:
                file = static_help_map.get(topic, 'unknown')
                token_estimate = {
                    'python-guide': '~2,500',
                    'markdown': '~4,000',
                    'reveal-guide': '~3,000',
                    'html': '~2,000',
                    'configuration': '~3,500',
                    'schemas': '~4,500'
                }.get(topic, '~2,000')
                print(f"  {topic:16} - {_get_guide_description(topic)}")
                print(f"                     File: {file}")
                print(f"                     Token cost: {token_estimate}")
            print()

        # Best Practices
        if any(t in static for t in best_practices):
            print("### Best Practices")
            for topic in [t for t in best_practices if t in static]:
                file = static_help_map.get(topic, 'unknown')
                token_estimate = {
                    'anti-patterns': '~2,000',
                    'tricks': '~3,500'
                }.get(topic, '~2,000')
                print(f"  {topic:16} - {_get_guide_description(topic)}")
                print(f"                     File: {file}")
                print(f"                     Token cost: {token_estimate}")
            print()

        # Development
        if any(t in static for t in dev_guides):
            print("### Development")
            for topic in [t for t in dev_guides if t in static]:
                file = static_help_map.get(topic, 'unknown')
                token_estimate = '~2,500'
                print(f"  {topic:16} - {_get_guide_description(topic)}")
                print(f"                     File: {file}")
                print(f"                     Token cost: {token_estimate}")
            print()

    # SPECIAL TOPICS
    print("## 🧭 SPECIAL TOPICS")
    print()
    print("  adapters         - Summary of all URI adapters")
    print("                     Type: Generated")
    print("                     Token cost: ~300 tokens")
    print()

    # NAVIGATION
    print("---")
    print()
    print("## Navigation Tips")
    print()
    print("**Start here:**")
    print("  reveal help://              # This index")
    print()
    print("**Bootstrap (AI agents):**")
    print("  reveal --agent-help         # Task-based patterns (~2,200 tokens)")
    print()
    print("**Discover adapters:**")
    print("  reveal help://adapters      # Summary of all URI adapters")
    print()
    print("**Learn specific feature:**")
    print("  reveal help://ast           # Deep dive on ast://")
    print("  reveal help://python        # Deep dive on python://")
    print()
    print("**Best practices:**")
    print("  reveal help://anti-patterns # Common mistakes to avoid")
    print("  reveal help://tricks        # Power user workflows")


def _get_guide_description(topic: str) -> str:
    """Get human-friendly description for a guide topic."""
    descriptions = {
        'agent': 'Quick reference (task-based patterns)',
        'agent-full': 'Comprehensive guide',
        'python': 'Python adapter with examples (duplicate of python-guide)',
        'python-guide': 'Python adapter deep dive',
        'reveal-guide': 'reveal:// adapter reference',
        'markdown': 'Markdown feature guide',
        'html': 'HTML feature guide',
        'configuration': 'Configuration system (rules, env vars, precedence)',
        'config': 'Alias for configuration',
        'schemas': 'Schema validation for markdown front matter (v0.29.0+)',
        'anti-patterns': 'Common mistakes to avoid',
        'adapter-authoring': 'Build your own adapters',
        'tricks': 'Cool tricks and hidden features',
        'help': 'How the help system works (meta!)',
        'release': 'Release process for maintainers'
    }
    return descriptions.get(topic, 'Static guide')


def _render_help_static_guide(data: Dict[str, Any]) -> None:
    """Render static guide from markdown file."""
    if 'error' in data:
        print(f"Error: {data['message']}", file=sys.stderr)
        sys.exit(1)

    # Add source attribution header
    topic = data.get('topic', 'unknown')
    file = data.get('file', 'unknown')

    print(f"<!-- Source: {file} | Type: Static Guide | Access: reveal help://{topic} or --agent-help{'-full' if topic == 'agent-full' else ''} -->")
    print()

    print(data['content'])


def _render_help_adapter_summary(data: Dict[str, Any]) -> None:
    """Render summary of all adapters."""
    print(f"# URI Adapters ({data['count']} total)")
    print()
    for scheme, info in sorted(data['adapters'].items()):
        print(f"## {scheme}://")
        print(f"{info['description']}")
        print(f"Syntax: {info['syntax']}")
        if info.get('example'):
            print(f"Example: {info['example']}")
        print()


def _render_help_section(data: Dict[str, Any]) -> None:
    """Render specific help section (help://ast/workflows)."""
    if 'error' in data:
        print(f"Error: {data['message']}", file=sys.stderr)
        sys.exit(1)

    adapter = data.get('adapter', '')
    section = data.get('section', '')
    content = data.get('content', [])

    print(f"# {adapter}:// - {section}")
    print()

    if section == 'workflows':
        for workflow in content:
            print(f"## {workflow['name']}")
            if workflow.get('scenario'):
                print(f"Scenario: {workflow['scenario']}")
            print()
            for step in workflow.get('steps', []):
                print(f"  {step}")
            print()
    elif section == 'try-now':
        print("Run these in your current directory:")
        print()
        for cmd in content:
            print(f"  {cmd}")
        print()
    elif section == 'anti-patterns':
        for ap in content:
            print(f"X {ap['bad']}")
            print(f"* {ap['good']}")
            if ap.get('why'):
                print(f"   Why: {ap['why']}")
            print()

    # Breadcrumbs for section views
    print("---")
    print()
    print(f"## See Full Help")
    print(f"  -> reveal help://{adapter}")
    print()


def _render_help_adapter_specific(data: Dict[str, Any]) -> None:
    """Render adapter-specific help documentation."""
    if 'error' in data:
        print(f"Error: {data['message']}", file=sys.stderr)
        sys.exit(1)

    scheme = data.get('scheme', data.get('name', ''))
    print(f"# {scheme}:// - {data.get('description', '')}")
    print()
    print(f"**Source:** {scheme}.py adapter (dynamic)")
    print(f"**Type:** URI Adapter")
    print(f"**Access:** reveal help://{scheme}")
    print()

    if data.get('syntax'):
        print(f"**Syntax:** `{data['syntax']}`")
        print()

    if data.get('operators'):
        print("## Operators")
        for op, desc in data['operators'].items():
            print(f"  {op:4} - {desc}")
        print()

    if data.get('filters'):
        print("## Filters")
        for name, desc in data['filters'].items():
            print(f"  {name:12} - {desc}")
        print()

    if data.get('features'):
        print("## Features")
        for feature in data['features']:
            print(f"  * {feature}")
        print()

    if data.get('categories'):
        print("## Categories")
        for cat, desc in data['categories'].items():
            print(f"  {cat:12} - {desc}")
        print()

    if data.get('examples'):
        print("## Examples")
        for ex in data['examples']:
            if isinstance(ex, dict):
                print(f"  {ex['uri']}")
                print(f"    -> {ex['description']}")
            else:
                print(f"  {ex}")
        print()

    if data.get('try_now'):
        print("## Try Now")
        print("  Run these in your current directory:")
        print()
        for cmd in data['try_now']:
            print(f"  {cmd}")
        print()

    if data.get('workflows'):
        print("## Workflows")
        for workflow in data['workflows']:
            print(f"  **{workflow['name']}**")
            if workflow.get('scenario'):
                print(f"  Scenario: {workflow['scenario']}")
            for step in workflow.get('steps', []):
                print(f"    {step}")
            print()

    if data.get('anti_patterns'):
        print("## Don't Do This")
        for ap in data['anti_patterns']:
            print(f"  X {ap['bad']}")
            print(f"  * {ap['good']}")
            if ap.get('why'):
                print(f"     Why: {ap['why']}")
            print()

    if data.get('notes'):
        print("## Notes")
        for note in data['notes']:
            print(f"  * {note}")
        print()

    if data.get('output_formats'):
        print(f"**Output formats:** {', '.join(data['output_formats'])}")
        print()

    if data.get('see_also'):
        print("## See Also")
        for item in data['see_also']:
            print(f"  * {item}")
        print()

    _render_help_breadcrumbs(scheme, data)


def render_help(data: Dict[str, Any], output_format: str, list_mode: bool = False) -> None:
    """Render help content.

    Args:
        data: Help data from adapter
        output_format: Output format (text, json, grep)
        list_mode: True if listing all topics, False for specific topic
    """
    if output_format == 'json':
        print(safe_json_dumps(data))
        return

    if list_mode:
        _render_help_list_mode(data)
        return

    # Dispatch to specific renderers based on help type
    help_type = data.get('type', 'unknown')

    renderers = {
        'static_guide': _render_help_static_guide,
        'adapter_summary': _render_help_adapter_summary,
        'help_section': _render_help_section,
    }

    renderer = renderers.get(help_type)
    if renderer:
        renderer(data)
    else:
        # Default: adapter-specific help
        _render_help_adapter_specific(data)
