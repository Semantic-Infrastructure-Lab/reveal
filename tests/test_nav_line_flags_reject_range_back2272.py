"""`--scope` and `--around` take one line; a range exits 2 instead of answering for its first line (BACK-2272).

`reveal main.py :100-110 --around 2` exited 0 and printed lines 98-102: the rest of the range
was dropped without a word. The other nav flags take ranges and must keep doing so.
"""

import json

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component

SOURCE = '''def target(order):
    total = 0
    for item in order:
        total += item
    return total
'''


@pytest.fixture
def path(tmp_path):
    p = tmp_path / 'app.py'
    p.write_text(SOURCE, encoding='utf-8')
    return str(p)


@pytest.mark.parametrize('flag', [['--around', '1'], ['--around'], ['--scope']])
@pytest.mark.parametrize('fmt', ['text', 'json'])
def test_range_is_rejected_with_exit_2(path, flag, fmt):
    result = _run_reveal_direct(path, ':2-4', *flag, '--format', fmt)
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    assert result.stdout == ''
    assert ':2-4' in result.stderr
    assert 'single line' in result.stderr
    assert flag[0] in result.stderr


@pytest.mark.parametrize('element', [':3', '3', ':3-3'])
def test_single_line_still_answers(path, element):
    # Negative control: one line, in each spelling, is unchanged.
    around = _run_reveal_direct(path, element, '--around', '1', '--format', 'json')
    assert around.returncode == 0, around.stderr
    payload = json.loads(around.stdout)
    assert payload['meta']['target_line'] == 3
    assert [f['line'] for f in payload['findings']] == [2, 3, 4]
    scope = _run_reveal_direct(path, element, '--scope')
    assert scope.returncode == 0, scope.stderr
    assert 'target' in scope.stdout


def test_other_nav_flags_still_take_a_range(path):
    # Negative control on the sibling path: --deps reads the whole range.
    result = _run_reveal_direct(path, ':2-4', '--deps', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['meta']['to_line'] == 4


def test_mcp_reveal_nav_reports_the_rejection(path):
    from reveal.mcp_server import reveal_nav
    out = reveal_nav(path, ':2-4', 'around', '1')
    assert 'exited with code 2' in out
    assert 'single line' in out
