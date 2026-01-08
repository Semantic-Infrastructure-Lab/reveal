"""Front matter validation engine.

This module provides validation utilities for F-series rules.
Supports type checking, custom validation, and schema context management.

The validation schema is passed via a global variable (_validation_schema_context)
which F-series rules access via get_validation_schema().

Example:
    >>> from reveal.rules.frontmatter import validate_type, get_validation_schema
    >>> validate_type("hello", "string")  # True
    >>> validate_type("hello", "integer")  # False
"""

import re
import logging
from typing import Any, Optional, Dict
from datetime import datetime, date

logger = logging.getLogger(__name__)

# Global validation schema context (set by CLI handler)
_validation_schema_context: Optional[Dict[str, Any]] = None


def validate_type(value: Any, expected_type: str) -> bool:
    """Validate that value matches expected type.

    Args:
        value: Value to check
        expected_type: Expected type (string, list, dict, integer, boolean, date)

    Returns:
        True if value matches expected type, False otherwise

    Example:
        >>> validate_type("hello", "string")
        True
        >>> validate_type(["a", "b"], "list")
        True
        >>> validate_type("2024-01-01", "date")
        True
        >>> validate_type("hello", "integer")
        False
    """
    if expected_type == "string":
        return isinstance(value, str)
    elif expected_type == "list":
        return isinstance(value, list)
    elif expected_type == "dict":
        return isinstance(value, dict)
    elif expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    elif expected_type == "boolean":
        return isinstance(value, bool)
    elif expected_type == "date":
        # Accept datetime.date/datetime.datetime objects (YAML auto-parses dates)
        if isinstance(value, (date, datetime)):
            return True
        # Also accept string dates in YYYY-MM-DD format (strict)
        if isinstance(value, str):
            # First check format with regex (ensures zero-padded)
            if not re.match(r'^\d{4}-\d{2}-\d{2}', value):
                return False
            # Then validate it's a real date
            try:
                datetime.strptime(value[:10], "%Y-%m-%d")
                return True
            except ValueError:
                return False
        return False
    else:
        logger.warning(f"Unknown type: {expected_type}")
        return False


def safe_eval_validation(check: str, context: Dict[str, Any]) -> bool:
    """Safely evaluate custom validation check.

    Args:
        check: Python expression to evaluate (e.g., "len(value) >= 1")
        context: Context dict with 'value' and other variables

    Returns:
        True if check passes, False otherwise

    Security:
        Uses restricted eval with limited builtins (len, re, str, int, etc.)
        No access to __builtins__, __import__, exec, eval, etc.

    Example:
        >>> safe_eval_validation("len(value) >= 1", {"value": ["topic1"]})
        True
        >>> safe_eval_validation("re.match(r'^[a-z]+$', value)", {"value": "hello"})
        True
    """
    # Safe builtins for validation
    safe_builtins = {
        'len': len,
        're': re,
        'str': str,
        'int': int,
        'bool': bool,
        'list': list,
        'dict': dict,
        'isinstance': isinstance,
        'all': all,        # For checking all items in a list
        'any': any,        # For checking any items in a list
        'True': True,
        'False': False,
        'None': None,
    }

    try:
        # Merge safe builtins with context
        eval_context = {**safe_builtins, **context}
        result = eval(check, {"__builtins__": {}}, eval_context)
        return bool(result)
    except Exception as e:
        # Debug-level logging to avoid confusing users
        # (exceptions are expected when types don't match)
        logger.debug(f"Validation check skipped due to error: {check} - {e}")
        return False


def get_validation_schema() -> Optional[Dict[str, Any]]:
    """Get the current validation schema context.

    Returns:
        Schema dict or None if no schema is set

    Example:
        >>> schema = get_validation_schema()
        >>> if schema:
        ...     required = schema.get('required_fields', [])
    """
    return _validation_schema_context


def set_validation_context(schema: Optional[Dict[str, Any]]) -> None:
    """Set the validation schema context.

    Args:
        schema: Schema dict or None to clear

    This is called by the CLI handler before running F-series rules.
    F-series rules access the schema via get_validation_schema().

    Example:
        >>> from reveal.schemas.frontmatter import load_schema
        >>> schema = load_schema('session')
        >>> set_validation_context(schema)
        >>> # ... run F-series rules ...
        >>> set_validation_context(None)  # Clear
    """
    global _validation_schema_context
    _validation_schema_context = schema
    if schema:
        logger.debug(f"Validation context set: {schema.get('name', 'unknown')}")
    else:
        logger.debug("Validation context cleared")


def clear_validation_context() -> None:
    """Clear the validation schema context.

    Convenience function, equivalent to set_validation_context(None).
    """
    set_validation_context(None)
