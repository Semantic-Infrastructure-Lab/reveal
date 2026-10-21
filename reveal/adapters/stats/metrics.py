"""Metrics calculation functions for stats adapter."""

from ...reveal_types import StructureItem
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from reveal.complexity import fallback_complexity
from reveal.utils.lines import split_lines

logger = logging.getLogger(__name__)


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


def estimate_complexity(func: StructureItem, content: str) -> int:
    """Estimate cyclomatic complexity for a function.

    Uses pre-computed complexity from the tree-sitter analyzer when available
    (all tree-sitter languages populate func['complexity'] in _build_function_dict).
    Falls back to ``reveal.complexity.fallback_complexity`` for analyzers that don't supply it.

    Args:
        func: Function metadata
        content: File content

    Returns:
        Complexity score
    """
    # Prefer the tree-sitter computed value — it's accurate and language-aware.
    if 'complexity' in func:
        return func['complexity']

    return fallback_complexity(func, content)  # BACK-1519: the one shared fallback


def _get_check_thresholds(file_path: Optional[Path]) -> tuple:
    """Resolve the effective C902/C905 thresholds for a file.

    Reads the SAME per-file .reveal.yaml rule config the real `--check`
    pipeline applies (RuleRegistry.get_configured_rule), instead of a second
    hardcoded copy of the rules' defaults — so a project that overrides
    C905's MAX_DEPTH (or any future C902 threshold key) doesn't see the
    hotspot tally flag functions its own config says are fine (BACK-775).
    Falls back to the rules' class defaults if config resolution fails for
    any reason (e.g. no file_path available).

    Returns:
        Tuple of (long_function_lines, deep_nesting_depth)
    """
    try:
        from ...rules import RuleRegistry
        c902 = RuleRegistry.get_configured_rule('C902', str(file_path)) if file_path else None
        c905 = RuleRegistry.get_configured_rule('C905', str(file_path)) if file_path else None
        long_threshold = c902.THRESHOLD_ERROR if c902 else 100
        depth_threshold = c905.MAX_DEPTH if c905 else 4
        return long_threshold, depth_threshold
    except Exception as e:  # boundary-ok: broad-except -- config resolution loads the project's .reveal.yaml and instantiates rule classes (YAML, OSError, and rule-constructor failures that this module cannot enumerate); the default thresholds apply and the reason is logged at warning
        logger.warning("Rule config for %s could not be resolved, using the default "
                       "long-function and nesting thresholds: %s", file_path, e)
        return 100, 4


def extract_complexity_metrics(functions: List[StructureItem], content: str, file_path: Optional[Path] = None) -> dict:
    """Extract complexity metrics from functions.

    Args:
        functions: List of function structures
        content: File content
        file_path: Path to the file, used to resolve per-project .reveal.yaml
            rule config for the long-function/deep-nesting thresholds
            (BACK-775). Optional — falls back to the rules' class defaults.

    Returns:
        Dict with complexities, long functions, and deep nesting
    """
    complexities = []
    long_functions = []
    deep_nesting = []
    long_threshold, depth_threshold = _get_check_thresholds(file_path)

    for func in functions:
        # Get complexity if available
        complexity = estimate_complexity(func, content)
        if complexity:
            complexities.append(complexity)

        # Check for long functions. code_line_count (comments/docstrings
        # excluded) falls back to the raw line_count span for analyzers
        # that don't populate it -- same field C902 thresholds on, kept
        # consistent with its docstring-aware length.
        func_lines = func.get('code_line_count', func.get('line_count', 0))
        if func_lines > long_threshold:
            long_functions.append({
                'name': func.get('name', '<unknown>'),
                'lines': func.get('line_count', 0),
                'start_line': func.get('line', 0)
            })

        # Check for deep nesting
        depth = func.get('depth', 0)
        if depth > depth_threshold:
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
    quality_config: Dict[str, Any],
    local_issue_counts: Optional[Dict[str, int]] = None,
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
        local_issue_counts: Counts of file-local check detections by severity
            (keys: 'critical', 'high', 'medium', 'low'); see stats/issue_count.py

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

    # Penalize file-local check rule detections by severity
    if local_issue_counts:
        check_pen = penalties.get('local_check_issues', {})
        penalty = (
            local_issue_counts.get('critical', 0) * check_pen.get('critical', 10) +
            local_issue_counts.get('high', 0) * check_pen.get('high', 5) +
            local_issue_counts.get('medium', 0) * check_pen.get('medium', 2) +
            local_issue_counts.get('low', 0) * check_pen.get('low', 0.5)
        )
        score -= min(check_pen.get('max', 40), penalty)

    return max(0, score)


def _count_local_check_issues(
    file_path: Path,
    structure: Dict[str, Any],
    content: str,
) -> Tuple[Dict[str, int], List[str]]:
    """Run the file-local check rules and count detections by severity (BACK-1884).

    Reuses already-computed structure and content -- no re-parsing. Only rules that declare
    ``RuleScope.FILE`` run (stats/issue_count.py): a rule that reads other files, a project
    index or the network is left to ``reveal check``, so the count does not move with a scan
    cap or a sibling file and needs no scan-cap disclosure.

    Returns:
        (counts, failed): counts for 'critical', 'high', 'medium', 'low', and the rules that
        could not run (their codes; 'all rules' when the run itself failed). A failure makes
        the counts a lower bound, which the caller records in the file's stats (BACK-1059).
    """
    counts: Dict[str, int] = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
    rule_errors: List[Dict[str, str]] = []
    try:
        from ...rules import RuleRegistry
        from .issue_count import ignored_codes
        detections = RuleRegistry.check_file(str(file_path), structure, content,
                                             ignore=ignored_codes(), errors=rule_errors)
        for d in detections:
            sev = d.severity.value if d.severity else 'medium'
            if sev in counts:
                counts[sev] += 1
    except Exception as e:  # boundary-ok: broad-except -- check_file() loads the project's .reveal.yaml and runs the file-local registered rules, plugin rules included (arbitrary code); one file's failed rule run must not drop its other statistics, and it is recorded as check_rules_failed in the file's stats
        logger.warning(f"Check rules failed for {file_path}, counting as 0 issues: {e}")
        return counts, ['all rules']
    return counts, sorted({err['rule'] for err in rule_errors})


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
    lines = split_lines(content)
    total_lines = len(lines)

    # Count different line types
    empty_lines, comment_lines, code_lines = count_line_types(lines)

    # Extract element counts
    functions = structure.get('functions', [])
    classes = structure.get('classes', [])
    imports = structure.get('imports', [])

    # Extract complexity metrics
    metrics = extract_complexity_metrics(functions, content, file_path)

    # Run the file-local check rules using already-computed structure + content (no re-parsing)
    local_issue_counts, check_rules_failed = _count_local_check_issues(file_path, structure, content)

    # Calculate quality score
    quality_score = calculate_quality_score(
        metrics['avg_complexity'],
        metrics['avg_func_length'],
        len(metrics['long_functions']),
        len(metrics['deep_nesting']),
        len(functions),
        quality_config,
        local_issue_counts,
    )

    # Get display path
    file_display = get_file_display_path_func(file_path)

    stats = {
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
            'local_check_issues': sum(local_issue_counts.values()),
        },
        'issues': {
            'long_functions': metrics['long_functions'],
            'deep_nesting': metrics['deep_nesting'],
        }
    }
    if check_rules_failed:
        stats['check_rules_failed'] = check_rules_failed
    return stats
