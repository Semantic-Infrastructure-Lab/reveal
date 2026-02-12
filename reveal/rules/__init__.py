"""Pattern detector system for reveal - auto-discovery and registry.

Industry-aligned pattern detection following Ruff, ESLint, and Semgrep patterns.
"""

import importlib
import logging
import re
from pathlib import Path
from typing import List, Type, Optional, Dict, Any

from .base import BaseRule, Detection, RulePrefix, Severity
from reveal.config import get_config

logger = logging.getLogger(__name__)


class RuleRegistry:
    """
    Auto-discover rules by filename.

    Convention: <CODE>.py → Rule <CODE>
    Example: B001.py contains class B001(BaseRule)

    NO MANUAL REGISTRATION NEEDED!
    """

    _rules: List[Type[BaseRule]] = []
    _rules_by_code: Dict[str, Type[BaseRule]] = {}
    _discovered: bool = False

    # ===== Helper Methods: Rule Discovery Logic =====
    # Clean separation of concerns for maintainability

    @staticmethod
    def _is_rule_module_file(file_path: Path) -> bool:
        """
        Determine if a file should be loaded as a rule module.

        Rule modules follow the naming convention: <CODE>.py (e.g., B001.py, V007.py)
        Non-rule files are skipped: __init__.py, utils.py, helpers.py, base.py

        Args:
            file_path: Path to the Python file

        Returns:
            True if file should be loaded as a rule, False for utility modules
        """
        filename = file_path.stem

        # Skip private modules
        if filename.startswith('_'):
            return False

        # Rule files match pattern: uppercase letter(s) + digits (e.g., B001, V007)
        return bool(re.match(r'^[A-Z]+\d+$', filename))

    @staticmethod
    def _should_warn_about_missing_rule_class(filename: str) -> bool:
        """
        Determine if we should warn about a missing rule class.

        Only warn for files that look like rule codes (B001, V007) but don't
        contain a valid rule class. Don't warn for utility files.

        Args:
            filename: File stem (e.g., "B001", "utils")

        Returns:
            True if we should warn, False to silently skip
        """
        # Only warn if filename matches rule code pattern
        return bool(re.match(r'^[A-Z]+\d+$', filename))

    @staticmethod
    def _extract_rule_class_from_module(
        module,
        expected_class_name: str
    ) -> Optional[Type[BaseRule]]:
        """
        Extract a rule class from an imported module.

        Looks for a class matching the expected name that's a valid BaseRule subclass.

        Args:
            module: Imported Python module
            expected_class_name: Expected class name (e.g., "B001")

        Returns:
            Rule class if found and valid, None otherwise
        """
        rule_class = getattr(module, expected_class_name, None)

        # Validate it's a proper BaseRule subclass
        if not rule_class:
            return None
        if not isinstance(rule_class, type):
            return None
        if not issubclass(rule_class, BaseRule):
            return None
        if rule_class == BaseRule:  # Don't register the base class itself
            return None

        return rule_class

    @classmethod
    def _register_rule_in_registry(cls, rule_class: Type[BaseRule]) -> None:
        """
        Register a discovered rule in the registry.

        Adds the rule to both the list and the code-indexed dictionary.

        Args:
            rule_class: The rule class to register
        """
        cls._rules.append(rule_class)
        cls._rules_by_code[rule_class.code] = rule_class
        logger.debug(f"Discovered rule: {rule_class.code} - {rule_class.message}")

    @classmethod
    def _discover_built_in_rules(cls):
        """Discover built-in rules from reveal/rules/*/."""
        rules_dir = Path(__file__).parent
        cls._discover_dir(rules_dir, "reveal.rules")

    @classmethod
    def _discover_user_rules(cls, config):
        """Discover user rules from XDG or legacy location."""
        user_rules_dir = config.user_data_dir / 'rules'

        if user_rules_dir.exists():
            cls._discover_dir(user_rules_dir, "user.rules")
            return

        # Legacy location: ~/.reveal/rules/ (backward compatibility)
        legacy_paths = config.get_legacy_paths()
        legacy_user_dir = legacy_paths['rules_user']

        if not legacy_user_dir.exists():
            return

        migrate_cmd = (
            f"mkdir -p {user_rules_dir} && "
            f"mv {legacy_user_dir}/* {user_rules_dir}/"
        )
        logger.warning(
            f"Using legacy rules directory: {legacy_user_dir}\n"
            f"Please migrate to XDG-compliant location: {user_rules_dir}\n"
            f"Run: {migrate_cmd}"
        )
        cls._discover_dir(legacy_user_dir, "user.rules")

    @classmethod
    def _discover_project_rules(cls, config):
        """Discover project-local rules from ./.reveal/rules/."""
        project_rules_dir = config.project_config_dir / 'rules'
        if project_rules_dir.exists():
            cls._discover_dir(project_rules_dir, "project.rules")

    @classmethod
    def _log_discovery_summary(cls):
        """Log summary of discovered rules."""
        num_rules = len(cls._rules)
        num_categories = len(set(r.category for r in cls._rules if r.category))
        logger.info(f"Discovered {num_rules} rules from {num_categories} categories")

    @classmethod
    def discover(cls, force: bool = False):
        """
        Auto-discover all rules in reveal/rules/*/.

        Args:
            force: Force rediscovery even if already discovered
        """
        if cls._discovered and not force:
            return

        cls._rules = []
        cls._rules_by_code = {}
        config = get_config()

        cls._discover_built_in_rules()
        cls._discover_user_rules(config)
        cls._discover_project_rules(config)

        cls._discovered = True
        cls._log_discovery_summary()

    @classmethod
    def _discover_dir(cls, rules_dir: Path, module_prefix: str):
        """
        Discover rules in a directory.

        Scans category subdirectories for rule modules, imports them,
        and registers valid rule classes in the registry.

        Args:
            rules_dir: Directory to search
            module_prefix: Module prefix for imports (e.g., "reveal.rules")
        """
        for subdir in rules_dir.iterdir():
            # Skip non-directories and private directories
            if not subdir.is_dir() or subdir.name.startswith('_'):
                continue

            cls._discover_rules_in_category_dir(subdir, module_prefix)

    @classmethod
    def _discover_rules_in_category_dir(
        cls,
        category_dir: Path,
        module_prefix: str
    ) -> None:
        """
        Discover all rules in a category directory.

        Args:
            category_dir: Category directory (e.g., rules/bugs/)
            module_prefix: Module prefix for imports (e.g., "reveal.rules")
        """
        for module_file in category_dir.glob('*.py'):
            # Skip if not a rule module file (filters out utils.py, etc.)
            if not cls._is_rule_module_file(module_file):
                continue

            cls._try_load_and_register_rule(module_file, category_dir, module_prefix)

    @classmethod
    def _try_load_and_register_rule(
        cls,
        module_file: Path,
        category_dir: Path,
        module_prefix: str
    ) -> None:
        """
        Attempt to load and register a single rule module.

        Args:
            module_file: Path to the rule module file
            category_dir: Category directory containing the file
            module_prefix: Module prefix for imports
        """
        try:
            module_name = f"{module_prefix}.{category_dir.name}.{module_file.stem}"
            module = importlib.import_module(module_name)

            expected_class_name = module_file.stem
            rule_class = cls._extract_rule_class_from_module(
                module,
                expected_class_name
            )

            if rule_class:
                cls._register_rule_in_registry(rule_class)
            elif cls._should_warn_about_missing_rule_class(expected_class_name):
                logger.warning(
                    f"File {module_file} does not contain a valid "
                    f"rule class named {expected_class_name}"
                )

        except Exception as e:
            logger.error(
                f"Failed to import rule from {module_file}: {e}",
                exc_info=True
            )

    @classmethod
    def _apply_select_filter(
        cls,
        rules: List[Type[BaseRule]],
        select: List[str]
    ) -> List[Type[BaseRule]]:
        """Apply select patterns filter to rules."""
        return [r for r in rules if cls._matches_patterns(r, select)]

    @classmethod
    def _apply_ignore_filter(
        cls,
        rules: List[Type[BaseRule]],
        ignore: List[str]
    ) -> List[Type[BaseRule]]:
        """Apply ignore patterns filter to rules."""
        return [r for r in rules if not cls._matches_patterns(r, ignore)]

    @classmethod
    def _apply_enabled_filter(
        cls,
        rules: List[Type[BaseRule]]
    ) -> List[Type[BaseRule]]:
        """Filter out disabled rules."""
        return [r for r in rules if r.enabled]

    @classmethod
    def get_rules(
        cls,
        select: Optional[List[str]] = None,
        ignore: Optional[List[str]] = None
    ) -> List[Type[BaseRule]]:
        """
        Get filtered rules.

        Args:
            select: Rule patterns to include (e.g., ["B", "S701"])
            ignore: Rule patterns to exclude (e.g., ["C901"])

        Returns:
            List of rule classes
        """
        if not cls._discovered:
            cls.discover()

        rules = cls._rules.copy()

        if select:
            rules = cls._apply_select_filter(rules, select)

        if ignore:
            rules = cls._apply_ignore_filter(rules, ignore)

        if not select:
            rules = cls._apply_enabled_filter(rules)

        return rules

    @classmethod
    def get_rule(cls, code: str) -> Optional[Type[BaseRule]]:
        """
        Get a specific rule by code.

        Args:
            code: Rule code (e.g., "B001")

        Returns:
            Rule class or None if not found
        """
        if not cls._discovered:
            cls.discover()

        return cls._rules_by_code.get(code)

    @classmethod
    def _matches_patterns(cls, rule_class: Type[BaseRule], patterns: List[str]) -> bool:
        """
        Check if rule matches any of the given patterns.

        Supports progressive specificity:
        - "B" matches B001, B002, etc.
        - "B0" matches B001, B002, etc.
        - "B001" matches B001 exactly

        Args:
            rule_class: Rule class to check
            patterns: List of patterns (e.g., ["B", "S701"])

        Returns:
            True if rule matches any pattern
        """
        code = rule_class.code
        for pattern in patterns:
            # Exact match
            if code == pattern:
                return True
            # Prefix match (e.g., "B" matches "B001")
            if code.startswith(pattern):
                return True
            # Category match (e.g., if pattern is a RulePrefix enum value)
            try:
                prefix = RulePrefix(pattern)
                if rule_class.category == prefix:
                    return True
            except (ValueError, AttributeError):
                pass

        return False

    @staticmethod
    def _rule_to_dict(rule_class: Type[BaseRule]) -> Dict[str, Any]:
        """
        Convert a rule class to a metadata dictionary.

        Args:
            rule_class: Rule class to convert

        Returns:
            Dictionary with rule metadata
        """
        category_value = (
            rule_class.category.value
            if rule_class.category
            else 'unknown'
        )
        return {
            'code': rule_class.code,
            'message': rule_class.message,
            'category': category_value,
            'severity': rule_class.severity.value,
            'file_patterns': rule_class.file_patterns,
            'uri_patterns': rule_class.uri_patterns,
            'version': rule_class.version,
            'enabled': rule_class.enabled,
        }

    @classmethod
    def list_rules(
        cls,
        select: Optional[List[str]] = None,
        category: Optional[RulePrefix] = None
    ) -> List[Dict[str, Any]]:
        """
        List rules with metadata.

        Args:
            select: Filter by patterns (e.g., ["B", "S"])
            category: Filter by category

        Returns:
            List of rule metadata dicts
        """
        if not cls._discovered:
            cls.discover()

        rules = cls.get_rules(select=select)

        if category:
            rules = [r for r in rules if r.category == category]

        sorted_rules = sorted(rules, key=lambda r: r.code)
        return [cls._rule_to_dict(rule_class) for rule_class in sorted_rules]

    @classmethod
    def check_file(cls,
                   file_path: str,
                   structure: Optional[Dict[str, Any]],
                   content: str,
                   select: Optional[List[str]] = None,
                   ignore: Optional[List[str]] = None) -> List[Detection]:
        """
        Run all applicable rules against a file.

        Args:
            file_path: Path to file
            structure: Parsed structure from analyzer
            content: File content
            select: Rules to include (CLI override)
            ignore: Rules to exclude (CLI override)

        Returns:
            List of all detections from all rules
        """
        if not cls._discovered:
            cls.discover()

        # Load config for this file
        from pathlib import Path
        file_path_obj = Path(file_path)
        config = get_config(start_path=file_path_obj.parent)
        file_config = config.get_file_config(file_path_obj)

        # Get base rules filtered by CLI select/ignore
        rules = cls.get_rules(select=select, ignore=ignore)
        detections: List[Detection] = []

        for rule_class in rules:
            # Check if rule applies to this file
            if not rule_class().matches_target(file_path):
                continue

            # Check if rule is enabled by config (unless CLI select overrides)
            if not select and not file_config.is_rule_enabled(rule_class.code):
                logger.debug(
                    f"Rule {rule_class.code} disabled by config for {file_path}"
                )
                continue

            try:
                # Instantiate rule and run check
                rule = rule_class()
                rule.set_current_file(file_path)

                # Pass config values to rule if it needs them
                # Access the raw config dict to get rule-specific config
                rules_config = file_config._config.get('rules', {})
                rule_config = rules_config.get(rule_class.code, {})
                if rule_config and isinstance(rule_config, dict):
                    # Update rule's config values
                    for key, value in rule_config.items():
                        if hasattr(rule, key):
                            setattr(rule, key, value)

                rule_detections = rule.check(file_path, structure, content)
                detections.extend(rule_detections)
                num_issues = len(rule_detections)
                logger.debug(
                    f"Rule {rule_class.code} found {num_issues} issues in {file_path}"
                )
            except Exception as e:
                logger.error(
                    f"Rule {rule_class.code} failed on {file_path}: {e}",
                    exc_info=True
                )

        return detections


# Auto-discover on import
RuleRegistry.discover()


# Export main classes
__all__ = [
    'BaseRule',
    'Detection',
    'RulePrefix',
    'Severity',
    'RuleRegistry',
]
