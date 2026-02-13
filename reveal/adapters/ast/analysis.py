"""File analysis and structure extraction for AST adapter."""

import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional


def try_add_file_structure(file_path: str, structures: List[Dict[str, Any]]) -> None:
    """Analyze file and add its structure to list if successful.

    Args:
        file_path: Path to file to analyze
        structures: List to append structure to
    """
    structure = analyze_file(file_path)
    if structure:
        structures.append(structure)


def collect_structures(path: str) -> List[Dict[str, Any]]:
    """Collect structure data from file(s).

    Args:
        path: File or directory path

    Returns:
        List of structure dicts with file metadata
    """
    structures: List[Dict[str, Any]] = []
    path_obj = Path(path)

    if path_obj.is_file():
        try_add_file_structure(str(path_obj), structures)
    elif path_obj.is_dir():
        # Recursively find all code files
        for file_path in path_obj.rglob('*'):
            if file_path.is_file() and is_code_file(file_path):
                try_add_file_structure(str(file_path), structures)

    return structures


def is_code_file(path: Path) -> bool:
    """Check if file is a code file we can analyze.

    Args:
        path: File path to check

    Returns:
        True if file has a code extension
    """
    # Common code extensions
    code_exts = {
        '.py', '.js', '.ts', '.jsx', '.tsx', '.rs', '.go',
        '.java', '.c', '.cpp', '.h', '.hpp', '.cs', '.rb',
        '.php', '.swift', '.kt', '.scala', '.sh', '.bash'
    }
    return path.suffix.lower() in code_exts


def create_element_dict(
    file_path: str,
    category: str,
    item: Dict[str, Any],
    analyzer
) -> Dict[str, Any]:
    """Create element dict from analyzer item.

    Args:
        file_path: Source file path
        category: Element category (functions, classes, etc.)
        item: Item dict from analyzer
        analyzer: Analyzer instance for complexity calculation

    Returns:
        Element dict with standardized fields
    """
    # Calculate line_count - functions have it, classes need computation
    line_count = item.get('line_count')
    if not line_count and item.get('line_end'):
        line_count = item.get('line_end', 0) - item.get('line', 0) + 1
    else:
        line_count = line_count or 0

    # For imports, use 'content' as the name since they don't have a 'name' field
    name = item.get('name', '')
    if category == 'imports' and not name and 'content' in item:
        name = item['content']

    element = {
        'file': file_path,
        'category': category,
        'name': name,
        'line': item.get('line', 0),
        'line_count': line_count,
        'signature': item.get('signature', ''),
        'decorators': item.get('decorators', []),
    }

    # Add complexity for functions/methods
    if category in ('functions', 'methods'):
        # Use complexity from item if available (tree-sitter calculated)
        # Otherwise calculate with heuristic
        element['complexity'] = item.get('complexity') or calculate_complexity(item, analyzer)

    return element


def analyze_file(file_path: str) -> Optional[Dict[str, Any]]:
    """Analyze a single file and extract structure.

    Args:
        file_path: Path to file

    Returns:
        Dict with file structure, or None if analysis fails
    """
    from ...registry import get_analyzer

    try:
        analyzer_class = get_analyzer(file_path)
        if not analyzer_class:
            return None

        analyzer = analyzer_class(file_path)
        structure = analyzer.get_structure()
        if not structure:
            return None

        # Flatten all elements from structure
        result: Dict[str, Any] = {'file': file_path, 'elements': []}

        for category, items in structure.items():
            for item in items:
                element = create_element_dict(file_path, category, item, analyzer)
                result['elements'].append(element)

        return result

    except Exception as e:
        # Skip files we can't analyze
        print(f"Warning: Failed to analyze {file_path}: {e}", file=sys.stderr)
        return None


def calculate_complexity(element: Dict[str, Any], analyzer) -> int:
    """Calculate cyclomatic complexity for a function.

    NOTE: This is a fallback heuristic for non-tree-sitter analyzers.
    Tree-sitter analyzers calculate proper McCabe complexity.

    Args:
        element: Function element dict
        analyzer: FileAnalyzer instance

    Returns:
        Complexity score (1 = simple, higher = more complex)
    """
    # Fallback heuristic based on line count
    # Used only when tree-sitter complexity is not available
    line_count: int = element.get('line_count', 0)

    # Very rough heuristic:
    # - Simple function (1-10 lines) = 1-2
    # - Medium function (11-30 lines) = 3-5
    # - Complex function (31-50 lines) = 6-8
    # - Very complex (50+) = proportional to lines

    if line_count <= 10:
        return 1
    elif line_count <= 20:
        return 2
    elif line_count <= 30:
        return 3
    elif line_count <= 40:
        return 5
    elif line_count <= 60:
        return 7
    else:
        # No cap! Let it scale with line count
        return line_count // 10
