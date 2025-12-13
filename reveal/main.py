"""Clean, simple CLI for reveal."""

import sys
import os
import argparse
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from .base import get_analyzer, get_all_analyzers, FileAnalyzer
from .tree_view import show_directory_tree
from . import __version__


def copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard.

    Uses native clipboard utilities without external dependencies.
    Supports: xclip, xsel (Linux), pbcopy (macOS), clip (Windows), wl-copy (Wayland).

    Args:
        text: Text to copy to clipboard

    Returns:
        True if successful, False otherwise
    """
    # Try clipboard utilities in order of preference
    clipboard_cmds = [
        ['xclip', '-selection', 'clipboard'],  # Linux X11
        ['xsel', '--clipboard', '--input'],     # Linux X11 alternative
        ['wl-copy'],                             # Linux Wayland
        ['pbcopy'],                              # macOS
        ['clip'],                                # Windows
    ]

    for cmd in clipboard_cmds:
        if shutil.which(cmd[0]):
            try:
                process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                process.communicate(input=text.encode('utf-8'))
                if process.returncode == 0:
                    return True
            except (subprocess.SubprocessError, OSError):
                continue

    return False



# ============================================================================
# Breadcrumb System - Agent-Friendly Navigation Hints
# ============================================================================

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
        context: 'structure', 'element', 'metadata'
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


def check_for_updates():
    """Check PyPI for newer version (once per day, non-blocking).

    - Checks at most once per day (cached in ~/.config/reveal/last_update_check)
    - 1-second timeout (doesn't slow down CLI)
    - Fails silently (no errors shown to user)
    - Opt-out: Set REVEAL_NO_UPDATE_CHECK=1 environment variable
    """
    # Opt-out check
    if os.environ.get('REVEAL_NO_UPDATE_CHECK'):
        return

    try:
        # Setup cache directory (platform-appropriate)
        if sys.platform == 'win32':
            # Windows: Use %LOCALAPPDATA%\reveal
            cache_dir = Path(os.getenv('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'reveal'
        else:
            # Unix/macOS: Use ~/.config/reveal
            cache_dir = Path.home() / '.config' / 'reveal'
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / 'last_update_check'

        # Check if we should update (once per day)
        if cache_file.exists():
            last_check_str = cache_file.read_text().strip()
            try:
                last_check = datetime.fromisoformat(last_check_str)
                if datetime.now() - last_check < timedelta(days=1):
                    return  # Checked recently, skip
            except (ValueError, OSError):
                pass  # Invalid cache, continue with check

        # Check PyPI (using urllib to avoid new dependencies)
        import urllib.request
        import json

        req = urllib.request.Request(
            'https://pypi.org/pypi/reveal-cli/json',
            headers={'User-Agent': f'reveal-cli/{__version__}'}
        )

        with urllib.request.urlopen(req, timeout=1) as response:
            data = json.loads(response.read().decode('utf-8'))
            latest_version = data['info']['version']

        # Update cache file
        cache_file.write_text(datetime.now().isoformat())

        # Compare versions (simple string comparison works for semver)
        if latest_version != __version__:
            # Parse versions for proper comparison
            def parse_version(v):
                return tuple(map(int, v.split('.')))

            try:
                if parse_version(latest_version) > parse_version(__version__):
                    print(f"⚠️  Update available: reveal {latest_version} (you have {__version__})")
                    print(f"Update available: pip install --upgrade reveal-cli\n")
            except (ValueError, AttributeError):
                pass  # Version comparison failed, ignore

    except Exception:
        # Fail silently - don't interrupt user's workflow
        pass


def main():
    """Main CLI entry point."""
    import io

    # Fix Windows console encoding for emoji/unicode support
    if sys.platform == 'win32':
        # Set environment variable for subprocess compatibility
        os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
        # Reconfigure stdout/stderr to use UTF-8 with error handling
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    # Check for --copy flag early (before full parsing)
    copy_mode = '--copy' in sys.argv or '-c' in sys.argv

    if copy_mode:
        # Capture stdout while still displaying it (tee behavior)
        captured_output = io.StringIO()
        original_stdout = sys.stdout

        class TeeWriter:
            """Write to both original stdout and capture buffer."""
            def __init__(self, original, capture):
                self.original = original
                self.capture = capture

            def write(self, data):
                self.original.write(data)
                self.capture.write(data)

            def flush(self):
                self.original.flush()

            # Support attributes like encoding, isatty, etc.
            def __getattr__(self, name):
                return getattr(self.original, name)

        sys.stdout = TeeWriter(original_stdout, captured_output)

    try:
        _main_impl()
    except BrokenPipeError:
        # Python flushes standard streams on exit; redirect remaining output
        # to devnull to avoid another BrokenPipeError at shutdown
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(0)  # Exit cleanly
    finally:
        if copy_mode:
            sys.stdout = original_stdout
            output_text = captured_output.getvalue()
            if output_text:
                if copy_to_clipboard(output_text):
                    print(f"\n📋 Copied {len(output_text)} chars to clipboard", file=sys.stderr)
                else:
                    print("\n⚠️  Could not copy to clipboard (no clipboard utility found)", file=sys.stderr)
                    print("   Install xclip, xsel (Linux), or use pbcopy (macOS)", file=sys.stderr)


def handle_uri(uri: str, element: Optional[str], args) -> None:
    """Handle URI-based resources (env://, https://, etc.).

    Args:
        uri: Full URI (e.g., env://, env://PATH)
        element: Optional element to extract
        args: Parsed command line arguments
    """
    # Parse URI
    if '://' not in uri:
        print(f"Error: Invalid URI format: {uri}", file=sys.stderr)
        sys.exit(1)

    scheme, resource = uri.split('://', 1)

    # Look up adapter from registry (pluggable!)
    from .adapters.base import get_adapter_class, list_supported_schemes
    from .adapters import env, ast, help, python, json_adapter, reveal  # Import to trigger registration

    adapter_class = get_adapter_class(scheme)
    if not adapter_class:
        print(f"Error: Unsupported URI scheme: {scheme}://", file=sys.stderr)
        schemes = ', '.join(f"{s}://" for s in list_supported_schemes())
        print(f"Supported schemes: {schemes}", file=sys.stderr)
        sys.exit(1)

    # Dispatch to adapter-specific handler
    _handle_adapter(adapter_class, scheme, resource, element, args)


def _handle_adapter(adapter_class: type, scheme: str, resource: str,
                    element: Optional[str], args) -> None:
    """Handle adapter-specific logic for different URI schemes.

    Args:
        adapter_class: The adapter class to instantiate
        scheme: URI scheme (env, ast, etc.)
        resource: Resource part of URI
        element: Optional element to extract
        args: CLI arguments
    """
    # Adapter-specific initialization and rendering
    if scheme == 'env':
        adapter = adapter_class()

        if element or resource:
            # Get specific variable (element takes precedence)
            var_name = element if element else resource
            result = adapter.get_element(var_name, show_secrets=False)

            if result is None:
                print(f"Error: Environment variable '{var_name}' not found", file=sys.stderr)
                sys.exit(1)

            render_env_variable(result, args.format)
        else:
            # Get all variables
            result = adapter.get_structure(show_secrets=False)
            render_env_structure(result, args.format)

    elif scheme == 'ast':
        # Parse path and query from resource
        if '?' in resource:
            path, query = resource.split('?', 1)
        else:
            path = resource
            query = None

        # Default to current directory if no path
        if not path:
            path = '.'

        adapter = adapter_class(path, query)
        result = adapter.get_structure()
        render_ast_structure(result, args.format)

    elif scheme == 'help':
        adapter = adapter_class(resource)

        if element or resource:
            # Get specific help topic (element takes precedence)
            topic = element if element else resource
            result = adapter.get_element(topic)

            if result is None:
                print(f"Error: Help topic '{topic}' not found", file=sys.stderr)
                available = adapter.get_structure()
                print(f"\nAvailable topics: {', '.join(available['available_topics'])}", file=sys.stderr)
                sys.exit(1)

            render_help(result, args.format)
        else:
            # List all help topics
            result = adapter.get_structure()
            render_help(result, args.format, list_mode=True)

    elif scheme == 'python':
        adapter = adapter_class()

        if element or resource:
            # Get specific Python runtime element (element takes precedence)
            element_name = element if element else resource
            result = adapter.get_element(element_name)

            if result is None:
                print(f"Error: Python element '{element_name}' not found", file=sys.stderr)
                print(f"\nAvailable elements: version, env, venv, packages, imports, debug/bytecode", file=sys.stderr)
                sys.exit(1)

            render_python_element(result, args.format)
        else:
            # Get overview
            result = adapter.get_structure()
            render_python_structure(result, args.format)

    elif scheme == 'json':
        # Parse path and query from resource
        if '?' in resource:
            path, query = resource.split('?', 1)
        else:
            path = resource
            query = None

        try:
            adapter = adapter_class(path, query)
            result = adapter.get_structure()
            render_json_result(result, args.format)
        except ValueError as e:
            # User error (e.g., wrong file type) - show friendly message without traceback
            print(str(e), file=sys.stderr)
            sys.exit(1)

    elif scheme == 'reveal':
        # reveal:// - Self-inspection
        adapter = adapter_class(resource if resource else None)
        result = adapter.get_structure()
        render_reveal_structure(result, args.format)


def render_reveal_structure(data: Dict[str, Any], output_format: str) -> None:
    """Render reveal:// adapter result.

    Args:
        data: Result from reveal adapter
        output_format: Output format (text, json)
    """
    import json as json_module

    if output_format == 'json':
        print(json_module.dumps(data, indent=2))
        return

    # Text format - show structure nicely
    print("Reveal Internal Structure\n")

    # Analyzers
    analyzers = data.get('analyzers', [])
    print(f"Analyzers ({len(analyzers)}):")
    for analyzer in analyzers:
        print(f"  • {analyzer['name']:<20} ({analyzer['path']})")

    # Adapters
    adapters = data.get('adapters', [])
    print(f"\nAdapters ({len(adapters)}):")
    for adapter in adapters:
        help_marker = '✓' if adapter.get('has_help') else ' '
        print(f"  {help_marker} {adapter['scheme'] + '://':<15} ({adapter['class']})")

    # Rules
    rules = data.get('rules', [])
    print(f"\nRules ({len(rules)}):")
    # Group by category
    by_category = {}
    for rule in rules:
        category = rule.get('category', 'unknown')
        if category not in by_category:
            by_category[category] = []
        by_category[category].append(rule)

    for category in sorted(by_category.keys()):
        rules_in_cat = by_category[category]
        codes = ', '.join(r['code'] for r in rules_in_cat)
        print(f"  • {category:<15} ({len(rules_in_cat):2}): {codes}")

    # Metadata
    metadata = data.get('metadata', {})
    print(f"\nMetadata:")
    print(f"  Root: {metadata.get('root')}")
    print(f"  Total: {metadata.get('analyzers_count')} analyzers, "
          f"{metadata.get('adapters_count')} adapters, "
          f"{metadata.get('rules_count')} rules")


def render_json_result(data: Dict[str, Any], output_format: str) -> None:
    """Render JSON adapter result.

    Args:
        data: Result from JSON adapter
        output_format: Output format (text, json)
    """
    import json as json_module

    result_type = data.get('type', 'unknown')

    if output_format == 'json':
        print(json_module.dumps(data, indent=2))
        return

    # Handle errors
    if result_type == 'json-error':
        print(f"Error: {data.get('error', 'Unknown error')}", file=sys.stderr)
        if 'valid_queries' in data:
            print(f"Valid queries: {', '.join(data['valid_queries'])}", file=sys.stderr)
        sys.exit(1)

    # Text format rendering
    file_path = data.get('file', '')
    json_path = data.get('path', '(root)')

    if result_type == 'json-value':
        value = data.get('value')
        value_type = data.get('value_type', '')
        print(f"File: {file_path}")
        print(f"Path: {json_path}")
        print(f"Type: {value_type}")
        print()
        if isinstance(value, (dict, list)):
            print(json_module.dumps(value, indent=2))
        else:
            print(value)

    elif result_type == 'json-schema':
        schema = data.get('schema', {})
        print(f"File: {file_path}")
        print(f"Path: {json_path}")
        print()
        print("Schema:")
        print(json_module.dumps(schema, indent=2))

    elif result_type == 'json-flatten':
        print(f"# File: {file_path}")
        print(f"# Path: {json_path}")
        print()
        for line in data.get('lines', []):
            print(line)

    elif result_type == 'json-type':
        print(f"File: {file_path}")
        print(f"Path: {json_path}")
        print(f"Type: {data.get('value_type', 'unknown')}")
        if data.get('length') is not None:
            print(f"Length: {data['length']}")

    elif result_type == 'json-keys':
        print(f"File: {file_path}")
        print(f"Path: {json_path}")
        print(f"Count: {data.get('count', 0)}")
        print()
        if 'keys' in data:
            for key in data['keys']:
                print(f"  {key}")
        elif 'indices' in data:
            print(f"  [0..{data['count'] - 1}]")

    elif result_type == 'json-length':
        print(f"File: {file_path}")
        print(f"Path: {json_path}")
        print(f"Type: {data.get('value_type', 'unknown')}")
        print(f"Length: {data.get('length', 0)}")

    else:
        # Fallback: just dump as JSON
        print(json_module.dumps(data, indent=2))


def render_env_structure(data: Dict[str, Any], output_format: str) -> None:
    """Render environment variables structure.

    Args:
        data: Environment data from adapter
        output_format: Output format (text, json, grep)
    """
    if output_format == 'json':
        import json
        print(json.dumps(data, indent=2))
        return

    # Text format
    print(f"Environment Variables ({data['total_count']})")
    print()

    for category, variables in data['categories'].items():
        if not variables:
            continue

        print(f"{category} ({len(variables)}):")
        for var in variables:
            sensitive_marker = " (sensitive)" if var['sensitive'] else ""
            if output_format == 'grep':
                # grep format: env://VAR_NAME:value
                print(f"env://{var['name']}:{var['value']}")
            else:
                # text format
                print(f"  {var['name']:<30s} {var['value']}{sensitive_marker}")
        print()


def render_env_variable(data: Dict[str, Any], output_format: str) -> None:
    """Render single environment variable.

    Args:
        data: Variable data from adapter
        output_format: Output format (text, json, grep)
    """
    if output_format == 'json':
        import json
        print(json.dumps(data, indent=2))
        return

    if output_format == 'grep':
        print(f"env://{data['name']}:{data['value']}")
        return

    # Text format
    print(f"Environment Variable: {data['name']}")
    print(f"Category: {data['category']}")
    print(f"Value: {data['value']}")
    if data['sensitive']:
        print(f"⚠️  Sensitive: This variable appears to contain sensitive data")
        print(f"    Use --show-secrets to display actual value")
    print(f"Length: {data['length']} characters")


def render_ast_structure(data: Dict[str, Any], output_format: str) -> None:
    """Render AST query results.

    Args:
        data: AST query results from adapter
        output_format: Output format (text, json, grep)
    """
    if output_format == 'json':
        import json
        print(json.dumps(data, indent=2))
        return

    # Text/grep format
    query = data.get('query', 'none')
    total_files = data.get('total_files', 0)
    total_results = data.get('total_results', 0)
    results = data.get('results', [])

    if output_format == 'grep':
        # grep format: file:line:name
        for result in results:
            file_path = result.get('file', '')
            line = result.get('line', 0)
            name = result.get('name', '')
            print(f"{file_path}:{line}:{name}")
        return

    # Text format
    print(f"AST Query: {data.get('path', '.')}")
    if query != 'none':
        print(f"Filter: {query}")
    print(f"Files scanned: {total_files}")
    print(f"Results: {total_results}")
    print()

    if not results:
        print("No matches found.")
        return

    # Group by file
    by_file = {}
    for result in results:
        file_path = result.get('file', '')
        if file_path not in by_file:
            by_file[file_path] = []
        by_file[file_path].append(result)

    # Render grouped results
    for file_path, elements in sorted(by_file.items()):
        print(f"📄 {file_path}")
        for elem in elements:
            category = elem.get('category', 'unknown')
            name = elem.get('name', '')
            line = elem.get('line', 0)
            line_count = elem.get('line_count', 0)
            complexity = elem.get('complexity')

            # Format output
            if complexity:
                print(f"  {file_path}:{line:>4}  {name} [{line_count} lines, complexity: {complexity}]")
            else:
                print(f"  {file_path}:{line:>4}  {name} [{line_count} lines]")

        print()


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
        print(f"  → reveal help://{related_adapters[0]}  # Related adapter")
        if len(related_adapters) > 1:
            print(f"  → reveal help://{related_adapters[1]}  # Another option")
        print("  → reveal .                   # Start exploring your code")
        print()

    # Point to deeper content
    print("## Go Deeper")
    print("  → reveal help://tricks         # Power user workflows")
    print("  → reveal help://anti-patterns  # Common mistakes to avoid")
    print()


def _render_help_list_mode(data: Dict[str, Any]) -> None:
    """Render help system topic list (reveal help://)."""
    print("# Reveal Help System")
    print()
    print(f"Available help topics ({len(data['available_topics'])} total):")
    print()

    # Group topics
    adapters = [a for a in data.get('adapters', []) if a.get('has_help')]
    static = data.get('static_guides', [])

    if adapters:
        print("## URI Adapters")
        for adapter in adapters:
            scheme = adapter['scheme']
            desc = adapter.get('description', 'No description')
            print(f"  {scheme:12} - {desc}")
            print(f"               Usage: reveal help://{scheme}")
        print()

    if static:
        print("## Guides")
        for topic in static:
            print(f"  {topic:12} - Static guide")
            print(f"               Usage: reveal help://{topic}")
        print()

    print("Examples:")
    print("  reveal help://ast         # Learn about ast:// adapter")
    print("  reveal help://adapters    # Summary of all adapters")
    print("  reveal help://agent       # Agent usage patterns")
    print()
    print("Alternative: Use --agent-help and --agent-help-full flags (llms.txt convention)")


def _render_help_static_guide(data: Dict[str, Any]) -> None:
    """Render static guide from markdown file."""
    if 'error' in data:
        print(f"Error: {data['message']}", file=sys.stderr)
        sys.exit(1)
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
            print(f"❌ {ap['bad']}")
            print(f"✅ {ap['good']}")
            if ap.get('why'):
                print(f"   Why: {ap['why']}")
            print()

    # Breadcrumbs for section views
    print("---")
    print()
    print(f"## See Full Help")
    print(f"  → reveal help://{adapter}")
    print()


def _render_help_adapter_specific(data: Dict[str, Any]) -> None:
    """Render adapter-specific help documentation."""
    if 'error' in data:
        print(f"Error: {data['message']}", file=sys.stderr)
        sys.exit(1)

    scheme = data.get('scheme', data.get('name', ''))
    print(f"# {scheme}:// - {data.get('description', '')}")
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
            print(f"  • {feature}")
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
                print(f"    → {ex['description']}")
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
            print(f"  ❌ {ap['bad']}")
            print(f"  ✅ {ap['good']}")
            if ap.get('why'):
                print(f"     Why: {ap['why']}")
            print()

    if data.get('notes'):
        print("## Notes")
        for note in data['notes']:
            print(f"  • {note}")
        print()

    if data.get('output_formats'):
        print(f"**Output formats:** {', '.join(data['output_formats'])}")
        print()

    if data.get('see_also'):
        print("## See Also")
        for item in data['see_also']:
            print(f"  • {item}")
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
        import json
        print(json.dumps(data, indent=2))
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


def render_python_structure(data: Dict[str, Any], output_format: str) -> None:
    """Render Python environment overview.

    Args:
        data: Python environment data from adapter
        output_format: Output format (text, json, grep)
    """
    if output_format == 'json':
        import json
        print(json.dumps(data, indent=2))
        return

    # Text format
    print(f"Python Environment")
    print()
    print(f"Version:        {data['version']} ({data['implementation']})")
    print(f"Executable:     {data['executable']}")
    print(f"Platform:       {data['platform']} ({data['architecture']})")
    print()

    # Virtual environment
    venv = data['virtual_env']
    if venv['active']:
        print(f"Virtual Env:    ✓ Active")
        print(f"  Path:         {venv['path']}")
        print(f"  Type:         {venv.get('type', 'venv')}")
    else:
        print(f"Virtual Env:    ✗ Not active")
    print()

    print(f"Packages:       {data['packages_count']} installed")
    print(f"Modules:        {data['modules_loaded']} loaded")


def _render_python_packages(data: Dict[str, Any]) -> None:
    """Render list of installed packages."""
    print(f"Installed Packages ({data['count']})")
    print()
    for pkg in data['packages']:
        print(f"  {pkg['name']:<30s} {pkg['version']:<15s} {pkg['location']}")


def _render_python_modules(data: Dict[str, Any]) -> None:
    """Render list of loaded modules."""
    print(f"Loaded Modules ({data['count']})")
    print()
    for mod in data['loaded'][:50]:  # Limit to first 50
        file_info = f" ({mod['file']})" if mod['file'] else " (built-in)"
        print(f"  {mod['name']}{file_info}")
    if data['count'] > 50:
        print(f"\n  ... and {data['count'] - 50} more modules")


def _render_python_doctor(data: Dict[str, Any]) -> None:
    """Render Python environment health diagnostics."""
    status_icon = "✓" if data['status'] == 'healthy' else "⚠️"
    print(f"Python Environment Health: {status_icon} {data['status'].upper()}")
    print(f"Health Score: {data['health_score']}/100")
    print()

    if data.get('issues'):
        print(f"Issues ({len(data['issues'])}):")
        for issue in data['issues']:
            print(f"  ❌ [{issue['category']}] {issue['message']}")
            if 'impact' in issue:
                print(f"     Impact: {issue['impact']}")
        print()

    if data.get('warnings'):
        print(f"Warnings ({len(data['warnings'])}):")
        for warn in data['warnings']:
            print(f"  ⚠️  [{warn['category']}] {warn['message']}")
            if 'impact' in warn:
                print(f"     Impact: {warn['impact']}")
        print()

    if data.get('info'):
        print(f"Info ({len(data['info'])}):")
        for info in data['info']:
            print(f"  ℹ️  [{info['category']}] {info['message']}")
        print()

    if data.get('recommendations'):
        print(f"Recommendations ({len(data['recommendations'])}):")
        for rec in data['recommendations']:
            print(f"  💡 {rec['message']}")
            if 'commands' in rec:
                for cmd in rec['commands']:
                    print(f"     $ {cmd}")
        print()

    print(f"Checks performed: {', '.join(data['checks_performed'])}")


def _render_python_bytecode(data: Dict[str, Any]) -> None:
    """Render bytecode debugging information."""
    print(f"Bytecode Check: {data['status'].upper()}")
    print()

    if data['issues']:
        print(f"Found {len(data['issues'])} issues:")
        print()
        for issue in data['issues']:
            severity_marker = "⚠️ " if issue['severity'] == 'warning' else "ℹ️ "
            print(f"{severity_marker} {issue['type']}")
            print(f"   File: {issue.get('file', issue.get('pyc_file', 'unknown'))}")
            print(f"   Problem: {issue['problem']}")
            print(f"   Fix: {issue['fix']}")
            print()
    else:
        print("✓ No bytecode issues found")


def _render_python_env_config(data: Dict[str, Any]) -> None:
    """Render Python environment configuration details."""
    print("Python Environment Configuration")
    print()

    venv = data['virtual_env']
    if venv['active']:
        print(f"Virtual Environment: ✓ Active")
        print(f"  Path: {venv['path']}")
        print(f"  Type: {venv.get('type', 'venv')}")
    else:
        print(f"Virtual Environment: ✗ Not active")
    print()

    print(f"sys.path ({data['sys_path_count']} entries):")
    for path in data['sys_path']:
        print(f"  {path}")
    print()

    print("Flags:")
    for flag, value in data['flags'].items():
        print(f"  {flag}: {value}")


def _render_python_version(data: Dict[str, Any]) -> None:
    """Render Python version details."""
    print("Python Version Details")
    print()
    print(f"Version:        {data['version']}")
    print(f"Implementation: {data['implementation']}")
    print(f"Compiler:       {data['compiler']}")
    print(f"Build:          {data['build_number']} ({data['build_date']})")
    print(f"Executable:     {data['executable']}")
    print(f"Prefix:         {data['prefix']}")
    print(f"Base Prefix:    {data['base_prefix']}")
    print(f"Platform:       {data['platform']} ({data['architecture']})")


def _render_python_venv_status(data: Dict[str, Any]) -> None:
    """Render virtual environment status."""
    print("Virtual Environment Status")
    print()
    if data['active']:
        print(f"Status:    ✓ Active")
        print(f"Path:      {data['path']}")
        print(f"Type:      {data.get('type', 'venv')}")
        if 'prompt' in data:
            print(f"Prompt:    {data['prompt']}")
        if 'python_version' in data:
            print(f"Python:    {data['python_version']}")
    else:
        print(f"Status:    ✗ Not active")
        print()
        print("No virtual environment detected.")
        print("Checked: VIRTUAL_ENV, sys.prefix, CONDA_DEFAULT_ENV")


def _render_python_package_details(data: Dict[str, Any]) -> None:
    """Render individual package details."""
    print(f"Package: {data['name']}")
    print()
    print(f"Version:    {data['version']}")
    print(f"Location:   {data['location']}")
    if 'summary' in data:
        print(f"Summary:    {data.get('summary', 'N/A')}")
    if 'author' in data:
        print(f"Author:     {data.get('author', 'N/A')}")
    if 'license' in data:
        print(f"License:    {data.get('license', 'N/A')}")
    if 'homepage' in data:
        print(f"Homepage:   {data.get('homepage', 'N/A')}")
    if 'dependencies' in data and data['dependencies']:
        print()
        print(f"Dependencies ({len(data['dependencies'])}):")
        for dep in data['dependencies']:
            print(f"  • {dep}")


def render_python_element(data: Dict[str, Any], output_format: str) -> None:
    """Render specific Python runtime element.

    Args:
        data: Python element data from adapter
        output_format: Output format (text, json, grep)
    """
    if output_format == 'json':
        import json
        print(json.dumps(data, indent=2))
        return

    # Handle errors
    if 'error' in data:
        print(f"Error: {data['error']}", file=sys.stderr)
        if 'details' in data:
            print(f"Details: {data['details']}", file=sys.stderr)
        sys.exit(1)

    # Detect element type and dispatch to appropriate renderer
    if 'packages' in data and 'count' in data:
        _render_python_packages(data)
    elif 'loaded' in data and 'count' in data:
        _render_python_modules(data)
    elif 'health_score' in data and 'checks_performed' in data:
        _render_python_doctor(data)
    elif 'status' in data and 'issues' in data:
        _render_python_bytecode(data)
    elif 'sys_path' in data:
        _render_python_env_config(data)
    elif 'executable' in data and 'compiler' in data:
        _render_python_version(data)
    elif 'active' in data:
        _render_python_venv_status(data)
    elif 'name' in data and 'version' in data and 'location' in data:
        _render_python_package_details(data)
    else:
        # Generic fallback
        import json
        print(json.dumps(data, indent=2))


def _build_help_epilog() -> str:
    """Build dynamic help with conditional jq examples."""
    import shutil

    has_jq = shutil.which('jq') is not None

    base_help = '''
Examples:
  # Basic structure exploration
  reveal src/                    # Directory tree
  reveal app.py                  # Show structure with metrics
  reveal app.py --meta           # File metadata

  # Semantic navigation - iterative deepening! (NEW in v0.12!)
  reveal conversation.jsonl --head 10    # First 10 records
  reveal conversation.jsonl --tail 5     # Last 5 records
  reveal conversation.jsonl --range 48-52 # Records 48-52 (1-indexed)
  reveal app.py --head 5                 # First 5 functions
  reveal doc.md --tail 3                 # Last 3 headings

  # Code quality checks (pattern detectors)
  reveal main.py --check         # Run all quality checks
  reveal main.py --check --select=B,S  # Select specific categories
  reveal Dockerfile --check      # Docker best practices

  # Hierarchical outline (see structure as a tree!)
  reveal app.py --outline        # Classes with methods, nested structures
  reveal app.py --outline --check    # Outline with quality checks

  # Element extraction
  reveal app.py load_config      # Extract specific function
  reveal app.py Database         # Extract class definition
  reveal conversation.jsonl 42   # Extract record #42

  # Output formats
  reveal app.py --format=json    # JSON for scripting
  reveal app.py --format=grep    # Pipeable format
  reveal app.py --copy           # Copy output to clipboard

  # Pipeline workflows (Unix composability!)
  find src/ -name "*.py" | reveal --stdin --check
  git diff --name-only | reveal --stdin --outline
  git ls-files "*.ts" | reveal --stdin --format=json
  ls src/*.py | reveal --stdin
'''

    if has_jq:
        base_help += '''
  # Semantic navigation + jq (token-efficient exploration!)
  reveal conversation.jsonl --tail 10 --format=json | jq '.structure.records[] | select(.name | contains("user"))'
  reveal app.py --head 20 --format=json | jq '.structure.functions[] | select(.line_count > 30)'
  reveal log.jsonl --range 100-150 --format=json | jq '.structure.records[] | select(.name | contains("error"))'

  # Advanced filtering with jq (powerful!)
  reveal app.py --format=json | jq '.structure.functions[] | select(.line_count > 100)'
  reveal app.py --format=json | jq '.structure.functions[] | select(.depth > 3)'
  reveal app.py --format=json | jq '.structure.functions[] | select(.line_count > 50 and .depth > 2)'
  reveal src/**/*.py --format=json | jq -r '.structure.functions[] | "\\(.file):\\(.line) \\(.name) [\\(.line_count) lines]"'

  # Pipeline + jq (combine the power!)
  find . -name "*.py" | reveal --stdin --format=json | jq '.structure.functions[] | select(.line_count > 100)'
  git diff --name-only | grep "\\.py$" | reveal --stdin --check --format=grep
'''

    base_help += '''
  # Markdown-specific features
  reveal doc.md --links                       # Extract all links
  reveal doc.md --links --link-type external  # Only external links
  reveal doc.md --code                        # Extract all code blocks
  reveal doc.md --code --language python      # Only Python code blocks

  # URI adapters - explore ANY resource!
  reveal help://                              # Discover all help topics
  reveal help://ast                           # Learn about ast:// queries
  reveal help://tricks                        # Cool tricks and hidden features
  reveal help://adapters                      # Summary of all adapters

  reveal env://                               # Show all environment variables
  reveal env://PATH                           # Get specific variable

  reveal 'ast://./src?complexity>10'          # Find complex functions
  reveal 'ast://app.py?lines>50'              # Find long functions
  reveal 'ast://.?type=function' --format=json  # All functions as JSON

File-type specific features:
  • Markdown: --links, --code (extract links/code blocks with filtering)
  • Code files: --check, --outline (quality checks, show hierarchical structure)
  • URI adapters: help:// (documentation), env:// (environment), ast:// (code queries)

Perfect filename:line format - works with vim, git, grep, sed, awk!
Metrics: All code files show [X lines, depth:Y] for complexity analysis
stdin: Reads file paths from stdin (one per line) - works with find, git, ls, etc.
'''

    return base_help


def _create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description='Reveal: Explore code semantically - The simplest way to understand code',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_build_help_epilog()
    )

    # Positional arguments
    parser.add_argument('path', nargs='?', help='File or directory to reveal')
    parser.add_argument('element', nargs='?', help='Element to extract (function, class, etc.)')

    # Basic flags
    parser.add_argument('--version', action='version', version=f'reveal {__version__}')
    parser.add_argument('--list-supported', '-l', action='store_true',
                        help='List all supported file types')
    parser.add_argument('--agent-help', action='store_true',
                        help='Show agent usage guide (llms.txt-style brief reference)')
    parser.add_argument('--agent-help-full', action='store_true',
                        help='Show comprehensive agent guide (complete examples, patterns, troubleshooting)')

    # Input/output options
    parser.add_argument('--stdin', action='store_true',
                        help='Read file paths from stdin (one per line) - enables Unix pipeline workflows')
    parser.add_argument('--meta', action='store_true', help='Show metadata only')
    parser.add_argument('--format', choices=['text', 'json', 'typed', 'grep'], default='text',
                        help='Output format (text, json, typed [typed JSON with types/relationships], grep)')
    parser.add_argument('--copy', '-c', action='store_true',
                        help='Copy output to clipboard (also prints normally)')

    # Display options
    parser.add_argument('--no-fallback', action='store_true',
                        help='Disable TreeSitter fallback for unknown file types')
    parser.add_argument('--depth', type=int, default=3, help='Directory tree depth (default: 3)')
    parser.add_argument('--max-entries', type=int, default=200,
                        help='Maximum entries to show in directory tree (default: 200, 0=unlimited)')
    parser.add_argument('--fast', action='store_true',
                        help='Fast mode: skip line counting for better performance')
    parser.add_argument('--outline', action='store_true',
                        help='Show hierarchical outline (classes with methods, nested structures)')

    # Pattern detection (linting)
    parser.add_argument('--check', '--lint', action='store_true',
                        help='Run pattern detectors (code quality, security, complexity checks)')
    parser.add_argument('--select', type=str, metavar='RULES',
                        help='Select specific rules or categories (e.g., "B,S" or "B001,S701")')
    parser.add_argument('--ignore', type=str, metavar='RULES',
                        help='Ignore specific rules or categories (e.g., "E501" or "C")')
    parser.add_argument('--rules', action='store_true',
                        help='List all available pattern detection rules')
    parser.add_argument('--explain', type=str, metavar='CODE',
                        help='Explain a specific rule (e.g., "B001")')

    # Semantic navigation
    parser.add_argument('--head', type=int, metavar='N',
                        help='Show first N semantic units (records, functions, sections)')
    parser.add_argument('--tail', type=int, metavar='N',
                        help='Show last N semantic units (records, functions, sections)')
    parser.add_argument('--range', type=str, metavar='START-END',
                        help='Show semantic units in range (e.g., 10-20, 1-indexed)')

    # Markdown entity filters
    parser.add_argument('--links', action='store_true',
                        help='Extract links from markdown files')
    parser.add_argument('--link-type', choices=['internal', 'external', 'email', 'all'],
                        help='Filter links by type (requires --links)')
    parser.add_argument('--domain', type=str,
                        help='Filter links by domain (requires --links)')
    parser.add_argument('--code', action='store_true',
                        help='Extract code blocks from markdown files')
    parser.add_argument('--language', type=str,
                        help='Filter code blocks by language (requires --code)')
    parser.add_argument('--inline', action='store_true',
                        help='Include inline code snippets (requires --code)')

    return parser


def _validate_navigation_args(args):
    """Validate and parse navigation arguments (--head, --tail, --range)."""
    # Check mutual exclusivity
    nav_args = [args.head, args.tail, args.range]
    nav_count = sum(1 for arg in nav_args if arg is not None)
    if nav_count > 1:
        print("Error: --head, --tail, and --range are mutually exclusive", file=sys.stderr)
        sys.exit(1)

    # Parse and validate range if provided
    if args.range:
        try:
            start, end = args.range.split('-')
            start, end = int(start), int(end)
            if start < 1 or end < 1:
                raise ValueError("Range must be 1-indexed (start from 1)")
            if start > end:
                raise ValueError("Range start must be <= end")
            # Store parsed range as tuple for easy access
            args.range = (start, end)
        except ValueError as e:
            print(f"Error: Invalid range format '{args.range}': {e}", file=sys.stderr)
            print("Expected format: START-END (e.g., 10-20, 1-indexed)", file=sys.stderr)
            sys.exit(1)


def _handle_list_supported():
    """Handle --list-supported flag."""
    list_supported_types()
    sys.exit(0)


def _handle_agent_help():
    """Handle --agent-help flag."""
    agent_help_path = Path(__file__).parent / 'AGENT_HELP.md'
    try:
        with open(agent_help_path, 'r', encoding='utf-8') as f:
            print(f.read())
    except FileNotFoundError:
        print(f"Error: AGENT_HELP.md not found at {agent_help_path}", file=sys.stderr)
        print("This is a bug - please report it at https://github.com/scottsen/reveal/issues", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


def _handle_agent_help_full():
    """Handle --agent-help-full flag."""
    agent_help_full_path = Path(__file__).parent / 'AGENT_HELP_FULL.md'
    try:
        with open(agent_help_full_path, 'r', encoding='utf-8') as f:
            print(f.read())
    except FileNotFoundError:
        print(f"Error: AGENT_HELP_FULL.md not found at {agent_help_full_path}", file=sys.stderr)
        print("This is a bug - please report it at https://github.com/scottsen/reveal/issues", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


def _handle_rules_list():
    """Handle --rules flag to list all pattern detection rules."""
    from .rules import RuleRegistry
    rules = RuleRegistry.list_rules()

    if not rules:
        print("No rules discovered")
        sys.exit(0)

    print(f"Reveal v{__version__} - Pattern Detection Rules\n")

    # Group by category
    by_category = {}
    for rule in rules:
        cat = rule['category']
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(rule)

    # Print by category
    for category in sorted(by_category.keys()):
        cat_rules = by_category[category]
        print(f"{category.upper()} Rules ({len(cat_rules)}):")
        for rule in sorted(cat_rules, key=lambda r: r['code']):
            status = "✓" if rule['enabled'] else "✗"
            severity_icon = {"low": "ℹ️", "medium": "⚠️", "high": "❌", "critical": "🚨"}.get(rule['severity'], "")
            print(f"  {status} {rule['code']:8s} {severity_icon} {rule['message']}")
            if rule['file_patterns'] != ['*']:
                print(f"             Files: {', '.join(rule['file_patterns'])}")
        print()

    print(f"Total: {len(rules)} rules")
    print("\nUsage: reveal <file> --check --select B,S --ignore E501")
    sys.exit(0)


def _handle_explain_rule(rule_code: str):
    """Handle --explain flag to explain a specific rule."""
    from .rules import RuleRegistry
    rule = RuleRegistry.get_rule(rule_code)

    if not rule:
        print(f"Error: Rule '{rule_code}' not found", file=sys.stderr)
        print("\nUse 'reveal --rules' to list all available rules", file=sys.stderr)
        sys.exit(1)

    print(f"Rule: {rule.code}")
    print(f"Message: {rule.message}")
    print(f"Category: {rule.category.value if rule.category else 'unknown'}")
    print(f"Severity: {rule.severity.value}")
    print(f"File Patterns: {', '.join(rule.file_patterns)}")
    if rule.uri_patterns:
        print(f"URI Patterns: {', '.join(rule.uri_patterns)}")
    print(f"Version: {rule.version}")
    print(f"Enabled: {'Yes' if rule.enabled else 'No'}")
    print(f"\nDescription:")
    print(f"  {rule.__doc__ or 'No description available.'}")
    sys.exit(0)


def _handle_stdin_mode(args):
    """Handle --stdin mode to process files from stdin."""
    if args.element:
        print("Error: Cannot use element extraction with --stdin", file=sys.stderr)
        sys.exit(1)

    # Read file paths from stdin (one per line)
    for line in sys.stdin:
        file_path = line.strip()
        if not file_path:
            continue  # Skip empty lines

        path = Path(file_path)

        # Skip if path doesn't exist (graceful degradation)
        if not path.exists():
            print(f"Warning: {file_path} not found, skipping", file=sys.stderr)
            continue

        # Skip directories (only process files)
        if path.is_dir():
            print(f"Warning: {file_path} is a directory, skipping (use reveal {file_path}/ directly)", file=sys.stderr)
            continue

        # Process the file
        if path.is_file():
            handle_file(str(path), None, args.meta, args.format, args)

    sys.exit(0)


def _handle_file_or_directory(path_str: str, args):
    """Handle regular file or directory path."""
    path = Path(path_str)
    if not path.exists():
        print(f"Error: {path_str} not found", file=sys.stderr)
        sys.exit(1)

    if path.is_dir():
        # Directory → show tree
        output = show_directory_tree(str(path), depth=args.depth,
                                     max_entries=args.max_entries, fast=args.fast)
        print(output)
    elif path.is_file():
        # File → show structure or extract element
        handle_file(str(path), args.element, args.meta, args.format, args)
    else:
        print(f"Error: {path_str} is neither file nor directory", file=sys.stderr)
        sys.exit(1)


def _main_impl():
    """Main CLI entry point."""
    # Parse arguments
    parser = _create_argument_parser()
    args = parser.parse_args()

    # Validate navigation arguments
    _validate_navigation_args(args)

    # Check for updates (once per day, non-blocking, opt-out available)
    check_for_updates()

    # Handle special modes (exit early)
    if args.list_supported:
        _handle_list_supported()
    if args.agent_help:
        _handle_agent_help()
    if args.agent_help_full:
        _handle_agent_help_full()
    if args.rules:
        _handle_rules_list()
    if args.explain:
        _handle_explain_rule(args.explain)

    # Handle stdin mode
    if args.stdin:
        _handle_stdin_mode(args)

    # Path is required if not using special modes or --stdin
    if not args.path:
        parser.print_help()
        sys.exit(1)

    # Check if this is a URI (scheme://)
    if '://' in args.path:
        handle_uri(args.path, args.element, args)
        sys.exit(0)

    # Handle regular file/directory path
    _handle_file_or_directory(args.path, args)


def list_supported_types():
    """List all supported file types."""
    analyzers = get_all_analyzers()

    if not analyzers:
        print("No file types registered")
        return

    print(f"Reveal v{__version__} - Supported File Types\n")

    # Sort by name for nice display
    sorted_analyzers = sorted(analyzers.items(), key=lambda x: x[1]['name'])

    print("Built-in Analyzers:")
    for ext, info in sorted_analyzers:
        name = info['name']
        print(f"  {name:20s} {ext}")

    print(f"\nTotal: {len(analyzers)} file types with full support")

    # Probe tree-sitter for additional languages
    try:
        import warnings
        warnings.filterwarnings('ignore', category=FutureWarning, module='tree_sitter')

        from tree_sitter_languages import get_language

        # Common languages to check (extension -> language name mapping)
        fallback_languages = {
            '.java': ('java', 'Java'),
            '.c': ('c', 'C'),
            '.cpp': ('cpp', 'C++'),
            '.cc': ('cpp', 'C++'),
            '.cxx': ('cpp', 'C++'),
            '.h': ('c', 'C/C++ Header'),
            '.hpp': ('cpp', 'C++ Header'),
            '.cs': ('c_sharp', 'C#'),
            '.rb': ('ruby', 'Ruby'),
            '.php': ('php', 'PHP'),
            '.swift': ('swift', 'Swift'),
            '.kt': ('kotlin', 'Kotlin'),
            '.scala': ('scala', 'Scala'),
            '.lua': ('lua', 'Lua'),
            '.hs': ('haskell', 'Haskell'),
            '.elm': ('elm', 'Elm'),
            '.ocaml': ('ocaml', 'OCaml'),
            '.ml': ('ocaml', 'OCaml'),
        }

        # Filter out languages already registered
        available_fallbacks = []
        for ext, (lang, display_name) in fallback_languages.items():
            if ext not in analyzers:  # Not already registered
                try:
                    get_language(lang)
                    available_fallbacks.append((display_name, ext))
                except Exception:
                    # Language not available in tree-sitter-languages, skip it
                    pass

        if available_fallbacks:
            print("\nTree-Sitter Auto-Supported (basic):")
            for name, ext in sorted(available_fallbacks):
                print(f"  {name:20s} {ext}")
            print(f"\nTotal: {len(available_fallbacks)} additional languages via fallback")
            print("Note: These work automatically but may have basic support.")
            print("Note: Contributions for full analyzers welcome!")

    except Exception:
        # tree-sitter-languages not available or probe failed
        pass

    print(f"\nUsage: reveal <file>")
    print(f"Help: reveal --help")


def run_pattern_detection(analyzer: FileAnalyzer, path: str, output_format: str, args):
    """Run pattern detection rules on a file.

    Args:
        analyzer: File analyzer instance
        path: File path
        output_format: Output format ('text', 'json', 'grep')
        args: CLI arguments (for --select, --ignore)
    """
    from .rules import RuleRegistry

    # Parse select/ignore options
    select = args.select.split(',') if args.select else None
    ignore = args.ignore.split(',') if args.ignore else None

    # Get structure and content
    structure = analyzer.get_structure()
    content = analyzer.content

    # Run rules
    detections = RuleRegistry.check_file(path, structure, content, select=select, ignore=ignore)

    # Output results
    if output_format == 'json':
        import json
        result = {
            'file': path,
            'detections': [d.to_dict() for d in detections],
            'total': len(detections)
        }
        print(json.dumps(result, indent=2))

    elif output_format == 'grep':
        # Grep format: file:line:column:code:message
        for d in detections:
            print(f"{d.file_path}:{d.line}:{d.column}:{d.rule_code}:{d.message}")

    else:  # text
        if not detections:
            print(f"{path}: ✅ No issues found")
        else:
            print(f"{path}: Found {len(detections)} issues\n")
            for d in sorted(detections, key=lambda x: (x.line, x.column)):
                print(d)
                print()  # Blank line between detections


def handle_file(path: str, element: Optional[str], show_meta: bool, output_format: str, args=None):
    """Handle file analysis.

    Args:
        path: File path
        element: Optional element to extract
        show_meta: Whether to show metadata only
        output_format: Output format ('text', 'json', 'grep')
        args: Full argument namespace (for filter options)
    """
    # Get analyzer
    # Check fallback setting
    allow_fallback = not getattr(args, 'no_fallback', False) if args else True

    analyzer_class = get_analyzer(path, allow_fallback=allow_fallback)
    if not analyzer_class:
        ext = Path(path).suffix or '(no extension)'
        print(f"Error: No analyzer found for {path} ({ext})", file=sys.stderr)
        print(f"\nError: File type '{ext}' is not supported yet", file=sys.stderr)
        print(f"Run 'reveal --list-supported' to see all supported file types", file=sys.stderr)
        print(f"Visit https://github.com/scottsen/reveal to request new file types", file=sys.stderr)
        sys.exit(1)

    analyzer = analyzer_class(path)

    # Show metadata only?
    if show_meta:
        show_metadata(analyzer, output_format)
        return

    # Pattern detection mode (--check)?
    if args and getattr(args, 'check', False):
        run_pattern_detection(analyzer, path, output_format, args)
        return

    # Extract specific element?
    if element:
        extract_element(analyzer, element, output_format)
        return

    # Default: show structure
    show_structure(analyzer, output_format, args)


def show_metadata(analyzer: FileAnalyzer, output_format: str):
    """Show file metadata."""
    meta = analyzer.get_metadata()

    if output_format == 'json':
        import json
        print(json.dumps(meta, indent=2))
    else:
        print(f"File: {meta['name']}\n")
        print(f"Path:     {meta['path']}")
        print(f"Size:     {meta['size_human']}")
        print(f"Lines:    {meta['lines']}")
        print(f"Encoding: {meta['encoding']}")
        print_breadcrumbs('metadata', meta['path'])


def build_hierarchy(structure: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Build hierarchical tree from flat structure.

    Args:
        structure: Flat structure from analyzer (imports, functions, classes)

    Returns:
        List of root-level items with 'children' added
    """
    # Collect all items with parent info
    all_items = []

    for category, items in structure.items():
        for item in items:
            item = item.copy()  # Don't mutate original
            item['category'] = category
            item['children'] = []
            all_items.append(item)

    # Sort by line number
    all_items.sort(key=lambda x: x.get('line', 0))

    # Build parent-child relationships based on line ranges
    # An item is a child if it's within another item's line range
    for i, item in enumerate(all_items):
        item_start = item.get('line', 0)
        item_end = item.get('line_end', item_start)

        # Find potential parent (previous item that contains this one)
        parent = None
        for j in range(i - 1, -1, -1):
            candidate = all_items[j]
            candidate_start = candidate.get('line', 0)
            candidate_end = candidate.get('line_end', candidate_start)

            # Check if candidate contains this item
            if candidate_start < item_start and candidate_end >= item_end:
                # Found a containing item - use most recent (closest parent)
                parent = candidate
                break

        # Add to parent's children or mark as root
        if parent:
            parent['children'].append(item)
            item['is_child'] = True
        else:
            item['is_child'] = False

    # Return only root-level items
    return [item for item in all_items if not item.get('is_child', False)]


def build_heading_hierarchy(headings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build hierarchical tree from flat heading list with levels.

    Args:
        headings: List of heading dicts with 'level', 'name', 'line' fields

    Returns:
        List of root-level headings with 'children' added

    Example:
        Input:  [{'level': 1, 'name': 'A'}, {'level': 2, 'name': 'B'}]
        Output: [{'level': 1, 'name': 'A', 'children': [{'level': 2, 'name': 'B', 'children': []}]}]
    """
    if not headings:
        return []

    # Add children field to all items
    items = [h.copy() for h in headings]
    for item in items:
        item['children'] = []

    # Build parent-child relationships based on level hierarchy
    root_items = []
    stack = []  # Stack of (level, item) for finding parents

    for item in items:
        level = item.get('level', 1)

        # Pop stack until we find the parent level (level - 1)
        while stack and stack[-1][0] >= level:
            stack.pop()

        if not stack:
            # This is a root item
            root_items.append(item)
        else:
            # Add to parent's children
            parent_item = stack[-1][1]
            parent_item['children'].append(item)

        # Push current item onto stack
        stack.append((level, item))

    return root_items


def render_outline(items: List[Dict[str, Any]], path: Path, indent: str = '', is_root: bool = True) -> None:
    """Render hierarchical outline with tree characters.

    Args:
        items: List of items (potentially with children)
        path: File path for line number display
        indent: Current indentation prefix
        is_root: Whether these are root-level items
    """
    if not items:
        return

    for i, item in enumerate(items):
        is_last_item = (i == len(items) - 1)

        # Format item
        line = item.get('line', '?')
        name = item.get('name', '')
        signature = item.get('signature', '')

        # Build metrics display
        metrics = ''
        if 'line_count' in item or 'depth' in item:
            parts = []
            if 'line_count' in item:
                parts.append(f"{item['line_count']} lines")
            if 'depth' in item:
                parts.append(f"depth:{item['depth']}")
            if parts:
                metrics = f" [{', '.join(parts)}]"

        # Format output
        if signature and name:
            display = f"{name}{signature}{metrics}"
        elif name:
            display = f"{name}{metrics}"
        else:
            display = item.get('content', '?')

        # Print item with appropriate prefix
        if is_root:
            # Root items - no tree chars, show full path
            print(f"{display} ({path}:{line})")
        else:
            # Child items - use tree chars
            tree_char = '└─ ' if is_last_item else '├─ '
            print(f"{indent}{tree_char}{display} (line {line})")

        # Recursively render children
        if item.get('children'):
            if is_root:
                # Children of root get minimal indent
                child_indent = '  '
            else:
                # Children of nested items continue the tree
                child_indent = indent + ('   ' if is_last_item else '│  ')
            render_outline(item['children'], path, child_indent, is_root=False)


def _format_links(items: List[Dict[str, Any]], path: Path, output_format: str) -> None:
    """Format and display link items grouped by type."""
    by_type = {}
    for item in items:
        link_type = item.get('type', 'unknown')
        by_type.setdefault(link_type, []).append(item)

    for link_type in ['external', 'internal', 'email']:
        if link_type not in by_type:
            continue

        type_items = by_type[link_type]
        print(f"\n  {link_type.capitalize()} ({len(type_items)}):")

        for item in type_items:
            line = item.get('line', '?')
            text = item.get('text', '')
            url = item.get('url', '')
            broken = item.get('broken', False)

            if output_format == 'grep':
                print(f"{path}:{line}:{url}")
            else:
                if broken:
                    print(f"    ❌ Line {line:<4} [{text}]({url}) [BROKEN]")
                else:
                    if link_type == 'external':
                        domain = item.get('domain', '')
                        print(f"    Line {line:<4} [{text}]({url})")
                        if domain:
                            print(f"             → {domain}")
                    else:
                        print(f"    Line {line:<4} [{text}]({url})")


def _format_code_blocks(items: List[Dict[str, Any]], path: Path, output_format: str) -> None:
    """Format and display code block items grouped by language."""
    by_lang = {}
    for item in items:
        lang = item.get('language', 'unknown')
        by_lang.setdefault(lang, []).append(item)

    # Show fenced blocks grouped by language
    for lang in sorted(by_lang.keys()):
        if lang == 'inline':
            continue

        lang_items = by_lang[lang]
        print(f"\n  {lang.capitalize()} ({len(lang_items)} blocks):")

        for item in lang_items:
            line_start = item.get('line_start', '?')
            line_end = item.get('line_end', '?')
            line_count = item.get('line_count', 0)
            source = item.get('source', '')

            if output_format == 'grep':
                first_line = source.split('\n')[0] if source else ''
                print(f"{path}:{line_start}:{first_line}")
            else:
                print(f"    Lines {line_start}-{line_end} ({line_count} lines)")
                preview_lines = source.split('\n')[:3]
                for preview_line in preview_lines:
                    print(f"      {preview_line}")
                if line_count > 3:
                    print(f"      ... ({line_count - 3} more lines)")

    # Show inline code if present
    if 'inline' in by_lang:
        inline_items = by_lang['inline']
        print(f"\n  Inline code ({len(inline_items)} snippets):")
        for item in inline_items[:10]:
            line = item.get('line', '?')
            source = item.get('source', '')
            if output_format == 'grep':
                print(f"{path}:{line}:{source}")
            else:
                print(f"    Line {line:<4} `{source}`")
        if len(inline_items) > 10:
            print(f"    ... and {len(inline_items) - 10} more")


def _format_standard_items(items: List[Dict[str, Any]], path: Path, output_format: str) -> None:
    """Format and display standard items (functions, classes, etc.)."""
    for item in items:
        line = item.get('line', '?')
        name = item.get('name', '')
        signature = item.get('signature', '')
        content = item.get('content', '')

        # Build metrics display (if available)
        metrics = ''
        if 'line_count' in item or 'depth' in item:
            parts = []
            if 'line_count' in item:
                parts.append(f"{item['line_count']} lines")
            if 'depth' in item:
                parts.append(f"depth:{item['depth']}")
            if parts:
                metrics = f" [{', '.join(parts)}]"

        # Format based on what's available
        if signature and name:
            if output_format == 'grep':
                print(f"{path}:{line}:{name}{signature}")
            else:
                print(f"  {path}:{line:<6} {name}{signature}{metrics}")
        elif name:
            if output_format == 'grep':
                print(f"{path}:{line}:{name}")
            else:
                print(f"  {path}:{line:<6} {name}{metrics}")
        elif content:
            if output_format == 'grep':
                print(f"{path}:{line}:{content}")
            else:
                print(f"  {path}:{line:<6} {content}")


def _build_analyzer_kwargs(analyzer: FileAnalyzer, args) -> Dict[str, Any]:
    """Build kwargs for get_structure() based on analyzer type and args.

    This centralizes all analyzer-specific argument mapping.
    """
    kwargs = {}

    # Navigation/slicing arguments (apply to all analyzers)
    if args:
        if getattr(args, 'head', None):
            kwargs['head'] = args.head
        if getattr(args, 'tail', None):
            kwargs['tail'] = args.tail
        if getattr(args, 'range', None):
            kwargs['range'] = args.range

    # Markdown-specific filters
    if args and hasattr(analyzer, '_extract_links'):
        if args.links or args.link_type or args.domain:
            kwargs['extract_links'] = True
            if args.link_type:
                kwargs['link_type'] = args.link_type
            if args.domain:
                kwargs['domain'] = args.domain

        if args.code or args.language or args.inline:
            kwargs['extract_code'] = True
            if args.language:
                kwargs['language'] = args.language
            if args.inline:
                kwargs['inline_code'] = args.inline

    return kwargs


def _print_file_header(path: Path, is_fallback: bool = False, fallback_lang: str = None) -> None:
    """Print file header with optional fallback indicator."""
    if is_fallback and fallback_lang:
        print(f"File: {path.name} (fallback: {fallback_lang})\n")
    else:
        print(f"File: {path.name}\n")


def _render_json_output(analyzer: FileAnalyzer, structure: Dict[str, List[Dict[str, Any]]]) -> None:
    """Render structure as JSON output (standard format)."""
    import json

    is_fallback = getattr(analyzer, 'is_fallback', False)
    fallback_lang = getattr(analyzer, 'fallback_language', None)
    file_path = str(analyzer.path)

    # Add 'file' field to each element in structure for --stdin compatibility
    enriched_structure = {}
    for category, items in structure.items():
        enriched_items = []
        for item in items:
            # Copy item and add file field
            enriched_item = item.copy()
            enriched_item['file'] = file_path
            enriched_items.append(enriched_item)
        enriched_structure[category] = enriched_items

    result = {
        'file': file_path,
        'type': analyzer.__class__.__name__.replace('Analyzer', '').lower(),
        'analyzer': {
            'type': 'fallback' if is_fallback else 'explicit',
            'language': fallback_lang if is_fallback else None,
            'explicit': not is_fallback,
            'name': analyzer.__class__.__name__
        },
        'structure': enriched_structure
    }
    print(json.dumps(result, indent=2))


def _render_typed_json_output(analyzer: FileAnalyzer, structure: Dict[str, List[Dict[str, Any]]]) -> None:
    """Render structure as typed JSON output (with types and relationships).

    This format includes:
    - Entities with explicit type fields
    - Relationships (including bidirectional)
    - Type counts
    - Rich properties

    Only available for analyzers that define types.
    Falls back to standard JSON if no types defined.
    """
    import json

    # Check if analyzer has type system
    if not hasattr(analyzer, '_type_registry') or analyzer._type_registry is None:
        # No type system - fall back to standard JSON
        _render_json_output(analyzer, structure)
        return

    is_fallback = getattr(analyzer, 'is_fallback', False)
    fallback_lang = getattr(analyzer, 'fallback_language', None)
    file_path = str(analyzer.path)

    # Build entities list with explicit types
    entities = []
    type_counts = {}

    # Map structure keys to type names (handle plural to singular)
    def normalize_type_name(structure_key: str) -> str:
        """Convert structure key to type name.

        Structure keys are often plural (functions, classes),
        but type definitions are singular (function, class).
        """
        # Check if singular form exists in type registry
        singular = structure_key.rstrip('s')  # Simple pluralization
        if analyzer._type_registry and singular in analyzer._type_registry.types:
            return singular

        # Check for exact match
        if analyzer._type_registry and structure_key in analyzer._type_registry.types:
            return structure_key

        # Fall back to structure key
        return structure_key

    for structure_key, items in structure.items():
        # Get normalized type name
        entity_type = normalize_type_name(structure_key)

        for item in items:
            # Create entity with explicit type field
            entity = {
                'type': entity_type,
                **item,  # Include all original properties
                'file': file_path  # Add file field for --stdin compatibility
            }
            entities.append(entity)

            # Count types
            type_counts[entity_type] = type_counts.get(entity_type, 0) + 1

    # Extract relationships if analyzer supports them
    relationships = {}
    if hasattr(analyzer, '_relationship_registry') and analyzer._relationship_registry is not None:
        # Call analyzer's relationship extraction
        raw_relationships = analyzer._extract_relationships(structure)

        # Build relationship index (adds bidirectional edges)
        if raw_relationships:
            relationships = analyzer._relationship_registry.build_index(raw_relationships)

    # Build result
    result = {
        'file': file_path,
        'analyzer': analyzer.__class__.__name__.replace('Analyzer', '').lower(),
        'analyzer_info': {
            'type': 'fallback' if is_fallback else 'explicit',
            'language': fallback_lang if is_fallback else None,
            'explicit': not is_fallback,
            'name': analyzer.__class__.__name__,
            'has_types': True,
            'has_relationships': len(relationships) > 0
        },
        'entities': entities,
        'type_counts': type_counts,
        'metadata': {
            'total_entities': len(entities),
            'total_relationships': sum(len(edges) for edges in relationships.values())
        }
    }

    # Add relationships if present
    if relationships:
        result['relationships'] = relationships

    print(json.dumps(result, indent=2))


def _render_text_categories(structure: Dict[str, List[Dict[str, Any]]],
                            path: Path, output_format: str) -> None:
    """Render each category in text format."""
    for category, items in structure.items():
        if not items:
            continue

        # Format category name (e.g., 'functions' → 'Functions')
        category_name = category.capitalize()
        print(f"{category_name} ({len(items)}):")

        # Special handling for different categories
        if category == 'links':
            _format_links(items, path, output_format)
        elif category == 'code_blocks':
            _format_code_blocks(items, path, output_format)
        else:
            _format_standard_items(items, path, output_format)

        print()  # Blank line between categories


def show_structure(analyzer: FileAnalyzer, output_format: str, args=None):
    """Show file structure.

    Simplified using extracted helper functions.
    """
    # Build kwargs and get structure
    kwargs = _build_analyzer_kwargs(analyzer, args)

    # Add outline flag for markdown analyzer (Issue #3)
    if args and hasattr(args, 'outline'):
        kwargs['outline'] = args.outline

    structure = analyzer.get_structure(**kwargs)
    path = analyzer.path

    # Get fallback info
    is_fallback = getattr(analyzer, 'is_fallback', False)
    fallback_lang = getattr(analyzer, 'fallback_language', None)

    # Handle outline mode
    if args and getattr(args, 'outline', False):
        _print_file_header(path, is_fallback, fallback_lang)
        if not structure:
            print("No structure available for this file type")
            return

        # Check if this is markdown with headings
        if 'headings' in structure and structure.get('headings'):
            # Markdown outline: use level-based hierarchy
            hierarchy = build_heading_hierarchy(structure['headings'])
        # Check if this is TOML with sections (level-based like markdown)
        elif 'sections' in structure and structure.get('sections'):
            # Check if sections have 'level' field (TOML outline mode)
            sections = structure['sections']
            if sections and 'level' in sections[0]:
                # TOML outline: use level-based hierarchy like markdown
                hierarchy = build_heading_hierarchy(sections)
            else:
                # Regular TOML: use line-range based hierarchy
                hierarchy = build_hierarchy(structure)
        else:
            # Code outline: use line-range based hierarchy
            hierarchy = build_hierarchy(structure)

        render_outline(hierarchy, path)
        return

    # Handle JSON output (standard format)
    if output_format == 'json':
        _render_json_output(analyzer, structure)
        return

    # Handle typed JSON output (with types and relationships)
    if output_format == 'typed':
        _render_typed_json_output(analyzer, structure)
        return

    # Handle empty structure
    if not structure:
        _print_file_header(path, is_fallback, fallback_lang)
        print("No structure available for this file type")
        return

    # Text output: show header, categories, and navigation hints
    _print_file_header(path, is_fallback, fallback_lang)
    _render_text_categories(structure, path, output_format)

    # Navigation hints
    if output_format == 'text':
        file_type = get_file_type_from_analyzer(analyzer)
        print_breadcrumbs('structure', path, file_type=file_type)


def extract_element(analyzer: FileAnalyzer, element: str, output_format: str):
    """Extract a specific element.

    Args:
        analyzer: File analyzer
        element: Element name to extract
        output_format: Output format
    """
    # Try common element types
    for element_type in ['function', 'class', 'struct', 'section', 'server', 'location', 'upstream']:
        result = analyzer.extract_element(element_type, element)
        if result:
            break
    else:
        # Not found
        print(f"Error: Element '{element}' not found in {analyzer.path}", file=sys.stderr)
        sys.exit(1)

    # Format output
    if output_format == 'json':
        import json
        print(json.dumps(result, indent=2))
        return

    path = analyzer.path
    line_start = result.get('line_start', 1)
    line_end = result.get('line_end', line_start)
    source = result.get('source', '')
    name = result.get('name', element)

    # Header
    print(f"{path}:{line_start}-{line_end} | {name}\n")

    # Source with line numbers
    if output_format == 'grep':
        # Grep format: filename:linenum:content
        for i, line in enumerate(source.split('\n')):
            line_num = line_start + i
            print(f"{path}:{line_num}:{line}")
    else:
        # Human-readable format
        formatted = analyzer.format_with_lines(source, line_start)
        print(formatted)

        # Navigation hints
        file_type = get_file_type_from_analyzer(analyzer)
        line_count = line_end - line_start + 1
        print_breadcrumbs('element', path, file_type=file_type,
                         element_name=name, line_count=line_count, line_start=line_start)


if __name__ == '__main__':
    main()
