"""BACK-1836: B006's Python exemptions must test what a handler does, not what it is named.

Each ``SWALLOWS`` case is a handler that still hides the failure and must be reported; each
``DISCLOSES`` case is the legitimate neighbour of the same shape and must stay quiet, so the
policy is checked in both directions (review: slice4.md F5).
"""

import pytest

from reveal.rules.bugs.B006 import B006

pytestmark = pytest.mark.component

HEAD = "def f(stats, metrics, handler):\n    try:\n        g()\n    except Exception as e:\n"


def _count(tmp_path, content):
    path = tmp_path / 'a.py'
    path.write_text(content, encoding='utf-8')
    return len(B006().check(str(path), None, content))


def _body(tmp_path, *lines):
    return _count(tmp_path, HEAD + ''.join(f"        {line}\n" for line in lines))


@pytest.mark.parametrize('lines', [
    ['metrics.fail()'],
    ['stats.handle_failure()'],
    ['assert e is not None'],
    ['assert isinstance(e, Exception)'],
    ['assert isinstance(e, BaseException)'],
    ['assert e'],
], ids=['counter-fail', 'counter-handle-failure', 'is-not-none', 'isinstance-exception',
        'isinstance-base', 'bare-truthy'])
def test_name_or_tautology_does_not_hide_a_swallow(tmp_path, lines):
    assert _body(tmp_path, *lines) == 1


@pytest.mark.parametrize('lines', [
    ['handler.fail("bad")'],
    ['handler.handle_failure(e)'],
    ['self.fail(str(e))'],
    ['assert e.args == ("x",)'],
    ['assert "boom" in str(e)'],
    ['assert isinstance(e, KeyError)'],
    ['assert e == expected'],
], ids=['fail-with-message', 'handler-gets-exception', 'unittest-fail', 'args-compared',
        'message-checked', 'specific-type', 'equality'])
def test_real_disclosure_stays_quiet(tmp_path, lines):
    assert _body(tmp_path, *lines) == 0


def test_error_list_asserted_only_not_none_is_still_silent(tmp_path):
    code = ('def test_case():\n'
            '    seen = []\n'
            '    try: run()\n'
            '    except Exception as e: seen.append(e)\n'
            '    assert seen is not None\n')
    assert _count(tmp_path, code) == 1


@pytest.mark.parametrize('assertion', ['assert not seen', 'assert seen == []', 'assert len(seen) == 0'])
def test_error_list_asserted_empty_is_observed(tmp_path, assertion):
    code = ('def test_case():\n'
            '    seen = []\n'
            '    try: run()\n'
            '    except Exception as e: seen.append(e)\n'
            f'    {assertion}\n')
    assert _count(tmp_path, code) == 0


FLAG = ('def test_case():\n'
        '    {init}\n'
        '    def worker():\n'
        '        nonlocal flag\n'
        '        try: run()\n'
        '        except Exception: flag = {assigned}\n'
        '    worker()\n'
        '    {assertion}\n')


@pytest.mark.parametrize('init, assigned, assertion, reported', [
    ('flag = False', 'True', 'assert flag', 1),          # set to the value the assert wants
    ('flag = True', 'False', 'assert not flag', 1),
    ('flag = True', 'False', 'assert flag', 0),          # the failure flips what is asserted
    ('flag = False', 'True', 'assert not flag', 0),
    ('flag = 0', 'True', 'assert not flag', 0),
])
def test_nonlocal_flag_must_flip_the_asserted_value(tmp_path, init, assigned, assertion, reported):
    code = FLAG.format(init=init, assigned=assigned, assertion=assertion)
    assert _count(tmp_path, code) == reported


def test_string_join_is_not_a_thread_join(tmp_path):
    code = ('def test_case():\n'
            '    errors = []\n'
            '    def worker():\n'
            '        try: run()\n'
            '        except Exception as e: errors.append(e)\n'
            '    label = ", ".join(["a", "b"])\n'
            '    assert not errors\n')
    assert _count(tmp_path, code) == 1


@pytest.mark.parametrize('join', ['thread.join()', 'thread.join(5)', 'thread.join(timeout=5)'])
def test_thread_join_still_counts(tmp_path, join):
    code = ('def test_case():\n'
            '    errors = []\n'
            '    def worker():\n'
            '        try: run()\n'
            '        except Exception as e: errors.append(e)\n'
            '    thread = Thread(target=worker)\n'
            '    thread.start()\n'
            f'    {join}\n'
            '    assert not errors\n')
    assert _count(tmp_path, code) == 0


@pytest.mark.parametrize('ret', [
    'return None, e',
    'return [None, e]',
    'return {"ok": False, "exc": e}',
    'return (e, None)',
], ids=['go-tuple', 'list', 'dict-value', 'tuple-first'])
def test_returning_the_exception_inside_a_container_hands_it_on(tmp_path, ret):
    assert _body(tmp_path, ret) == 0


@pytest.mark.parametrize('ret', [
    'return None, e.args',
    'return [None, str(e).upper()]',
    'return None, 0',
    'return {"ok": False}',
], ids=['attribute', 'reduced', 'constant-pair', 'flag-only'])
def test_container_without_the_exception_object_is_still_silent(tmp_path, ret):
    assert _body(tmp_path, ret) == 1
