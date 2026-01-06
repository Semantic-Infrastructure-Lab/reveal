"""Breadcrumb system for agent-friendly navigation hints."""
import re

# File type groupings for consistent suggestions
_CODE_TYPES = frozenset(['python', 'javascript', 'typescript', 'rust', 'go', 'bash', 'gdscript'])
_CONFIG_TYPES = frozenset(['yaml', 'json', 'toml', 'jsonl'])
_INFRA_TYPES = frozenset(['dockerfile', 'nginx'])


def get_element_placeholder(file_type):
    """Get appropriate element placeholder for file type.

    Args:
        file_type: File type string (e.g., 'python', 'yaml')

    Returns:
        String placeholder like '<function>', '<key>', etc.
    """
    mapping = {
        'python': '<function>',
        'javascript': '<function>',
        'typescript': '<function>',
        'rust': '<function>',
        'go': '<function>',
        'bash': '<function>',
        'gdscript': '<function>',
        'yaml': '<key>',
        'json': '<key>',
        'jsonl': '<entry>',
        'toml': '<key>',
        'markdown': '<heading>',
        'html': '<element>',
        'dockerfile': '<instruction>',
        'nginx': '<directive>',
        'jupyter': '<cell>',
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
        'PythonAnalyzer': 'python',
        'JavaScriptAnalyzer': 'javascript',
        'TypeScriptAnalyzer': 'typescript',
        'RustAnalyzer': 'rust',
        'GoAnalyzer': 'go',
        'BashAnalyzer': 'bash',
        'MarkdownAnalyzer': 'markdown',
        'YamlAnalyzer': 'yaml',
        'JsonAnalyzer': 'json',
        'JsonlAnalyzer': 'jsonl',
        'TomlAnalyzer': 'toml',
        'DockerfileAnalyzer': 'dockerfile',
        'NginxAnalyzer': 'nginx',
        'GDScriptAnalyzer': 'gdscript',
        'JupyterAnalyzer': 'jupyter',
        'HtmlAnalyzer': 'html',
        'TreeSitterAnalyzer': None,  # Generic fallback
    }
    return mapping.get(class_name, None)


def _get_config_for_path(path):
    """Load config for the given path."""
    from pathlib import Path as PathLib
    from reveal.config import RevealConfig

    file_path = PathLib(path) if isinstance(path, str) else path
    start_path = file_path.parent if file_path.is_file() else file_path
    return RevealConfig.get(start_path=start_path)


def _print_type_specific_hints(path, file_type):
    """Print file-type-specific command hints."""
    if file_type in _CODE_TYPES:
        print(f"      reveal {path} --check      # Check code quality")
        print(f"      reveal {path} --outline    # Nested structure")
    elif file_type == 'markdown':
        print(f"      reveal {path} --links      # Extract links")
        print(f"      reveal {path} --code       # Extract code blocks")
        print(f"      reveal {path} --frontmatter # Extract YAML front matter")
    elif file_type == 'html':
        print(f"      reveal {path} --check      # Validate HTML")
        print(f"      reveal {path} --links      # Extract all links")
    elif file_type in _CONFIG_TYPES:
        print(f"      reveal {path} --check      # Validate syntax")
    elif file_type in _INFRA_TYPES:
        print(f"      reveal {path} --check      # Validate configuration")


def _print_typed_hints(path, file_type):
    """Print hints for typed/outline context (subset of structure hints)."""
    if file_type in _CODE_TYPES:
        print(f"      reveal {path} --check      # Check code quality")
    elif file_type == 'markdown':
        print(f"      reveal {path} --links      # Extract links")
    elif file_type == 'html':
        print(f"      reveal {path} --check      # Validate HTML")
        print(f"      reveal {path} --links      # Extract all links")
    elif file_type in _CONFIG_TYPES:
        print(f"      reveal {path} --check      # Validate syntax")
    elif file_type in _INFRA_TYPES:
        print(f"      reveal {path} --check      # Validate configuration")


# --- Context handlers ---

def _handle_metadata(path, file_type, **kwargs):
    """Handle 'metadata' context breadcrumbs."""
    print(f"Next: reveal {path}              # See structure")
    print(f"      reveal {path} --check      # Quality check")


def _handle_structure(path, file_type, **kwargs):
    """Handle 'structure' context breadcrumbs."""
    element_placeholder = get_element_placeholder(file_type)
    print(f"Next: reveal {path} {element_placeholder}   # Extract specific element")

    structure = kwargs.get('structure', {})

    # Suggest imports:// for files with many imports
    if structure and 'imports' in structure:
        import_count = len(structure.get('imports', []))
        if import_count > 5 and file_type in ('python', 'javascript', 'typescript'):
            print(f"      reveal 'imports://{path}'   # ({import_count} imports)")

    # Suggest AST queries for large files
    if structure:
        total = sum(len(v) for v in structure.values() if isinstance(v, list))
        large_file_types = ('python', 'javascript', 'typescript', 'rust', 'go')
        if total > 20 and file_type in large_file_types:
            print(f"      reveal 'ast://{path}?complexity>10'   # Find complex functions")
            print(f"      reveal 'ast://{path}?lines>50'        # Find large elements")
            print(f"      reveal {path} --check      # Check code quality")
            return  # Skip standard suggestions for large files

    _print_type_specific_hints(path, file_type)


def _handle_typed(path, file_type, **kwargs):
    """Handle 'typed' (outline) context breadcrumbs."""
    element_placeholder = get_element_placeholder(file_type)
    print(f"Next: reveal {path} {element_placeholder}   # Extract specific element")
    print(f"      reveal {path}              # See flat structure")
    _print_typed_hints(path, file_type)


def _handle_element(path, file_type, **kwargs):
    """Handle 'element' context breadcrumbs."""
    element_name = kwargs.get('element_name', '')
    line_count = kwargs.get('line_count', '')

    info = f"Extracted {element_name}"
    if line_count:
        info += f" ({line_count} lines)"

    print(info)
    print(f"  → Back: reveal {path}          # See full structure")
    print(f"  → Check: reveal {path} --check # Quality analysis")


def _handle_quality_check(path, file_type, **kwargs):
    """Handle 'quality-check' context breadcrumbs."""
    detections = kwargs.get('detections', [])

    if not detections:
        print(f"Next: reveal {path}              # See structure")
        print(f"      reveal {path} --outline    # Nested hierarchy")
        return

    # Find complex functions from C901/C902 detections
    complex_elements = _extract_complex_elements(detections)

    if complex_elements:
        print(f"Next: reveal {path} {complex_elements[0]}   # View complex function")
    else:
        print(f"Next: reveal {path}              # See structure")

    print(f"      reveal stats://{path}      # Analyze complexity trends")
    print(f"      reveal help://rules        # Learn about rules")


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
    print("Pre-Commit Workflow:")

    if total_issues > 0:
        print(f"  1. Fix the {total_issues} issues above")
        print(f"  2. reveal diff://git://HEAD/.:.     # Review all changes")
        print(f"  3. reveal stats://{path}            # Check complexity trends")
    else:
        print(f"  ✅ All {files_checked} files clean")
        print(f"  1. reveal diff://git://HEAD/.:.     # Review staged changes")
        print(f"  2. git commit                       # Ready to commit")


def _handle_code_review(path, file_type, **kwargs):
    """Handle 'code-review' context breadcrumbs."""
    print()
    print("Code Review Workflow:")
    print(f"  1. reveal stats://{path}            # Check complexity trends")
    print(f"  2. reveal imports://. --circular    # Check for new cycles")
    print(f"  3. reveal {path} --check            # Quality check changed files")


# Dispatch table for context handlers
_CONTEXT_HANDLERS = {
    'metadata': _handle_metadata,
    'structure': _handle_structure,
    'typed': _handle_typed,
    'element': _handle_element,
    'quality-check': _handle_quality_check,
    'directory-check': _handle_directory_check,
    'code-review': _handle_code_review,
}


def print_breadcrumbs(context, path, file_type=None, config=None, **kwargs):
    """Print navigation breadcrumbs with reveal command suggestions.

    Args:
        context: 'structure', 'element', 'metadata', 'typed', 'quality-check',
                 'directory-check', or 'code-review'
        path: File or directory path
        file_type: Optional file type for context-specific suggestions
        config: Optional RevealConfig instance (if None, loads default)
        **kwargs: Additional context (element_name, line_count, detections, etc.)
    """
    if config is None:
        config = _get_config_for_path(path)

    if not config.is_breadcrumbs_enabled():
        return

    print()  # Blank line before breadcrumbs

    handler = _CONTEXT_HANDLERS.get(context)
    if handler:
        handler(path, file_type, **kwargs)
