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

        - name: "domain"
          paths: ["src/domain/**"]
          allow_imports: []        # nothing outside the layer itself

A layer may always import its own files. `allow_imports`, when present (even empty), limits the
layer to those files plus the listed prefixes; omit it for no allow list. `deny_imports` wins.
"""

import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from ..base import BaseRule, Detection, RulePrefix, Severity, RuleScope
from ...analyzers.imports.python import extract_python_imports
from ...analyzers.imports.resolver import resolve_python_import
from ...utils.request_cache import register_request_cache
from ...utils.path_utils import failure_of

logger = logging.getLogger(__name__)

# Module-level cache: directory_path -> (layer_config, project_root, load_error)
# All files in the same directory resolve to the same .reveal.yaml, so we
# only need to walk + parse once per unique directory (typically 1 parse total
# when all files share the same project root config). load_error is the reason a
# .reveal.yaml was found but could not be used (None when it loaded or none exists);
# it is cached with the config so every file under it reports it, not only the first.
_config_cache: Dict[Path, Tuple[Optional[Any], Optional[Path], Optional[str]]] = {}
# One YAML parse per directory is cheap: reset at every host request, so an edited
# .reveal.yaml is not served from the first request's parse (BACK-1572).
register_request_cache(__name__, _config_cache.clear)


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
    scope = RuleScope.CROSS_FILE
    category = RulePrefix.I
    severity = Severity.HIGH
    message = "Architectural layer violation"
    # extract_python_imports() only understands Python's tree-sitter import node
    # kinds (BACK-432) — on any other language it silently finds zero imports
    # (safe, but the inherited default file_patterns=['*'] falsely advertised
    # universal support and made the rule run its full config-load + parse path
    # on every non-Python file for no reason).
    file_patterns = ['.py']

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
        detections: List[Detection] = []
        path = Path(file_path)

        # Load layer configuration and find project root
        try:
            layer_config, project_root, load_error = self._load_config_and_find_root(path)
        except (ImportError, OSError) as e:
            # PyYAML missing, or the directory walk hit an unreadable path
            logger.warning(f"I003: failed to load layer config for {file_path}: {e}")
            return self.unavailable(
                f"layer config lookup failed: {failure_of(e).cause}", file_path)

        if load_error:
            return self.unavailable(load_error, file_path)

        # No layer config found - skip this file
        if not layer_config or not layer_config.layers:
            return detections

        # Extract imports from the file
        try:
            imports = extract_python_imports(path)
        except Exception as e:  # boundary-ok: broad-except -- the extractor walks tree-sitter nodes of arbitrary user source (native binding, no enumerable error set); one file must not end the run, and it is recorded as this rule's unavailable outcome with the file as subject
            logger.warning(f"I003: failed to extract imports from {file_path}: {e}")
            return self.unavailable(f"import extraction failed: {type(e).__name__}: {e}", file_path)

        # Check each import against layer rules
        for import_stmt in imports:
            detection = self._check_import_violation(
                import_stmt, file_path, path, layer_config, project_root
            )
            if detection:
                detections.append(detection)

        return detections

    def _load_config_and_find_root(
            self, start_path: Path) -> tuple[Optional[Any], Optional[Path], Optional[str]]:
        """Load layer config and return it along with project root.

        Uses a module-level cache keyed by directory so all files in the same
        project share one YAML parse instead of re-parsing on every call.

        Args:
            start_path: Starting path for search

        Returns:
            Tuple of (layer_config, project_root, load_error) where project_root is where
            .reveal.yaml was found and load_error says why a found .reveal.yaml was unusable
        """
        cache_key = start_path if start_path.is_dir() else start_path.parent
        if cache_key in _config_cache:
            return _config_cache[cache_key]

        import yaml

        current = cache_key
        result: tuple[Optional[Any], Optional[Path], Optional[str]] = (None, None, None)

        def _try_load(config_file: Path):
            """(config, root) on success, (None, None) for an empty file, or an error string."""
            try:
                from ...analyzers.imports import LayerConfig
                with open(config_file, encoding='utf-8') as f:
                    config_dict = yaml.safe_load(f)
                return (LayerConfig.from_dict(config_dict), config_file.parent) if config_dict else None
            except Exception as e:  # boundary-ok: broad-except -- a user-authored .reveal.yaml of any shape reaches LayerConfig.from_dict, which does unguarded .get()/iteration on it (AttributeError/TypeError on foreign data) next to yaml and file errors; the reason is returned and reported as the rule's unavailable outcome for every file under it
                return f"layer config {config_file} could not be used: {type(e).__name__}: {e}"

        while current != current.parent:
            config_file = current / ".reveal.yaml"
            if config_file.exists():
                loaded = _try_load(config_file)
                if isinstance(loaded, str):
                    logger.warning(f"I003: {loaded}")      # once per directory, like the cache
                    result = (None, None, loaded)
                elif loaded is not None:
                    result = (loaded[0], loaded[1], None)
                break
            current = current.parent

        _config_cache[cache_key] = result
        return result

    def _check_import_violation(self, import_stmt, file_path, path, layer_config, project_root):
        """Check a single import statement for layer violations. Returns Detection or None."""
        try:
            search_paths = [project_root] if project_root else []
            resolved = resolve_python_import(import_stmt, path.parent, search_paths=search_paths)
            if not resolved:
                return None
            violation = layer_config.check_import(path, resolved, project_root)
            if not violation:
                return None
            layer_name, reason = violation
            return self.create_detection(
                file_path=file_path,
                line=import_stmt.line_number,
                message=reason,
                suggestion=self._create_suggestion(layer_name, layer_config),
                context=f"Import: {import_stmt.module_name}",
            )
        except Exception as e:  # boundary-ok: broad-except -- the resolver runs over arbitrary import strings and layer matching runs user-authored globs (no enumerable error set); one import must not end the file, and it is recorded as this rule's unavailable outcome with file:line as subject
            logger.warning(f"I003: error checking import {import_stmt.module_name} in {file_path}: {e}")
            self.unavailable(
                f"import {import_stmt.module_name} could not be checked: {type(e).__name__}: {e}",
                f"{file_path}:{import_stmt.line_number}")
            return None

    def _create_suggestion(self, layer_name: str, config) -> str:
        """Create helpful suggestion for fixing layer violation.

        Args:
            layer_name: Name of the layer that was violated
            config: LayerConfig instance

        Returns:
            Suggestion string
        """
        # Find the layer definition
        layer = next((lyr for lyr in config.layers if lyr.name == layer_name), None)

        if not layer:
            return "Review architectural layer constraints in .reveal.yaml"

        suggestions = []

        if layer.allow_imports is not None:
            if layer.allow_imports:
                allowed = ", ".join(layer.allow_imports)
                suggestions.append(f"The {layer_name} layer can only import from itself and: {allowed}")
            else:
                suggestions.append(f"The {layer_name} layer cannot import from outside itself")

        if layer.deny_imports:
            denied = ", ".join(layer.deny_imports)
            suggestions.append(f"The {layer_name} layer cannot import from: {denied}")

        if not suggestions:
            return "Review architectural layer constraints in .reveal.yaml"

        suggestions.append("Consider refactoring to move shared code or adjust layer definitions")

        return " | ".join(suggestions)
