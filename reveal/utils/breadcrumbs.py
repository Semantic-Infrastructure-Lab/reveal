"""Breadcrumb system for agent-friendly navigation hints."""
import json
import re

# File type groupings for consistent suggestions
_CODE_TYPES = frozenset([
    'python', 'javascript', 'typescript', 'rust', 'go', 'bash', 'gdscript',
    'java', 'kotlin', 'swift', 'dart', 'scala', 'csharp', 'cpp', 'c',
    'ruby', 'php', 'lua', 'zig', 'powershell', 'batch', 'sql', 'elixir',
])
_CONFIG_TYPES = frozenset(['yaml', 'json', 'toml', 'jsonl', 'ini', 'properties'])
_INFRA_TYPES = frozenset(['dockerfile', 'nginx', 'terraform', 'hcl'])
_DATA_TYPES = frozenset(['csv', 'tsv', 'xml'])
_API_TYPES = frozenset(['graphql', 'protobuf'])


def get_element_placeholder(file_type):
    """Get appropriate element placeholder for file type.

    Args:
        file_type: File type string (e.g., 'python', 'yaml')

    Returns:
        String placeholder like '<function>', '<key>', etc.
    """
    mapping = {
        # Code types
        'python': '<function>',
        'javascript': '<function>',
        'typescript': '<function>',
        'rust': '<function>',
        'go': '<function>',
        'bash': '<function>',
        'gdscript': '<function>',
        'java': '<function>',
        'kotlin': '<function>',
        'swift': '<function>',
        'dart': '<function>',
        'scala': '<function>',
        'csharp': '<function>',
        'cpp': '<function>',
        'c': '<function>',
        'ruby': '<function>',
        'php': '<function>',
        'lua': '<function>',
        'zig': '<function>',
        'powershell': '<function>',
        'batch': '<label>',
        'sql': '<function>',
        'elixir': '<function>',
        # Config types
        'yaml': '<key>',
        'json': '<key>',
        'jsonl': '<entry>',
        'toml': '<key>',
        'ini': '<section>',
        'properties': '<key>',
        # Data types
        'csv': '<row>',
        'tsv': '<row>',
        'xml': '<element>',
        # Document types
        'markdown': '<section>',
        'html': '<element>',
        'jupyter': '<cell>',
        # Infrastructure types
        'dockerfile': '<instruction>',
        'nginx': '<directive>',
        'terraform': '<resource>',
        'hcl': '<resource>',
        # API types
        'graphql': '<type>',
        'protobuf': '<message>',
    }
    return mapping.get(file_type, '<element>')


def get_file_type_from_analyzer(analyzer):
    """Get file type string from analyzer class name.

    Args:
        analyzer: FileAnalyzer instance

    Returns:
        File type string (e.g., 'python', 'markdown') or None
    """
    class_name = type(analyzer).__name__
    mapping = {
        # Code analyzers
        'PythonAnalyzer': 'python',
        'JavaScriptAnalyzer': 'javascript',
        'TypeScriptAnalyzer': 'typescript',
        'RustAnalyzer': 'rust',
        'GoAnalyzer': 'go',
        'BashAnalyzer': 'bash',
        'GDScriptAnalyzer': 'gdscript',
        'JavaAnalyzer': 'java',
        'KotlinAnalyzer': 'kotlin',
        'SwiftAnalyzer': 'swift',
        'DartAnalyzer': 'dart',
        'ScalaAnalyzer': 'scala',
        'CSharpAnalyzer': 'csharp',
        'CppAnalyzer': 'cpp',
        'CAnalyzer': 'c',
        'RubyAnalyzer': 'ruby',
        'PhpAnalyzer': 'php',
        'LuaAnalyzer': 'lua',
        'ZigAnalyzer': 'zig',
        'PowerShellAnalyzer': 'powershell',
        'BatchAnalyzer': 'batch',
        'SQLAnalyzer': 'sql',
        'TSXAnalyzer': 'typescript',
        'ElixirAnalyzer': 'elixir',
        # Config analyzers
        'YamlAnalyzer': 'yaml',
        'JsonAnalyzer': 'json',
        'JsonlAnalyzer': 'jsonl',
        'TomlAnalyzer': 'toml',
        'IniAnalyzer': 'ini',
        # Data analyzers
        'CsvAnalyzer': 'csv',
        'XmlAnalyzer': 'xml',
        # Document analyzers
        'MarkdownAnalyzer': 'markdown',
        'HTMLAnalyzer': 'html',
        'JupyterAnalyzer': 'jupyter',
        # Infrastructure analyzers
        'DockerfileAnalyzer': 'dockerfile',
        'NginxAnalyzer': 'nginx',
        'HCLAnalyzer': 'terraform',
        # API analyzers
        'GraphQLAnalyzer': 'graphql',
        'ProtobufAnalyzer': 'protobuf',
        # Fallback
        'TreeSitterAnalyzer': None,
    }
    return mapping.get(class_name, None)


def _get_config_for_path(path):
    """Load config for the given path."""
    from pathlib import Path as PathLib
    from reveal.config import RevealConfig

    file_path = PathLib(path) if isinstance(path, str) else path
    start_path = file_path.parent if file_path.is_file() else file_path
    return RevealConfig.get(start_path=start_path)


def _show_breadcrumb_hint_once() -> None:
    """Show a one-time orientation nudge toward --agent-help (stderr, no pipe interference)."""
    import sys
    from reveal.config import get_data_path
    hint_file = get_data_path('seen_breadcrumb_hint')
    if hint_file.exists():
        return
    try:
        hint_file.touch()
    except OSError:
        return
    print(
        "New here? reveal --agent-help  (~2,200 tokens: how to use reveal well)\n"
        "Tip: Permanently disable navigation hints with: reveal --disable-breadcrumbs",
        file=sys.stderr,
    )


def _seen_hints_file():
    from reveal.config import get_data_path
    return get_data_path('seen_hints.json')


def _load_seen_hints() -> set:
    """Load the set of hint_ids `_show_hint_once` has already shown, ever."""
    hints_file = _seen_hints_file()
    if not hints_file.exists():
        return set()
    try:
        return set(json.loads(hints_file.read_text(encoding='utf-8')))
    except (OSError, ValueError):
        return set()


def _save_seen_hints(seen: set) -> None:
    try:
        _seen_hints_file().write_text(json.dumps(sorted(seen)), encoding='utf-8')
    except OSError:
        pass


def _show_hint_once(hint_id: str, lines: list) -> bool:
    """Print `lines` the first time `hint_id` is seen, ever; silent after.

    Generalizes _show_breadcrumb_hint_once's marker-file pattern (one
    hardcoded hint) to any number of boilerplate hint_ids, backed by one
    JSON set file under the same ~/.local/share/reveal/ data dir instead of
    one marker file per hint. Reserved for lines that repeat the same
    lesson regardless of file content (e.g. "you can extract by name") —
    lines that vary with what's actually in the file (a real class/heading
    name, a computed line number) should stay unconditional `print()` calls
    instead. See BREADCRUMB_HINT_THROTTLING_2026-08-02.md for the full
    classification.

    Returns:
        True if `lines` were printed (first time), False if suppressed —
        callers that count "hints shown" for a display budget (e.g.
        _suggest_ordinal_extraction) should use this, not assume printing
        happened.
    """
    seen = _load_seen_hints()
    if hint_id in seen:
        return False
    seen.add(hint_id)
    _save_seen_hints(seen)
    for line in lines:
        print(line)
    return True


# BACK-923: single source of truth for both structure- and typed-context
# file-type hints, which used to be two independently hand-maintained
# elif-chains that had already drifted (typed context silently had no
# _API_TYPES branch at all — reveal some.graphql --outline got zero
# format-specific hint while reveal some.graphql did).
#
# Each entry is (category_id, predicate, structure_lines, typed_lines).
# category_id feeds _show_hint_once (BREADCRUMB_HINT_THROTTLING_2026-08-02.md:
# this is boilerplate — the same lesson for every file of a given type —
# so it's shown once per (category, context) rather than on every call.
# typed_lines=None means "same as structure" (the common case). Where they
# differ it's deliberate, not drift: typed context IS the --outline view
# already, so it omits/replaces lines that would just repeat what's already
# on screen (--outline itself for code types; markdown swaps --code for
# --section, a more specific next step once you're already looking at the
# outline).
_TYPE_HINT_TABLE = [
    ('code', lambda ft: ft in _CODE_TYPES, [
        "      reveal {path} --check      # Check code quality",
        "      reveal {path} --outline    # Nested structure",
    ], [
        "      reveal {path} --check      # Check code quality",
    ]),
    ('markdown', lambda ft: ft == 'markdown', [
        "      reveal {path} --links      # Extract links",
        "      reveal {path} --code       # Extract code blocks",
    ], [
        "      reveal {path} --section 'Name'  # Extract section by heading",
        "      reveal {path} --links      # Extract links",
    ]),
    ('html', lambda ft: ft == 'html', [
        "      reveal {path} --check      # Validate HTML",
        "      reveal {path} --links      # Extract all links",
    ], None),
    ('config', lambda ft: ft in _CONFIG_TYPES, [
        "      reveal {path} --check      # Validate syntax",
    ], None),
    ('nginx', lambda ft: ft == 'nginx', [
        "      reveal {path} --check      # Validate configuration",
        "      reveal {path} --extract domains | reveal --stdin --check  # SSL audit",
    ], None),
    ('infra', lambda ft: ft in _INFRA_TYPES, [
        "      reveal {path} --check      # Validate configuration",
    ], None),
    ('data', lambda ft: ft in _DATA_TYPES, [
        "      reveal {path} --head 10    # First 10 rows/elements",
    ], None),
    ('api', lambda ft: ft in _API_TYPES, [
        "      reveal {path} --outline    # Type hierarchy",
    ], [
        # Typed context already IS --outline, so repeating it would be a
        # no-op; offer --check instead — API types had no --check
        # suggestion in either context before this fix.
        "      reveal {path} --check      # Check code quality",
    ]),
]


def _type_hint_lines(file_type, *, typed):
    """Look up (category_id, hint_lines) for `file_type`.

    Selects the typed-context override when one exists, else structure's.
    """
    for category_id, predicate, structure_lines, typed_lines in _TYPE_HINT_TABLE:
        if predicate(file_type):
            lines = typed_lines if (typed and typed_lines is not None) else structure_lines
            return category_id, lines
    return None, []


def _print_type_specific_hints(path, file_type):
    """Print file-type-specific command hints (structure context), once per type."""
    category_id, lines = _type_hint_lines(file_type, typed=False)
    if lines:
        hint_id = f'type_hint_structure_{category_id}'
        _show_hint_once(hint_id, [line.format(path=path) for line in lines])


def _print_typed_hints(path, file_type):
    """Print file-type-specific command hints (typed/outline context), once per type."""
    category_id, lines = _type_hint_lines(file_type, typed=True)
    if lines:
        hint_id = f'type_hint_typed_{category_id}'
        _show_hint_once(hint_id, [line.format(path=path) for line in lines])


# --- Context handlers ---

def _handle_metadata(path, file_type, **kwargs):
    """Handle 'metadata' context breadcrumbs."""
    _show_hint_once('metadata_see_structure', [
        f"Next: reveal {path}              # See structure",
        f"      reveal {path} --check      # Quality check",
    ])


def _handle_structure(path, file_type, **kwargs):
    """Handle 'structure' context breadcrumbs."""
    element_placeholder = get_element_placeholder(file_type)
    _show_hint_once('structure_extract_by_name', [
        f"Next: reveal {path} {element_placeholder}   # Extract by name",
    ])

    if file_type == 'markdown':
        _show_hint_once('structure_markdown_outline_note', [
            f"      Outline only — headings show where, not what. "
            f"Read a section: reveal {path} --section 'X'"
        ])

    structure = kwargs.get('structure', {})
    if not structure:
        _print_type_specific_hints(path, file_type)
        return

    # Try various suggestion strategies
    hints_shown = 0
    hints_shown += _suggest_hierarchical_extraction(path, file_type, structure)
    hints_shown += _suggest_doc_section_extraction(path, file_type, structure)
    hints_shown += _suggest_line_extraction(path, file_type, structure, hints_shown)
    hints_shown += _suggest_ordinal_extraction(path, structure, hints_shown)
    _suggest_imports_analysis(path, file_type, structure)

    # Check for large files - suggest AST queries and exit early
    if _suggest_ast_queries_for_large_file(path, file_type, structure):
        return

    _print_type_specific_hints(path, file_type)


def _suggest_hierarchical_extraction(path, file_type, structure):
    """Suggest hierarchical extraction for classes with methods.

    Returns:
        Number of hints shown (0 or 1)
    """
    if file_type not in _CODE_TYPES:
        return 0

    classes = structure.get('classes', [])
    if not classes:
        return 0

    # Find first class with a name
    for cls in classes:
        cls_name = cls.get('name', '') if isinstance(cls, dict) else str(cls)
        if cls_name:
            print(f"      reveal {path} {cls_name}.method  # Hierarchical extraction")
            return 1

    return 0


def _suggest_doc_section_extraction(path, file_type, structure):
    """Suggest section extraction for the first heading in a doc.

    Doc equivalent of _suggest_hierarchical_extraction: gives markdown files
    the same "here's a concrete next command" treatment code files get from
    their first class.

    Returns:
        Number of hints shown (0 or 1)
    """
    if file_type != 'markdown':
        return 0

    headings = structure.get('headings', [])
    if not headings:
        return 0

    first = headings[0]
    name = first.get('name', '') if isinstance(first, dict) else str(first)
    if name:
        print(f"      reveal {path} --section '{name}'  # Extract this section")
        return 1

    return 0


def _suggest_line_extraction(path, file_type, structure, hints_shown):
    """Suggest line-based extraction using first function's line.

    Returns:
        Number of hints shown (0 or 1)
    """
    if file_type not in _CODE_TYPES or hints_shown >= 2:
        return 0

    functions = structure.get('functions', [])
    if not functions:
        return 0

    first_func = functions[0]
    line = first_func.get('line', 0) if isinstance(first_func, dict) else 0
    if line:
        print(f"      reveal {path} :{line}       # Extract at line number")
        return 1

    return 0


def _suggest_ordinal_extraction(path, structure, hints_shown):
    """Suggest ordinal extraction for files with many elements.

    Returns:
        Number of hints shown (0 or 1) — 0 if the show-once hint was
        already seen, so it doesn't eat into the 2-hint display budget on
        repeat calls.
    """
    if hints_shown >= 2:
        return 0

    total = sum(len(v) for v in structure.values() if isinstance(v, list))
    if total > 5:
        shown = _show_hint_once('ordinal_extraction', [
            f"      reveal {path} @3           # Extract 3rd element",
        ])
        return 1 if shown else 0

    return 0


def _suggest_imports_analysis(path, file_type, structure):
    """Suggest imports:// for files with many imports."""
    if 'imports' not in structure:
        return

    import_count = len(structure.get('imports', []))
    if import_count > 5 and file_type in ('python', 'javascript', 'typescript'):
        print(f"      reveal 'imports://{path}'   # ({import_count} imports)")


def _suggest_ast_queries_for_large_file(path, file_type, structure):
    """Suggest AST queries for large files.

    Returns:
        True if this is a large file of a matching type (caller should skip
        other hints) — True regardless of whether the show-once text was
        actually printed this call, since "is a large file" is a fact about
        the file, not about what's already been shown this install.
    """
    total = sum(len(v) for v in structure.values() if isinstance(v, list))
    large_file_types = ('python', 'javascript', 'typescript', 'rust', 'go')

    if total > 20 and file_type in large_file_types:
        _show_hint_once('large_file_ast_queries', [
            f"      reveal 'ast://{path}?complexity>10'   # Find complex functions",
            f"      reveal 'ast://{path}?lines>50'        # Find large elements",
            f"      reveal {path} --check      # Check code quality",
        ])
        return True

    return False


def _handle_typed(path, file_type, **kwargs):
    """Handle 'typed' (outline) context breadcrumbs."""
    element_placeholder = get_element_placeholder(file_type)
    _show_hint_once('typed_extract_element', [
        f"Next: reveal {path} {element_placeholder}   # Extract specific element",
        f"      reveal {path}              # See flat structure",
    ])
    _print_typed_hints(path, file_type)


def _handle_element(path, file_type, **kwargs):
    """Handle 'element' context breadcrumbs."""
    element_name = kwargs.get('element_name', '')
    line_count = kwargs.get('line_count', 0)
    line_start = kwargs.get('line_start', 0)

    info = f"Extracted {element_name}"
    if line_count:
        info += f" ({line_count} lines)"

    print(info)
    _show_hint_once('element_back_to_structure', [
        f"  → Back: reveal {path}          # See full structure",
    ])

    # Suggest line-based extraction for navigating to nearby elements
    if line_start and file_type in _CODE_TYPES:
        print(f"  → Nearby: reveal {path} :{line_start + line_count + 5}  # Next element")
    else:
        _show_hint_once('element_check_fallback', [
            f"  → Check: reveal {path} --check # Quality analysis",
        ])


def _handle_quality_check(path, file_type, **kwargs):
    """Handle 'quality-check' context breadcrumbs."""
    detections = kwargs.get('detections', [])

    if not detections:
        _show_hint_once('quality_check_clean', [
            f"Next: reveal {path}              # See structure",
            f"      reveal {path} --outline    # Nested hierarchy",
        ])
        return

    # Find complex functions from C901/C902 detections
    complex_elements = _extract_complex_elements(detections)

    if complex_elements:
        print(f"Next: reveal {path} {complex_elements[0]}   # View complex function")
    else:
        _show_hint_once('quality_check_see_structure', [
            f"Next: reveal {path}              # See structure",
        ])

    _show_hint_once('quality_check_trailer', [
        f"      reveal stats://{path}      # Analyze complexity trends",
        "      reveal help://rules        # Learn about rules",
    ])


def _extract_complex_elements(detections):
    """Extract function names from complexity-related detections."""
    complexity_rules = ('C901', 'C902')
    complex_elements = []

    for d in detections:
        if d.rule_code in complexity_rules and d.context:
            match = re.search(r'Function:\s*(\w+)', d.context)
            if match:
                complex_elements.append(match.group(1))

    return complex_elements


def _handle_directory_check(path, file_type, **kwargs):
    """Handle 'directory-check' context breadcrumbs (pre-commit workflow)."""
    total_issues = kwargs.get('total_issues', 0)
    files_checked = kwargs.get('files_checked', 0)

    print()

    if total_issues > 0:
        _show_hint_once('directory_check_workflow_issues', [
            "Pre-Commit Workflow:",
            f"  1. Fix the {total_issues} issues above",
            "  2. reveal diff://git://HEAD/.:.     # Review all changes",
            f"  3. reveal stats://{path}            # Check complexity trends",
        ])
    else:
        _show_hint_once('directory_check_workflow_clean', [
            "Pre-Commit Workflow:",
            f"  ✅ All {files_checked} files clean",
            "  1. reveal diff://git://HEAD/.:.     # Review staged changes",
            "  2. git commit                       # Ready to commit",
        ])


# Dispatch table for context handlers
_CONTEXT_HANDLERS = {
    'metadata': _handle_metadata,
    'structure': _handle_structure,
    'typed': _handle_typed,
    'element': _handle_element,
    'quality-check': _handle_quality_check,
    'directory-check': _handle_directory_check,
}


def print_breadcrumbs(context, path, file_type=None, config=None, **kwargs):
    """Print navigation breadcrumbs with reveal command suggestions.

    Args:
        context: 'structure', 'element', 'metadata', 'typed', 'quality-check',
                 or 'directory-check'
        path: File or directory path
        file_type: Optional file type for context-specific suggestions
        config: Optional RevealConfig instance (if None, loads default)
        **kwargs: Additional context (element_name, line_count, detections, etc.)
    """
    if config is None:
        config = _get_config_for_path(path)

    if not config.is_breadcrumbs_enabled():
        return

    _show_breadcrumb_hint_once()
    print()  # Blank line before breadcrumbs

    handler = _CONTEXT_HANDLERS.get(context)
    if handler:
        handler(path, file_type, **kwargs)
