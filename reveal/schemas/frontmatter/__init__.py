"""Front matter schema loader and validator.

This module provides schema loading and validation for markdown front matter.
Schemas define required fields, type constraints, and custom validation rules.

Example:
    >>> from reveal.schemas.frontmatter import load_schema
    >>> schema = load_schema('beth')
    >>> print(schema['name'])
    'Beth Session Schema'
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class SchemaLoader:
    """Load and validate front matter schemas.

    Schemas can be loaded by name (built-in) or by file path (custom).
    Schemas are cached after first load to avoid repeated YAML parsing.

    Built-in schemas are located in this directory (reveal/schemas/frontmatter/).
    Custom schemas can be loaded from any file path.

    Example:
        >>> schema = SchemaLoader.load_schema('beth')
        >>> schema = SchemaLoader.load_schema('/path/to/custom.yaml')
        >>> schemas = SchemaLoader.list_builtin_schemas()
    """

    _schema_cache: Dict[str, Dict[str, Any]] = {}
    _schema_dir = Path(__file__).parent

    @classmethod
    def load_schema(cls, schema_name_or_path: str) -> Optional[Dict[str, Any]]:
        """Load schema by name or file path.

        Args:
            schema_name_or_path: Schema name (beth, hugo, obsidian) or path to YAML file

        Returns:
            Schema dict or None if not found/invalid

        Example:
            >>> schema = SchemaLoader.load_schema('beth')
            >>> schema = SchemaLoader.load_schema('/tmp/custom.yaml')
        """
        # Check cache
        if schema_name_or_path in cls._schema_cache:
            logger.debug(f"Schema '{schema_name_or_path}' loaded from cache")
            return cls._schema_cache[schema_name_or_path]

        # Resolve to file path
        schema_path = cls._resolve_schema_path(schema_name_or_path)
        if not schema_path or not schema_path.exists():
            logger.error(f"Schema not found: {schema_name_or_path}")
            return None

        # Load YAML
        try:
            with open(schema_path, 'r') as f:
                schema = yaml.safe_load(f)

            if not schema:
                logger.error(f"Schema file is empty: {schema_path}")
                return None

            # Validate schema structure
            if not cls._validate_schema_structure(schema):
                logger.error(f"Invalid schema structure: {schema_path}")
                return None

            # Cache and return
            cls._schema_cache[schema_name_or_path] = schema
            logger.debug(f"Schema '{schema_name_or_path}' loaded from {schema_path}")
            return schema

        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML in {schema_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to load schema {schema_path}: {e}")
            return None

    @classmethod
    def _resolve_schema_path(cls, name_or_path: str) -> Optional[Path]:
        """Resolve schema name to file path.

        Args:
            name_or_path: Schema name or file path

        Returns:
            Path object or None if not found

        Resolution order:
            1. If it's an existing file path, use it
            2. Try as built-in schema (name.yaml in schema directory)
            3. Try with .yaml extension if missing
        """
        path = Path(name_or_path)

        # If it's an existing absolute/relative file, use it
        if path.exists() and path.is_file():
            return path.resolve()

        # Try as built-in schema (with or without .yaml extension)
        if not path.suffix or path.suffix == '.yaml':
            schema_name = path.stem if path.suffix else name_or_path
            builtin = cls._schema_dir / f"{schema_name}.yaml"
            if builtin.exists():
                return builtin

        return None

    @classmethod
    def _validate_schema_structure(cls, schema: Dict[str, Any]) -> bool:
        """Validate schema has required structure.

        Args:
            schema: Schema dict

        Returns:
            True if valid, False otherwise

        Requirements:
            - Must have 'name' field
            - Must have at least one constraint field:
              - required_fields
              - optional_fields
              - field_types
              - validation_rules
              - constraints
        """
        # Required: name field
        if 'name' not in schema:
            logger.error("Schema missing required 'name' field")
            return False

        # Must have at least one constraint field
        constraint_fields = [
            'required_fields',
            'optional_fields',
            'field_types',
            'validation_rules',
            'constraints'
        ]

        has_constraints = any(field in schema for field in constraint_fields)

        if not has_constraints:
            logger.error(
                f"Schema must include at least one of: {', '.join(constraint_fields)}"
            )
            return False

        return True

    @classmethod
    def list_builtin_schemas(cls) -> List[str]:
        """List all built-in schemas.

        Returns:
            List of schema names (without .yaml extension), sorted alphabetically

        Example:
            >>> schemas = SchemaLoader.list_builtin_schemas()
            >>> print(schemas)
            ['beth', 'hugo', 'obsidian']
        """
        schemas = []
        for file in cls._schema_dir.glob('*.yaml'):
            schemas.append(file.stem)
        return sorted(schemas)

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the schema cache.

        Useful for testing or if schemas are modified at runtime.
        """
        cls._schema_cache.clear()
        logger.debug("Schema cache cleared")


# Public API functions

def load_schema(name_or_path: str) -> Optional[Dict[str, Any]]:
    """Load a front matter schema.

    Public API for schema loading. Schemas are cached after first load.

    Args:
        name_or_path: Schema name (beth, hugo, obsidian) or path to YAML file

    Returns:
        Schema dict or None if not found/invalid

    Example:
        >>> schema = load_schema('beth')
        >>> if schema:
        ...     print(f"Loaded schema: {schema['name']}")
    """
    return SchemaLoader.load_schema(name_or_path)


def list_schemas() -> List[str]:
    """List all built-in schemas.

    Returns:
        List of schema names, sorted alphabetically

    Example:
        >>> schemas = list_schemas()
        >>> for name in schemas:
        ...     print(f"Available schema: {name}")
    """
    return SchemaLoader.list_builtin_schemas()


def clear_cache() -> None:
    """Clear the schema cache.

    Useful for testing or if schemas are modified at runtime.
    """
    SchemaLoader.clear_cache()
