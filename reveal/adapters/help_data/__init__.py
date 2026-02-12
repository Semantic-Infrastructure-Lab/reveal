"""Help data loader for adapter help documentation.

Loads help data from YAML files to reduce complexity of get_help() functions.
Pattern follows reveal/schemas/frontmatter/ design.
"""

import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, cast

logger = logging.getLogger(__name__)


class HelpDataLoader:
    """Load help data from YAML files.

    Reduces complexity in adapter get_help() functions by externalizing
    large help dictionaries to YAML files.

    Example:
        >>> help_data = HelpDataLoader.load('mysql')
        >>> help_data = HelpDataLoader.load('diff')
    """

    _cache: Dict[str, Dict[str, Any]] = {}
    _help_dir = Path(__file__).parent

    @classmethod
    def load(cls, adapter_name: str) -> Optional[Dict[str, Any]]:
        """Load help data for an adapter.

        Args:
            adapter_name: Name of adapter (mysql, diff, stats, etc.)

        Returns:
            Help data dict or None if not found

        Example:
            >>> help_data = HelpDataLoader.load('mysql')
        """
        # Check cache
        if adapter_name in cls._cache:
            logger.debug(f"Help data '{adapter_name}' loaded from cache")
            return cls._cache[adapter_name]

        # Construct file path
        help_file = cls._help_dir / f"{adapter_name}.yaml"
        if not help_file.exists():
            logger.error(f"Help data file not found: {help_file}")
            return None

        # Load YAML
        try:
            with open(help_file, 'r', encoding='utf-8') as f:
                help_data = yaml.safe_load(f)

            if not help_data:
                logger.error(f"Help data file is empty: {help_file}")
                return None

            # Cache and return
            cls._cache[adapter_name] = help_data
            logger.debug(f"Help data '{adapter_name}' loaded from {help_file}")
            return cast(Dict[str, Any], help_data)

        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML in {help_file}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to load help data {help_file}: {e}")
            return None

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the help data cache."""
        cls._cache.clear()
        logger.debug("Help data cache cleared")


# Convenience function
def load_help_data(adapter_name: str) -> Optional[Dict[str, Any]]:
    """Load help data for an adapter.

    Args:
        adapter_name: Name of adapter (mysql, diff, stats, etc.)

    Returns:
        Help data dict or None if not found

    Example:
        >>> from reveal.adapters.help_data import load_help_data
        >>> help_data = load_help_data('mysql')
    """
    return HelpDataLoader.load(adapter_name)
