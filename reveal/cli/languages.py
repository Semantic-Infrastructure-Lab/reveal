"""
Language support listing for reveal.

Provides introspection into which languages reveal can analyze and how.
Distinguishes between explicit analyzers (full featured) and tree-sitter
fallback analyzers (basic structure extraction).
"""

from typing import Dict, List, Tuple


def _collect_language_support():
    """Collect the explicit-analyzer / tree-sitter-fallback split.

    The data half of `list_supported_languages()`, factored out so the
    `--languages` flag and `help://languages` (BACK-846) render from one
    source instead of two drifting copies.

    Returns:
        (explicit_extensions, fallback_languages, AMBIGUOUS_EXTENSIONS)
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

    return explicit_extensions, fallback_languages, AMBIGUOUS_EXTENSIONS


def _group_by_language(explicit_extensions: Dict[str, dict]) -> List[dict]:
    """One entry per language, not per extension.

    The total used to count extension rows, so C++ (.cpp, .hpp, ...) counted
    once per extension and adding .pyi made Python count twice. Sorted by name;
    the capability comes from the first extension's analyzer class.
    """
    groups: Dict[str, dict] = {}
    for ext, info in sorted(explicit_extensions.items()):
        name = str(info['name'])
        group = groups.setdefault(name, {
            'name': name, 'icon': info['icon'], 'class': info['class'], 'extensions': [],
        })
        group['extensions'].append(ext)
    return sorted(groups.values(), key=lambda g: g['name'].lower())


def build_languages_payload() -> dict:
    """Structured language-support catalog, for help://languages (BACK-846).

    Same data `--languages` formats as text; carries the capability
    conformance level per explicit analyzer (BACK-444) rather than the
    ``[tag]`` shorthand the text view uses.
    """
    from ..capabilities import get_capability

    explicit_extensions, fallback_languages, ambiguous = _collect_language_support()

    explicit = []
    for group in _group_by_language(explicit_extensions):
        cap = get_capability(group['class'])
        explicit.append({
            'name': group['name'],
            'extensions': group['extensions'],
            'conformance_level': cap.conformance_level if cap else None,
            'content_dependent': [ext for ext in group['extensions'] if ext in ambiguous],
        })

    fallback = [
        {'name': lang, 'extensions': list(exts)}
        for lang, exts in sorted(fallback_languages)
    ]

    return {
        'explicit': explicit,
        'fallback': fallback,
        'total': len(explicit) + len(fallback),
        'ambiguous': {
            ext: note for ext, note in ambiguous.items()
            if ext in explicit_extensions
        },
    }


def list_supported_languages() -> str:
    """Generate formatted list of all supported languages.

    Returns:
        Formatted string showing explicit and fallback language support
    """
    explicit_extensions, fallback_languages, AMBIGUOUS_EXTENSIONS = _collect_language_support()
    languages = _group_by_language(explicit_extensions)

    # Format output
    lines = []
    lines.append("Supported Languages\n")
    lines.append("=" * 70)

    # Explicit analyzers section
    lines.append(f"\n✅ Explicit Analyzers ({len(languages)})")
    lines.append("-" * 70)
    lines.append("Full analysis with language-specific features\n")

    from ..capabilities import get_capability

    for group in languages:
        cap = get_capability(group['class'])
        tag = f" [{cap.conformance_level}]" if cap else ""
        # BACK-583: an extension registered by more than one analyzer is
        # dispatched by content/path sniffing, not by this row's class.
        exts = ', '.join(
            f"{ext} *" if ext in AMBIGUOUS_EXTENSIONS else ext for ext in group['extensions']
        )
        lines.append(f"  {group['icon']} {group['name']:20} ({exts}){tag}")

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
    total = len(languages) + len(fallback_languages)
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

    Exactly the extensions get_analyzer() routes to a dynamic fallback. A curated
    map here once advertised Julia, Perl, Nim, Crystal, Scheme, VHDL, Nix, Thrift,
    GLSL and CUDA, none of which reveal could open (BACK-1255).

    Returns:
        List of (language_name, [extensions]) tuples, sorted by language
    """
    from ..registry import fallback_languages

    by_language: Dict[str, List[str]] = {}
    for ext, grammar in fallback_languages().items():
        by_language.setdefault(grammar, []).append(ext)
    return [(lang, sorted(exts)) for lang, exts in sorted(by_language.items())]


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
