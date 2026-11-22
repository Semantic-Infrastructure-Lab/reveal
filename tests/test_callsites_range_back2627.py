"""BACK-2627 F1 (X9): ``--callsites`` honours ``--range``, the element selection every line-reading view takes.

``reveal FILE ELEMENT --callsites --range 13-14`` printed every call site of the element and counted the range as read
(the S3b-1 measurement: 6 rows with and without it). X9 makes ``--range`` the element-selection modifier and retires
``--callsites N-M``'s own value into it, so the bare operation selects the range's lines, exactly as its old value did.
"""
import json

from conftest import _run_reveal_direct as run

FILE = 'tests/fixtures/conformance/python/sample.py'
ELEMENT = 'process_order'


def _rows(*flags):
    response = run(FILE, ELEMENT, '--callsites', *flags, '--format', 'json')
    assert response.returncode == 0, response.stderr[:400]
    return json.loads(response.stdout)


def test_callsites_selects_the_range_lines():
    whole, ranged = _rows(), _rows('--range', '13-14')
    lines = [row['line'] for row in ranged['findings']]
    assert lines and all(13 <= line <= 14 for line in lines), lines
    assert len(ranged['findings']) < len(whole['findings'])


def test_callsites_range_answers_what_its_old_value_answers():
    assert _rows('--range', '13-14')['findings'] == _rows('13-14')['findings']


def test_sibling_its_own_value_still_selects_lines():
    lines = [row['line'] for row in _rows('13-14')['findings']]
    assert lines and all(13 <= line <= 14 for line in lines), lines
