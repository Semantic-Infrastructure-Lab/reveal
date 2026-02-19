"""Metrics calculation functions for stats adapter."""

from pathlib import Path
from typing import Dict, Any, Optional


def count_line_types(lines: list) -> tuple:
    """Count different types of lines.

    Args:
        lines: List of file lines

    Returns:
        Tuple of (empty_lines, comment_lines, code_lines)
    """
    empty_lines = sum(1 for line in lines if not line.strip())
    comment_lines = sum(1 for line in lines if line.strip().startswith(('#', '//', '/*', '*')))
    total_lines = len(lines)
    code_lines = total_lines - empty_lines - comment_lines
    return empty_lines, comment_lines, code_lines


def estimate_complexity(func: Dict[str, Any], content: str) -> Optional[int]:
    """Estimate cyclomatic complexity for a function.

    Args:
        func: Function metadata
        content: File content

    Returns:
        Complexity score or None
    """
    start_line = func.get('line', 0)
    end_line = func.get('end_line', start_line)

    if start_line == 0 or end_line == 0:
        return None

    lines = content.splitlines()
    if start_line > len(lines) or end_line > len(lines):
        return None

    func_content = '\n'.join(lines[start_line - 1:end_line])

    # Calculate complexity (same algorithm as C901 rule)
    complexity = 1
    decision_keywords = [
        'if ', 'elif ', 'else:', 'else ', 'for ', 'while ',
        'and ', 'or ', 'try:', 'except ', 'except:', 'case ', 'when ',
    ]

    for keyword in decision_keywords:
        complexity += func_content.count(keyword)

    return complexity


def extract_complexity_metrics(functions: list, content: str) -> dict:
    """Extract complexity metrics from functions.

    Args:
        functions: List of function structures
        content: File content

    Returns:
        Dict with complexities, long functions, and deep nesting
    """
    complexities = []
    long_functions = []
    deep_nesting = []

    for func in functions:
        # Get complexity if available
        complexity = estimate_complexity(func, content)
        if complexity:
            complexities.append(complexity)

        # Check for long functions (>100 lines)
        func_lines = func.get('line_count', 0)
        if func_lines > 100:
            long_functions.append({
                'name': func.get('name', '<unknown>'),
                'lines': func_lines,
                'start_line': func.get('line', 0)
            })

        # Check for deep nesting (>4 levels)
        depth = func.get('depth', 0)
        if depth > 4:
            deep_nesting.append({
                'name': func.get('name', '<unknown>'),
                'depth': depth,
                'start_line': func.get('line', 0)
            })

    avg_complexity = sum(complexities) / len(complexities) if complexities else 0
    avg_func_length = sum(f.get('line_count', 0) for f in functions) / len(functions) if functions else 0

    return {
        'complexities': complexities,
        'long_functions': long_functions,
        'deep_nesting': deep_nesting,
        'avg_complexity': avg_complexity,
        'avg_func_length': avg_func_length,
    }


def calculate_quality_score(
    avg_complexity: float,
    avg_func_length: float,
    long_func_count: int,
    deep_nesting_count: int,
    total_functions: int,
    quality_config: Dict[str, Any]
) -> float:
    """Calculate quality score (0-100, higher is better).

    Uses configurable thresholds from .reveal/stats-quality.yaml or defaults.

    Args:
        avg_complexity: Average cyclomatic complexity
        avg_func_length: Average function length in lines
        long_func_count: Number of functions >100 lines
        deep_nesting_count: Number of functions with depth >4
        total_functions: Total number of functions
        quality_config: Quality configuration dict

    Returns:
        Quality score 0-100
    """
    # Get config values (with defaults)
    thresholds = quality_config.get('thresholds', {})
    penalties = quality_config.get('penalties', {})

    complexity_target = thresholds.get('complexity_target', 10)
    length_target = thresholds.get('function_length_target', 50)

    complexity_pen = penalties.get('complexity', {})
    length_pen = penalties.get('length', {})
    ratio_pen = penalties.get('ratios', {})

    score = 100.0

    # Penalize high complexity
    if avg_complexity > complexity_target:
        multiplier = complexity_pen.get('multiplier', 3)
        max_penalty = complexity_pen.get('max', 30)
        score -= min(max_penalty, (avg_complexity - complexity_target) * multiplier)

    # Penalize long functions
    if avg_func_length > length_target:
        divisor = length_pen.get('divisor', 2)
        max_penalty = length_pen.get('max', 20)
        score -= min(max_penalty, (avg_func_length - length_target) / divisor)

    # Penalize files with many long functions
    if total_functions > 0:
        long_func_ratio = long_func_count / total_functions
        multiplier = ratio_pen.get('multiplier', 50)
        max_penalty = ratio_pen.get('max', 25)
        score -= min(max_penalty, long_func_ratio * multiplier)

    # Penalize deep nesting
    if total_functions > 0:
        deep_nesting_ratio = deep_nesting_count / total_functions
        multiplier = ratio_pen.get('multiplier', 50)
        max_penalty = ratio_pen.get('max', 25)
        score -= min(max_penalty, deep_nesting_ratio * multiplier)

    return max(0, score)


def calculate_file_stats(
    file_path: Path,
    structure: Dict[str, Any],
    content: str,
    quality_config: Dict[str, Any],
    get_file_display_path_func
) -> Dict[str, Any]:
    """Calculate statistics for a file.

    Args:
        file_path: Path to file
        structure: Parsed structure from analyzer
        content: File content
        quality_config: Quality configuration dict
        get_file_display_path_func: Function to get display path

    Returns:
        Dict with file statistics
    """
    lines = content.splitlines()
    total_lines = len(lines)

    # Count different line types
    empty_lines, comment_lines, code_lines = count_line_types(lines)

    # Extract element counts
    functions = structure.get('functions', [])
    classes = structure.get('classes', [])
    imports = structure.get('imports', [])

    # Extract complexity metrics
    metrics = extract_complexity_metrics(functions, content)

    # Calculate quality score
    quality_score = calculate_quality_score(
        metrics['avg_complexity'],
        metrics['avg_func_length'],
        len(metrics['long_functions']),
        len(metrics['deep_nesting']),
        len(functions),
        quality_config
    )

    # Get display path
    file_display = get_file_display_path_func(file_path)

    return {
        'file': file_display,
        'lines': {
            'total': total_lines,
            'code': code_lines,
            'empty': empty_lines,
            'comments': comment_lines,
        },
        'elements': {
            'functions': len(functions),
            'classes': len(classes),
            'imports': len(imports),
        },
        'complexity': {
            'average': round(metrics['avg_complexity'], 2),
            'max': max(metrics['complexities']) if metrics['complexities'] else 0,
            'min': min(metrics['complexities']) if metrics['complexities'] else 0,
        },
        'quality': {
            'score': round(quality_score, 1),
            'long_functions': len(metrics['long_functions']),
            'deep_nesting': len(metrics['deep_nesting']),
            'avg_function_length': round(metrics['avg_func_length'], 1),
        },
        'issues': {
            'long_functions': metrics['long_functions'],
            'deep_nesting': metrics['deep_nesting'],
        }
    }
