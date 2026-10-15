"""BACK-1835: B006 decides forwarding by the callee's role and by whether the exception's
content flows into the call, not by a list of names seen in reviewed corpora.

Three groups, each measured on the pinned corpora and the Sprint 4 review fixtures:
- must NOT report: the exception (or what it says) is handed to an effect-shaped call, or an
  assertion consumes it.  Real shapes from vscode, WordPress, dagster and three.js.
- must report: the exception only feeds a computation, a predicate, a converter or a lookup, so the
  caller learns nothing about the failure.  These are swallows whatever the callee is called.
- the policy is the same in Python, JavaScript/TypeScript and Java.
"""

import pytest

from reveal.rules.bugs.B006 import B006

pytestmark = pytest.mark.component

PY_HEAD = "def f(handler, errors, logger):\n    try:\n        g()\n    except Exception as e:\n"
JAVA_HEAD = "class P {\n    Object f(Listener handler) {\n        try { g(); } catch (Exception e) {\n"
JAVA_TAIL = "        }\n        return null;\n    }\n}\n"


def _count(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content, encoding='utf-8')
    return len(B006().check(str(path), None, content))


def _py(tmp_path, body):
    return _count(tmp_path, "a.py", PY_HEAD + "".join(f"        {line}\n" for line in body.split('\n')))


def _java(tmp_path, body):
    return _count(tmp_path, "P.java", JAVA_HEAD + f"            {body}\n" + JAVA_TAIL)


def _js(tmp_path, body, name="a.js"):
    # async so a body may use await
    return _count(tmp_path, name, "async function f(){ try { g(); } catch (e) { " + body + " } }\n")


# --- Python -------------------------------------------------------------------------------

PY_DISCLOSED = [
    'future.set_exception(RuntimeError(str(e)))',
    'return HttpResponseBadRequest(str(e))',
    'return JsonResponse({"detail": str(e)}, status=400)',
    'sys.exit(f"error: {e}")',
    'sys.stderr.write(str(e) + "\\n")',
    'click.echo(f"failed: {e}", err=True)',
    'callback(None, RuntimeError(e))',
    'abort(500, description=str(e))',
    'warnings.warn(str(e))',
    'return dict(ok=False, error=e)',
    'self.assertEqual(str(e), "boom")',
    'self.assertIn("boom", e.args)',
    # dagster: a stderr write and a result object carrying the message
    'sys.stderr.write(f"Exception raised: {e}\\n")',
    'return PackageConflictCheckResult(request_error_msg=str(e))',
]

PY_SWALLOWED = [
    # the Sprint 4 review's synthetic swallows
    "return hasattr(e, 'code')",
    'return callable(e)',
    'return vars(e)',
    'return is_retryable(e)',
    'return CODES.get(e)',
    'return issubclass(type(e), KeyError)',
    'return isinstance(e, KeyError)',
    "return getattr(e, 'default', None)",
    'return len(e.args)',
    'return bool(e)',
    'return dict(ok=False, tag=id(e))',
    'statsd.incr(type(e).__name__)',
    'hash(e)',
    # an effect call that only receives something computed from the exception
    'report(len(e.args))',
    'report(isinstance(e, KeyError))',
    'report(e is None)',
    'report(type(e) == KeyError)',
    'return str(e).upper()',
    # debug-level logging by name, not just the exact word
    'self.debug_message(str(e))',
]

PY_CALLBACK_WITH_COMPUTED_CALLEE = ['callbacks[0](e)', '(on_error or on_other)(e)']


@pytest.mark.parametrize('body', PY_DISCLOSED)
def test_python_effect_call_that_carries_the_exception_discloses_it(tmp_path, body):
    assert _py(tmp_path, body) == 0


@pytest.mark.parametrize('body', PY_CALLBACK_WITH_COMPUTED_CALLEE)
def test_python_a_computed_callee_is_a_callback_invocation(tmp_path, body):
    assert _py(tmp_path, body) == 0


@pytest.mark.parametrize('body', PY_SWALLOWED)
def test_python_computation_of_the_exception_is_a_swallow(tmp_path, body):
    assert _py(tmp_path, body) == 1


def test_python_a_callee_named_report_does_not_disclose_a_computed_value(tmp_path):
    # The old rule keyed on the name `report`; the flow is what matters.
    assert _py(tmp_path, 'report(len(e.args))') == 1
    assert _py(tmp_path, 'report(e)') == 0


# --- JavaScript / TypeScript -------------------------------------------------------------

JS_DISCLOSED = [
    'cb(new Error("wrap: " + e.message));',
    'next(createError(500, e));',
    'res.status(500).json({ error: e.message });',
    'res.status(500).send(e.message);',
    'setError(e.message);',
    'createErrorNotice(e.message);',
    'self.postMessage({ action: "reject", value: e });',
    'this._onError.fire(e instanceof Error ? e : new Error(String(e)));',
    'this._onDidWatchError.fire(e instanceof Error ? e.message : String(e));',
    'alert(e.message);',
    'process.stderr.write(String(e));',
    'console["log"](e && e.stack);',
    'process.parentPort.postMessage({ error: e.toString() });',
    'transport.send(jsonRpcErrorFrom(msg.id, e));',
    'writeJsonError(res, 400, "bad", `Failed to read body: ${stringifyError(e)}`);',
    'setNotice({ type: "error", message: e.message });',
    'dispatch.cancelItem(id, new UploadError({ error: e }));',
    # expected-exception assertions in tests: the assertion consumes the error
    "assert.strictEqual(e.message, 'nice error');",
    "return assert(e.message === 'Canceled');",
    'assert.ok(e instanceof ProtocolError, `expected ProtocolError, got: ${e}`);',
    'assert.deepStrictEqual(e.code, ErrorCode.NotFound);',
    'assert.strictEqual(toErrorCode(e instanceof Error ? e : undefined), Code.NoPermissions);',
    "expect(e.message).toBe('boom');",
    'assert.ok(e instanceof Error); assert.ok(e.message.includes("RECURSIVELY"));',
    'assert(isCancellationError(e));',
    'await reporter.capture(e);',
    # a callback chosen at run time: error-first callback convention
    'args[args.length - 1](e);',
]

JS_SWALLOWED = [
    'return Boolean(e);',
    'return JSON.stringify(e);',
    'return Object.keys(e);',
    'return Array.from(e);',
    'return Object.is(e, sentinel);',
    'return Number.isNaN(e);',
    'return Promise.resolve(e);',
    'return Array.isArray(e);',
    'return Number(e instanceof TypeError);',
    'return String(e);',
    'return e.message;',
    'cache.delete(e);',
    'logger.debug(e);',
    'this.debugMessage(e + " at " + this.position);',
    # an effect call that only receives something computed from the exception
    'report(Boolean(e));',
    'report(e instanceof TypeError);',
    'report(e.code === 404);',
    'report(Object.keys(e));',
    'await sleep(e ? 10 : 0);',
]


@pytest.mark.parametrize('body', JS_DISCLOSED)
@pytest.mark.parametrize('name', ['a.js', 'a.ts'])
def test_js_effect_call_or_assertion_that_carries_the_exception_discloses_it(tmp_path, body, name):
    assert _js(tmp_path, body, name) == 0


@pytest.mark.parametrize('body', JS_SWALLOWED)
@pytest.mark.parametrize('name', ['a.js', 'a.ts'])
def test_js_computation_of_the_exception_is_a_swallow(tmp_path, body, name):
    assert _js(tmp_path, body, name) == 1


# --- Java --------------------------------------------------------------------------------

JAVA_DISCLOSED = [
    'future.setException(new RuntimeException(e));',
    'result.completeExceptionally(new CompletionException(e));',
    'callback.failed(new IOException(e));',
    'return Futures.immediateFailedFuture(e);',
    'return Result.error(e.getMessage());',
    'System.err.println("failed: " + e);',
    'System.err.printf("failed: %s%n", e);',
    'return wrap(e);',
    'assertEquals("boom", e.getMessage());',
    'assertThat(e).hasMessageThat().contains("boom");',
    'handler.onFailure(e);',
]

JAVA_SWALLOWED = [
    'return Objects.isNull(e);',
    'return Objects.nonNull(e);',
    'return Objects.equals(e, other);',
    'return Objects.toString(e);',
    'return Objects.hash(e);',
    'return Optional.ofNullable(e);',
    'return e.getMessage();',
    'return String.valueOf(e);',
    'LOG.debug("x", e);',
    'handler.accept(e.hashCode());',
    'handler.accept(Objects.hash(e));',
]


@pytest.mark.parametrize('body', JAVA_DISCLOSED)
def test_java_effect_call_or_assertion_that_carries_the_exception_discloses_it(tmp_path, body):
    assert _java(tmp_path, body) == 0


@pytest.mark.parametrize('body', JAVA_SWALLOWED)
def test_java_computation_of_the_exception_is_a_swallow(tmp_path, body):
    assert _java(tmp_path, body) == 1


# --- the corpus-tuned names are gone ----------------------------------------------------

@pytest.mark.parametrize('name', ['setAppState', 'setErrorMessage', 'updateScene',
                                  'updateMagicGeneration', 'immediateFailedFuture'])
def test_no_callee_is_special_because_a_corpus_needed_it(name):
    # BACK-1835: these five existed only to hold back reviewed Excalidraw and Guava cases.
    from reveal.rules.bugs import _exception_flow as flow
    assert flow.callee_role(name, None) == 'effect'
    assert not hasattr(B006, '_REPORTING_CALLEES')


@pytest.mark.parametrize('name,receiver,role', [
    ('isRetryable', None, 'silent'), ('is_retryable', None, 'silent'), ('hasCode', None, 'silent'),
    ('isolate', None, 'effect'), ('hasattr', None, 'silent'), ('len', None, 'silent'),
    ('assertEquals', None, 'assertion'), ('expect', None, 'assertion'), ('ok', 'assert', 'assertion'),
    ('nonNull', 'Objects', 'silent'), ('keys', 'Object', 'silent'), ('reject', 'Promise', 'effect'),
    ('stringify', 'JSON', 'converter'), ('str', None, 'converter'), ('valueOf', 'String', 'converter'),
    ('ignoreError', None, 'silent'), ('swallowError', None, 'silent'), ('add', 'errors', 'silent'),
    ('report', None, 'effect'), ('onFailure', 'listener', 'effect'), (None, None, 'effect'),
    ('debugMessage', 'this', 'silent'), ('verbose_log', None, 'silent'), ('debugger', None, 'effect'),
    ('traceError', 'this', 'effect'),
])
def test_callee_roles(name, receiver, role):
    from reveal.rules.bugs import _exception_flow as flow
    assert flow.callee_role(name, receiver) == role
