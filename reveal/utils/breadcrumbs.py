"""Breadcrumb system for agent-friendly navigation hints."""
import re


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


def print_breadcrumbs(context, path, file_type=None, config=None, **kwargs):
    """Print navigation breadcrumbs with reveal command suggestions.

    Args:
        context: 'structure', 'element', 'metadata', 'typed'
        path: File or directory path
        file_type: Optional file type for context-specific suggestions
        config: Optional RevealConfig instance (if None, loads default)
        **kwargs: Additional context (element_name, line_count, etc.)
    """
    # Check if breadcrumbs are enabled
    if config is None:
        from pathlib import Path as PathLib
        from reveal.config import RevealConfig
        # Get config for the file's directory
        file_path = PathLib(path) if isinstance(path, str) else path
        if file_path.is_file():
            config = RevealConfig.get(start_path=file_path.parent)
        else:
            config = RevealConfig.get(start_path=file_path)

    if not config.is_breadcrumbs_enabled():
        return  # Exit early if breadcrumbs are disabled

    print()  # Blank line before breadcrumbs

    if context == 'metadata':
        print(f"Next: reveal {path}              # See structure")
        print(f"      reveal {path} --check      # Quality check")

    elif context == 'structure':
        element_placeholder = get_element_placeholder(file_type)
        print(f"Next: reveal {path} {element_placeholder}   # Extract specific element")

        # Check structure for smart suggestions
        structure = kwargs.get('structure', {})

        # Check for many imports - suggest imports:// adapter
        if structure and 'imports' in structure:
            import_count = len(structure.get('imports', []))
            if import_count > 5 and file_type in ['python', 'javascript', 'typescript']:
                print(f"      reveal 'imports://{path}'   # Analyze dependencies ({import_count} imports)")

        # Check for large files - suggest AST queries for navigation
        if structure:
            total_elements = sum(len(items) for items in structure.values() if isinstance(items, list))
            if total_elements > 20 and file_type in ['python', 'javascript', 'typescript', 'rust', 'go']:
                # Large file - suggest AST queries for finding hotspots
                print(f"      reveal 'ast://{path}?complexity>10'   # Find complex functions")
                print(f"      reveal 'ast://{path}?lines>50'        # Find large elements")
                print(f"      reveal {path} --check      # Check code quality")
                return  # Skip standard suggestions for large files

        if file_type in ['python', 'javascript', 'typescript', 'rust', 'go', 'bash', 'gdscript']:
            print(f"      reveal {path} --check      # Check code quality")
            print(f"      reveal {path} --outline    # Nested structure")
        elif file_type == 'markdown':
            print(f"      reveal {path} --links      # Extract links")
            print(f"      reveal {path} --code       # Extract code blocks")
            print(f"      reveal {path} --frontmatter # Extract YAML front matter")
        elif file_type == 'html':
            print(f"      reveal {path} --check      # Validate HTML")
            print(f"      reveal {path} --links      # Extract all links")
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
        elif file_type == 'markdown':
            print(f"      reveal {path} --links      # Extract links")
        elif file_type == 'html':
            print(f"      reveal {path} --check      # Validate HTML")
            print(f"      reveal {path} --links      # Extract all links")
        elif file_type in ['yaml', 'json', 'toml', 'jsonl']:
            print(f"      reveal {path} --check      # Validate syntax")
        elif file_type in ['dockerfile', 'nginx']:
            print(f"      reveal {path} --check      # Validate configuration")

    elif context == 'element':
        element_name = kwargs.get('element_name', '')
        line_count = kwargs.get('line_count', '')

        info = f"Extracted {element_name}"
        if line_count:
            info += f" ({line_count} lines)"

        print(info)
        print(f"  → Back: reveal {path}          # See full structure")
        print(f"  → Check: reveal {path} --check # Quality analysis")

    elif context == 'quality-check':
        detections = kwargs.get('detections', [])

        if not detections:
            # No issues - suggest exploration
            print(f"Next: reveal {path}              # See structure")
            print(f"      reveal {path} --outline    # Nested hierarchy")
            return

        # Group detections by rule_code to find patterns
        rules = {}
        for d in detections:
            rule_code = d.rule_code
            if rule_code not in rules:
                rules[rule_code] = []
            rules[rule_code].append(d)

        # Check for complexity issues (C901, C902)
        complexity_rules = ['C901', 'C902']
        complex_elements = []
        for rule_code in complexity_rules:
            if rule_code in rules:
                for d in rules[rule_code]:
                    # Extract function name from context if available
                    if d.context:
                        # Context format: "Function: name" or "Function: name (N lines)"
                        match = re.search(r'Function:\s*(\w+)', d.context)
                        if match:
                            complex_elements.append(match.group(1))

        if complex_elements:
            # Suggest viewing the first complex element
            print(f"Next: reveal {path} {complex_elements[0]}   # View complex function")
        else:
            print(f"Next: reveal {path}              # See structure")

        print(f"      reveal stats://{path}      # Analyze complexity trends")
        print(f"      reveal help://rules        # Learn about rules")

    elif context == 'directory-check':
        # Pre-commit workflow - after checking a directory
        total_issues = kwargs.get('total_issues', 0)
        files_with_issues = kwargs.get('files_with_issues', 0)
        files_checked = kwargs.get('files_checked', 0)

        if total_issues > 0:
            # Issues found - suggest fixes
            print()
            print("Pre-Commit Workflow:")
            print(f"  1. Fix the {total_issues} issues above")
            print(f"  2. reveal diff://git://HEAD/.:.     # Review all changes")
            print(f"  3. reveal stats://{path}            # Check complexity trends")
        else:
            # Clean - suggest commit
            print()
            print("Pre-Commit Workflow:")
            print(f"  ✅ All {files_checked} files clean")
            print(f"  1. reveal diff://git://HEAD/.:.     # Review staged changes")
            print(f"  2. git commit                       # Ready to commit")

    elif context == 'code-review':
        # After viewing a diff with git refs
        left_ref = kwargs.get('left_ref', 'HEAD')
        right_ref = kwargs.get('right_ref', 'working tree')

        print()
        print("Code Review Workflow:")
        print(f"  1. reveal stats://{path}            # Check complexity trends")
        print(f"  2. reveal imports://. --circular    # Check for new cycles")
        print(f"  3. reveal {path} --check            # Quality check changed files")
