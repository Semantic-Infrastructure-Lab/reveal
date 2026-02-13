"""Aggregation and hotspot identification for stats adapter."""

from pathlib import Path
from typing import Dict, Any, List


def aggregate_stats(file_stats: List[Dict[str, Any]], source_path: Path) -> Dict[str, Any]:
    """Aggregate statistics from multiple files.

    Args:
        file_stats: List of file statistics
        source_path: Source path for the aggregation

    Returns:
        Dict with aggregated statistics
    """
    if not file_stats:
        return {
            'contract_version': '1.0',
            'type': 'stats_summary',
            'source': str(source_path),
            'source_type': 'directory' if source_path.is_dir() else 'file',
            'summary': {
                'total_files': 0,
                'total_lines': 0,
                'total_code_lines': 0,
                'total_functions': 0,
                'total_classes': 0,
                'avg_complexity': 0,
                'avg_quality_score': 0,
            },
            'files': []
        }

    total_lines = sum(s['lines']['total'] for s in file_stats)
    total_code = sum(s['lines']['code'] for s in file_stats)
    total_functions = sum(s['elements']['functions'] for s in file_stats)
    total_classes = sum(s['elements']['classes'] for s in file_stats)

    # Weighted average complexity (by number of functions)
    complexity_sum = sum(s['complexity']['average'] * s['elements']['functions'] for s in file_stats)
    avg_complexity = complexity_sum / total_functions if total_functions > 0 else 0

    avg_quality = sum(s['quality']['score'] for s in file_stats) / len(file_stats)

    return {
        'contract_version': '1.0',
        'type': 'stats_summary',
        'source': str(source_path),
        'source_type': 'directory' if source_path.is_dir() else 'file',
        'summary': {
            'total_files': len(file_stats),
            'total_lines': total_lines,
            'total_code_lines': total_code,
            'total_functions': total_functions,
            'total_classes': total_classes,
            'avg_complexity': round(avg_complexity, 2),
            'avg_quality_score': round(avg_quality, 1),
        },
        'files': file_stats
    }


def identify_hotspots(file_stats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Identify top 10 hotspot files.

    Hotspots are files with quality issues: long functions, high complexity,
    deep nesting, or low quality scores.

    Args:
        file_stats: List of file statistics

    Returns:
        List of top 10 hotspot files sorted by severity
    """
    # Score each file by number and severity of issues
    scored_files = []
    for stats in file_stats:
        hotspot_score = 0
        issues = []

        # Low quality score
        quality = stats['quality']['score']
        if quality < 70:
            hotspot_score += (70 - quality) / 10
            issues.append(f"Quality: {quality:.1f}/100")

        # High complexity
        complexity = stats['complexity']['average']
        if complexity > 10:
            hotspot_score += complexity - 10
            issues.append(f"Avg complexity: {complexity:.1f}")

        # Long functions
        long_funcs = stats['quality']['long_functions']
        if long_funcs > 0:
            hotspot_score += long_funcs * 5
            issues.append(f"{long_funcs} function(s) >100 lines")

        # Deep nesting
        deep_nest = stats['quality']['deep_nesting']
        if deep_nest > 0:
            hotspot_score += deep_nest * 3
            issues.append(f"{deep_nest} function(s) depth >4")

        if hotspot_score > 0:
            scored_files.append({
                'file': stats['file'],
                'hotspot_score': round(hotspot_score, 1),
                'quality_score': quality,
                'issues': issues,
                'details': {
                    'lines': stats['lines']['total'],
                    'functions': stats['elements']['functions'],
                    'complexity': stats['complexity']['average'],
                }
            })

    # Sort by hotspot score (descending) and return top 10
    scored_files.sort(key=lambda x: x['hotspot_score'], reverse=True)
    return scored_files[:10]
