"""BACK-1639: diff://a:b/elem with the element on neither side is a failed lookup
(top-level error, available_elements, exit 1), like `reveal a.py nope`; it used to be
answered as a verdict, change: not_found, with exit 0."""

import json
import subprocess
import sys

import pytest

from reveal.adapters.diff import DiffAdapter
from reveal.diff import compute_element_diff


@pytest.fixture
def pair(tmp_path):
    (tmp_path / 'a.py').write_text('def foo():\n    return 1\n\ndef only_left():\n    pass\n',
                                   encoding='utf-8')
    (tmp_path / 'b.py').write_text('def foo():\n    return 2\n\ndef only_right():\n    pass\n',
                                   encoding='utf-8')
    return tmp_path


def _reveal(cwd, *args):
    return subprocess.run([sys.executable, '-m', 'reveal', *args], cwd=cwd,
                          capture_output=True, text=True, encoding='utf-8', timeout=60)


def test_adapter_answers_none_and_lists_both_sides(pair):
    adapter = DiffAdapter(str(pair / 'a.py'), str(pair / 'b.py'))
    assert adapter.get_element('nope') is None
    assert adapter.list_elements() == ['foo', 'only_left', 'only_right']


def test_one_sided_element_is_still_a_verdict(pair):
    adapter = DiffAdapter(str(pair / 'a.py'), str(pair / 'b.py'))
    assert adapter.get_element('only_left')['change'] == 'removed'
    assert adapter.get_element('only_right')['change'] == 'added'


def test_compute_element_diff_refuses_neither_side():
    with pytest.raises(ValueError, match="not found in either resource"):
        compute_element_diff(None, None, 'nope')


def test_cli_json_fails_with_available_elements(pair):
    proc = _reveal(pair, 'diff://a.py:b.py/nope', '--format', 'json')
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert result['error'] == "Element 'nope' not found"
    assert result['available_elements'] == ['foo', 'only_left', 'only_right']
    assert 'change' not in result


def test_cli_text_fails_on_stderr(pair):
    proc = _reveal(pair, 'diff://a.py:b.py/nope')
    assert proc.returncode == 1
    assert "Element 'nope' not found" in proc.stderr
    assert 'Available elements: foo, only_left, only_right' in proc.stderr
