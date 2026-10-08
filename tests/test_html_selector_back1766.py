"""BACK-1766: an HTML element that is not a valid CSS selector never tracebacks.

`reveal a.html /abs/b.html --metadata` hands the second path to the element
reader as "function /abs/b.html"; soupsieve raised SelectorSyntaxError out of
HTMLAnalyzer.extract_by_selector. An unparseable selector is a non-match, so
the normal "not found" result (exit 1) answers it.
"""
import pytest

from conftest import _run_reveal_direct

PAGE = (
    '<html><head><title>T</title></head><body>'
    '<div class="box"><p id="x">hi</p></div></body></html>'
)


@pytest.fixture
def pages(tmp_path):
    a = tmp_path / 'a.html'
    b = tmp_path / 'b.html'
    a.write_text(PAGE, encoding='utf-8')
    b.write_text(PAGE, encoding='utf-8')
    return a, b


def _assert_clean_not_found(r):
    assert 'Traceback' not in r.stderr
    assert 'SelectorSyntaxError' not in r.stderr
    assert r.returncode == 1
    assert 'not found' in r.stderr


def test_second_path_with_metadata_is_refused_not_a_traceback(pages):
    # The original BACK-1766 repro. Since BACK-1773 the second path is refused up front (exit 2)
    # instead of reaching the selector; the invariant here is that it never tracebacks.
    a, b = pages
    r = _run_reveal_direct(a, b, '--metadata')
    assert 'Traceback' not in r.stderr
    assert 'SelectorSyntaxError' not in r.stderr
    assert r.returncode == 2
    assert '--metadata' in r.stderr


@pytest.mark.parametrize('selector', ['.', '#', '> p', 'div >', 'a b/c', '.box /x'])
def test_invalid_selector_is_not_found(pages, selector):
    a, _ = pages
    r = _run_reveal_direct(a, selector)
    _assert_clean_not_found(r)


def test_invalid_selector_json_has_no_traceback(pages):
    a, _ = pages
    r = _run_reveal_direct(a, '.box /x', '--format', 'json')
    assert 'Traceback' not in r.stderr
    assert r.returncode == 1


# Negative controls: valid selectors still extract, a missing one is still not found.
@pytest.mark.parametrize('selector, tag', [
    ('#x', 'p'), ('x', 'p'), ('p', 'p'), ('.box', 'div'), ('div > p', 'p'), ('.box p', 'p'),
])
def test_valid_selector_still_extracts(pages, selector, tag):
    a, _ = pages
    r = _run_reveal_direct(a, selector)
    assert r.returncode == 0, r.stderr
    assert f'<{tag}' in r.stdout


def test_missing_element_is_still_not_found(pages):
    a, _ = pages
    r = _run_reveal_direct(a, 'nosuchthing')
    _assert_clean_not_found(r)
