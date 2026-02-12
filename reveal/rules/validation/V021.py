"""V021: Detect inappropriate regex usage when tree-sitter is available.

Validates that analyzers use tree-sitter for code parsing instead of regex.
Regex is brittle for parsing structured code and fails on edge cases like:
- Nested blocks
- Comments inside code
- Multi-line constructs
- Complex quoting/escaping

Tree-sitter provides robust AST-based parsing for 40+ languages.

Example violations:
    - GDScript analyzer uses regex patterns for classes/functions (gdscript.py)
    - Dockerfile analyzer uses regex for directive parsing
    - TOML analyzer uses regex for section headers
    - YAML/JSON analyzers use regex for key extraction

The rule:
    - Analyzers should inherit from TreeSitterAnalyzer when available
    - Just set: language = 'gdscript' (or 'dockerfile', 'toml', etc.)
    - Tree-sitter handles all structure extraction automatically
    - Regex is appropriate for: version extraction, link matching, text patterns

Tree-sitter available for:
    Python, JavaScript, TypeScript, Go, Rust, C, C++, C#, Java, Ruby,
    PHP, Swift, Kotlin, Scala, Dart, Lua, GDScript, Dockerfile, Nginx,
    TOML, YAML, JSON, HTML, CSS, Markdown, SQL, GraphQL, Protobuf, etc.

Migration is easy:
    Before (gdscript.py - 197 lines with regex):
        CLASS_PATTERN = re.compile(r'^\s*class\s+(\w+)\s*:')
        FUNC_PATTERN = re.compile(...)
        # 150+ lines of regex parsing

    After (3 lines - automatic):
        from ..treesitter import TreeSitterAnalyzer

        @register('.gd', name='GDScript', icon='')
        class GDScriptAnalyzer(TreeSitterAnalyzer):
            language = 'gdscript'
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
import ast

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root


class V021(BaseRule):
    """Validate analyzers use tree-sitter instead of regex for code parsing."""

    code = "V021"
    message = "Analyzer uses regex when tree-sitter is available"
    category = RulePrefix.V
    severity = Severity.HIGH
    file_patterns = ['*']  # Runs on reveal:// URIs

    # Languages with tree-sitter support in tree-sitter-language-pack
    TREE_SITTER_LANGUAGES = {
        'bash', 'c', 'cpp', 'c_sharp', 'css', 'dart', 'dockerfile',
        'go', 'graphql', 'hcl', 'html', 'java', 'javascript', 'json',
        'kotlin', 'lua', 'markdown', 'php', 'python', 'ruby', 'rust',
        'scala', 'sql', 'swift', 'toml', 'typescript', 'yaml', 'zig',
        'gdscript',  # GDScript has tree-sitter support
    }

    # Analyzers that legitimately use regex for text patterns (not code parsing)
    REGEX_WHITELIST = {
        'markdown.py',    # Link/heading patterns (also uses tree-sitter)
        'html.py',        # Template variable detection (supplemental)
        'imports/base.py',  # String literal extraction from imports
    }

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check that analyzers use tree-sitter instead of regex."""
        # Only run this check for reveal:// URIs
        if not file_path.startswith('reveal://'):
            return []

        # Find reveal root
        reveal_root = find_reveal_root()
        if not reveal_root:
            return []

        analyzers_dir = reveal_root / 'analyzers'
        if not analyzers_dir.exists():
            return []

        detections: List[Detection] = []

        # Check all analyzer files
        for analyzer_file in analyzers_dir.rglob('*.py'):
            if analyzer_file.name == '__init__.py':
                continue

            # Skip whitelisted files
            relative = analyzer_file.relative_to(analyzers_dir)
            if str(relative) in self.REGEX_WHITELIST:
                continue

            try:
                file_content = analyzer_file.read_text(encoding='utf-8')
            except Exception:
                continue

            # Check if file imports 're' module
            if not self._imports_re_module(file_content):
                continue

            # Check if this analyzer could use tree-sitter
            language_name = self._infer_language(analyzer_file, file_content)
            if not language_name:
                continue

            # Check if tree-sitter is available for this language
            if language_name not in self.TREE_SITTER_LANGUAGES:
                continue

            # Check if already using TreeSitterAnalyzer
            if self._uses_treesitter_analyzer(file_content):
                # Using tree-sitter as primary but regex for supplemental text patterns
                # This is okay (e.g., markdown.py does this)
                continue

            # Found violation: regex-based analyzer when tree-sitter is available
            detection = self._create_violation(
                analyzer_file,
                language_name,
                file_content
            )
            if detection:
                detections.append(detection)

        return detections

    def _imports_re_module(self, content: str) -> bool:
        """Check if file imports the 're' module."""
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == 're':
                            return True
                elif isinstance(node, ast.ImportFrom):
                    if node.module == 're':
                        return True
        except SyntaxError:
            # Fallback to simple string search
            return 'import re' in content or 'from re import' in content
        return False

    def _infer_language(self, file_path: Path, content: str) -> Optional[str]:
        """Infer language name from analyzer file."""
        # Try to extract from filename first
        stem = file_path.stem

        # Direct mappings
        language_map = {
            'gdscript': 'gdscript',
            'dockerfile': 'dockerfile',
            'nginx': 'nginx',
            'toml': 'toml',
            'yaml_json': 'yaml',  # yaml analyzer
            'javascript': 'javascript',
            'typescript': 'typescript',
            'python': 'python',
            'go': 'go',
            'rust': 'rust',
            'c': 'c',
            'cpp': 'cpp',
            'csharp': 'c_sharp',
            'java': 'java',
            'ruby': 'ruby',
            'php': 'php',
            'swift': 'swift',
            'kotlin': 'kotlin',
            'scala': 'scala',
            'dart': 'dart',
            'lua': 'lua',
            'bash': 'bash',
            'sql': 'sql',
            'graphql': 'graphql',
            'hcl': 'hcl',
            'html': 'html',
            'css': 'css',
            'markdown': 'markdown',
        }

        return language_map.get(stem)

    def _uses_treesitter_analyzer(self, content: str) -> bool:
        """Check if analyzer inherits from TreeSitterAnalyzer."""
        return 'TreeSitterAnalyzer' in content

    def _create_violation(
        self,
        analyzer_file: Path,
        language: str,
        content: str
    ) -> Optional[Detection]:
        """Create detection for inappropriate regex usage."""
        # Find the import line for 're'
        import_line = 1
        for i, line in enumerate(content.splitlines(), 1):
            if 'import re' in line:
                import_line = i
                break

        # Count regex patterns to estimate migration effort
        regex_count = content.count('re.compile') + content.count('re.match') + \
                     content.count('re.search') + content.count('re.findall') + \
                     content.count('re.finditer')

        effort_estimate = "small" if regex_count < 3 else "medium" if regex_count < 7 else "large"

        message = (
            f"Analyzer uses regex for parsing {language} code instead of tree-sitter. "
            f"Found {regex_count} regex operations. Migration effort: {effort_estimate}."
        )

        suggestion = f"""Migrate to TreeSitterAnalyzer for robust AST-based parsing:

1. Import TreeSitterAnalyzer:
   from ..treesitter import TreeSitterAnalyzer

2. Change class to inherit from TreeSitterAnalyzer:
   class {analyzer_file.stem.title()}Analyzer(TreeSitterAnalyzer):
       language = '{language}'

3. Remove regex patterns - tree-sitter handles structure extraction automatically

Benefits:
- Automatic extraction of functions, classes, imports, etc.
- Handles nested blocks, comments, multi-line constructs correctly
- 10-50x less code to maintain
- Better error handling

See treesitter.py for full capabilities and analyzers/python.py for example.
Current regex-based implementation: ~{len(content.splitlines())} lines
Tree-sitter implementation: ~10-15 lines (just set language attribute)"""

        return self.create_detection(
            file_path=str(analyzer_file),
            line=import_line,
            message=message,
            suggestion=suggestion,
            context=f"Language: {language}, Regex operations: {regex_count}, Effort: {effort_estimate}"
        )
