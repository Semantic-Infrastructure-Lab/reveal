"""Centralized configuration management for reveal.

Follows XDG Base Directory Specification for Unix systems.
https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html

Configuration precedence (first found wins):
1. Project-local: ./.reveal/<name>
2. User config: ~/.config/reveal/<name> (or $XDG_CONFIG_HOME/reveal)
3. System config: /etc/reveal/<name>

Data/cache locations:
- User data: ~/.local/share/reveal (or $XDG_DATA_HOME/reveal)
- User cache: ~/.cache/reveal (or $XDG_CACHE_HOME/reveal)
"""

from pathlib import Path
import os
from typing import Optional, List, Dict, Any
import yaml


class RevealConfig:
    """Unified configuration system following XDG standards."""

    def __init__(self):
        self._init_paths()

    def _init_paths(self):
        """Initialize XDG-compliant paths."""
        # XDG Base Directory Specification
        self.user_config_dir = Path(os.getenv('XDG_CONFIG_HOME', Path.home() / '.config')) / 'reveal'
        self.user_data_dir = Path(os.getenv('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / 'reveal'
        self.user_cache_dir = Path(os.getenv('XDG_CACHE_HOME', Path.home() / '.cache')) / 'reveal'
        self.system_config_dir = Path('/etc/reveal')

        # Project-local config (current directory)
        self.project_config_dir = Path.cwd() / '.reveal'

    def get_config_paths(self, name: str) -> List[Path]:
        """Get all possible config file paths in precedence order.

        Args:
            name: Config filename (e.g., 'mysql-health-checks.yaml')

        Returns:
            List of paths in precedence order (project → user → system)
        """
        return [
            self.project_config_dir / name,
            self.user_config_dir / name,
            self.system_config_dir / name,
        ]

    def get_config_file(self, name: str, create_dirs: bool = False) -> Optional[Path]:
        """Get path to a config file, checking precedence order.

        Precedence:
        1. Project: ./.reveal/<name>
        2. User: ~/.config/reveal/<name>
        3. System: /etc/reveal/<name>

        Args:
            name: Config filename (e.g., 'mysql-health-checks.yaml')
            create_dirs: If True, create parent directories for user config

        Returns:
            Path to first existing config file, or user config path if none exist
        """
        # Return first existing file
        for path in self.get_config_paths(name):
            if path.exists():
                return path

        # None exist - return user config path (for creation)
        user_path = self.user_config_dir / name
        if create_dirs:
            user_path.parent.mkdir(parents=True, exist_ok=True)
        return user_path

    def load_yaml(self, name: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Load YAML config with fallback to defaults.

        Args:
            name: Config filename (e.g., 'mysql-health-checks.yaml')
            default: Default config dict if file doesn't exist or is malformed

        Returns:
            Loaded config dict or default
        """
        for config_path in self.get_config_paths(name):
            if config_path.exists():
                try:
                    with open(config_path) as f:
                        loaded = yaml.safe_load(f)
                        if loaded is not None:
                            return loaded
                except Exception:
                    # Malformed config at this location, try next
                    continue

        # No valid config found
        return default or {}

    def get_cache_file(self, name: str, create_dirs: bool = True) -> Path:
        """Get path to a cache file.

        Args:
            name: Cache filename (e.g., 'last_update_check')
            create_dirs: If True, create parent directories

        Returns:
            Path to cache file in ~/.cache/reveal/
        """
        cache_path = self.user_cache_dir / name
        if create_dirs:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
        return cache_path

    def get_data_file(self, name: str, create_dirs: bool = True) -> Path:
        """Get path to a data file.

        Args:
            name: Data filename (e.g., 'history.db')
            create_dirs: If True, create parent directories

        Returns:
            Path to data file in ~/.local/share/reveal/
        """
        data_path = self.user_data_dir / name
        if create_dirs:
            data_path.parent.mkdir(parents=True, exist_ok=True)
        return data_path

    def get_legacy_paths(self) -> Dict[str, Path]:
        """Get legacy config paths for migration.

        Returns:
            Dict mapping old locations to their purposes
        """
        return {
            'rules_user': Path.home() / '.reveal' / 'rules',
            'rules_project': Path.cwd() / '.reveal' / 'rules',
        }


# Global singleton
_config: Optional[RevealConfig] = None


def get_config() -> RevealConfig:
    """Get global config instance (singleton).

    Returns:
        RevealConfig singleton instance
    """
    global _config
    if _config is None:
        _config = RevealConfig()
    return _config


# Convenience functions for common operations
def load_config(name: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Load YAML config file with defaults (convenience function).

    Args:
        name: Config filename
        default: Default config if file not found

    Returns:
        Config dict
    """
    return get_config().load_yaml(name, default)


def get_cache_path(name: str) -> Path:
    """Get cache file path (convenience function).

    Args:
        name: Cache filename

    Returns:
        Path to cache file
    """
    return get_config().get_cache_file(name)


def get_data_path(name: str) -> Path:
    """Get data file path (convenience function).

    Args:
        name: Data filename

    Returns:
        Path to data file
    """
    return get_config().get_data_file(name)
