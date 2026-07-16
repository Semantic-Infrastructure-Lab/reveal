"""
Language support listing for reveal.

Provides introspection into which languages reveal can analyze and how.
Distinguishes between explicit analyzers (full featured) and tree-sitter
fallback analyzers (basic structure extraction).
"""

from typing import Dict, List, Tuple


def list_supported_languages() -> str:
    """Generate formatted list of all supported languages.

    Returns:
        Formatted string showing explicit and fallback language support
    """
    from ..registry import get_analyzer_mapping, AMBIGUOUS_EXTENSIONS

    # Get explicit analyzers
    analyzer_mapping = get_analyzer_mapping()
    explicit_extensions = {}  # ext -> (analyzer_class, name, icon)

    for ext, analyzer_class in analyzer_mapping.items():
        # Check if it's an explicit analyzer (not dynamic)
        class_name = analyzer_class.__name__
        is_fallback = class_name.startswith('Dynamic') or getattr(analyzer_class, 'is_fallback', False)

        if not is_fallback:
            explicit_extensions[ext] = {
                'class': analyzer_class,
                'name': getattr(analyzer_class, 'type_name', class_name.replace('Analyzer', '')),
                'icon': getattr(analyzer_class, 'icon', '📄')
            }

    # Get fallback languages (estimate from tree-sitter-language-pack)
    fallback_languages = _get_fallback_languages()

    # Filter out fallback languages that have explicit analyzers
    explicit_exts = set(explicit_extensions.keys())
    fallback_filtered = [
        (lang, exts) for lang, exts in fallback_languages
        if not any(ext in explicit_exts for ext in exts)
    ]
    fallback_languages = fallback_filtered

    # Format output
    lines = []
    lines.append("Supported Languages\n")
    lines.append("=" * 70)

    # Explicit analyzers section
    lines.append(f"\n✅ Explicit Analyzers ({len(explicit_extensions)})")
    lines.append("-" * 70)
    lines.append("Full analysis with language-specific features\n")

    # Group by extension
    from ..capabilities import get_capability

    explicit_sorted = sorted(explicit_extensions.items(), key=lambda x: str(x[1]['name']).lower())
    for ext, info in explicit_sorted:
        name = info['name']
        icon = info['icon']
        cap = get_capability(info['class'])
        tag = f" [{cap.conformance_level}]" if cap else ""
        # BACK-583: this line's class is only the registry's last-registered
        # winner for extensions registered by more than one analyzer — real
        # dispatch resolves those by content/path sniffing instead.
        marker = " *" if ext in AMBIGUOUS_EXTENSIONS else ""
        lines.append(f"  {icon} {name:20} ({ext}){tag}{marker}")

    # Fallback section
    lines.append(f"\n🔄 Tree-sitter Fallback ({len(fallback_languages)})")
    lines.append("-" * 70)
    lines.append("Basic analysis (functions, classes, imports)\n")

    fallback_sorted = sorted(fallback_languages)
    for lang_info in fallback_sorted:
        lang, exts = lang_info
        ext_str = ', '.join(exts)
        lines.append(f"  📄 {lang:20} ({ext_str})")

    # Total
    total = len(explicit_extensions) + len(fallback_languages)
    lines.append(f"\n{'='*70}")
    lines.append(f"Total: {total} languages supported")
    lines.append(
        "\n[tag] = capability conformance level (BACK-444): "
        "tier1-verified > smoke-tested > structure-only > untested. "
        "See: reveal --language-info <name>"
    )
    ambiguous_in_output = {ext: note for ext, note in AMBIGUOUS_EXTENSIONS.items() if ext in explicit_extensions}
    if ambiguous_in_output:
        lines.append(
            "\n* Content-dependent — actual analyzer chosen per-file, not by extension alone:"
        )
        for ext, note in sorted(ambiguous_in_output.items()):
            lines.append(f"  {ext}: {note}")

    # Usage hints
    lines.append("\n💡 Usage:")
    lines.append("  reveal file.ext                  # Analyze file")
    lines.append("  reveal file.ext --explain-file   # See how file is analyzed")
    lines.append("  reveal --language-info python    # Language details")

    return '\n'.join(lines)


def _get_fallback_languages() -> List[Tuple[str, List[str]]]:
    """Get list of languages supported via tree-sitter fallback.

    Returns:
        List of (language_name, [extensions]) tuples
    """
    # Common tree-sitter languages and their extensions
    # This is a curated list of widely-used languages that tree-sitter-language-pack supports
    fallback_map = {
        'kotlin': ['.kt', '.kts'],
        'swift': ['.swift'],
        'dart': ['.dart'],
        'elixir': ['.ex', '.exs'],
        'elm': ['.elm'],
        'erlang': ['.erl', '.hrl'],
        'haskell': ['.hs', '.lhs'],
        'julia': ['.jl'],
        'ocaml': ['.ml', '.mli'],
        'perl': ['.pl', '.pm'],
        'r': ['.r', '.R'],
        'scheme': ['.scm', '.ss'],
        'zig': ['.zig'],
        'nim': ['.nim'],
        'crystal': ['.cr'],
        'verilog': ['.v', '.vh'],
        'vhdl': ['.vhd', '.vhdl'],
        'terraform': ['.tf'],
        'nix': ['.nix'],
        'proto': ['.proto'],
        'thrift': ['.thrift'],
        'glsl': ['.glsl', '.vert', '.frag'],
        'cuda': ['.cu', '.cuh'],
    }

    # Filter to only languages that tree-sitter-language-pack actually supports
    # by testing if we can import the parser
    supported = []
    try:
        from tree_sitter_language_pack import get_parser
        for lang, exts in fallback_map.items():
            try:
                get_parser(lang)  # type: ignore[arg-type]  # language is validated at runtime
                supported.append((lang, exts))
            except Exception:
                # Language not available in this version
                pass
    except ImportError:
        # tree-sitter not installed
        pass

    return supported


def get_language_info(language: str) -> Dict:
    """Get detailed information about a specific language.

    Args:
        language: Language name (e.g., 'python', 'rust', 'kotlin')

    Returns:
        Dict with language capabilities and features
    """
    from ..registry import get_analyzer_mapping

    # Find analyzer for this language
    analyzer_mapping = get_analyzer_mapping()

    for ext, analyzer_class in analyzer_mapping.items():
        type_name = getattr(analyzer_class, 'type_name', '').lower()
        if type_name == language.lower():
            return {
                'name': type_name,
                'extension': ext,
                'analyzer': analyzer_class.__name__,
                'is_fallback': getattr(analyzer_class, 'is_fallback', False),
                'features': _get_analyzer_features(analyzer_class),
            }

    return {'error': f'Language not found: {language}'}


def _get_analyzer_features(analyzer_class) -> List[str]:
    """Get list of features supported by analyzer.

    Args:
        analyzer_class: Analyzer class

    Returns:
        List of feature strings
    """
    features = []

    # Check for common analyzer capabilities
    if hasattr(analyzer_class, 'get_structure'):
        features.append('Structure extraction')

    if hasattr(analyzer_class, 'get_imports'):
        features.append('Import analysis')

    if hasattr(analyzer_class, 'get_complexity'):
        features.append('Complexity metrics')

    if hasattr(analyzer_class, 'extract_element'):
        features.append('Element extraction')

    is_fallback = getattr(analyzer_class, 'is_fallback', False)
    if is_fallback:
        features.append('Functions')
        features.append('Classes')
        features.append('Imports (basic)')

    return features
