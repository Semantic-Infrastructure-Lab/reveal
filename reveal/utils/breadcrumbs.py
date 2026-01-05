"""Breadcrumb system for agent-friendly navigation hints."""


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
        'TreeSitterAnalyzer': None,  # Generic fallback
    }
    return mapping.get(class_name, None)


def print_breadcrumbs(context, path, file_type=None, **kwargs):
    """Print navigation breadcrumbs with reveal command suggestions.

    Args:
        context: 'structure', 'element', 'metadata', 'typed'
        path: File or directory path
        file_type: Optional file type for context-specific suggestions
        **kwargs: Additional context (element_name, line_count, etc.)
    """
    print()  # Blank line before breadcrumbs

    if context == 'metadata':
        print(f"Next: reveal {path}              # See structure")
        print(f"      reveal {path} --check      # Quality check")

    elif context == 'structure':
        element_placeholder = get_element_placeholder(file_type)
        print(f"Next: reveal {path} {element_placeholder}   # Extract specific element")

        if file_type in ['python', 'javascript', 'typescript', 'rust', 'go', 'bash', 'gdscript']:
            print(f"      reveal {path} --check      # Check code quality")
            print(f"      reveal {path} --outline    # Nested structure")
        elif file_type == 'markdown':
            print(f"      reveal {path} --links      # Extract links")
            print(f"      reveal {path} --code       # Extract code blocks")
            print(f"      reveal {path} --frontmatter # Extract YAML front matter")
        elif file_type in ['yaml', 'json', 'toml', 'jsonl']:
            print(f"      reveal {path} --check      # Validate syntax")
        elif file_type in ['dockerfile', 'nginx']:
            print(f"      reveal {path} --check      # Validate configuration")

    elif context == 'typed':
        # Outline/hierarchical view context
        element_placeholder = get_element_placeholder(file_type)
        print(f"Next: reveal {path} {element_placeholder}   # Extract specific element")
        print(f"      reveal {path}              # See flat structure")
        if file_type in ['python', 'javascript', 'typescript', 'rust', 'go', 'bash', 'gdscript']:
            print(f"      reveal {path} --check      # Check code quality")

    elif context == 'element':
        element_name = kwargs.get('element_name', '')
        line_count = kwargs.get('line_count', '')

        info = f"Extracted {element_name}"
        if line_count:
            info += f" ({line_count} lines)"

        print(info)
        print(f"  → Back: reveal {path}          # See full structure")
        print(f"  → Check: reveal {path} --check # Quality analysis")
