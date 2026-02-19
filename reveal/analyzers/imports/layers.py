"""
Layer architecture configuration and validation.

This module provides support for defining and enforcing architectural layers
through .reveal.yaml configuration. Layers define which parts of the codebase
can import from which other parts, enabling architectural constraints to be
validated at CI time.

Example .reveal.yaml:
    architecture:
      layers:
        - name: "presentation"
          paths: ["src/routes/**", "src/api/**"]
          allow_imports: ["src/services", "src/models"]
          deny_imports: ["src/database"]

        - name: "services"
          paths: ["src/services/**"]
          allow_imports: ["src/repositories", "src/models"]
          deny_imports: ["src/routes", "src/api"]
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)


@dataclass
class LayerRule:
    """Defines architectural layer constraints."""

    name: str
    paths: List[str]  # Glob patterns
    allow_imports: List[str]  # Module prefixes allowed
    deny_imports: List[str]  # Module prefixes denied

    def matches_file(self, file_path: Path, project_root: Optional[Path] = None) -> bool:
        """Check if a file belongs to this layer.

        Args:
            file_path: Path to check
            project_root: Project root for normalizing paths

        Returns:
            True if file matches any of this layer's path patterns
        """
        # Normalize file path relative to project root if provided
        if project_root:
            try:
                file_relative = file_path.relative_to(project_root)
                file_str = str(file_relative)
            except ValueError:
                # file_path is not under project_root
                return False
        else:
            file_str = str(file_path)

        for pattern in self.paths:
            # Handle glob patterns with **
            if "**" in pattern:
                # Convert glob to simple prefix matching for directories
                prefix = pattern.replace("**", "").rstrip("/")
                if prefix and file_str.startswith(prefix):
                    return True
            else:
                # Simple prefix or exact match
                if file_str.startswith(pattern.rstrip("/")):
                    return True

        return False

    def is_violation(self, from_file: Path, to_file: Path, project_root: Optional[Path] = None) -> Tuple[bool, Optional[str]]:
        """Check if import violates layer boundary.

        Args:
            from_file: Source file doing the import
            to_file: Target file or directory being imported
            project_root: Project root for normalizing paths

        Returns:
            Tuple of (is_violation, reason). If no violation, reason is None.
        """
        if not self.matches_file(from_file, project_root):
            return False, None

        to_module = self._normalize_to_module(to_file, project_root)
        if to_module is None:
            return False, None

        # Check deny list first (explicit denials take precedence)
        for deny_pattern in self.deny_imports:
            pattern = deny_pattern if deny_pattern.endswith("/") else deny_pattern + "/"
            if to_module.startswith(pattern):
                return True, f"{self.name} layer cannot import from {deny_pattern}"

        # If allow_imports is specified, target must match one of them
        if self.allow_imports and not self._is_target_allowed(to_module):
            allowed_str = ", ".join(self.allow_imports)
            return True, f"{self.name} layer can only import from: {allowed_str}"

        return False, None

    def _normalize_to_module(self, to_file: Path, project_root: Optional[Path]) -> Optional[str]:
        """Return *to_file* as a slash-terminated module path, or None if outside project root."""
        if project_root:
            try:
                return str(to_file.relative_to(project_root)) + "/"
            except ValueError:
                return None
        return str(to_file) + "/"

    def _is_target_allowed(self, to_module: str) -> bool:
        """Return True if *to_module* matches at least one pattern in allow_imports."""
        for allow_pattern in self.allow_imports:
            pattern = allow_pattern if allow_pattern.endswith("/") else allow_pattern + "/"
            if to_module.startswith(pattern):
                return True
        return False


@dataclass
class LayerConfig:
    """Container for all layer rules."""

    layers: List[LayerRule]

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "LayerConfig":
        """Load layer configuration from dictionary.

        Args:
            config_dict: Dictionary from .reveal.yaml

        Returns:
            LayerConfig instance

        Example:
            config = LayerConfig.from_dict({
                'architecture': {
                    'layers': [
                        {
                            'name': 'services',
                            'paths': ['src/services/**'],
                            'allow_imports': ['src/models'],
                            'deny_imports': ['src/api']
                        }
                    ]
                }
            })
        """
        layers = []

        # Navigate to architecture.layers
        arch = config_dict.get("architecture", {})
        layer_defs = arch.get("layers", [])

        for layer_def in layer_defs:
            try:
                layer = LayerRule(
                    name=layer_def.get("name", "unnamed"),
                    paths=layer_def.get("paths", []),
                    allow_imports=layer_def.get("allow_imports", []),
                    deny_imports=layer_def.get("deny_imports", []),
                )
                layers.append(layer)
            except Exception as e:
                logger.warning(f"Failed to load layer definition: {e}")
                continue

        return cls(layers=layers)

    def check_import(
        self, from_file: Path, to_file: Path, project_root: Optional[Path] = None
    ) -> Optional[Tuple[str, Optional[str]]]:
        """Check if import violates any layer rules.

        Args:
            from_file: Source file
            to_file: Target file
            project_root: Project root for normalizing paths

        Returns:
            Tuple of (layer_name, violation_reason) if violation found, None otherwise
        """
        for layer in self.layers:
            is_violation, reason = layer.is_violation(from_file, to_file, project_root)
            if is_violation:
                return (layer.name, reason)

        return None


def load_layer_config(start_path: Path) -> Optional[LayerConfig]:
    """Load layer configuration using unified config system.

    Uses RevealConfig to load architecture.layers from .reveal.yaml,
    supporting multi-level precedence and directory walk-up.

    Args:
        start_path: Starting path (file or directory)

    Returns:
        LayerConfig if found, None otherwise
    """
    try:
        # Use unified config system (supports precedence, walk-up, etc.)
        from reveal.config import RevealConfig

        config = RevealConfig.get(start_path)
        layers_list = config.get_layers()

        if not layers_list:
            return None

        # Convert to LayerConfig format
        config_dict = {'architecture': {'layers': layers_list}}
        return LayerConfig.from_dict(config_dict)

    except Exception as e:
        logger.debug(f"Failed to load layer config from unified config: {e}")

        # Fallback to old direct loading for backwards compatibility
        # This ensures existing .reveal.yaml files still work during migration
        import yaml

        current = start_path if start_path.is_dir() else start_path.parent

        while current != current.parent:
            config_file = current / ".reveal.yaml"
            if config_file.exists():
                try:
                    with open(config_file, encoding='utf-8') as f:
                        config_dict = yaml.safe_load(f)
                    if config_dict:
                        return LayerConfig.from_dict(config_dict)
                except Exception as load_error:
                    logger.warning(f"Failed to load .reveal.yaml from {config_file}: {load_error}")
                    return None

            current = current.parent

        return None
