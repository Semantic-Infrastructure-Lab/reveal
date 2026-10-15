"""BACK-1836: JS/TS/Java B006 parity with Python for what a handler returns and what it calls.

Python already treats ``return e`` and the pairs / records that carry the exception object as
handing it to the caller.  A bare ``err()`` call with nothing to say is not a report.  Each
case is checked both ways (review: slice4.md F5).
"""

import pytest

from reveal.rules.bugs.B006 import B006

pytestmark = pytest.mark.component


def _count(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content, encoding='utf-8')
    return len(B006().check(str(path), None, content))


def _js(tmp_path, body, name='a.js'):
    return _count(tmp_path, name, "function f(){ try { g(); } catch (err) { " + body + " } }\n")


def _java(tmp_path, body):
    return _count(tmp_path, 'A.java',
                  "class A { Object f() { try { g(); } catch (Exception e) { " + body + " } return null; } }\n")


@pytest.mark.parametrize('name', ['a.js', 'a.ts'])
@pytest.mark.parametrize('body', [
    'return err;',
    'return [null, err];',
    'return { ok: false, error: err };',
    'return { err };',
    'return [err, null];',
], ids=['bare', 'go-pair', 'record', 'shorthand', 'pair-first'])
def test_returning_the_exception_object_hands_it_on(tmp_path, name, body):
    assert _js(tmp_path, body, name) == 0


@pytest.mark.parametrize('name', ['a.js', 'a.ts'])
@pytest.mark.parametrize('body', [
    'return null;',
    'return [null, err.code];',
    'return { ok: false };',
    'return { code: err.code };',
    'return err();',
    'err();',
], ids=['null', 'attribute-pair', 'flag-only', 'attribute-record', 'return-bare-call', 'bare-call'])
def test_returns_and_calls_that_do_not_carry_it_stay_silent(tmp_path, name, body):
    assert _js(tmp_path, body, name) == 1


@pytest.mark.parametrize('body', ['err("failed");', 'console.error(err);', 'error(err.message);'])
def test_real_reports_stay_quiet(tmp_path, body):
    assert _js(tmp_path, body) == 0


def test_returned_arrow_function_does_not_count(tmp_path):
    assert _js(tmp_path, 'return () => err;') == 1


def test_java_return_of_the_caught_exception(tmp_path):
    assert _java(tmp_path, 'return e;') == 0


def test_java_return_of_something_else_is_silent(tmp_path):
    assert _java(tmp_path, 'return null;') == 1
    assert _java(tmp_path, 'return e.getMessage();') == 1
