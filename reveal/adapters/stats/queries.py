"""Query and filtering functions for stats adapter."""

import copy
from pathlib import Path
from typing import Dict, Any, Optional, List, cast

from ...utils.query import compare_values


# Quality scoring defaults - configurable via .reveal/stats-quality.yaml
QUALITY_DEFAULTS = {
    'thresholds': {
        'complexity_target': 10,       # Functions above this get penalized
        'function_length_target': 50,  # Lines; functions above this penalized
        'deep_nesting_depth': 4,       # Nesting beyond this penalized
    },
    'penalties': {
        'complexity': {
            'multiplier': 3,           # Points lost per unit above target
            'max': 30,                 # Maximum penalty
        },
        'length': {
            'divisor': 2,              # Points lost = (excess / divisor)
            'max': 20,
        },
        'ratios': {
            'multiplier': 50,          # For long_func_ratio, deep_nesting_ratio
            'max': 25,
        },
    }
}


def get_quality_config(path: Path) -> Dict[str, Any]:
    """Load quality scoring configuration.

    Config search order:
    1. ./.reveal/stats-quality.yaml (project)
    2. ~/.config/reveal/stats-quality.yaml (user)
    3. Hardcoded QUALITY_DEFAULTS (fallback)

    Args:
        path: Base path for config search

    Returns:
        Quality config dict with thresholds and penalties
    """
    config = copy.deepcopy(QUALITY_DEFAULTS)

    config_paths = [
        path / '.reveal' / 'stats-quality.yaml' if path.is_dir() else path.parent / '.reveal' / 'stats-quality.yaml',
        Path.home() / '.config' / 'reveal' / 'stats-quality.yaml',
    ]

    try:
        import yaml
        for config_path in config_paths:
            if config_path.exists():
                with open(config_path) as f:
                    loaded_raw = yaml.safe_load(f)
                    if loaded_raw and isinstance(loaded_raw, dict):
                        loaded: Dict[str, Any] = loaded_raw
                        # Deep merge loaded config into defaults
                        for key in ['thresholds', 'penalties']:
                            if key in loaded and isinstance(loaded[key], dict) and isinstance(config[key], dict):
                                loaded_section = cast(Dict[str, Any], loaded[key])
                                config_section = cast(Dict[str, Any], config[key])
                                if key == 'penalties':
                                    for subkey in loaded_section:
                                        if subkey in config_section:
                                            config_section[subkey].update(loaded_section[subkey])
                                else:
                                    config_section.update(loaded_section)
                        break
    except ImportError:
        pass  # yaml not available, use defaults
    except Exception:
        pass  # Any config error, use defaults

    return config


def field_value(stats: Dict[str, Any], field: str) -> Any:
    """Extract field value from stats dict.

    Supports nested fields like 'lines.total', 'complexity.average', etc.

    Args:
        stats: File statistics dict
        field: Field name (may include dots for nesting)

    Returns:
        Field value or None if not found
    """
    # Map common field names to nested paths
    field_map = {
        'lines': 'lines.total',
        'code_lines': 'lines.code',
        'comment_lines': 'lines.comments',
        'complexity': 'complexity.average',
        'max_complexity': 'complexity.max',
        'functions': 'elements.functions',
        'classes': 'elements.classes',
        'quality': 'quality.score',
    }

    # Use mapped field if available
    field_path = field_map.get(field, field)

    # Navigate nested structure
    value = stats
    for part in field_path.split('.'):
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return None

    return value


def compare(value: Any, op: str, target: Any) -> bool:
    """Compare a value against a target using an operator.

    Uses unified compare_values() from query.py to eliminate duplication.

    Args:
        value: The value to compare
        op: Comparison operator (>, <, >=, <=, ==, =, !=, ~=, ..)
        target: The target value

    Returns:
        True if comparison passes
    """
    return compare_values(
        value,
        op,
        target,
        options={
            'allow_list_any': False,  # Stats doesn't have list fields
            'case_sensitive': False,
            'coerce_numeric': True,
            'none_matches_not_equal': False  # Stats: None doesn't match anything
        }
    )


def matches_filters(
    stats: Dict[str, Any],
    min_lines: Optional[int],
    max_lines: Optional[int],
    min_complexity: Optional[float],
    max_complexity: Optional[float],
    min_functions: Optional[int],
    query_filters: list,
    field_value_func,
    compare_func
) -> bool:
    """Check if file stats match filter criteria.

    Supports both legacy parameters (min_lines, max_lines, etc.) and
    new unified query filters (lines>50, complexity=5..15, etc.).

    Args:
        stats: File statistics
        min_lines: Minimum line count (legacy)
        max_lines: Maximum line count (legacy)
        min_complexity: Minimum avg complexity (legacy)
        max_complexity: Maximum avg complexity (legacy)
        min_functions: Minimum function count (legacy)
        query_filters: List of query filter objects
        field_value_func: Function to extract field values
        compare_func: Function to compare values

    Returns:
        True if matches all filters
    """
    # Check legacy parameters (backward compatibility)
    if min_lines is not None and stats['lines']['total'] < min_lines:
        return False
    if max_lines is not None and stats['lines']['total'] > max_lines:
        return False
    if min_complexity is not None and stats['complexity']['average'] < min_complexity:
        return False
    if max_complexity is not None and stats['complexity']['average'] > max_complexity:
        return False
    if min_functions is not None and stats['elements']['functions'] < min_functions:
        return False

    # Check new query filters (unified syntax)
    for qf in query_filters:
        value = field_value_func(stats, qf.field)
        if not compare_func(value, qf.op, qf.value):
            return False

    return True
