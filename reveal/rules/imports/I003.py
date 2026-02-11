"""
I003: Architectural layer violations.

Detects when code in one architectural layer imports from a forbidden layer,
violating the defined architecture constraints in .reveal.yaml.

Example .reveal.yaml configuration:
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
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ...analyzers.imports.python import extract_python_imports
from ...analyzers.imports.resolver import resolve_python_import

logger = logging.getLogger(__name__)


class I003(BaseRule):
    """Detect architectural layer violations.

    This rule enforces architectural layer constraints defined in .reveal.yaml.
    It checks that files in a given layer only import from allowed layers.

    Example:
        # In .reveal.yaml
        architecture:
          layers:
            - name: "services"
              paths: ["src/services/**"]
              allow_imports: ["src/repositories"]
              deny_imports: ["src/api"]

        # This would be flagged:
        # src/services/user_service.py
        from src.api import routes  # ❌ services can't import from api
    """

    code = "I003"
    category = RulePrefix.I
    severity = Severity.HIGH
    message = "Architectural layer violation"

    def check(
        self,
        file_path: str,
        structure: Optional[Dict[str, Any]],
        content: str,
    ) -> List[Detection]:
        """Check for layer violations in import statements.

        Args:
            file_path: Path to file being checked
            structure: Unused (required by BaseRule interface)
            content: File content

        Returns:
            List of detections for layer violations
        """
        detections: List[Dict[str, Any]] = []
        path = Path(file_path)

        # Load layer configuration and find project root
        try:
            layer_config, project_root = self._load_config_and_find_root(path)
        except Exception as e:
            logger.debug(f"Failed to load layer config for {file_path}: {e}")
            return detections

        # No layer config found - skip this file
        if not layer_config or not layer_config.layers:
            return detections

        # Extract imports from the file
        try:
            imports = extract_python_imports(path)
        except Exception as e:
            logger.debug(f"Failed to extract imports from {file_path}: {e}")
            return detections

        # Check each import against layer rules
        for import_stmt in imports:
            try:
                # Resolve import to actual file path (include project root in search paths)
                search_paths = [project_root] if project_root else []
                resolved = resolve_python_import(import_stmt, path.parent, search_paths=search_paths)

                if not resolved:
                    # Can't resolve - might be stdlib or external package
                    continue

                # Check if this import violates any layer rules
                violation = layer_config.check_import(path, resolved, project_root)

                if violation:
                    layer_name, reason = violation
                    suggestion = self._create_suggestion(layer_name, layer_config)

                    detection = self.create_detection(
                        file_path=file_path,
                        line=import_stmt.line_number,
                        message=reason,
                        suggestion=suggestion,
                        context=f"Import: {import_stmt.module_name}",
                    )
                    detections.append(detection)

            except Exception as e:
                logger.debug(
                    f"Error checking import {import_stmt.module_name} in {file_path}: {e}"
                )
                continue

        return detections

    def _load_config_and_find_root(self, start_path: Path) -> tuple[Optional[Any], Optional[Path]]:
        """Load layer config and return it along with project root.

        Args:
            start_path: Starting path for search

        Returns:
            Tuple of (layer_config, project_root) where project_root is where .reveal.yaml was found
        """
        import yaml

        current = start_path if start_path.is_dir() else start_path.parent

        while current != current.parent:
            config_file = current / ".reveal.yaml"
            if config_file.exists():
                try:
                    from ...analyzers.imports import LayerConfig
                    with open(config_file) as f:
                        config_dict = yaml.safe_load(f)
                    if config_dict:
                        return LayerConfig.from_dict(config_dict), current
                except Exception as e:
                    logger.warning(f"Failed to load .reveal.yaml from {config_file}: {e}")
                    return None, None

            current = current.parent

        return None, None

    def _create_suggestion(self, layer_name: str, config) -> str:
        """Create helpful suggestion for fixing layer violation.

        Args:
            layer_name: Name of the layer that was violated
            config: LayerConfig instance

        Returns:
            Suggestion string
        """
        # Find the layer definition
        layer = next((l for l in config.layers if l.name == layer_name), None)

        if not layer:
            return "Review architectural layer constraints in .reveal.yaml"

        suggestions = []

        if layer.allow_imports:
            allowed = ", ".join(layer.allow_imports)
            suggestions.append(f"The {layer_name} layer can only import from: {allowed}")

        if layer.deny_imports:
            denied = ", ".join(layer.deny_imports)
            suggestions.append(f"The {layer_name} layer cannot import from: {denied}")

        if not suggestions:
            return "Review architectural layer constraints in .reveal.yaml"

        suggestions.append("Consider refactoring to move shared code or adjust layer definitions")

        return " | ".join(suggestions)
