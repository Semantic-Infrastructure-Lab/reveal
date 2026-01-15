"""Introspection commands for reveal - explain, show-ast, language-info.

This module provides commands for understanding how reveal analyzes files:
- explain_file(): Show which analyzer was used and why
- show_ast(): Display tree-sitter AST for a file
- get_language_info_detailed(): Show detailed language capabilities
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any

from ..registry import get_analyzer, get_all_analyzers
from ..base import FileAnalyzer


def explain_file(path: str, verbose: bool = False) -> str:
    """Explain how reveal will analyze a file.

    Args:
        path: File path to explain
        verbose: Show additional technical details

    Returns:
        Formatted explanation string
    """
    file_path = Path(path)

    if not file_path.exists():
        return f"❌ File not found: {path}"

    # Get the analyzer that would be used
    analyzer_cls = get_analyzer(path, allow_fallback=True)

    if not analyzer_cls:
        return f"❌ No analyzer available for: {path}\n\nTry: reveal --languages to see supported types"

    # Build explanation
    lines = []
    lines.append(f"📄 File: {path}")
    lines.append("")

    # Analyzer info
    analyzer_name = getattr(analyzer_cls, 'type_name', analyzer_cls.__name__.replace('Analyzer', ''))
    icon = getattr(analyzer_cls, 'icon', '📄')
    lines.append(f"🔍 Analyzer: {icon} {analyzer_name}")
    lines.append(f"   Class: {analyzer_cls.__name__}")

    # Check if it's a fallback
    is_fallback = getattr(analyzer_cls, 'is_fallback', False)
    if is_fallback:
        lines.append("")
        lines.append("⚠️  Tree-sitter Fallback Mode")
        fallback_lang = getattr(analyzer_cls, 'fallback_language', 'unknown')
        fallback_quality = getattr(analyzer_cls, 'fallback_quality', 'unknown')
        lines.append(f"   Language: {fallback_lang}")
        lines.append(f"   Quality: {fallback_quality}")
        lines.append("")
        lines.append("   What this means:")
        lines.append("   • Basic structural analysis (functions, classes, imports)")
        lines.append("   • No language-specific features")
        lines.append("   • Generic tree-sitter parsing")
    else:
        lines.append("   ✅ Full language-specific analysis")

    # Show capabilities (if verbose)
    if verbose:
        lines.append("")
        lines.append("🛠️  Capabilities:")

        # Check what the analyzer can extract
        caps = []

        # Most analyzers have these methods
        if hasattr(analyzer_cls, 'get_functions'):
            caps.append("Functions")
        if hasattr(analyzer_cls, 'get_classes'):
            caps.append("Classes")
        if hasattr(analyzer_cls, 'get_imports'):
            caps.append("Imports")
        if hasattr(analyzer_cls, 'get_structure'):
            caps.append("Structure")
        if hasattr(analyzer_cls, 'get_decorators'):
            caps.append("Decorators")
        if hasattr(analyzer_cls, 'get_types'):
            caps.append("Types")
        if hasattr(analyzer_cls, 'get_comments'):
            caps.append("Comments")

        if caps:
            for cap in caps:
                lines.append(f"   • {cap}")
        else:
            lines.append("   • Basic AST extraction")

    # Extension info
    ext = file_path.suffix.lower()
    if ext:
        lines.append("")
        lines.append(f"📋 Extension: {ext}")

    # Suggest alternatives
    if is_fallback:
        lines.append("")
        lines.append("💡 Tip: Check if a language-specific analyzer exists:")
        lines.append("   reveal --languages | grep -i <language>")

    return "\n".join(lines)


def show_ast(path: str, max_depth: Optional[int] = None) -> str:
    """Show the tree-sitter AST for a file.

    Args:
        path: File path to analyze
        max_depth: Maximum depth to display (None = unlimited)

    Returns:
        Formatted AST tree
    """
    file_path = Path(path)

    if not file_path.exists():
        return f"❌ File not found: {path}"

    # Get analyzer
    analyzer_cls = get_analyzer(path, allow_fallback=True)

    if not analyzer_cls:
        return f"❌ No analyzer available for: {path}"

    # Check if it's a tree-sitter based analyzer
    from ..treesitter import TreeSitterAnalyzer
    if not issubclass(analyzer_cls, TreeSitterAnalyzer):
        return f"⚠️  {analyzer_cls.__name__} does not use tree-sitter\n\nAST display is only available for tree-sitter based analyzers."

    try:
        # Create analyzer instance
        analyzer = analyzer_cls(path)

        # Get the AST
        if not hasattr(analyzer, 'tree') or not analyzer.tree:
            return f"❌ Failed to parse file: {path}"

        # Format the AST
        lines = []
        lines.append(f"🌳 Tree-sitter AST: {path}")
        lines.append("")

        root_node = analyzer.tree.root_node
        lines.append(_format_ast_node(root_node, depth=0, max_depth=max_depth))

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Error analyzing file: {e}"


def _format_ast_node(node, depth: int = 0, max_depth: Optional[int] = None, prefix: str = "") -> str:
    """Format a tree-sitter node for display.

    Args:
        node: Tree-sitter node
        depth: Current depth
        max_depth: Maximum depth to display
        prefix: Prefix for tree structure

    Returns:
        Formatted node string
    """
    if max_depth is not None and depth >= max_depth:
        return f"{prefix}..."

    lines = []

    # Node type and text
    indent = "  " * depth
    node_type = node.type

    # Show text for leaf nodes
    if node.child_count == 0:
        text = node.text.decode('utf-8', errors='ignore') if node.text else ""
        if len(text) > 50:
            text = text[:47] + "..."
        lines.append(f"{indent}{node_type}: \"{text}\"")
    else:
        lines.append(f"{indent}{node_type}")

    # Recurse for children
    for child in node.children:
        lines.append(_format_ast_node(child, depth + 1, max_depth, prefix))

    return "\n".join(lines)


def get_language_info_detailed(language: str) -> str:
    """Get detailed information about a language's capabilities.

    Args:
        language: Language name or extension (e.g., 'python', '.py')

    Returns:
        Formatted language information
    """
    # Normalize input
    if not language.startswith('.'):
        # Try to find extension by language name
        all_analyzers = get_all_analyzers()
        matches = []
        for ext, info in all_analyzers.items():
            if language.lower() in info['name'].lower():
                matches.append((ext, info))

        if not matches:
            return f"❌ Language not found: {language}\n\nTry: reveal --languages to see all supported languages"

        if len(matches) > 1:
            lines = [f"🔍 Multiple matches for '{language}':"]
            lines.append("")
            for ext, info in matches:
                icon = info['icon'] or '📄'
                lines.append(f"  {icon} {info['name']} ({ext})")
            lines.append("")
            lines.append("Please specify extension: reveal --language-info <extension>")
            return "\n".join(lines)

        ext, info = matches[0]
    else:
        ext = language.lower()
        all_analyzers = get_all_analyzers()
        if ext not in all_analyzers:
            return f"❌ Extension not supported: {ext}\n\nTry: reveal --languages"
        info = all_analyzers[ext]

    # Build detailed info
    lines = []
    icon = info['icon'] or '📄'
    lines.append(f"{icon} {info['name']}")
    lines.append("=" * 50)
    lines.append("")

    lines.append(f"📋 Extension: {ext}")
    lines.append(f"🔧 Analyzer: {info['class'].__name__}")
    lines.append("")

    # Fallback info
    if info['is_fallback']:
        lines.append("⚠️  Tree-sitter Fallback")
        lines.append(f"   Language: {info['fallback_language']}")
        lines.append(f"   Quality: {info['fallback_quality']}")
        lines.append("")
        lines.append("📊 Capabilities (Basic):")
        lines.append("   • Functions")
        lines.append("   • Classes")
        lines.append("   • Imports")
        lines.append("   • Structure")
        lines.append("")
        lines.append("⚠️  Note: Fallback analyzers provide basic structural")
        lines.append("   analysis only. No language-specific features.")
    else:
        lines.append("✅ Full Language Support")
        lines.append("")

        # Try to determine capabilities
        analyzer_cls = info['class']
        lines.append("📊 Capabilities:")

        caps = []
        if hasattr(analyzer_cls, 'get_functions'):
            caps.append("Functions with signatures")
        if hasattr(analyzer_cls, 'get_classes'):
            caps.append("Classes with methods")
        if hasattr(analyzer_cls, 'get_imports'):
            caps.append("Import statements")
        if hasattr(analyzer_cls, 'get_decorators'):
            caps.append("Decorators/annotations")
        if hasattr(analyzer_cls, 'get_types'):
            caps.append("Type definitions")
        if hasattr(analyzer_cls, 'get_structure'):
            caps.append("File structure")
        if hasattr(analyzer_cls, 'get_comments'):
            caps.append("Comments and docstrings")

        for cap in caps:
            lines.append(f"   • {cap}")

        if not caps:
            lines.append("   • Basic structure extraction")

    # Usage examples
    lines.append("")
    lines.append("💡 Usage Examples:")
    lines.append(f"   reveal file{ext}              # Show structure")
    lines.append(f"   reveal file{ext} MyClass      # Extract specific class")
    lines.append(f"   reveal file{ext} --check      # Run quality checks")
    lines.append(f"   reveal file{ext} --explain    # Show how it's analyzed")

    return "\n".join(lines)
