"""Tests for reveal.rules.base_mixins — the shared AST parse cache.

_cached_ast_parse() backs ASTParsingMixin, inherited by 12 rules. A parse
failure here used to log only at debug (invisible by default), so a crash
in reveal's own parser rendered as "0 issues" across every dependent rule,
indistinguishable from genuinely clean code. See the BACK-984/985 case
study — same disease, different call site.
"""

import logging

import pytest

from reveal.rules.base_mixins import _cached_ast_parse, ASTParsingMixin

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP/network
pytestmark = pytest.mark.component


class TestCachedAstParse:
    def test_valid_source_returns_tree(self):
        tree = _cached_ast_parse("x = 1\n", "valid.py")
        assert tree is not None

    def test_syntax_error_returns_none(self):
        tree = _cached_ast_parse("def f(:\n", "broken.py")
        assert tree is None

    def test_syntax_error_logs_warning_not_debug(self, caplog):
        with caplog.at_level(logging.WARNING, logger="reveal.rules.base_mixins"):
            _cached_ast_parse("def f(:\n", "warn_check.py")
        assert any("warn_check.py" in r.message for r in caplog.records)
        assert all(r.levelno >= logging.WARNING for r in caplog.records)


class TestASTParsingMixin:
    def test_parse_python_returns_none_on_syntax_error(self):
        class Rule(ASTParsingMixin):
            pass

        assert Rule()._parse_python("def f(:\n", "mixin_broken.py") is None

    def test_parse_python_or_skip_returns_empty_detections(self):
        class Rule(ASTParsingMixin):
            pass

        tree, detections = Rule()._parse_python_or_skip("def f(:\n", "mixin_skip.py")
        assert tree is None
        assert detections == []
