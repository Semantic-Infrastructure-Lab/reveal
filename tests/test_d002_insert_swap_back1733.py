"""BACK-1733: D002 must still see a near-copy after one inserted guard and one swapped line.

`_token_shape` renames identifiers by order of first appearance, so an early
inserted guard plus a swapped statement shifts every later name and the shaped
sequence match collapses (probe below: plain token match 0.86, shaped 0.42, cut
at 0.5).  Before vivid-gleam this pair reported "fetch_b ~98% similar to fetch_a".
Also: True/False/None are keywords and must stay literal (the lookup lowercased
the token, so the case-sensitive keyword list never matched them).
"""

import pytest

from reveal.analyzers.python import PythonAnalyzer
from reveal.rules.duplicates.D002 import D002

pytestmark = pytest.mark.component

# fetch_b = fetch_a + a two-line cache guard up front + two swapped lines.
INSERT_AND_SWAP = '''def fetch_a(path, key):
    cfg = load_config(path)
    client = make_client(cfg.url, cfg.token)
    retries = cfg.retries
    result = None
    for attempt in range(retries):
        try:
            result = client.fetch(key)
            break
        except TimeoutError:
            sleep(backoff(attempt))
    if result is None:
        raise FetchError(key)
    return result.payload


def fetch_b(path, key, cache):
    if key in cache:
        return cache[key]
    cfg = load_config(path)
    retries = cfg.retries
    client = make_client(cfg.url, cfg.token)
    result = None
    for attempt in range(retries):
        try:
            result = client.fetch(key)
            break
        except TimeoutError:
            sleep(backoff(attempt))
    if result is None:
        raise FetchError(key)
    return result.payload
'''

# Similar length and skeleton, unrelated content: must stay below the threshold.
DIFFERENT_FUNCTIONS = '''def parse_invoice(text):
    rows = []
    total = 0
    for line in text.splitlines():
        try:
            sku, qty, price = line.split(",")
            rows.append((sku, int(qty)))
            total += int(qty) * float(price)
        except ValueError:
            continue
    if not rows:
        raise InvoiceError(text)
    return rows, total


def render_banner(width, title):
    pad = " " * width
    edge = "+" + "-" * width + "+"
    out = [edge]
    for part in title.split():
        if len(part) > width:
            part = part[:width]
        out.append("|" + part.center(width) + "|")
    out.append(pad)
    out.append(edge)
    return "\\n".join(out)
'''


def _candidates(tmp_path, source):
    path = tmp_path / "m.py"
    path.write_text(source, encoding="utf-8")
    structure = PythonAnalyzer(str(path)).get_structure()
    return D002().check(str(path), structure, source)


def test_near_copy_with_inserted_guard_and_swapped_lines_is_a_candidate(tmp_path):
    (det,) = _candidates(tmp_path, INSERT_AND_SWAP)
    assert "'fetch_b'" in det.message and "'fetch_a'" in det.message


def test_different_functions_of_similar_length_stay_below_threshold(tmp_path):
    assert _candidates(tmp_path, DIFFERENT_FUNCTIONS) == []


def test_python_constants_are_keywords_not_renamed_identifiers():
    shape = D002()._token_shape("x = True\ny = None\nz = False")
    assert shape == ["#0", "=", "True", "#1", "=", "None", "#2", "=", "False"]
