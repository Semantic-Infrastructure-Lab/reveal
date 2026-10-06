"""BACK-1430: B006 treats handing the caught exception to a callee as disclosure.

The dominant Java listener style is ``catch (Exception e) { listener.onFailure(e); }``:
the exception object itself is delivered to the code that reports or handles it,
so the handler is not silent.  The recognition is deliberately narrow (see
``B006._forwards_exception``): the caught variable must be a *bare* argument of a
call whose result is discarded, and the callee must not be a debug-level log
call, a container store or a name that announces a discard.  Those keep the
debug-only / swallow policy from the developer guidelines (item 3).
"""

import pytest

from reveal.rules.bugs.B006 import B006

pytestmark = pytest.mark.component

PY_HEAD = "def f(handler, errors, logger):\n    try:\n        g()\n    except Exception as e:\n"
JAVA_HEAD = "class P {\n    void f(Listener handler) {\n        try { g(); } catch (Exception e) {\n"
JAVA_TAIL = "        }\n    }\n}\n"


def _count(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content, encoding='utf-8')
    return len(B006().check(str(path), None, content))


def _py(tmp_path, body):
    return _count(tmp_path, "a.py", PY_HEAD + "".join(f"        {line}\n" for line in body))


def _java(tmp_path, body):
    return _count(tmp_path, "P.java", JAVA_HEAD + "".join(f"            {line}\n" for line in body) + JAVA_TAIL)


def _js(tmp_path, body, name="a.js"):
    return _count(tmp_path, name, "function f(){ try { g(); } catch (e) { " + body + " } }\n")


class TestForwardingIsDisclosure:
    """Positive: the exception is handed to a callee, so these are not flagged."""

    def test_python_callback(self, tmp_path):
        assert _py(tmp_path, ["handler.on_failure(e)"]) == 0

    def test_python_keyword_argument(self, tmp_path):
        assert _py(tmp_path, ["handler.report(error=e)"]) == 0

    def test_java_listener(self, tmp_path):
        assert _java(tmp_path, ["handler.onFailure(e);"]) == 0

    def test_java_bare_call(self, tmp_path):
        assert _java(tmp_path, ["fail(e);"]) == 0

    def test_js_reject(self, tmp_path):
        assert _js(tmp_path, "reject(e);") == 0

    def test_ts_member_callback(self, tmp_path):
        assert _js(tmp_path, "this.onError(e);", "a.ts") == 0


class TestOtherwiseStillFlagged:
    """Negative controls: nothing here hands the exception to a reporting callee."""

    def test_python_callback_given_something_else(self, tmp_path):
        assert _py(tmp_path, ["handler.on_failure('failed')"]) == 1

    def test_python_callback_given_other_variable(self, tmp_path):
        assert _py(tmp_path, ["other = 1", "handler.on_failure(other)"]) == 1

    def test_python_debug_log_only(self, tmp_path):
        assert _py(tmp_path, ["logger.debug('x', e)"]) == 1

    def test_python_container_store_only(self, tmp_path):
        assert _py(tmp_path, ["errors.append(e)"]) == 1

    def test_python_conversion_is_not_forwarding(self, tmp_path):
        assert _py(tmp_path, ["text = str(e)"]) == 1

    def test_python_discard_named_callee(self, tmp_path):
        assert _py(tmp_path, ["ignore_error(e)"]) == 1

    def test_java_callback_given_something_else(self, tmp_path):
        assert _java(tmp_path, ['handler.onFailure("failed");']) == 1

    def test_java_debug_log_only(self, tmp_path):
        assert _java(tmp_path, ['log.debug("x", e);']) == 1

    def test_java_container_store_only(self, tmp_path):
        assert _java(tmp_path, ["errors.add(e);"]) == 1

    def test_java_forwarding_in_a_different_catch_does_not_leak(self, tmp_path):
        content = (
            "class P {\n    void f(Listener h) {\n"
            "        try { g(); } catch (Exception e) { h.onFailure(e); }\n"
            "        try { g(); } catch (Exception e) { }\n    }\n}\n"
        )
        assert _count(tmp_path, "P.java", content) == 1

    def test_js_callback_given_something_else(self, tmp_path):
        assert _js(tmp_path, "done();") == 1

    def test_js_debug_log_only(self, tmp_path):
        assert _js(tmp_path, "logger.debug(e);", "a.ts") == 1

    def test_js_container_store_only(self, tmp_path):
        assert _js(tmp_path, "errors.push(e);") == 1
