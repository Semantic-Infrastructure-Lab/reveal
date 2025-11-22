"""Python file analyzer."""

import ast
from typing import Dict, Any, List
from .base import BaseAnalyzer
from ..registry import register


@register(['.py', '.pyx', '.pyi'], name='Python', icon='🐍')
class PythonAnalyzer(BaseAnalyzer):
    """Analyzer for Python source files with AST-based analysis"""

    def __init__(self, lines: List[str]):
        super().__init__(lines)
        self.parse_error = None
        self.tree = None

        try:
            content = '\n'.join(lines)
            self.tree = ast.parse(content)
        except Exception as e:
            self.parse_error = str(e)

    def analyze_structure(self) -> Dict[str, Any]:
        """Analyze Python structure."""
        if self.parse_error:
            return {
                'error': self.parse_error,
                'imports': [],
                'classes': [],
                'functions': [],
                'assignments': []
            }

        imports = []
        classes = []
        functions = []
        assignments = []

        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                for alias in node.names:
                    imports.append(f"{module}.{alias.name}" if module else alias.name)

        # Only top-level elements
        for node in self.tree.body:
            if isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                functions.append(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assignments.append(target.id)

        return {
            'imports': imports,
            'classes': classes,
            'functions': functions,
            'assignments': assignments
        }

    def generate_preview(self) -> List[tuple[int, str]]:
        """Generate Python preview."""
        preview = []

        # Module docstring
        if self.tree and isinstance(self.tree.body[0], ast.Expr) and isinstance(self.tree.body[0].value, ast.Constant):
            docstring_node = self.tree.body[0]
            # Find docstring in lines
            for i, line in enumerate(self.lines[:20], 1):
                if '"""' in line or "'''" in line:
                    preview.append((i, line))
                    # Add next few lines if multiline docstring
                    if line.count('"""') == 1 or line.count("'''") == 1:
                        for j in range(i, min(i + 10, len(self.lines) + 1)):
                            if j > i:
                                preview.append((j, self.lines[j - 1]))
                            if '"""' in self.lines[j - 1][1:] or "'''" in self.lines[j - 1][1:]:
                                break
                    break

        if self.parse_error:
            # Fallback to first 20 lines
            for i, line in enumerate(self.lines[:20], 1):
                if (i, line) not in preview:
                    preview.append((i, line))
            return preview

        # Class signatures + first docstring line
        for node in self.tree.body:
            if isinstance(node, ast.ClassDef):
                class_line = node.lineno
                preview.append((class_line, self.lines[class_line - 1]))

                # Get class docstring
                if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
                    doc_line = node.body[0].lineno
                    preview.append((doc_line, self.lines[doc_line - 1]))

        # Function signatures + first docstring line
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_line = node.lineno
                preview.append((func_line, self.lines[func_line - 1]))

                # Get function docstring
                if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
                    doc_line = node.body[0].lineno
                    preview.append((doc_line, self.lines[doc_line - 1]))

        # Sort by line number and limit
        preview = sorted(list(set(preview)), key=lambda x: x[0])
        return preview[:30]
