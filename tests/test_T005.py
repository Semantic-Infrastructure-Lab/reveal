"""Tests for T005 rule: Annotation coverage reporter."""

import pytest
from reveal.rules.types.T005 import T005


class TestT005Attributes:
    def test_rule_attributes(self):
        rule = T005()
        assert rule.code == "T005"
        assert rule.severity.name == "LOW"
        assert '.py' in rule.file_patterns

    def test_invalid_python_returns_empty(self):
        rule = T005()
        detections = rule.check("file.py", None, "def func(: this is not python")
        assert len(detections) == 0


class TestT005PartialAnnotation:
    """Core detection: partially annotated functions are flagged."""

    def test_missing_return_annotation(self):
        content = "def func(x: int, y: str): pass"
        rule = T005()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 1
        assert "return unannotated" in detections[0].message

    def test_missing_param_annotation(self):
        content = "def func(x: int, y) -> bool: pass"
        rule = T005()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 1
        assert "1/2 params annotated" in detections[0].message

    def test_missing_param_and_return(self):
        content = "def func(x: int, y) -> None: pass\ndef other(a, b: str): pass"
        rule = T005()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 2

    def test_suggestion_names_unannotated_params(self):
        content = "def func(x: int, y, z) -> bool: pass"
        rule = T005()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 1
        assert "y" in detections[0].suggestion
        assert "z" in detections[0].suggestion

    def test_correct_line_number(self):
        content = "\n\ndef func(x: int, y) -> bool: pass"
        rule = T005()
        detections = rule.check("file.py", None, content)
        assert detections[0].line == 3

    def test_async_function_detected(self):
        content = "async def func(x: int, y): pass"
        rule = T005()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 1


class TestT005NoFalsePositives:
    """Fully annotated and fully unannotated functions are not flagged."""

    def test_fully_annotated_no_detection(self):
        content = "def func(x: int, y: str) -> bool: pass"
        rule = T005()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 0

    def test_fully_unannotated_no_detection(self):
        content = "def func(x, y): pass"
        rule = T005()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 0

    def test_no_params_fully_annotated(self):
        content = "def func() -> None: pass"
        rule = T005()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 0

    def test_self_excluded_from_param_count(self):
        content = "class C:\n    def method(self, x: int) -> bool: pass"
        rule = T005()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 0

    def test_cls_excluded_from_param_count(self):
        content = "class C:\n    @classmethod\n    def make(cls, x: int) -> 'C': pass"
        rule = T005()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 0

    def test_no_params_no_return_no_detection(self):
        content = "def func(): pass"
        rule = T005()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 0


class TestT005MessageFormat:
    """Detection message includes function name and summary."""

    def test_message_includes_function_name(self):
        content = "def process_trade(x: dict, y) -> None: pass"
        rule = T005()
        detections = rule.check("file.py", None, content)
        assert "process_trade" in detections[0].message

    def test_message_param_ratio(self):
        content = "def f(a: int, b: str, c) -> bool: pass"
        rule = T005()
        detections = rule.check("file.py", None, content)
        assert "2/3 params annotated" in detections[0].message

    def test_context_is_function_signature(self):
        content = "def myfunc(x: int, y) -> bool: pass"
        rule = T005()
        detections = rule.check("file.py", None, content)
        assert detections[0].context is not None
        assert "myfunc" in detections[0].context
