"""Tests for T004 rule: Implicit Optional parameter detector."""

import pytest
from reveal.rules.types.T004 import T004


class TestT004Attributes:
    def test_rule_attributes(self):
        rule = T004()
        assert rule.code == "T004"
        assert rule.severity.name == "MEDIUM"
        assert '.py' in rule.file_patterns

    def test_invalid_python_returns_empty(self):
        rule = T004()
        detections = rule.check("file.py", None, "def func(: this is not python")
        assert len(detections) == 0


class TestT004BasicDetection:
    """Core detection: type hint + None default → flag it."""

    def test_simple_implicit_optional_detected(self):
        content = "def func(path: str = None): pass"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 1
        assert detections[0].line == 1

    def test_multiple_parameters_all_flagged(self):
        content = "def func(a: str = None, b: int = None): pass"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 2

    def test_detection_reports_correct_param_name(self):
        content = "def func(mypath: str = None): pass"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 1
        assert "mypath" in detections[0].suggestion

    def test_suggestion_includes_optional_syntax(self):
        content = "def func(x: int = None): pass"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert "Optional" in detections[0].suggestion

    def test_suggestion_includes_union_syntax(self):
        content = "def func(x: int = None): pass"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert "| None" in detections[0].suggestion

    def test_context_is_function_signature(self):
        content = "def myfunc(x: int = None): pass"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert detections[0].context is not None
        assert "myfunc" in detections[0].context

    def test_async_function_detected(self):
        content = "async def func(x: str = None): pass"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 1

    def test_nested_function_detected(self):
        content = (
            "def outer():\n"
            "    def inner(x: str = None):\n"
            "        pass\n"
        )
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 1

    def test_class_method_detected(self):
        content = (
            "class Foo:\n"
            "    def method(self, x: str = None): pass\n"
        )
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 1


class TestT004NoFalsePositives:
    """Cases that should NOT be flagged."""

    def test_optional_annotation_ok(self):
        content = "from typing import Optional\ndef func(path: Optional[str] = None): pass"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 0

    def test_union_with_none_ok(self):
        content = "from typing import Union\ndef func(path: Union[str, None] = None): pass"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 0

    def test_pipe_none_syntax_ok(self):
        content = "def func(path: str | None = None): pass"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 0

    def test_none_pipe_type_syntax_ok(self):
        content = "def func(path: None | str = None): pass"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 0

    def test_no_annotation_ok(self):
        content = "def func(path=None): pass"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 0

    def test_non_none_default_ok(self):
        content = "def func(path: str = 'default'): pass"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 0

    def test_no_default_ok(self):
        content = "def func(path: str): pass"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 0

    def test_self_parameter_ok(self):
        content = "class Foo:\n    def method(self, x: str = 'hi'): pass\n"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 0

    def test_zero_default_ok(self):
        content = "def func(x: int = 0): pass"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 0

    def test_empty_default_string_ok(self):
        content = "def func(x: str = ''): pass"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 0


class TestT004KeywordOnlyArgs:
    """Keyword-only parameters (after *) are also checked."""

    def test_kwonly_with_type_hint_and_none_flagged(self):
        content = "def func(*, key: int = None): pass"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 1

    def test_kwonly_with_optional_ok(self):
        content = "from typing import Optional\ndef func(*, key: Optional[int] = None): pass"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 0

    def test_kwonly_without_default_ok(self):
        content = "def func(*, key: int): pass"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 0

    def test_kwonly_none_default_no_annotation_ok(self):
        content = "def func(*, key=None): pass"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 0

    def test_mixed_regular_and_kwonly(self):
        content = "def func(a: str = None, *, b: int = None): pass"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 2

    def test_kwonly_detection_reports_param_name(self):
        content = "def func(*, mykey: str = None): pass"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 1
        assert "mykey" in detections[0].suggestion


class TestT004IsImplicitOptional:
    """Unit tests for _is_implicit_optional helper."""

    def _make_arg(self, annotation_src, default_src=None):
        import ast
        # Build a minimal function node to extract arg and default
        src = f"def f(x{': ' + annotation_src if annotation_src else ''}{'=' + default_src if default_src else ''}): pass"
        tree = ast.parse(src)
        func = tree.body[0]
        arg = func.args.args[0]
        default = func.args.defaults[0] if func.args.defaults else None
        return arg, default

    def test_returns_false_when_no_default(self):
        rule = T004()
        arg, default = self._make_arg("str")
        assert rule._is_implicit_optional(arg, None) is False

    def test_returns_false_when_no_annotation(self):
        import ast
        rule = T004()
        arg, default = self._make_arg(None, "None")
        arg.annotation = None
        assert rule._is_implicit_optional(arg, default) is False

    def test_returns_false_when_default_not_none(self):
        rule = T004()
        arg, default = self._make_arg("str", "'hello'")
        assert rule._is_implicit_optional(arg, default) is False

    def test_returns_true_for_violation(self):
        rule = T004()
        arg, default = self._make_arg("str", "None")
        assert rule._is_implicit_optional(arg, default) is True

    def test_returns_false_for_optional(self):
        rule = T004()
        arg, default = self._make_arg("Optional[str]", "None")
        assert rule._is_implicit_optional(arg, default) is False

    def test_returns_false_for_union_none(self):
        rule = T004()
        arg, default = self._make_arg("Union[str, None]", "None")
        assert rule._is_implicit_optional(arg, default) is False

    def test_returns_false_for_pipe_none(self):
        rule = T004()
        arg, default = self._make_arg("str | None", "None")
        assert rule._is_implicit_optional(arg, default) is False


class TestT004AddDetection:
    """Ensure _add_detection generates complete detection objects."""

    def test_detection_has_rule_code(self):
        content = "def func(x: str = None): pass"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert detections[0].rule_code == "T004"

    def test_detection_has_file_path(self):
        content = "def func(x: str = None): pass"
        rule = T004()
        detections = rule.check("myfile.py", None, content)
        assert detections[0].file_path == "myfile.py"

    def test_detection_line_number_correct(self):
        content = "\n\ndef func(x: str = None): pass\n"
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert detections[0].line == 3

    def test_multiline_function_signature_context(self):
        content = (
            "def func(\n"
            "    x: str = None,\n"
            "    y: int = 0,\n"
            "): pass\n"
        )
        rule = T004()
        detections = rule.check("file.py", None, content)
        assert len(detections) == 1
        # Context should be first line of signature
        assert detections[0].context is not None
