"""BACK-2529: element flags on deeply nested code report a required-analysis failure, not a traceback.

The variable-flow walker recurses once per syntax level, so a function with a few hundred
nested calls (common in generated parsers) exhausted Python's recursion limit and printed a
RecursionError traceback (exit 1). D6: the request was valid and the required analysis
failed, so the answer is exit 3 with a diagnostic naming the flag and the element.
"""
import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component

DEEP = 500
FLAGS = ['--boundary', '--inputs', '--outputs', '--varflow=x', '--mutations', '--flow']


def _nested_python(path, depth):
    path.write_text('def f(a):\n    x = ' + 'g(' * depth + 'a' + ')' * depth + '\n    return x\n',
                    encoding='utf-8')
    return path


def _nested_js(path, depth):
    path.write_text('function f(a) {\n  var x;\n  x = ' + 'g(' * depth + 'a' + ')' * depth
                    + ';\n  return x;\n}\n', encoding='utf-8')
    return path


@pytest.mark.parametrize('flag', FLAGS)
@pytest.mark.parametrize('lang', ['py', 'js'])
def test_deep_nesting_is_an_analysis_failure_not_a_traceback(tmp_path, flag, lang):
    make = _nested_python if lang == 'py' else _nested_js
    source = make(tmp_path / f'deep.{lang}', DEEP)
    result = _run_reveal_direct(str(source), 'f', flag)
    assert result.returncode == 3, (result.returncode, result.stderr[-500:])
    assert 'Traceback' not in result.stderr and 'RecursionError' not in result.stderr
    assert flag.split('=')[0] in result.stderr and "'f'" in result.stderr
    assert 'nested' in result.stderr
    assert result.stdout == ''


@pytest.mark.parametrize('flag', FLAGS)
def test_shallow_nesting_still_answers(tmp_path, flag):
    source = _nested_python(tmp_path / 'shallow.py', 20)
    result = _run_reveal_direct(str(source), 'f', flag)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()


def test_json_format_emits_no_partial_document(tmp_path):
    source = _nested_python(tmp_path / 'deep.py', DEEP)
    result = _run_reveal_direct(str(source), 'f', '--boundary', '--format', 'json')
    assert result.returncode == 3
    assert result.stdout == ''


def test_mcp_nav_reports_a_public_failure(tmp_path):
    pytest.importorskip('mcp')
    from reveal.mcp_server import _ToolFailure, reveal_nav

    source = _nested_python(tmp_path / 'deep.py', DEEP)
    answer = reveal_nav(path=str(source), element='f', flag='boundary')
    assert isinstance(answer, _ToolFailure) and answer.public, answer
    assert 'nested' in str(answer) and 'Traceback' not in str(answer)
