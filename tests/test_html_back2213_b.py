"""BACK-2213 lane b: HTML link and selector fixes found by the guide review.

CB9:  `--links` text printed "Links (N)" and then only the external and internal groups;
      anchor, mailto, tel and relative links were dropped.
CB10: `--broken-only` did nothing for HTML (every link came back, none marked broken), and
      `--link-type all` / `email` matched nothing.
CB11: a `tag.class` selector such as `table.data` was not found, though `.data` was.
"""
import json
import os
import subprocess
import sys

import pytest

_LINKS = """<!DOCTYPE html>
<html><body>
<a href="/about">About</a>
<a href="https://example.com/x">Ext</a>
<a href="#s">Anchor</a>
<a href="mailto:a@example.com">Mail</a>
<a href="tel:+15550100">Call</a>
<a href="./page.html">Page</a>
<a href="./missing.html">Missing</a>
<table class="data"><tr><td>1</td></tr></table>
<div class="content"><p>para</p></div>
</body></html>
"""


def _reveal(*args):
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    return subprocess.run([sys.executable, '-m', 'reveal', *args], capture_output=True,
                          text=True, encoding='utf-8', timeout=60, env=env)


@pytest.fixture()
def page(tmp_path):
    (tmp_path / 'page.html').write_text('<p>exists</p>\n', encoding='utf-8')
    path = tmp_path / 'index.html'
    path.write_text(_LINKS, encoding='utf-8')
    return str(path)


def test_links_text_lists_every_link_type(page):
    r = _reveal(page, '--links')
    assert r.returncode == 0, r.stderr
    for url in ('/about', 'https://example.com/x', '#s', 'mailto:a@example.com', 'tel:+15550100',
                './page.html', './missing.html'):
        assert url in r.stdout, (url, r.stdout)


def _links_json(*args):
    r = _reveal(*args, '--format', 'json')
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)['structure']['links']


def test_broken_only_keeps_only_the_missing_local_link(page):
    links = _links_json(page, '--links', '--broken-only')
    assert [link['url'] for link in links] == ['./missing.html']
    assert links[0]['broken'] is True


def test_link_type_all_is_no_filter_and_email_means_mailto(page):
    assert len(_links_json(page, '--links', '--link-type', 'all')) == 7
    assert [link['url'] for link in _links_json(page, '--links', '--link-type', 'email')] == ['mailto:a@example.com']
    # positive control: a literal type still filters
    assert [link['url'] for link in _links_json(page, '--links', '--link-type', 'external')] == ['https://example.com/x']


@pytest.mark.parametrize('selector, needle', [('table.data', '<td>1</td>'), ('div.content', 'para'),
                                              ('.data', '<td>1</td>'), ('div.content > p', 'para')])
def test_tag_class_selectors_are_found(page, selector, needle):
    r = _reveal(page, selector)
    assert r.returncode == 0, (selector, r.stderr)
    assert needle in r.stdout


@pytest.mark.parametrize('selector', ['p::before', 'div.content::after', '.data::first-line'])
def test_unsupported_selectors_report_not_found_without_a_traceback(page, selector):
    r = _reveal(page, selector)
    assert 'Traceback' not in r.stderr, (selector, r.stderr)
    assert 'NotImplementedError' not in r.stderr
