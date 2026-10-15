"""BACK-1430: B006 treats handing the caught exception to a callee as disclosure.

The dominant Java listener style is ``catch (Exception e) { listener.onFailure(e); }``:
the exception object itself is delivered to the code that reports or handles it,
so the handler is not silent.  The recognition is deliberately narrow (see
``B006._forwards_exception``): the caught variable must be an argument of a
direct, returned or awaited call (a wrapped argument counts only for a callee in
``_REPORTING_CALLEES``), and the callee must not be a debug-level log
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


@pytest.mark.parametrize('body', [
    ['setattr(handler, "err", e)'], ['errors.remove(e)'], ['q.put_nowait(e)'],
    ['return str(e)'], ['return repr(e)'], ['str(e)'],
    ['def later():', '    handler.on_failure(e)'],
    ['later = lambda: handler.on_failure(e)'],
    ['def later():', '    print(e)'],
])
def test_unexecuted_and_non_reporting_python_sinks_remain_silent(tmp_path, body):
    assert _py(tmp_path, body) == 1


@pytest.mark.parametrize('body', ['Objects.requireNonNull(e);', 'cache.remove(key, e);',
                                   'return String.valueOf(e);',
                                   'Runnable later = () -> handler.onFailure(e);'])
def test_non_reporting_java_sinks_remain_silent(tmp_path, body):
    assert _java(tmp_path, [body]) == 1


@pytest.mark.parametrize('body', ['const later = () => report(e);', 'function later(){ report(e); }',
                                   'cache.delete(e);', 'return String(e);'])
def test_unexecuted_and_non_reporting_js_sinks_remain_silent(tmp_path, body):
    assert _js(tmp_path, body) == 1


@pytest.mark.parametrize('body', [['return handler.on_failure(e)'], ['return handler.report(str(e))'],
                                   ['await handler.report(e)']])
def test_python_return_and_await_forwarding(tmp_path, body):
    # Await is syntactically valid only in an async function.
    content = PY_HEAD.replace('def f', 'async def f') + ''.join(f'        {line}\n' for line in body)
    assert _count(tmp_path, 'a.py', content) == 0


@pytest.mark.parametrize('body', ['return handler.onFailure(e);', 'handler.onFailure(format(e));'])
def test_java_return_and_wrapped_forwarding(tmp_path, body):
    assert _java(tmp_path, [body]) == 0


@pytest.mark.parametrize('body', ['await report(e);', 'return report(e);', 'report(String(e));'])
def test_js_return_await_and_wrapped_forwarding(tmp_path, body):
    assert _js(tmp_path, body) == 0


@pytest.mark.parametrize('body', [
    'return isinstance(e, KeyError)', 'return bool(e)', 'return len(e.args)',
    "return getattr(e, 'default', None)", 'statsd.incr(type(e).__name__)',
])
def test_python_computation_of_exception_is_still_silent(tmp_path, body):
    assert _py(tmp_path, [body]) == 1


@pytest.mark.parametrize('body', ['return Objects.isNull(e);', 'return Objects.hash(e);'])
def test_java_computation_of_exception_is_still_silent(tmp_path, body):
    assert _java(tmp_path, [body]) == 1


@pytest.mark.parametrize('body', ['return Boolean(e);', 'return Promise.resolve(e);',
                                   'return Array.isArray(e);'])
def test_js_computation_of_exception_is_still_silent(tmp_path, body):
    assert _js(tmp_path, body) == 1


@pytest.mark.parametrize('body', ['return self.retry(exc=e)',
                                   "return {'error': str(e)}", 'handler.report(str(e))'])
def test_python_forwarding_and_error_result_remain_visible(tmp_path, body):
    assert _py(tmp_path, [body]) == 0


def test_js_state_error_result_remains_visible(tmp_path):
    assert _js(tmp_path, 'setState({errorMessage: e.message});') == 0


@pytest.mark.parametrize('body', [
    ['assert e == expected'],
    ['info = ExceptionInfo()', 'assert info.traceback'],
    ['ret = Retry("failed", e)', 'assert ret.exc == e'],
    ['handler.on_success((1, ExceptionInfo(), 0.001))',
     'handler.on_failure.assert_called()'],
])
def test_checked_exception_handler_is_visible(tmp_path, body):
    assert _py(tmp_path, body) == 0


def test_unrelated_assert_does_not_hide_silent_handler(tmp_path):
    assert _py(tmp_path, ['assert True']) == 1


def test_click_fail_reports_failure(tmp_path):
    assert _py(tmp_path, ['handler.fail("bad")']) == 0


def test_checked_joined_thread_error_list(tmp_path):
    code = ('def test_case():\n'
            '    errors = []\n'
            '    def worker():\n'
            '        try: run()\n'
            '        except Exception as e: errors.append(e)\n'
            '    thread = Thread(target=worker)\n'
            '    thread.start()\n'
            '    thread.join()\n'
            '    assert not errors\n')
    assert _count(tmp_path, 'thread.py', code) == 0


def test_unchecked_thread_error_list_is_silent(tmp_path):
    code = ('def test_case():\n'
            '    errors = []\n'
            '    def worker():\n'
            '        try: run()\n'
            '        except Exception as e: errors.append(e)\n'
            '    thread = Thread(target=worker)\n'
            '    thread.start()\n')
    assert _count(tmp_path, 'thread.py', code) == 1


def test_checked_nonlocal_failure_flag(tmp_path):
    code = ('def test_case():\n'
            '    passed = True\n'
            '    def callback():\n'
            '        nonlocal passed\n'
            '        try: run()\n'
            '        except Exception: passed = False\n'
            '    callback()\n'
            '    assert passed\n')
    assert _count(tmp_path, 'flag.py', code) == 0


def test_caught_exception_returned_to_caller(tmp_path):
    assert _py(tmp_path, ['return e']) == 0


def test_error_list_asserted_after_try(tmp_path):
    code = ('def test_case():\n'
            '    failures = []\n'
            '    try: run()\n'
            '    except Exception as e: failures.append(e)\n'
            '    assert not failures\n')
    assert _count(tmp_path, 'checked.py', code) == 0


def test_error_list_asserted_after_loop(tmp_path):
    code = ('def test_case():\n'
            '    failures = []\n'
            '    for item in items:\n'
            '        try: run(item)\n'
            '        except Exception as e: failures.append((item, e))\n'
            '    assert not failures\n')
    assert _count(tmp_path, 'checked.py', code) == 0


def test_captured_exception_info_forwarded_after_handler(tmp_path):
    code = ('def test_case():\n'
            '    try: run()\n'
            '    except Exception: info = ExceptionInfo()\n'
            '    callback(info)\n')
    assert _count(tmp_path, 'checked.py', code) == 0


def test_java_nested_failed_future_remains_disclosed(tmp_path):
    assert _java(tmp_path, ['return singletonList(immediateFailedFuture(e));']) == 0


def test_js_error_state_and_warning_remain_visible(tmp_path):
    assert _js(tmp_path, 'setAppState({errorMessage: e.message});') == 0
    assert _js(tmp_path, 'warnOnce(`failed: ${e.message}`);') == 0
