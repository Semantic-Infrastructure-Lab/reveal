"""Unified configuration system for reveal.

Supports multi-level precedence with deep merge semantics:
1. Command line flags (--select, --ignore, --config)
2. Environment variables (REVEAL_CONFIG, REVEAL_RULES_DISABLE)
3. Project config (.reveal.yaml - walks up directory tree)
4. User config (~/.config/reveal/config.yaml)
5. System config (/etc/reveal/config.yaml)
6. Built-in defaults (hardcoded in rules)

Configuration files are discovered by walking up the directory tree from the
target path until a config with root:true is found or the filesystem root.

YAML is the primary format. TOML support via pyproject.toml [tool.reveal] section.
"""

from pathlib import Path
import os
import sys
import logging
import json
import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import fnmatch

try:
    import yaml
except ImportError:
    yaml = None

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # Backport
    except ImportError:
        tomllib = None

try:
    import jsonschema
except ImportError:
    jsonschema = None

logger = logging.getLogger(__name__)


def glob_match(path: Path, pattern: str) -> bool:
    """Match a path against a glob pattern with ** support (gitignore-style).

    Supports:
    - * matches anything except /
    - ** matches zero or more path components
    - ? matches any single character except /

    Args:
        path: Path to match (can be relative or absolute)
        pattern: Glob pattern

    Returns:
        True if path matches pattern
    """
    path_str = str(path).replace(os.sep, '/')

    # Convert glob pattern to regex
    # Handle ** specially for gitignore-style matching
    if '**' in pattern:
        # Replace ** with regex that matches zero or more path components
        # Handle different positions of **
        pattern = pattern.replace('/**/', '/§§/')  # Middle position
        pattern = pattern.replace('**/', '§§/')     # Start position
        pattern = pattern.replace('/**', '/§§')     # End position
        pattern = pattern.replace('**', '§§')       # Standalone

        # Now convert the rest to regex using fnmatch
        pattern = fnmatch.translate(pattern)

        # Replace our markers with proper regex
        # /§§/ means zero or more path components with slashes
        pattern = pattern.replace('/§§/', '(/|/.*/)')
        # §§/ at start means zero or more path components
        pattern = pattern.replace('§§/', '(.*/)?')
        # /§§ at end means zero or more path components
        pattern = pattern.replace('/§§', '(/.*)?')
        # Standalone §§
        pattern = pattern.replace('§§', '.*')
    else:
        # Simple pattern, use fnmatch
        pattern = fnmatch.translate(pattern)

    # Match the pattern
    return re.match(pattern, path_str) is not None


# JSON Schema for .reveal.yaml validation
CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "root": {"type": "boolean"},
        "extends": {"type": "string"},
        "ignore": {
            "type": "array",
            "items": {"type": "string"}
        },
        "include": {
            "type": "array",
            "items": {"type": "string"}
        },
        "rules": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"},
                "disable": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "select": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "additionalProperties": True  # Per-rule configs
        },
        "overrides": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["files"],
                "properties": {
                    "files": {"type": "string"},
                    "rules": {"type": "object"}
                }
            }
        },
        "architecture": {
            "type": "object",
            "properties": {
                "layers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "paths"],
                        "properties": {
                            "name": {"type": "string"},
                            "paths": {"type": "array"},
                            "allow_imports": {"type": "array"},
                            "deny_imports": {"type": "array"}
                        }
                    }
                }
            }
        },
        "imports": {"type": "object"},
        "adapters": {"type": "object"},
        "plugins": {"type": "object"},
        "output": {"type": "object"},
        "cache": {"type": "object"},
        "display": {
            "type": "object",
            "properties": {
                "breadcrumbs": {"type": "boolean"}
            },
            "additionalProperties": False
        }
    },
    "additionalProperties": False
}


@dataclass
class Override:
    """Per-directory configuration override."""

    files_pattern: str
    config: Dict[str, Any]

    def matches(self, file_path: Path, project_root: Optional[Path] = None) -> bool:
        """Check if this override matches the given file path.

        Args:
            file_path: File to check
            project_root: Project root for relative matching

        Returns:
            True if pattern matches file_path
        """
        if project_root:
            try:
                # Resolve both paths to handle symlinks consistently (macOS /var vs /private/var)
                resolved_file = file_path.resolve()
                resolved_root = project_root.resolve()
                rel_path = resolved_file.relative_to(resolved_root)
            except ValueError:
                rel_path = file_path
        else:
            rel_path = file_path

        # Use glob_match for proper ** support
        return glob_match(rel_path, self.files_pattern)


@dataclass
class FileConfig:
    """Configuration effective for a specific file (after applying overrides)."""

    _config: Dict[str, Any]
    _file_path: Path

    def is_rule_enabled(self, rule_code: str) -> bool:
        """Check if a rule is enabled for this file.

        Args:
            rule_code: Rule code (e.g., "E501", "C901")

        Returns:
            True if rule should run on this file
        """
        rules = self._config.get('rules', {})

        # Check global enabled flag
        if not rules.get('enabled', True):
            return False

        # Check if in disable list
        disabled = rules.get('disable', [])
        if rule_code in disabled:
            return False

        # Check if in select list (if select is specified, only those run)
        selected = rules.get('select', [])
        if selected:
            # Check if rule code or prefix matches
            if rule_code not in selected:
                # Check prefix (e.g., "B" matches "B001", "B002")
                prefix = rule_code[0] if rule_code else ""
                if prefix not in selected:
                    return False

        return True

    def get_rule_config(self, rule_code: str, key: str, default: Any = None) -> Any:
        """Get configuration value for a specific rule.

        Args:
            rule_code: Rule code (e.g., "E501")
            key: Config key (e.g., "max_length")
            default: Default value if not set

        Returns:
            Config value or default
        """
        rules = self._config.get('rules', {})
        rule_config = rules.get(rule_code, {})
        return rule_config.get(key, default)


class RevealConfig:
    """Unified configuration manager with multi-level precedence."""

    # Class-level cache: project_root -> config instance
    _cache: Dict[Path, 'RevealConfig'] = {}

    def __init__(self, merged_config: Dict[str, Any], project_root: Optional[Path] = None):
        """Initialize with merged configuration.

        Args:
            merged_config: Final merged configuration dict
            project_root: Project root directory (where root:true config lives)
        """
        self._config = merged_config
        self._project_root = project_root or Path.cwd()
        self._overrides = self._parse_overrides()

    def _parse_overrides(self) -> List[Override]:
        """Parse override sections into Override objects."""
        overrides = []
        for override in self._config.get('overrides', []):
            overrides.append(Override(
                files_pattern=override['files'],
                config=override
            ))
        return overrides

    @classmethod
    def get(cls,
            start_path: Optional[Path] = None,
            cli_overrides: Optional[Dict[str, Any]] = None,
            no_config: bool = False) -> 'RevealConfig':
        """Get or create config instance (singleton per project root).

        Args:
            start_path: Starting path for config discovery (default: cwd)
            cli_overrides: Command-line overrides (highest precedence)
            no_config: If True, use only defaults (skip all config files)

        Environment variables:
            REVEAL_NO_CONFIG: Set to '1' to skip all config files (like --no-config)
            REVEAL_CONFIG: Path to a specific config file to load instead of discovery

        Returns:
            RevealConfig instance
        """
        # Check REVEAL_NO_CONFIG environment variable
        if os.getenv('REVEAL_NO_CONFIG') == '1':
            no_config = True

        if start_path is None:
            start_path = Path.cwd()

        # Normalize to absolute path
        start_path = start_path.resolve()
        if start_path.is_file():
            start_path = start_path.parent

        # Check cache (unless no_config mode)
        if not no_config:
            project_root = cls._find_project_root(start_path)
            # Make cli_overrides hashable by converting to JSON string
            cli_key = json.dumps(cli_overrides or {}, sort_keys=True)
            cache_key = (project_root, cli_key)
            if cache_key in cls._cache:
                return cls._cache[cache_key]
        else:
            project_root = start_path

        # Load and merge configs
        merged = cls._load_and_merge(start_path, cli_overrides, no_config)

        # Create instance
        instance = cls(merged, project_root)

        # Cache it
        if not no_config:
            cls._cache[cache_key] = instance

        return instance

    @classmethod
    def _find_project_root(cls, start_path: Path) -> Path:
        """Find project root (where root:true config lives or git root)."""
        current = start_path

        while current != current.parent:
            # Check for .reveal.yaml with root:true
            config_file = current / '.reveal.yaml'
            if config_file.exists():
                try:
                    if yaml:
                        with open(config_file) as f:
                            config = yaml.safe_load(f) or {}
                        if config.get('root'):
                            return current.resolve()
                except Exception:
                    pass

            # Check for .git (common project root marker)
            if (current / '.git').exists():
                return current.resolve()

            current = current.parent

        # Fallback to start_path
        return start_path.resolve()

    @classmethod
    def _load_and_merge(cls,
                        start_path: Path,
                        cli_overrides: Optional[Dict[str, Any]] = None,
                        no_config: bool = False) -> Dict[str, Any]:
        """Load all configs and merge with precedence rules.

        Precedence (high to low):
        1. CLI overrides
        2. Environment variables
        3. REVEAL_CONFIG custom file (if specified)
        4. Project configs (walk up tree)
        5. User config
        6. System config
        7. Built-in defaults
        """
        configs = []

        if not no_config:
            # Check for REVEAL_CONFIG environment variable
            custom_config_path = os.getenv('REVEAL_CONFIG')

            if custom_config_path:
                # Load only the specified config file
                custom_config = cls._load_file(Path(custom_config_path))
                if custom_config:
                    configs.append(custom_config)
                else:
                    logger.warning(
                        f"REVEAL_CONFIG specified but file not found: {custom_config_path}"
                    )
            else:
                # Normal config discovery
                # 1. System config
                system_config = cls._load_file(Path('/etc/reveal/config.yaml'))
                if system_config:
                    configs.append(system_config)

                # 2. User config
                user_config_path = cls._get_user_config_path()
                if user_config_path.exists():
                    user_config = cls._load_file(user_config_path)
                    if user_config:
                        configs.append(user_config)

                # 3. Project configs (walk up from start_path)
                project_configs = cls._discover_project_configs(start_path)
                configs.extend(reversed(project_configs))  # Reverse so nearest is last

            # 4. Environment variables (always loaded, even with REVEAL_CONFIG)
            env_config = cls._load_from_env()
            if env_config:
                configs.append(env_config)

        # 5. CLI overrides (highest precedence)
        if cli_overrides:
            configs.append(cli_overrides)

        # Merge all configs (later configs override earlier)
        merged = {}
        for config in configs:
            merged = deep_merge(merged, config)

        return merged

    @classmethod
    def _discover_project_configs(cls, start_path: Path) -> List[Dict[str, Any]]:
        """Walk up directory tree finding .reveal.yaml files.

        Returns:
            List of configs from root to start_path (furthest to nearest)
        """
        configs = []
        current = start_path

        while current != current.parent:
            # Check .reveal.yaml first
            config_file = current / '.reveal.yaml'
            if config_file.exists():
                config = cls._load_file(config_file)
                if config:
                    configs.append(config)
                    # Stop if root:true
                    if config.get('root'):
                        break

            # Check pyproject.toml [tool.reveal]
            pyproject = current / 'pyproject.toml'
            if pyproject.exists() and tomllib:
                try:
                    with open(pyproject, 'rb') as f:
                        data = tomllib.load(f)
                    reveal_config = data.get('tool', {}).get('reveal')
                    if reveal_config:
                        configs.append(reveal_config)
                        if reveal_config.get('root'):
                            break
                except Exception as e:
                    logger.debug(f"Failed to load {pyproject}: {e}")

            current = current.parent

        return configs

    @classmethod
    def _load_file(cls, path: Path) -> Optional[Dict[str, Any]]:
        """Load and validate a config file.

        Args:
            path: Path to YAML config file

        Returns:
            Loaded config dict or None if error
        """
        if not path.exists():
            return None

        try:
            if yaml:
                with open(path) as f:
                    config = yaml.safe_load(f)

                if config is None:
                    return {}

                # Validate schema if jsonschema available
                if jsonschema:
                    try:
                        jsonschema.validate(config, CONFIG_SCHEMA)
                    except jsonschema.ValidationError as e:
                        logger.warning(f"Invalid config in {path}: {e.message}")
                        # Continue anyway (don't fail on validation)

                return config
            else:
                logger.warning(f"PyYAML not installed, cannot load {path}")
                return None

        except Exception as e:
            logger.error(f"Failed to load config {path}: {e}")
            return None

    @classmethod
    def _get_user_config_path(cls) -> Path:
        """Get user config path following XDG spec."""
        xdg_config = os.getenv('XDG_CONFIG_HOME')
        if xdg_config:
            return Path(xdg_config) / 'reveal' / 'config.yaml'
        return Path.home() / '.config' / 'reveal' / 'config.yaml'

    @classmethod
    def _load_from_env(cls) -> Dict[str, Any]:
        """Load configuration from environment variables.

        Supported environment variables:
        - REVEAL_RULES_DISABLE: Comma-separated list of rules to disable
        - REVEAL_RULES_SELECT: Comma-separated list of rules/categories to select
        - REVEAL_FORMAT: Output format (json, yaml, etc.)
        - REVEAL_IGNORE: Comma-separated glob patterns to ignore
        - REVEAL_C901_THRESHOLD: Complexity threshold for C901 rule
        - REVEAL_E501_MAX_LENGTH: Max line length for E501 rule
        - REVEAL_BREADCRUMBS: Enable/disable breadcrumbs (0/1, false/true, no/yes)

        Examples:
            export REVEAL_RULES_DISABLE="E501,D001"
            export REVEAL_RULES_SELECT="B,S"
            export REVEAL_FORMAT=json
            export REVEAL_IGNORE="*.min.js,vendor/**"
            export REVEAL_C901_THRESHOLD=20
            export REVEAL_E501_MAX_LENGTH=120
            export REVEAL_BREADCRUMBS=0
        """
        config: Dict[str, Any] = {}

        # REVEAL_RULES_DISABLE="E501,D001"
        if disable := os.getenv('REVEAL_RULES_DISABLE'):
            config['rules'] = {'disable': [r.strip() for r in disable.split(',')]}

        # REVEAL_RULES_SELECT="B,S"
        if select := os.getenv('REVEAL_RULES_SELECT'):
            config.setdefault('rules', {})['select'] = [r.strip() for r in select.split(',')]

        # REVEAL_FORMAT=json
        if fmt := os.getenv('REVEAL_FORMAT'):
            config['output'] = {'format': fmt}

        # REVEAL_IGNORE="*.min.js,vendor/**"
        if ignore := os.getenv('REVEAL_IGNORE'):
            config['ignore'] = [p.strip() for p in ignore.split(',')]

        # Rule-specific configuration via environment variables
        # REVEAL_C901_THRESHOLD=20
        if threshold := os.getenv('REVEAL_C901_THRESHOLD'):
            try:
                config.setdefault('rules', {})['C901'] = {'threshold': int(threshold)}
            except ValueError:
                logger.warning(f"Invalid REVEAL_C901_THRESHOLD value: {threshold}")

        # REVEAL_E501_MAX_LENGTH=120
        if max_length := os.getenv('REVEAL_E501_MAX_LENGTH'):
            try:
                config.setdefault('rules', {})['E501'] = {'max_length': int(max_length)}
            except ValueError:
                logger.warning(f"Invalid REVEAL_E501_MAX_LENGTH value: {max_length}")

        # REVEAL_BREADCRUMBS=0 (or 1, false, true, no, yes)
        if breadcrumbs_env := os.getenv('REVEAL_BREADCRUMBS'):
            config.setdefault('display', {})['breadcrumbs'] = (
                breadcrumbs_env.lower() not in ('0', 'false', 'no')
            )

        return config

    def get_file_config(self, file_path: Path) -> FileConfig:
        """Get effective configuration for a specific file.

        Applies overrides matching the file path.

        Args:
            file_path: File to get config for

        Returns:
            FileConfig instance with merged configuration
        """
        # Start with base config
        effective = self._config.copy()

        # Apply matching overrides
        for override in self._overrides:
            if override.matches(file_path, self._project_root):
                effective = deep_merge(effective, override.config)

        return FileConfig(effective, file_path)

    def is_rule_enabled(self, rule_code: str, file_path: Optional[Path] = None) -> bool:
        """Check if a rule is globally enabled.

        Args:
            rule_code: Rule code (e.g., "E501")
            file_path: Optional file path for per-file config

        Returns:
            True if rule should run
        """
        if file_path:
            return self.get_file_config(file_path).is_rule_enabled(rule_code)

        # Global check
        rules = self._config.get('rules', {})

        if not rules.get('enabled', True):
            return False

        disabled = rules.get('disable', [])
        if rule_code in disabled:
            return False

        selected = rules.get('select', [])
        if selected:
            if rule_code not in selected:
                prefix = rule_code[0] if rule_code else ""
                if prefix not in selected:
                    return False

        return True

    def get_rule_config(self, rule_code: str, key: str, default: Any = None) -> Any:
        """Get configuration for a specific rule.

        Args:
            rule_code: Rule code (e.g., "C901")
            key: Config key (e.g., "threshold")
            default: Default value

        Returns:
            Configuration value or default
        """
        rules = self._config.get('rules', {})
        rule_config = rules.get(rule_code, {})
        return rule_config.get(key, default)

    def should_ignore(self, path: Path) -> bool:
        """Check if a path should be ignored.

        Args:
            path: Path to check

        Returns:
            True if path matches ignore patterns
        """
        ignore_patterns = self._config.get('ignore', [])

        # Normalize to relative path
        if self._project_root:
            try:
                # Resolve both paths to handle symlinks consistently (macOS /var vs /private/var)
                resolved_path = path.resolve()
                resolved_root = self._project_root.resolve()
                rel_path = resolved_path.relative_to(resolved_root)
            except ValueError:
                rel_path = path
        else:
            rel_path = path

        # Use glob_match for proper ** support
        for pattern in ignore_patterns:
            if glob_match(rel_path, pattern):
                return True

        return False

    def get_layers(self) -> List[Dict[str, Any]]:
        """Get architectural layers configuration (for I003).

        Returns:
            List of layer definitions
        """
        arch = self._config.get('architecture', {})
        return arch.get('layers', [])

    def get_adapter_config(self, adapter_name: str, section: Optional[str] = None) -> Dict[str, Any]:
        """Get adapter-specific configuration.

        Args:
            adapter_name: Adapter name (e.g., "mysql")
            section: Optional section within adapter config

        Returns:
            Adapter configuration dict
        """
        adapters = self._config.get('adapters', {})
        adapter_config = adapters.get(adapter_name, {})

        if section:
            return adapter_config.get(section, {})
        return adapter_config

    def get_plugin_config(self, plugin_name: str) -> Dict[str, Any]:
        """Get plugin-specific configuration (namespace isolated).

        Args:
            plugin_name: Plugin name

        Returns:
            Plugin configuration dict
        """
        plugins = self._config.get('plugins', {})
        return plugins.get(plugin_name, {})

    def dump(self) -> str:
        """Dump merged configuration as YAML for debugging.

        Returns:
            YAML string of merged config
        """
        if yaml:
            return yaml.dump(self._config, default_flow_style=False)
        return str(self._config)

    @property
    def project_root(self) -> Path:
        """Get project root directory."""
        return self._project_root

    @property
    def user_data_dir(self) -> Path:
        """Get user data directory (backwards compatibility for rule discovery)."""
        return get_data_path('').parent

    @property
    def project_config_dir(self) -> Path:
        """Get project config directory (backwards compatibility for rule discovery)."""
        return Path.cwd() / '.reveal'

    def get_legacy_paths(self) -> Dict[str, Path]:
        """Get legacy config paths for migration (backwards compatibility).

        Returns:
            Dict mapping old locations to their purposes
        """
        return {
            'rules_user': Path.home() / '.reveal' / 'rules',
            'rules_project': Path.cwd() / '.reveal' / 'rules',
        }

    def is_breadcrumbs_enabled(self) -> bool:
        """Check if breadcrumbs are enabled.

        Breadcrumbs are navigation hints printed after reveal output.
        They can be disabled via config, environment, or CLI.

        TTY Detection:
            When stdout is not a TTY (piped to file, AI agent, etc.),
            breadcrumbs are automatically suppressed.

        First-run hint:
            On first use in a terminal, shows a hint about --no-breadcrumbs.

        Returns:
            True if breadcrumbs should be displayed (default: True for TTY)
        """
        display_config = self._config.get('display', {})

        # Explicit config always wins
        if 'breadcrumbs' in display_config:
            return display_config['breadcrumbs']

        # TTY detection: suppress breadcrumbs when output is piped
        if not sys.stdout.isatty():
            return False

        # First time in terminal: hint about disabling
        _show_breadcrumb_hint_once()
        return True


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deeply merge two configuration dictionaries.

    Merge rules:
    - Scalars (str, int, bool): override replaces base
    - Lists: override extends base (concatenate)
    - Dicts: recursive deep merge

    Args:
        base: Base configuration (lower precedence)
        override: Override configuration (higher precedence)

    Returns:
        Merged configuration dict
    """
    result = base.copy()

    for key, value in override.items():
        if key not in result:
            # New key from override
            result[key] = value

        elif isinstance(value, dict) and isinstance(result[key], dict):
            # Both dicts: recursive merge
            result[key] = deep_merge(result[key], value)

        elif isinstance(value, list) and isinstance(result[key], list):
            # Both lists: extend (concatenate)
            result[key] = result[key] + value

        else:
            # Scalar or type mismatch: override wins
            result[key] = value

    return result


# Global singleton instance
_config: Optional[RevealConfig] = None


def get_config(start_path: Optional[Path] = None, **kwargs) -> RevealConfig:
    """Get global config instance (convenience function).

    Args:
        start_path: Starting path for discovery
        **kwargs: Additional arguments passed to RevealConfig.get()

    Returns:
        RevealConfig instance
    """
    global _config
    if _config is None or start_path is not None:
        _config = RevealConfig.get(start_path, **kwargs)
    return _config


# Backwards compatibility functions (for existing code)
def load_config(name: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """DEPRECATED: Load YAML config file with defaults.

    This function maintains backwards compatibility with old code.
    New code should use RevealConfig.get() instead.

    Args:
        name: Config filename (e.g., 'mysql-health-checks.yaml')
        default: Default config if not found

    Returns:
        Config dict
    """
    logger.warning(f"load_config('{name}') is deprecated. Use RevealConfig.get() instead.")

    # Try to load from old locations for backwards compatibility
    config_paths = [
        Path.cwd() / '.reveal' / name,
        Path.home() / '.config' / 'reveal' / name,
        Path('/etc/reveal') / name,
    ]

    for path in config_paths:
        if path.exists() and yaml:
            try:
                with open(path) as f:
                    loaded = yaml.safe_load(f)
                    if loaded is not None:
                        return loaded
            except Exception:
                continue

    return default or {}


def get_cache_path(name: str) -> Path:
    """Get cache file path (convenience function).

    Args:
        name: Cache filename

    Returns:
        Path to cache file in ~/.cache/reveal/
    """
    cache_dir = Path(os.getenv('XDG_CACHE_HOME', Path.home() / '.cache')) / 'reveal'
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / name


def get_data_path(name: str) -> Path:
    """Get data file path (convenience function).

    Args:
        name: Data filename

    Returns:
        Path to data file in ~/.local/share/reveal/
    """
    data_dir = Path(os.getenv('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / 'reveal'
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / name


def _show_breadcrumb_hint_once() -> None:
    """Show a one-time hint about disabling breadcrumbs.

    Prints to stderr so it doesn't interfere with piped output.
    Only shows once per user (tracked via state file).
    """
    hint_file = get_data_path('seen_breadcrumb_hint')
    if hint_file.exists():
        return

    # Mark as seen before printing to avoid race conditions
    try:
        hint_file.touch()
    except OSError:
        return  # Can't track state, skip the hint

    print(
        "Tip: Permanently disable navigation hints with: reveal --disable-breadcrumbs",
        file=sys.stderr
    )


def disable_breadcrumbs_permanently() -> bool:
    """Disable breadcrumbs by updating user config file.

    Creates or updates ~/.config/reveal/config.yaml with:
        display:
          breadcrumbs: false

    Returns:
        True if successful, False otherwise
    """
    config_path = RevealConfig._get_user_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing config or start fresh
    config = {}
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
        except Exception:
            pass

    # Update display.breadcrumbs
    config.setdefault('display', {})['breadcrumbs'] = False

    # Write back
    try:
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        print(f"Breadcrumbs disabled in {config_path}")
        return True
    except Exception as e:
        print(f"Failed to update config: {e}", file=sys.stderr)
        return False
