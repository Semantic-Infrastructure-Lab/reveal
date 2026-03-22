"""Comprehensive tests for reveal rules base infrastructure.

Tests the foundational BaseRule class, Detection dataclass, Severity and RulePrefix enums,
and core rule system functionality.
"""

import logging
import pytest
from reveal.rules.base import (
    BaseRule,
    Detection,
    Severity,
    RulePrefix
)
from reveal.rules import RuleRegistry


class TestSeverity:
    """Test Severity enum."""

    def test_severity_values(self):
        """Severity enum has all expected values."""
        assert Severity.LOW.value == "low"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.HIGH.value == "high"
        assert Severity.CRITICAL.value == "critical"

    def test_severity_comparison(self):
        """Severity levels can be compared."""
        assert Severity.LOW == Severity.LOW
        assert Severity.HIGH != Severity.MEDIUM


class TestRulePrefix:
    """Test RulePrefix enum."""

    def test_rule_prefix_values(self):
        """RulePrefix enum has all expected values."""
        assert RulePrefix.E.value == "E"  # Errors
        assert RulePrefix.S.value == "S"  # Security
        assert RulePrefix.C.value == "C"  # Complexity
        assert RulePrefix.B.value == "B"  # Bugs
        assert RulePrefix.PERF.value == "PERF"  # Performance
        assert RulePrefix.M.value == "M"  # Maintainability
        assert RulePrefix.I.value == "I"  # Infrastructure
        assert RulePrefix.U.value == "U"  # URLs
        assert RulePrefix.R.value == "R"  # Refactoring
        assert RulePrefix.D.value == "D"  # Duplicates
        assert RulePrefix.L.value == "L"  # Links

    def test_rule_prefix_comparison(self):
        """RulePrefix values can be compared."""
        assert RulePrefix.E == RulePrefix.E
        assert RulePrefix.S != RulePrefix.C


class TestDetection:
    """Test Detection dataclass."""

    def test_detection_creation_minimal(self):
        """Can create detection with minimal required fields."""
        detection = Detection(
            file_path="test.py",
            line=10,
            rule_code="B001",
            message="Test issue"
        )
        assert detection.file_path == "test.py"
        assert detection.line == 10
        assert detection.rule_code == "B001"
        assert detection.message == "Test issue"
        assert detection.column == 1  # Default
        assert detection.severity == Severity.MEDIUM  # Default
        assert detection.suggestion is None
        assert detection.context is None

    def test_detection_creation_full(self):
        """Can create detection with all fields."""
        detection = Detection(
            file_path="example.py",
            line=42,
            rule_code="S701",
            message="Security issue",
            column=15,
            suggestion="Fix it like this",
            context="bad_code()",
            severity=Severity.HIGH,
            category=RulePrefix.S
        )
        assert detection.file_path == "example.py"
        assert detection.line == 42
        assert detection.rule_code == "S701"
        assert detection.message == "Security issue"
        assert detection.column == 15
        assert detection.suggestion == "Fix it like this"
        assert detection.context == "bad_code()"
        assert detection.severity == Severity.HIGH
        assert detection.category == RulePrefix.S

    def test_detection_to_dict(self):
        """Detection can be serialized to dict."""
        detection = Detection(
            file_path="test.py",
            line=10,
            rule_code="B001",
            message="Test",
            severity=Severity.HIGH,
            category=RulePrefix.B
        )
        result = detection.to_dict()

        assert result['file_path'] == "test.py"
        assert result['line'] == 10
        assert result['rule_code'] == "B001"
        assert result['message'] == "Test"
        assert result['severity'] == "high"  # Enum converted to string
        assert result['category'] == "B"  # Enum converted to string
        assert result['column'] == 1
        assert result['suggestion'] is None
        assert result['context'] is None

    def test_detection_to_dict_without_enums(self):
        """Detection to_dict handles None enums."""
        detection = Detection(
            file_path="test.py",
            line=10,
            rule_code="B001",
            message="Test"
        )
        result = detection.to_dict()

        assert result['severity'] == "medium"  # Default severity
        assert result['category'] is None

    def test_detection_str_minimal(self):
        """Detection __str__ formats basic detection."""
        detection = Detection(
            file_path="test.py",
            line=10,
            rule_code="B001",
            message="Test issue"
        )
        result = str(detection)

        assert "test.py:10:1" in result
        assert "⚠️" in result  # MEDIUM severity marker
        assert "B001" in result
        assert "Test issue" in result

    def test_detection_str_with_suggestion(self):
        """Detection __str__ includes suggestion when present."""
        detection = Detection(
            file_path="test.py",
            line=10,
            rule_code="B001",
            message="Test issue",
            suggestion="Fix it"
        )
        result = str(detection)

        assert "Fix it" in result
        assert "💡" in result

    def test_detection_str_with_context(self):
        """Detection __str__ includes context when present."""
        detection = Detection(
            file_path="test.py",
            line=10,
            rule_code="B001",
            message="Test issue",
            context="bad_code()"
        )
        result = str(detection)

        assert "bad_code()" in result
        assert "📝" in result

    def test_detection_str_severity_markers(self):
        """Detection __str__ uses correct severity markers."""
        for severity, marker in [
            (Severity.LOW, "ℹ️"),
            (Severity.MEDIUM, "⚠️"),
            (Severity.HIGH, "❌"),
            (Severity.CRITICAL, "🚨"),
        ]:
            detection = Detection(
                file_path="test.py",
                line=1,
                rule_code="X001",
                message="Test",
                severity=severity
            )
            result = str(detection)
            assert marker in result, f"Expected {marker} for {severity}"


class TestBaseRule:
    """Test BaseRule abstract base class."""

    def test_base_rule_is_abstract(self):
        """BaseRule cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            BaseRule()

    def test_concrete_rule_implementation(self):
        """Can create concrete rule by implementing check method."""

        class TestRule(BaseRule):
            code = "T001"
            message = "Test rule"
            category = RulePrefix.M
            severity = Severity.LOW
            file_patterns = ['*.py']

            def check(self, file_path, structure, content):
                return []

        rule = TestRule()
        assert rule.code == "T001"
        assert rule.message == "Test rule"
        assert rule.category == RulePrefix.M
        assert rule.severity == Severity.LOW
        assert rule.file_patterns == ['*.py']

    def test_concrete_rule_check_method(self):
        """Concrete rule's check method is called and returns detections."""

        class TestRule(BaseRule):
            code = "T001"
            message = "Test rule"
            category = RulePrefix.M
            severity = Severity.LOW
            file_patterns = ['*.py']

            def check(self, file_path, structure, content):
                # Return detection if content contains "bad"
                if "bad" in content:
                    return [Detection(
                        file_path=file_path,
                        line=1,
                        rule_code=self.code,
                        message=self.message
                    )]
                return []

        rule = TestRule()

        # No violations in good content
        detections = rule.check("test.py", {}, "good code")
        assert len(detections) == 0

        # Violation in bad content
        detections = rule.check("test.py", {}, "bad code")
        assert len(detections) == 1
        assert detections[0].rule_code == "T001"
        assert detections[0].message == "Test rule"

    def test_rule_with_structure_parameter(self):
        """Rule can use structure parameter for AST-based checks."""

        class TestRule(BaseRule):
            code = "T002"
            message = "Too many functions"
            category = RulePrefix.C
            severity = Severity.MEDIUM
            file_patterns = ['*.py']

            def check(self, file_path, structure, content):
                if structure and 'functions' in structure:
                    if len(structure['functions']) > 10:
                        return [Detection(
                            file_path=file_path,
                            line=1,
                            rule_code=self.code,
                            message=f"{len(structure['functions'])} functions found"
                        )]
                return []

        rule = TestRule()

        # No violations with few functions
        detections = rule.check("test.py", {'functions': [1, 2, 3]}, "")
        assert len(detections) == 0

        # Violation with many functions
        detections = rule.check("test.py", {'functions': list(range(15))}, "")
        assert len(detections) == 1
        assert "15 functions" in detections[0].message

    def test_rule_without_structure(self):
        """Rule handles None structure gracefully."""

        class TestRule(BaseRule):
            code = "T003"
            message = "Test"
            category = RulePrefix.M
            severity = Severity.LOW
            file_patterns = ['*']

            def check(self, file_path, structure, content):
                if structure is None:
                    return []
                return [Detection(file_path, 1, self.code, "Found structure")]

        rule = TestRule()
        detections = rule.check("test.txt", None, "content")
        assert len(detections) == 0

    def test_multiple_detections(self):
        """Rule can return multiple detections."""

        class TestRule(BaseRule):
            code = "T004"
            message = "Line too long"
            category = RulePrefix.E
            severity = Severity.LOW
            file_patterns = ['*.py']

            def check(self, file_path, structure, content):
                detections = []
                for i, line in enumerate(content.split('\n'), 1):
                    if len(line) > 80:
                        detections.append(Detection(
                            file_path=file_path,
                            line=i,
                            rule_code=self.code,
                            message=f"Line {i} is {len(line)} characters"
                        ))
                return detections

        rule = TestRule()
        content = "short\n" + ("x" * 100) + "\nshort\n" + ("y" * 90)
        detections = rule.check("test.py", None, content)

        assert len(detections) == 2
        assert detections[0].line == 2
        assert "100 characters" in detections[0].message
        assert detections[1].line == 4
        assert "90 characters" in detections[1].message


# ---------------------------------------------------------------------------
# CFG-01: _ALLOWED_RULE_CONFIG_KEYS completeness
# ---------------------------------------------------------------------------

class _StubRule(BaseRule):
    """Minimal rule for testing unknown-key warning behavior."""
    code = "Z999"
    message = "stub"
    category = RulePrefix.E
    severity = Severity.LOW
    file_patterns = ['*.py']

    def check(self, file_path, structure, content):
        return []


class TestAllowedRuleConfigKeys:
    """CFG-01: _ALLOWED_RULE_CONFIG_KEYS must include all keys rules actually use."""

    def test_real_rule_config_keys_in_allowlist(self):
        """Keys that real built-in rules actually use must be in the allowlist.

        This imports each rule, reads its configurable class attributes, and
        verifies they are in _ALLOWED_RULE_CONFIG_KEYS. Uses real rule instances
        rather than a hand-maintained list to prevent the test mirroring the
        implementation.
        """
        from reveal.rules.complexity.C905 import C905
        from reveal.rules.refactoring.R913 import R913

        # C905 has MAX_DEPTH as a class attribute — users configure it as MAX_DEPTH
        assert 'MAX_DEPTH' in RuleRegistry._ALLOWED_RULE_CONFIG_KEYS, (
            "C905 uses MAX_DEPTH but it's missing from _ALLOWED_RULE_CONFIG_KEYS"
        )
        assert hasattr(C905, 'MAX_DEPTH'), "Sanity check: C905.MAX_DEPTH must exist"

        # R913 has MAX_ARGS as a class attribute — users configure it as MAX_ARGS
        assert 'MAX_ARGS' in RuleRegistry._ALLOWED_RULE_CONFIG_KEYS, (
            "R913 uses MAX_ARGS but it's missing from _ALLOWED_RULE_CONFIG_KEYS"
        )
        assert hasattr(R913, 'MAX_ARGS'), "Sanity check: R913.MAX_ARGS must exist"

        # E501 reads max_length via get_threshold() — users configure it as max_length
        assert 'max_length' in RuleRegistry._ALLOWED_RULE_CONFIG_KEYS, (
            "E501 reads max_length via get_threshold but it's missing from _ALLOWED_RULE_CONFIG_KEYS"
        )

    def test_real_rule_config_keys_applied_without_warning(self, caplog):
        """Configuring built-in rules with their documented keys must not produce warnings.

        Uses real rule instances (not a stub) so the test fails if a rule renames
        its config attribute without updating _ALLOWED_RULE_CONFIG_KEYS.
        """
        from reveal.rules.complexity.C905 import C905
        from reveal.rules.refactoring.R913 import R913

        cases = [
            (C905(), {'MAX_DEPTH': 6}),
            (R913(), {'MAX_ARGS': 3}),
        ]
        for rule, config in cases:
            with caplog.at_level(logging.WARNING, logger='reveal.rules'):
                RuleRegistry._apply_rule_config(rule, config)

        unknown_warnings = [r for r in caplog.records if 'Unknown rule config key' in r.message]
        assert unknown_warnings == [], (
            f"Unexpected warnings when configuring real rules: {[w.message for w in unknown_warnings]}"
        )

    def test_real_rule_attributes_set_after_config(self):
        """_apply_rule_config must actually mutate the rule's configurable attributes."""
        from reveal.rules.complexity.C905 import C905
        from reveal.rules.refactoring.R913 import R913

        c905 = C905()
        original_depth = c905.MAX_DEPTH
        RuleRegistry._apply_rule_config(c905, {'MAX_DEPTH': original_depth + 10})
        assert c905.MAX_DEPTH == original_depth + 10, (
            f"MAX_DEPTH not updated — expected {original_depth + 10}, got {c905.MAX_DEPTH}"
        )

        r913 = R913()
        original_args = r913.MAX_ARGS
        RuleRegistry._apply_rule_config(r913, {'MAX_ARGS': original_args + 10})
        assert r913.MAX_ARGS == original_args + 10

    def test_truly_unknown_key_logs_warning(self, caplog):
        """Keys not in the allowlist must still produce a warning (guard against over-permissive allowlist)."""
        rule = _StubRule()
        with caplog.at_level(logging.WARNING, logger='reveal.rules'):
            RuleRegistry._apply_rule_config(rule, {'nonexistent_key': 99})

        assert any('nonexistent_key' in r.message for r in caplog.records)
