"""Tests for B006: Silent broad exception handler detector."""

import unittest
import tempfile
import os
from reveal.rules.bugs.B006 import B006
from reveal.rules.base import Severity


class TestB006SilentBroadException(unittest.TestCase):
    """Test B006: Silent broad exception handler detector."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.rule = B006()

    def tearDown(self):
        """Clean up temp files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def create_temp_file(self, content: str, name: str = "test.py") -> str:
        """Helper: Create temp file with given content."""
        path = os.path.join(self.temp_dir, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    # ==================== Tests for detection ====================

    def test_detect_silent_exception_pass(self):
        """Test detection of except Exception: pass with no comment."""
        content = """
def foo():
    try:
        risky_operation()
    except Exception:
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].rule_code, 'B006')
        self.assertEqual(detections[0].severity, Severity.MEDIUM)
        self.assertIn('specific exception types', detections[0].suggestion)

    def test_detect_silent_exception_as_e_pass(self):
        """Test detection of except Exception as e: pass with no comment."""
        content = """
def foo():
    try:
        risky_operation()
    except Exception as e:
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].rule_code, 'B006')

    def test_detect_base_exception_pass(self):
        """Test detection of except BaseException: pass."""
        content = """
def foo():
    try:
        risky_operation()
    except BaseException:
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].rule_code, 'B006')

    def test_detect_tuple_with_exception(self):
        """Test detection when Exception is in tuple of exceptions."""
        content = """
def foo():
    try:
        risky_operation()
    except (ValueError, Exception):
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].rule_code, 'B006')

    def test_multiple_silent_exceptions(self):
        """Test detection of multiple silent exception handlers in same file."""
        content = """
def foo():
    try:
        risky_operation()
    except Exception:
        pass

def bar():
    try:
        another_risky()
    except Exception:
        pass

class Baz:
    def method(self):
        try:
            risky()
        except Exception:
            pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 3)

    # ==================== Tests for allowed patterns (no detection) ====================

    def test_allow_specific_exception(self):
        """Test that specific exceptions with pass are allowed."""
        content = """
def foo():
    try:
        risky_operation()
    except ValueError:
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_allow_multiple_specific_exceptions(self):
        """Test that tuple of specific exceptions is allowed."""
        content = """
def foo():
    try:
        risky_operation()
    except (ValueError, KeyError, TypeError):
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_allow_bare_except(self):
        """Test that bare except is not flagged (handled by B001)."""
        content = """
def foo():
    try:
        risky_operation()
    except:
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # B006 should not flag bare except (that's B001's job)
        self.assertEqual(len(detections), 0)

    def test_debug_logging_alone_still_flagged(self):
        """logger.debug() alone is invisible by default — still silent (BACK-983).

        Previously B006 treated any logging call as sufficient to exempt a
        handler. debug-level logging doesn't show in a normal run, so this
        is just as silent as bare pass — this is the exact shape found
        hiding real bugs in BACK-979/981/982.
        """
        content = """
import logging
logger = logging.getLogger(__name__)

def foo():
    try:
        risky_operation()
    except Exception as e:
        logger.debug(f"Ignoring error: {e}")
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)

    def test_warning_logging_exempts(self):
        """logger.warning() (or higher) is a real visible signal — exempt."""
        content = """
import logging
logger = logging.getLogger(__name__)

def foo():
    try:
        risky_operation()
    except Exception as e:
        logger.warning(f"Ignoring error: {e}")
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_silent_return_none_now_flagged(self):
        """except Exception: return None with no log/comment is silent — flag it (BACK-983).

        No log at all is at least as silent as logger.debug(); this is the
        return-a-plausible-empty-value shape found across BACK-981/982.
        """
        content = """
def foo():
    try:
        risky_operation()
    except Exception:
        return None
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)

    def test_allow_exception_with_inline_comment(self):
        """Test that exception with inline comment on except line is allowed."""
        content = """
def foo():
    try:
        risky_operation()
    except Exception:  # Intentional: best-effort operation
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_allow_exception_with_comment_on_pass(self):
        """Test that exception with comment on pass line is allowed."""
        content = """
def foo():
    try:
        risky_operation()
    except Exception:
        pass  # Intentional: cleanup operation, errors don't matter
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_allow_exception_with_comment_between_except_and_pass(self):
        """Test that exception with comment between except and pass is allowed."""
        content = """
def foo():
    try:
        risky_operation()
    except Exception:
        # If operation fails, return empty
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_allow_exception_with_multiline_body(self):
        """Test that exception with multiple statements is allowed."""
        content = """
def foo():
    try:
        risky_operation()
    except Exception:
        pass
        pass  # Two pass statements (weird but not our concern)
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # Not just a single pass, so shouldn't flag
        self.assertEqual(len(detections), 0)

    # ==================== Tests for edge cases ====================

    def test_nested_try_except(self):
        """Test detection in nested try-except blocks."""
        content = """
def foo():
    try:
        try:
            inner_risky()
        except Exception:
            pass
    except ValueError:
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # Should only flag the inner Exception handler
        self.assertEqual(len(detections), 1)

    def test_syntax_error_handling(self):
        """Test that syntax errors are handled gracefully."""
        content = """
def foo()  # Missing colon
    try:
        risky()
    except Exception:
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # Should return empty list on syntax error, not crash
        self.assertEqual(len(detections), 0)

    def test_empty_file(self):
        """Test that empty file doesn't cause errors."""
        content = ""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_rule_metadata(self):
        """Test that rule has correct metadata."""
        self.assertEqual(self.rule.code, 'B006')
        self.assertEqual(self.rule.severity, Severity.MEDIUM)
        self.assertIn('.py', self.rule.file_patterns)
        self.assertIn('Broad exception', self.rule.message)

    def test_detection_message_helpful(self):
        """Test that detection message includes helpful suggestions."""
        content = """
def foo():
    try:
        risky()
    except Exception:
        pass
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        suggestion = detections[0].suggestion
        # Check for key suggestions
        self.assertIn('specific exception types', suggestion)
        self.assertIn('logging', suggestion)
        self.assertIn('comment', suggestion)
        self.assertIn('Re-raise', suggestion)

    # ==================== Real-world patterns ====================

    def test_real_world_file_reading_pattern(self):
        """Test common pattern in file reading with silent failure."""
        content = """
def read_config(path):
    try:
        with open(path) as f:
            return f.read()
    except Exception:
        pass
    return None
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # Should flag this - better to catch FileNotFoundError, IOError
        self.assertEqual(len(detections), 1)

    def test_real_world_import_pattern_with_comment(self):
        """Test common pattern in optional imports with comment."""
        content = """
try:
    import optional_dependency
except Exception:
    optional_dependency = None  # Not just pass, has assignment
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # Should not flag - has action beyond pass
        self.assertEqual(len(detections), 0)

    def test_real_world_cleanup_pattern_commented(self):
        """Test cleanup pattern with explanatory comment."""
        content = """
def cleanup():
    try:
        os.remove(temp_file)
    except Exception:
        pass  # Best effort cleanup, errors don't matter
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # Should not flag - has explanatory comment
        self.assertEqual(len(detections), 0)


    def test_try_then_try_fallback_first_handler_not_flagged(self):
        """try → except pass → try (multi-attempt pattern): first handler is exempt,
        but the terminal handler with no visible signal is now flagged (BACK-983).

        The first handler is a genuine "continue to next attempt" — exempt.
        The second (terminal) handler silently returns b'' on ANY exception,
        indistinguishable from "fetched successfully, got empty content" —
        exactly the shape found masking real failures in BACK-981/982.
        """
        content = """
def fetch_data(url):
    try:
        result = subprocess.run(['curl', url], capture_output=True, timeout=10)
        if result.returncode == 0:
            return result.stdout
    except Exception:
        pass
    # Fallback: try wget
    try:
        result = subprocess.run(['wget', '-qO-', url], capture_output=True, timeout=10)
        return result.stdout
    except Exception:
        return b''
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        lines = content.split('\n')
        second_except_line = max(i + 1 for i, l in enumerate(lines) if 'except Exception' in l)
        self.assertEqual(detections[0].line, second_except_line)

    def test_try_then_return_still_flagged(self):
        """try → except pass → return default should still be flagged (not a multi-attempt pattern)."""
        content = """
def read_config(path):
    try:
        with open(path) as f:
            return f.read()
    except Exception:
        pass
    return None
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        # Single try block with silent pass + return default — still a B006 finding
        self.assertEqual(len(detections), 1)

    # ==================== BACK-992: false-positive tuning ====================

    def test_known_helper_call_is_visible_signal(self):
        """record_composed_error() logs internally (BACK-984) — not silent."""
        content = """
def scan(adapter, path):
    try:
        return other.get_structure()
    except Exception as exc:
        adapter.record_composed_error('OtherAdapter', path, exc)
        return {}
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_unknown_helper_call_still_flagged(self):
        """A method call with an error-sounding name is NOT a free pass —
        only the explicitly-named known helper is recognized (BACK-992)."""
        content = """
def scan(adapter, path):
    try:
        return other.get_structure()
    except Exception as exc:
        adapter.handle_error(exc)
        return {}
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)

    def test_error_field_dict_assignment_is_visible_signal(self):
        """result['status'] = 'query_failed' records failure in-band."""
        content = """
def query(nameserver):
    result = {}
    try:
        result['answer'] = do_query(nameserver)
    except Exception as e:
        result['status'] = 'query_failed'
    return result
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_error_field_attribute_assignment_is_visible_signal(self):
        """self.parse_error = ... records failure in-band."""
        content = """
class Doc:
    def open(self, path):
        try:
            self.tree = parse(path)
        except Exception as e:
            self.parse_error = f"Error opening document: {e}"
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_unrelated_field_assignment_still_flagged(self):
        """Assigning to a field NOT in the known error-name set stays silent —
        the escape hatch is narrow, not 'any assignment counts' (BACK-992)."""
        content = """
def query(nameserver):
    result = {}
    try:
        result['answer'] = do_query(nameserver)
    except Exception:
        result['value'] = None
    return result
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)

    def test_error_field_dict_literal_return_is_visible_signal(self):
        """return {'error': str(e), ...} records failure in-band via a dict
        *literal*, not an assignment — the dominant real shape adapter
        handlers use (BACK-989 triage)."""
        content = """
def get_plan(path):
    try:
        return {'content': path.read_text()}
    except Exception as e:
        return {'type': 'plan', 'error': str(e)}
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_error_field_dict_literal_with_spread_is_visible_signal(self):
        """return {**base, 'error': str(e), ...} — spread plus literal keys."""
        content = """
def get_agent(base, name):
    try:
        return {**base, 'name': name}
    except Exception as e:
        return {**base, 'type': 'agent', 'error': str(e), 'name': name}
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_result_builder_create_error_is_visible_signal(self):
        """ResultBuilder.create_error(...) always sets the dict's 'error'
        field — a canonical factory helper, same idea as
        record_composed_error (BACK-992), found widespread in xlsx.py and
        the analyzers/adapters that use ResultBuilder (BACK-989 triage)."""
        content = """
def read(path):
    try:
        return ResultBuilder.create(result_type='x', source=path, data={})
    except Exception as e:
        return ResultBuilder.create_error(result_type='x', source=path, error=str(e))
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_create_error_result_convenience_function_is_visible_signal(self):
        """create_error_result(...) — the module-level convenience wrapper
        around ResultBuilder.create_error() — counts the same way."""
        content = """
def read(path):
    try:
        return create(result_type='x', source=path, data={})
    except Exception as e:
        return create_error_result(result_type='x', source=path, error=str(e))
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_unrelated_dict_literal_still_flagged(self):
        """A dict literal without an error-field key doesn't earn the pass —
        the escape hatch stays narrow (BACK-992)."""
        content = """
def query(nameserver):
    try:
        return {'answer': do_query(nameserver)}
    except Exception:
        return {'value': None}
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)

    # ============ Tests for deferred visible signal (BACK-989) ============

    def test_captured_error_surfaced_in_later_dict_literal(self):
        """except Exception as e: error = str(e); ... later: {'error': error}
        surfaces the failure one statement outside the handler — not silent."""
        content = """
def check_upstreams(servers):
    results = []
    for server in servers:
        try:
            connect(server)
            reachable = True
            error = None
        except Exception as e:
            reachable = False
            error = str(e)
        results.append({'server': server, 'reachable': reachable, 'error': error})
    return results
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_captured_tuple_assignment_surfaced_later(self):
        """except Exception as exc: a, b = 1, f"...{exc}"; a/b used later —
        tuple-target form of the same deferred-signal pattern."""
        content = """
def run_all(targets):
    results = []
    for target in targets:
        try:
            exit_code, summary = check(target)
        except Exception as exc:
            exit_code, summary = 2, f"error: {exc}"
        results.append({'exit_code': exit_code, 'summary': summary})
    return results
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_captured_variable_never_used_still_flagged(self):
        """Capturing str(e) into a variable that's never read again is just
        as silent as not capturing it at all — must still be flagged."""
        content = """
def check_upstream(server):
    try:
        connect(server)
        return True
    except Exception as e:
        error = str(e)
        return False
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)

    def test_unrelated_variable_alongside_capture_does_not_launder_silence(self):
        """A plain `ok = False` that doesn't reference the exception, with no
        later use of anything from the handler, stays flagged — the escape
        hatch requires an actual reference to the exception binding."""
        content = """
def check_upstream(server):
    try:
        connect(server)
        ok = True
    except Exception:
        ok = False
    return None
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)

    def test_docstring_fails_for_any_reason_recognized(self):
        """Broadened docstring-tolerance wording: 'fails for any reason'
        wasn't matched by the original narrower 'if fails' phrase."""
        content = """
def resolve_thresholds(file_path=None):
    '''Falls back to class defaults if config resolution fails for any reason.'''
    try:
        return load_config(file_path)
    except Exception:
        return DEFAULTS
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_docstring_best_effort_recognized(self):
        """Broadened docstring-tolerance wording: 'best-effort'."""
        content = """
def scan_optional(path):
    '''Best-effort scan; returns None if it can't complete.'''
    try:
        return do_scan(path)
    except Exception:
        return None
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)


class TestB006CSharp(unittest.TestCase):
    """Test B006's C# port (BACK-1011): silent broad `catch` clauses."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.rule = B006()

    def tearDown(self):
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def create_temp_file(self, content: str, name: str = "test.cs") -> str:
        path = os.path.join(self.temp_dir, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_bare_catch_flagged(self):
        content = """
class Foo {
    void M() {
        try { DoWork(); }
        catch { }
    }
}
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].rule_code, 'B006')
        self.assertEqual(detections[0].severity, Severity.MEDIUM)

    def test_broad_exception_catch_flagged(self):
        content = """
class Foo {
    void M() {
        try { DoWork(); }
        catch (Exception e) { }
    }
}
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)

    def test_specific_exception_type_not_flagged(self):
        content = """
class Foo {
    void M() {
        try { DoWork(); }
        catch (IOException e) { }
    }
}
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_rethrow_not_flagged(self):
        content = """
class Foo {
    void M() {
        try { DoWork(); }
        catch (Exception e) { throw; }
    }
}
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_log_warning_not_flagged(self):
        content = """
class Foo {
    void M() {
        try { DoWork(); }
        catch (Exception e) { _logger.LogWarning(e, "failed"); }
    }
}
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_log_debug_still_flagged(self):
        """LogDebug/LogTrace are invisible by default — same rationale as
        the Python side's logger.debug exclusion (BACK-983)."""
        content = """
class Foo {
    void M() {
        try { DoWork(); }
        catch (Exception e) { _logger.LogDebug(e, "swallowed"); }
    }
}
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)

    def test_explanatory_comment_not_flagged(self):
        content = """
class Foo {
    void M() {
        try { DoWork(); }
        catch {
            // Logged at lower levels
        }
    }
}
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_python_path_unaffected(self):
        """Guard against the .cs dispatch branch swallowing .py files."""
        content = """
def foo():
    try:
        risky_operation()
    except Exception:
        pass
"""
        path = self.create_temp_file(content, name="test.py")
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)


class TestB006Java(unittest.TestCase):
    """Test B006's Java port (BACK-1011)."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.rule = B006()

    def tearDown(self):
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def create_temp_file(self, content: str, name: str = "test.java") -> str:
        path = os.path.join(self.temp_dir, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_broad_exception_silent_flagged(self):
        content = """
class C {
    void m() {
        try { foo(); } catch (Exception e) { }
    }
}
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].rule_code, 'B006')

    def test_multi_catch_specific_types_not_flagged(self):
        """IOException | SQLException — neither is a broad type."""
        content = """
class C {
    void m() {
        try { foo(); } catch (IOException | SQLException e) { }
    }
}
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_logged_not_flagged(self):
        content = """
class C {
    void m() {
        try { foo(); } catch (Exception e) { log.error("x", e); }
    }
}
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_print_stack_trace_not_flagged(self):
        content = """
class C {
    void m() {
        try { foo(); } catch (Exception e) { e.printStackTrace(); }
    }
}
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_debug_only_still_flagged(self):
        content = """
class C {
    void m() {
        try { foo(); } catch (Exception e) { log.debug("x", e); }
    }
}
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)

    def test_rethrow_not_flagged(self):
        content = """
class C {
    void m() {
        try { foo(); } catch (Exception e) { throw new RuntimeException(e); }
    }
}
"""
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)


class TestB006JavaScriptTypeScript(unittest.TestCase):
    """Test B006's JS/TS port (BACK-1011).

    Unlike the typed-language ports, every catch is unconditionally
    "broad" here (JS/TS have no catch-type syntax), so only silence
    matters.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.rule = B006()

    def tearDown(self):
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def create_temp_file(self, content: str, name: str) -> str:
        path = os.path.join(self.temp_dir, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_silent_catch_with_param_flagged_js(self):
        content = "try { foo(); } catch (e) { }"
        path = self.create_temp_file(content, "a.js")
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)

    def test_silent_paramless_catch_flagged_ts(self):
        content = "try { foo(); } catch { }"
        path = self.create_temp_file(content, "a.ts")
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)

    def test_console_error_not_flagged(self):
        content = "try { foo(); } catch (e) { console.error(e); }"
        path = self.create_temp_file(content, "a.js")
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_console_log_not_flagged(self):
        """console.* is always emitted (no configurable level), unlike a
        backend logger's debug/trace — any console method counts."""
        content = "try { foo(); } catch (e) { console.log(e); }"
        path = self.create_temp_file(content, "a.js")
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_custom_logger_warn_not_flagged(self):
        content = "try { foo(); } catch (e) { logger.warn(e); }"
        path = self.create_temp_file(content, "a.ts")
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_rethrow_not_flagged(self):
        content = "try { foo(); } catch (e) { throw e; }"
        path = self.create_temp_file(content, "a.ts")
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_explanatory_comment_not_flagged(self):
        content = "try { foo(); } catch (e) { /* swallowed intentionally */ }"
        path = self.create_temp_file(content, "a.js")
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)


class TestB006PHP(unittest.TestCase):
    """Test B006's PHP port (BACK-1011)."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.rule = B006()

    def tearDown(self):
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def create_temp_file(self, content: str, name: str = "test.php") -> str:
        path = os.path.join(self.temp_dir, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_broad_exception_silent_flagged(self):
        content = "<?php try { foo(); } catch (Exception $e) { } ?>"
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)

    def test_specific_type_not_flagged(self):
        content = "<?php try { foo(); } catch (IOException $e) { } ?>"
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_error_log_not_flagged(self):
        content = "<?php try { foo(); } catch (Exception $e) { error_log($e); } ?>"
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_member_logger_error_not_flagged(self):
        content = "<?php try { foo(); } catch (Exception $e) { $this->logger->error('x', $e); } ?>"
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_member_logger_debug_still_flagged(self):
        content = "<?php try { foo(); } catch (Exception $e) { $this->logger->debug('x', $e); } ?>"
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)

    def test_rethrow_not_flagged(self):
        content = "<?php try { foo(); } catch (Exception $e) { throw $e; } ?>"
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 0)

    def test_multi_catch_broad_flagged(self):
        content = "<?php try { foo(); } catch (IOException | Throwable $e) { } ?>"
        path = self.create_temp_file(content)
        detections = self.rule.check(path, None, content)
        self.assertEqual(len(detections), 1)


if __name__ == '__main__':
    unittest.main()
