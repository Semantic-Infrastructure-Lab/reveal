"""Pattern detector system for reveal - auto-discovery and registry.

Industry-aligned pattern detection following Ruff, ESLint, and Semgrep patterns.
"""

import importlib
import importlib.util
import logging
import re
import sys
import time
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

    # Namespace for rule modules loaded from outside the reveal package. Their
    # synthetic dotted names ("user.rules.…", "project.rules.…") are not real
    # importable packages, so they are loaded by file path and parked here in
    # sys.modules under a reveal-owned prefix that cannot shadow a real package.
    _EXTERNAL_MODULE_NAMESPACE = 'reveal._external_rules'

    @staticmethod
    def _load_module_from_path(module_file: Path, module_name: str):
        """
        Load a rule module from an arbitrary filesystem path.

        User- and project-local rule directories live outside the reveal
        package, so importlib.import_module() cannot find them — there is no
        `user`/`project` package on sys.path. Load them by location instead.

        Args:
            module_file: Path to the .py file to load
            module_name: Name to register the module under in sys.modules

        Returns:
            The loaded module

        Raises:
            ImportError: If a loader cannot be built for the file
        """
        spec = importlib.util.spec_from_file_location(module_name, module_file)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot build a module loader for {module_file}")

        module = importlib.util.module_from_spec(spec)
        # Register before exec so the module can reference itself (dataclasses,
        # pickling, and typing.get_type_hints all look it up in sys.modules).
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(module_name, None)
            raise
        return module

    @classmethod
    def _normalize_rule_class(cls, rule_class: Type[BaseRule]) -> None:
        """
        Coerce loosely-typed class attributes to their enum types.

        Rule classes are hand-authored — by reveal's own scaffold and by users
        in ~/.local/share/reveal/rules/ — so `severity = "high"` is a natural
        way to write what the type system wants to be `Severity.HIGH`.
        Normalize once here, where a rule enters the registry, instead of
        defending against it at each of the ~10 sites that read
        `.severity.value` / `.category.value`.

        An unrecognized severity degrades to MEDIUM with a warning rather than
        raising: one mistyped user rule must not take down `reveal --rules`
        for every other rule (BACK-856).

        Args:
            rule_class: The rule class to normalize in place
        """
        severity = rule_class.severity
        if isinstance(severity, str):
            try:
                rule_class.severity = Severity(severity.lower())
            except ValueError:
                logger.warning(
                    f"Rule {rule_class.code}: unknown severity {severity!r} "
                    f"(expected one of {[s.value for s in Severity]}); "
                    f"treating it as {Severity.MEDIUM.value}"
                )
                rule_class.severity = Severity.MEDIUM

        category = rule_class.category
        if isinstance(category, str):
            try:
                rule_class.category = RulePrefix(category.upper())
            except ValueError:
                # A prefix outside the known set is legitimate: the rule
                # scaffold emits a plain string for these by design (see
                # cli/scaffold/rule.py:_get_category_value), and consumers
                # tolerate a str category. Leave it as authored.
                pass

    @classmethod
    def _register_rule_in_registry(cls, rule_class: Type[BaseRule]) -> None:
        """
        Register a discovered rule in the registry.

        Adds the rule to both the list and the code-indexed dictionary.

        Args:
            rule_class: The rule class to register
        """
        cls._normalize_rule_class(rule_class)
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
            cls._discover_dir(user_rules_dir, "user.rules", external=True)
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
        cls._discover_dir(legacy_user_dir, "user.rules", external=True)

    @classmethod
    def _discover_project_rules(cls, config):
        """Discover project-local rules from <project root>/.reveal/rules/."""
        project_rules_dir = config.project_config_dir / 'rules'
        if project_rules_dir.exists():
            cls._discover_dir(project_rules_dir, "project.rules", external=True)

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
    def _discover_dir(cls, rules_dir: Path, module_prefix: str, external: bool = False):
        """
        Discover rules in a directory.

        Scans category subdirectories for rule modules, imports them,
        and registers valid rule classes in the registry.

        Args:
            rules_dir: Directory to search
            module_prefix: Module prefix for imports (e.g., "reveal.rules")
            external: True when rules_dir is outside the reveal package, so
                modules must be loaded by file path rather than imported
        """
        for subdir in rules_dir.iterdir():
            # Skip non-directories and private directories
            if not subdir.is_dir() or subdir.name.startswith('_'):
                continue

            cls._discover_rules_in_category_dir(subdir, module_prefix, external)

    @classmethod
    def _discover_rules_in_category_dir(
        cls,
        category_dir: Path,
        module_prefix: str,
        external: bool = False
    ) -> None:
        """
        Discover all rules in a category directory.

        Args:
            category_dir: Category directory (e.g., rules/bugs/)
            module_prefix: Module prefix for imports (e.g., "reveal.rules")
            external: True when the directory is outside the reveal package
        """
        for module_file in category_dir.glob('*.py'):
            # Skip if not a rule module file (filters out utils.py, etc.)
            if not cls._is_rule_module_file(module_file):
                continue

            cls._try_load_and_register_rule(
                module_file, category_dir, module_prefix, external
            )

    @classmethod
    def _try_load_and_register_rule(
        cls,
        module_file: Path,
        category_dir: Path,
        module_prefix: str,
        external: bool = False
    ) -> None:
        """
        Attempt to load and register a single rule module.

        Args:
            module_file: Path to the rule module file
            category_dir: Category directory containing the file
            module_prefix: Module prefix for imports
            external: True when the module lives outside the reveal package
        """
        try:
            module_name = f"{module_prefix}.{category_dir.name}.{module_file.stem}"
            if external:
                module = cls._load_module_from_path(
                    module_file, f"{cls._EXTERNAL_MODULE_NAMESPACE}.{module_name}"
                )
            else:
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
    def get_configured_rule(cls, code: str, file_path: str) -> Optional[BaseRule]:
        """
        Instantiate a rule with this file's .reveal.yaml config applied.

        Lets callers outside the check pipeline (e.g. stats/hotspots scoring)
        read a rule's *effective* threshold attributes (BACK-775) instead of
        hardcoding a second copy of the default, so a project only has to
        configure a threshold once.

        Args:
            code: Rule code (e.g., "C902")
            file_path: Path to file, used to resolve config precedence

        Returns:
            Configured rule instance, or None if the rule code is unknown
        """
        rule_class = cls.get_rule(code)
        if rule_class is None:
            return None

        rule = rule_class()
        config = get_config(start_path=Path(file_path).parent)
        file_config = config.get_file_config(Path(file_path))
        rules_config = file_config._config.get('rules', {})
        rule_config = rules_config.get(code, {})
        if rule_config and isinstance(rule_config, dict):
            cls._apply_rule_config(rule, rule_config)
        return rule

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
        category = rule_class.category
        if not category:
            category_value = 'unknown'
        elif isinstance(category, str):
            # Rules scaffolded with a prefix outside the known RulePrefix set
            # (see cli/scaffold/rule.py:_get_category_value) store a plain
            # string here instead of a RulePrefix member.
            category_value = category
        else:
            category_value = category.value
        from .coverage import derive_verified_languages
        return {
            'code': rule_class.code,
            'message': rule_class.message,
            'category': category_value,
            'severity': rule_class.severity.value,
            'file_patterns': rule_class.file_patterns,
            'uri_patterns': rule_class.uri_patterns,
            'version': rule_class.version,
            'enabled': rule_class.enabled,
            'internal': rule_class.internal,
            'verified_languages': derive_verified_languages(rule_class),
        }

    @classmethod
    def list_rules(
        cls,
        select: Optional[List[str]] = None,
        category: Optional[RulePrefix] = None,
        include_disabled: bool = True,
        include_internal: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        List rules with metadata.

        Args:
            select: Filter by patterns (e.g., ["B", "S"])
            category: Filter by category
            include_disabled: When True (default), include opt-in/disabled rules so users
                can discover them. The enabled field in the returned dict indicates status.
            include_internal: When False (default), exclude rules that only ever apply to
                reveal's own source (rule_class.internal is True) from the listing — they
                can never fire against an external user's codebase.

        Returns:
            List of rule metadata dicts
        """
        if not cls._discovered:
            cls.discover()

        if select:
            rules = cls.get_rules(select=select)
        elif include_disabled:
            # Return all rules (enabled + disabled) so the listing is complete
            rules = sorted(cls._rules.copy(), key=lambda r: r.code)
        else:
            rules = cls.get_rules(select=None)

        if category:
            rules = [r for r in rules if r.category == category]

        if not include_internal:
            rules = [r for r in rules if not r.internal]

        sorted_rules = sorted(rules, key=lambda r: r.code)
        return [cls._rule_to_dict(rule_class) for rule_class in sorted_rules]

    _ALLOWED_RULE_CONFIG_KEYS = frozenset({
        'enabled', 'severity', 'threshold', 'message', 'description',
        'max_length', 'MAX_DEPTH', 'MAX_ARGS', 'skip_categories',
    })

    @classmethod
    def _apply_rule_config(cls, rule, rule_config: dict) -> None:
        """Apply config key-value pairs to a rule instance."""
        for key, value in rule_config.items():
            if key not in cls._ALLOWED_RULE_CONFIG_KEYS:
                logger.warning(f"Unknown rule config key {key!r} for rule {rule.code} — ignored")
                continue
            if hasattr(rule, key):
                setattr(rule, key, value)

    @classmethod
    def check_file(cls,
                   file_path: str,
                   structure: Optional[Dict[str, Any]],
                   content: str,
                   select: Optional[List[str]] = None,
                   ignore: Optional[List[str]] = None,
                   profile: Optional[Dict[str, float]] = None) -> List[Detection]:
        """
        Run all applicable rules against a file.

        Args:
            file_path: Path to file
            structure: Parsed structure from analyzer
            content: File content
            select: Rules to include (CLI override)
            ignore: Rules to exclude (CLI override)
            profile: When given, accumulates each rule's wall-clock seconds into
                profile[rule.code] (BACK-540). A single real pass, not a serial
                A/B — a rule's cost lands on whichever call actually paid it
                (e.g. I002 gets charged for building its import graph on the
                file that first triggers it), so there is no cross-run cache
                state to contaminate the comparison.

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
            # Check if rule applies to this file (classmethod — no instantiation)
            if not rule_class.matches_target(file_path):
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

                # Pass config values to rule if it needs them
                rules_config = file_config._config.get('rules', {})
                rule_config = rules_config.get(rule_class.code, {})
                if rule_config and isinstance(rule_config, dict):
                    cls._apply_rule_config(rule, rule_config)

                if profile is not None:
                    start = time.perf_counter()
                    rule_detections = rule.check(file_path, structure, content)
                    profile[rule_class.code] = profile.get(rule_class.code, 0.0) + (time.perf_counter() - start)
                else:
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


# Export main classes
__all__ = [
    'BaseRule',
    'Detection',
    'RulePrefix',
    'Severity',
    'RuleRegistry',
]
