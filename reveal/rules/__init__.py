"""Pattern detector system for reveal - auto-discovery and registry.

Industry-aligned pattern detection following Ruff, ESLint, and Semgrep patterns.
"""

import importlib
import logging
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

        # Built-in rules
        rules_dir = Path(__file__).parent
        cls._discover_dir(rules_dir, "reveal.rules")

        # User rules: ~/.local/share/reveal/rules/ (XDG_DATA_HOME)
        user_rules_dir = config.user_data_dir / 'rules'
        if user_rules_dir.exists():
            cls._discover_dir(user_rules_dir, "user.rules")

        # Legacy user rules: ~/.reveal/rules/ (backward compatibility)
        legacy_paths = config.get_legacy_paths()
        legacy_user_dir = legacy_paths['rules_user']
        if legacy_user_dir.exists() and not user_rules_dir.exists():
            logger.warning(
                f"Using legacy rules directory: {legacy_user_dir}\n"
                f"Please migrate to XDG-compliant location: {user_rules_dir}\n"
                f"Run: mkdir -p {user_rules_dir} && mv {legacy_user_dir}/* {user_rules_dir}/"
            )
            cls._discover_dir(legacy_user_dir, "user.rules")

        # Project rules: ./.reveal/rules/ (stays the same - project-local)
        project_rules_dir = config.project_config_dir / 'rules'
        if project_rules_dir.exists():
            cls._discover_dir(project_rules_dir, "project.rules")

        cls._discovered = True
        logger.info(f"Discovered {len(cls._rules)} rules from {len(set(r.category for r in cls._rules if r.category))} categories")

    @classmethod
    def _discover_dir(cls, rules_dir: Path, module_prefix: str):
        """
        Discover rules in a directory.

        Args:
            rules_dir: Directory to search
            module_prefix: Module prefix for imports (e.g., "reveal.rules")
        """
        # Find all category subdirectories
        for subdir in rules_dir.iterdir():
            if not subdir.is_dir() or subdir.name.startswith('_'):
                continue

            # Import all .py files in subdir (each is a rule)
            for module_file in subdir.glob('*.py'):
                if module_file.stem.startswith('_'):
                    continue

                try:
                    # Construct module path
                    module_name = f"{module_prefix}.{subdir.name}.{module_file.stem}"

                    # Import module
                    mod = importlib.import_module(module_name)

                    # Find BaseRule subclass matching filename
                    rule_class_name = module_file.stem  # e.g., "B001"
                    rule_class = getattr(mod, rule_class_name, None)

                    if rule_class and isinstance(rule_class, type) and issubclass(rule_class, BaseRule) and rule_class != BaseRule:
                        cls._rules.append(rule_class)
                        cls._rules_by_code[rule_class.code] = rule_class
                        logger.debug(f"Discovered rule: {rule_class.code} - {rule_class.message}")
                    else:
                        logger.warning(f"File {module_file} does not contain a valid rule class named {rule_class_name}")

                except Exception as e:
                    logger.error(f"Failed to import rule from {module_file}: {e}", exc_info=True)

    @classmethod
    def get_rules(cls, select: Optional[List[str]] = None, ignore: Optional[List[str]] = None) -> List[Type[BaseRule]]:
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

        # Filter by select (if provided)
        if select:
            rules = [r for r in rules if cls._matches_patterns(r, select)]

        # Filter by ignore (if provided)
        if ignore:
            rules = [r for r in rules if not cls._matches_patterns(r, ignore)]

        # Filter out disabled rules (but allow explicitly selected disabled rules)
        if not select:
            rules = [r for r in rules if r.enabled]

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

    @classmethod
    def list_rules(cls, select: Optional[List[str]] = None, category: Optional[RulePrefix] = None) -> List[Dict[str, Any]]:
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

        result = []
        for rule_class in sorted(rules, key=lambda r: r.code):
            result.append({
                'code': rule_class.code,
                'message': rule_class.message,
                'category': rule_class.category.value if rule_class.category else 'unknown',
                'severity': rule_class.severity.value,
                'file_patterns': rule_class.file_patterns,
                'uri_patterns': rule_class.uri_patterns,
                'version': rule_class.version,
                'enabled': rule_class.enabled,
            })

        return result

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
            select: Rules to include
            ignore: Rules to exclude

        Returns:
            List of all detections from all rules
        """
        if not cls._discovered:
            cls.discover()

        rules = cls.get_rules(select=select, ignore=ignore)
        detections = []

        for rule_class in rules:
            # Check if rule applies to this file
            if not rule_class().matches_target(file_path):
                continue

            try:
                # Instantiate rule and run check
                rule = rule_class()
                rule.set_current_file(file_path)
                rule_detections = rule.check(file_path, structure, content)
                detections.extend(rule_detections)
                logger.debug(f"Rule {rule_class.code} found {len(rule_detections)} issues in {file_path}")
            except Exception as e:
                logger.error(f"Rule {rule_class.code} failed on {file_path}: {e}", exc_info=True)

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
