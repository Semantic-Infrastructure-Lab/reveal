"""Tests for B007: adapter exception handler logs but never records the
failure in the Output Contract envelope (BACK-1017)."""

import unittest
import tempfile
import os
import pytest

from reveal.rules.bugs.B007 import B007
from reveal.rules.base import Severity

# BACK-1149: component-layer test -- single rule/module in isolation, no subprocess/CLI/MCP
pytestmark = pytest.mark.component


class TestB007EnvelopeBlindAdapterHandler(unittest.TestCase):
    """Test B007: envelope-blind adapter exception handler detector."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.rule = B007()

    def tearDown(self):
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def create_temp_file(self, content: str, name: str = "test.py") -> str:
        path = os.path.join(self.temp_dir, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    # ==================== Detection: module-level helper functions ====================

    def test_module_level_helper_logs_without_envelope_flagged(self):
        """BACK-1016's actual shape: a helper function taking the adapter as
        a parameter, logging on failure but never calling record_composed_error()."""
        content = '''
import logging
logger = logging.getLogger(__name__)

def _run_scope(adapter: "OverviewAdapter", path):
    try:
        return scope_dict_for_path(path)
    except Exception as exc:
        logger.warning("scope census failed for %s: %s", path, exc)
        return {}
'''
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].rule_code, 'B007')
        self.assertEqual(detections[0].severity, Severity.MEDIUM)

    def test_module_level_helper_with_envelope_call_not_flagged(self):
        """Same shape, but calling record_composed_error() — the fixed version."""
        content = '''
import logging
logger = logging.getLogger(__name__)

def _run_scope(adapter: "OverviewAdapter", path):
    try:
        return scope_dict_for_path(path)
    except Exception as exc:
        logger.warning("scope census failed for %s: %s", path, exc)
        adapter.record_composed_error("scope_dict_for_path", path, exc)
        return {}
'''
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    # ==================== Detection: methods on Adapter-derived classes ====================

    def test_method_on_adapter_subclass_logs_without_envelope_flagged(self):
        content = '''
import logging
logger = logging.getLogger(__name__)

class OverviewAdapter(ResourceAdapter):
    def method_bad(self):
        try:
            do_thing()
        except Exception as exc:
            logger.error("failed: %s", exc)
'''
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)

    def test_method_on_adapter_subclass_with_envelope_call_not_flagged(self):
        content = '''
import logging
logger = logging.getLogger(__name__)

class OverviewAdapter(ResourceAdapter):
    def method_ok(self):
        try:
            do_thing()
        except Exception as exc:
            logger.warning("failed")
            self.record_composed_error("x", self.path, exc)
'''
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_create_error_result_counts_as_envelope_call(self):
        content = '''
class ClaudeAdapter(ResourceAdapter):
    def method_ok(self):
        try:
            do_thing()
        except Exception as exc:
            logger.warning("failed")
            return self.create_error_result(str(exc))
'''
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    # ==================== BACK-2254: meta.warnings and returned failures ====================

    def test_note_warning_counts_as_envelope_call(self):
        """A failure that leaves the rest of the answer standing goes to meta.warnings."""
        content = '''
class HelpAdapter(ResourceAdapter):
    def add_see_also(self, data):
        try:
            extra = load()
        except Exception as exc:
            logger.warning("see_also not shown: %s", exc)
            note_warning(data, {'type': 'x', 'message': str(exc)})
            return
'''
        path = self.create_temp_file(content)
        self.assertEqual(len(self.rule.check(path, None, content)), 0)

    def test_failure_returned_to_caller_not_flagged(self):
        """The handler adds its exception to a list the function returns; the caller records it."""
        content = '''
class HelpAdapter(ResourceAdapter):
    def schemes(self):
        found, failures = [], []
        for s in names():
            try:
                found.append(check(s))
            except Exception as exc:
                logger.warning("%s left out: %s", s, exc)
                failures.append((s, exc))
        return sorted(found), warning_for(failures)
'''
        path = self.create_temp_file(content)
        self.assertEqual(len(self.rule.check(path, None, content)), 0)

    def test_failure_collected_but_not_returned_flagged(self):
        """Negative control: a list that never leaves the function discloses nothing."""
        content = '''
class HelpAdapter(ResourceAdapter):
    def schemes(self):
        found, failures = [], []
        for s in names():
            try:
                found.append(check(s))
            except Exception as exc:
                logger.warning("%s left out: %s", s, exc)
                failures.append((s, exc))
        return sorted(found)
'''
        path = self.create_temp_file(content)
        self.assertEqual(len(self.rule.check(path, None, content)), 1)

    def test_returned_list_without_the_exception_flagged(self):
        """Appending something other than the exception to a returned list is not disclosure."""
        content = '''
class HelpAdapter(ResourceAdapter):
    def schemes(self):
        found = []
        for s in names():
            try:
                check(s)
            except Exception as exc:
                logger.warning("%s left out: %s", s, exc)
                found.append(s)
        return found
'''
        path = self.create_temp_file(content)
        self.assertEqual(len(self.rule.check(path, None, content)), 1)

    # ==================== Scope: not adapter-context code ====================

    def test_non_adapter_function_not_flagged(self):
        """Ordinary code with no adapter parameter/base class is out of scope
        for B007 (that's B006's territory, not B007's)."""
        content = '''
import logging
logger = logging.getLogger(__name__)

def helper(path):
    try:
        return risky(path)
    except Exception as exc:
        logger.warning("failed: %s", exc)
        return None
'''
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_method_on_non_adapter_class_not_flagged(self):
        content = '''
import logging
logger = logging.getLogger(__name__)

class Widget:
    def render(self):
        try:
            do_thing()
        except Exception as exc:
            logger.warning("failed: %s", exc)
'''
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    # ==================== Fully-silent handlers are B006's territory, not B007's ====================

    def test_fully_silent_handler_in_adapter_context_not_flagged(self):
        """No log call at all -> B006's remit, not a "logs but doesn't
        envelope" gap -> B007 stays quiet to avoid double-flagging."""
        content = '''
class OverviewAdapter(ResourceAdapter):
    def method_silent(self):
        try:
            do_thing()
        except Exception:
            pass
'''
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    # ==================== Nested-function scoping ====================

    def test_nested_non_adapter_function_inside_adapter_method_not_flagged(self):
        """A handler inside a nested function that itself has no adapter
        param/base is attributed to the nested function's own scope, not
        inherited from the enclosing adapter method."""
        content = '''
class OverviewAdapter(ResourceAdapter):
    def outer(self):
        def inner(x):
            try:
                return risky(x)
            except Exception as exc:
                logger.warning("nested failure: %s", exc)
                return None
        return inner(1)
'''
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)


if __name__ == '__main__':
    unittest.main()
