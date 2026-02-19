"""Renderer for help:// documentation adapter."""

import sys
from typing import Any, Dict, Optional

from reveal.utils import safe_json_dumps


# Module constants for help list mode
STABLE_ADAPTERS = {'help', 'env', 'ast', 'python'}
BETA_ADAPTERS = {'diff', 'imports', 'sqlite', 'mysql', 'stats', 'json', 'markdown', 'git', 'ssl', 'domain', 'xlsx'}
PROJECT_ADAPTERS = {'reveal', 'claude'}

GUIDE_CATEGORIES = {
    'getting_started': ['quick-start'],
    'ai_guides': ['agent', 'agent-full'],
    'feature_guides': ['python-guide', 'markdown', 'reveal-guide', 'html', 'configuration', 'schemas', 'duplicates'],
    'best_practices': ['anti-patterns', 'tricks'],
    'dev_guides': ['adapter-authoring', 'help', 'release'],
}

TOKEN_ESTIMATES = {
    'quick-start': '~2,000',
    'agent': '~2,200',
    'agent-full': '~12,000',
    'python-guide': '~2,500',
    'markdown': '~4,000',
    'reveal-guide': '~3,000',
    'html': '~2,000',
    'configuration': '~3,500',
    'schemas': '~4,500',
    'duplicates': '~5,500',
    'anti-patterns': '~2,000',
    'tricks': '~3,500',
    'adapter-authoring': '~2,500',
    'help': '~2,500',
    'release': '~2,500',
}


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
        'diff': ['stats', 'ast'],
        'stats': ['ast', 'diff'],
        'imports': ['ast', 'stats'],
    }

    # Special workflow hints for diff adapter
    if scheme == 'diff':
        print("## Try It Now")
        print("  # Compare uncommitted changes:")
        print("  reveal 'diff://git://HEAD/.:.'")
        print()
        print("  # Compare specific files:")
        print("  reveal 'diff://old.py:new.py'")
        print()
        print("  # Compare a specific function:")
        print("  reveal 'diff://old.py:new.py/function_name'")
        print()

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


def _get_stability_badge(scheme: str) -> str:
    """Get stability badge for an adapter."""
    if scheme in STABLE_ADAPTERS:
        return "🟢"
    elif scheme in BETA_ADAPTERS:
        return "🟡"
    elif scheme in PROJECT_ADAPTERS:
        return "🎓"
    else:
        return "🔴"


def _render_help_header() -> None:
    """Render help system header."""
    print("# Reveal Help System")
    print("**Purpose:** Progressive, explorable documentation")
    print("**Usage:** reveal help://<topic>")
    print()
    print("---")
    print()


def _render_dynamic_adapters_section(adapters: list) -> None:
    """Render dynamic adapters section.

    Args:
        adapters: List of adapter dicts with 'scheme' and 'description'
    """
    print("## 📦 DYNAMIC CONTENT (Runtime Discovery)")
    print()

    if not adapters:
        return

    print("### URI Adapters ({} registered)".format(len(adapters)))
    print("Source: Live adapter registry")
    print("Updates: Automatic when new adapters added")
    print("Legend: 🟢 Stable | 🟡 Beta | 🎓 Project Adapters | 🔴 Experimental")
    print()
    for adapter in adapters:
        scheme = adapter['scheme']
        desc = adapter.get('description', 'No description')
        badge = _get_stability_badge(scheme)
        print(f"  {badge} {scheme}://      - {desc}")
        print(f"                 Details: reveal help://{scheme}")
    print()


def _render_static_guides_header() -> None:
    """Render static guides section header."""
    print("## 📄 STATIC GUIDES (Markdown Files)")
    print("Source: reveal/ and reveal/adapters/ directories")
    print("Location: Bundled with installation")
    print()


def _render_guide_category(category_name: str, topics: list, static: list,
                            static_help_map: dict, special_handling: Optional[dict] = None) -> None:
    """Render a category of guide topics.

    Args:
        category_name: Display name for the category
        topics: List of topic IDs in this category
        static: List of available static guides
        static_help_map: Map of topic IDs to file paths
        special_handling: Optional dict with topic-specific handling (aliases, notes, etc.)
    """
    available_topics = [t for t in topics if t in static]
    if not available_topics and category_name != "For AI Agents":
        return

    print(f"### {category_name}")
    for topic in available_topics:
        file = static_help_map.get(topic, 'unknown')
        token_estimate = TOKEN_ESTIMATES.get(topic, '~2,000')

        # Handle special cases
        extra_info = ''
        if special_handling and topic in special_handling:
            extra_info = special_handling[topic]

        print(f"  {topic:16} - {_get_guide_description(topic)}")
        print(f"                     File: {file}")
        print(f"                     Token cost: {token_estimate}{extra_info}")
    print()


def _render_special_topics_section() -> None:
    """Render special topics section."""
    print("## 🧭 SPECIAL TOPICS")
    print()
    print("  adapters         - Summary of all URI adapters")
    print("                     Type: Generated")
    print("                     Token cost: ~300 tokens")
    print()


def _render_navigation_section() -> None:
    """Render navigation tips section."""
    print("---")
    print()
    print("## Navigation Tips")
    print()
    print("**Start here:**")
    print("  reveal help://              # This index")
    print()
    print("**New users:**")
    print("  reveal help://quick-start   # 5-minute introduction")
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
    print()
    print("**Build your own adapters:**")
    print("  🎓 Project Adapters = Production-ready examples for specific projects")
    print("  reveal:// and claude:// show how to adapt reveal to YOUR project")
    print("  -> reveal help://adapter-authoring  # Learn how to build adapters")


def _render_help_list_mode(data: Dict[str, Any]) -> None:
    """Render help system topic list (reveal help://)."""
    _render_help_header()

    # Group topics
    adapters = [a for a in data.get('adapters', []) if a.get('has_help')]
    static = data.get('static_guides', [])

    # Render dynamic adapters
    _render_dynamic_adapters_section(adapters)

    # Render static guides
    if static:
        from reveal.adapters.help import HelpAdapter
        static_help_map = HelpAdapter.STATIC_HELP

        _render_static_guides_header()

        # Getting Started
        _render_guide_category(
            "Getting Started",
            GUIDE_CATEGORIES['getting_started'],
            static, static_help_map,
            {'quick-start': '\n                     Recommended: Start here if you\'re new to reveal!'}
        )

        # AI Agent Guides
        _render_guide_category(
            "For AI Agents",
            GUIDE_CATEGORIES['ai_guides'],
            static, static_help_map,
            {
                'agent': '\n                     Alias: --agent-help flag',
                'agent-full': '\n                     Alias: --agent-help-full flag'
            }
        )

        # Feature Guides
        _render_guide_category(
            "Feature Guides",
            GUIDE_CATEGORIES['feature_guides'],
            static, static_help_map
        )

        # Best Practices
        _render_guide_category(
            "Best Practices",
            GUIDE_CATEGORIES['best_practices'],
            static, static_help_map
        )

        # Development
        _render_guide_category(
            "Development",
            GUIDE_CATEGORIES['dev_guides'],
            static, static_help_map
        )

    # Special topics and navigation
    _render_special_topics_section()
    _render_navigation_section()


def _get_guide_description(topic: str) -> str:
    """Get human-friendly description for a guide topic."""
    descriptions = {
        'quick-start': '5-minute introduction to reveal',
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
        'duplicates': 'Duplicate code detection (D001/D002 rules, workflows, limitations)',
        'duplicate-detection': 'Alias for duplicates',
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


def _render_workflows(content: list) -> None:
    """Render workflows section."""
    for workflow in content:
        print(f"## {workflow['name']}")
        if workflow.get('scenario'):
            print(f"Scenario: {workflow['scenario']}")
        print()
        for step in workflow.get('steps', []):
            print(f"  {step}")
        print()


def _render_try_now(content: list) -> None:
    """Render try-now section."""
    print("Run these in your current directory:")
    print()
    for cmd in content:
        print(f"  {cmd}")
    print()


def _render_anti_patterns(content: list) -> None:
    """Render anti-patterns section."""
    for ap in content:
        print(f"X {ap['bad']}")
        print(f"* {ap['good']}")
        if ap.get('why'):
            print(f"   Why: {ap['why']}")
        print()


_SECTION_RENDERERS = {
    'workflows': _render_workflows,
    'try-now': _render_try_now,
    'anti-patterns': _render_anti_patterns,
}


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

    renderer = _SECTION_RENDERERS.get(section)
    if renderer:
        renderer(content)

    # Breadcrumbs for section views
    print("---")
    print()
    print("## See Full Help")
    print(f"  -> reveal help://{adapter}")
    print()


# Section renderers - each handles one aspect of help documentation
def _render_help_detail_header(scheme: str, data: Dict[str, Any]) -> None:
    """Render help header with scheme, description, and metadata for detail mode."""
    # Stability classification
    stable_adapters = {'help', 'env', 'ast', 'python', 'reveal'}
    beta_adapters = {'diff', 'imports', 'sqlite', 'mysql', 'stats', 'json', 'markdown', 'git'}

    stability = "Stable 🟢" if scheme in stable_adapters else "Beta 🟡" if scheme in beta_adapters else "Experimental 🔴"

    print(f"# {scheme}:// - {data.get('description', '')}")
    print()
    print(f"**Source:** {scheme}.py adapter (dynamic)")
    print("**Type:** URI Adapter")
    print(f"**Stability:** {stability}")
    print(f"**Access:** reveal help://{scheme}")
    print()


def _render_help_syntax(data: Dict[str, Any]) -> None:
    """Render syntax section if present."""
    if data.get('syntax'):
        print(f"**Syntax:** `{data['syntax']}`")
        print()


def _render_help_operators(data: Dict[str, Any]) -> None:
    """Render operators section if present."""
    if data.get('operators'):
        print("## Operators")
        for op, desc in data['operators'].items():
            print(f"  {op:4} - {desc}")
        print()


def _render_help_filters(data: Dict[str, Any]) -> None:
    """Render filters section if present."""
    if data.get('filters'):
        print("## Filters")
        for name, desc in data['filters'].items():
            print(f"  {name:12} - {desc}")
        print()


def _render_help_features(data: Dict[str, Any]) -> None:
    """Render features list if present."""
    if data.get('features'):
        print("## Features")
        for feature in data['features']:
            print(f"  * {feature}")
        print()


def _render_help_categories(data: Dict[str, Any]) -> None:
    """Render categories section if present."""
    if data.get('categories'):
        print("## Categories")
        for cat, desc in data['categories'].items():
            print(f"  {cat:12} - {desc}")
        print()


def _render_help_examples(data: Dict[str, Any]) -> None:
    """Render examples section if present."""
    if data.get('examples'):
        print("## Examples")
        for ex in data['examples']:
            if isinstance(ex, dict):
                print(f"  {ex['uri']}")
                print(f"    -> {ex['description']}")
            else:
                print(f"  {ex}")
        print()


def _render_help_try_now(data: Dict[str, Any]) -> None:
    """Render try now commands if present."""
    if data.get('try_now'):
        print("## Try Now")
        print("  Run these in your current directory:")
        print()
        for cmd in data['try_now']:
            print(f"  {cmd}")
        print()


def _render_help_workflows(data: Dict[str, Any]) -> None:
    """Render workflows section if present."""
    if data.get('workflows'):
        print("## Workflows")
        for workflow in data['workflows']:
            print(f"  **{workflow['name']}**")
            if workflow.get('scenario'):
                print(f"  Scenario: {workflow['scenario']}")
            for step in workflow.get('steps', []):
                print(f"    {step}")
            print()


def _render_help_anti_patterns(data: Dict[str, Any]) -> None:
    """Render anti-patterns section if present."""
    if data.get('anti_patterns'):
        print("## Don't Do This")
        for ap in data['anti_patterns']:
            print(f"  X {ap['bad']}")
            print(f"  * {ap['good']}")
            if ap.get('why'):
                print(f"     Why: {ap['why']}")
            print()


def _render_help_notes(data: Dict[str, Any]) -> None:
    """Render notes section if present."""
    if data.get('notes'):
        print("## Notes")
        for note in data['notes']:
            print(f"  * {note}")
        print()


def _render_help_output_formats(data: Dict[str, Any]) -> None:
    """Render output formats if present."""
    if data.get('output_formats'):
        print(f"**Output formats:** {', '.join(data['output_formats'])}")
        print()


def _render_help_see_also(data: Dict[str, Any]) -> None:
    """Render see also section if present."""
    if data.get('see_also'):
        print("## See Also")
        for item in data['see_also']:
            print(f"  * {item}")
        print()


def _render_help_adapter_specific(data: Dict[str, Any]) -> None:
    """Render adapter-specific help documentation.

    Orchestrates rendering of all help sections in order.
    Each section is handled by a dedicated function for clarity.
    """
    if 'error' in data:
        print(f"Error: {data['message']}", file=sys.stderr)
        sys.exit(1)

    scheme = data.get('scheme', data.get('name', ''))

    # Render all sections in order
    _render_help_detail_header(scheme, data)
    _render_help_syntax(data)
    _render_help_operators(data)
    _render_help_filters(data)
    _render_help_features(data)
    _render_help_categories(data)
    _render_help_examples(data)
    _render_help_try_now(data)
    _render_help_workflows(data)
    _render_help_anti_patterns(data)
    _render_help_notes(data)
    _render_help_output_formats(data)
    _render_help_see_also(data)
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
