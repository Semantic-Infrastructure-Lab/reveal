"""Each HTML link, script and stylesheet reports its own line (BACK-2287).

bs4 records ``sourceline`` only with the stdlib ``html.parser`` builder. With lxml (the
preferred builder, installed by the ``[html]`` extra) every element has ``sourceline=None``,
and the fallback scanned for the first source line holding ``<a`` (``<script``) plus the
element's id or first class. A tag with neither matched the first tag of its name: every
link after the first reported the first link's line, and an inline ``<script>`` reported
the external script's line, so ``--links --format grep``'s ``path:line`` pointed elsewhere.

The CI venvs do not install lxml, so ``no_sourceline`` reproduces the lxml case with the
stdlib builder and ``store_line_numbers=False``; the ``lxml`` case runs where lxml exists.
"""
import pytest

from conftest import _run_reveal_direct

from reveal.analyzers import html as html_module
from reveal.analyzers.html import HTMLAnalyzer

pytestmark = [pytest.mark.component]

# Line numbers are the fixture's 1-based lines; the commented-out <a> and the "<a" inside the
# inline script's string are not links.
LINES = [
    '<html><body>',                                 # 1
    '<p>x</p>',                                     # 2
    '<a href="a.html">A</a>',                       # 3
    '<p>y</p>',                                     # 4
    '<a href="b.html">B</a>',                       # 5
    '<script src="ext.js"></script>',               # 6
    '<script>var s = "<a href=fake>";</script>',    # 7
    '<!-- <a href="commented.html">C</a> -->',      # 8
    '<a href="a.html">A</a>',                       # 9  (identical to line 3)
    '<link rel="stylesheet" href="s.css">',         # 10
    '<link rel="stylesheet" href="t.css">',         # 11
    '<a id="named" href="c.html">N</a>',            # 12 (has an id: the old fallback found it)
    '</body></html>',                               # 13
]
LINKS = [('a.html', 3), ('b.html', 5), ('a.html', 9), ('c.html', 12)]
SCRIPTS = [('external', 6), ('inline', 7)]
STYLES = [('s.css', 10), ('t.css', 11)]


def _write(tmp_path, newline='\n'):
    path = tmp_path / 'ln.html'
    path.write_bytes((newline.join(LINES) + newline).encode('utf-8'))
    return path


@pytest.fixture
def no_sourceline(monkeypatch):
    """The analyzer's parser keeps no source lines, as lxml does."""
    import bs4

    def builder(markup, _parser, **kwargs):
        return bs4.BeautifulSoup(markup, 'html.parser', store_line_numbers=False, **kwargs)

    monkeypatch.setattr(html_module, 'BeautifulSoup', builder)


@pytest.fixture(params=['no_sourceline', 'lxml'])
def parser_case(request):
    if request.param == 'lxml':
        pytest.importorskip('lxml')
    else:
        request.getfixturevalue('no_sourceline')
    return request.param


def _links(analyzer):
    return [(link['url'], link['line']) for link in analyzer._extract_links()]


@pytest.mark.parametrize('newline', ['\n', '\r\n'], ids=['lf', 'crlf'])
def test_each_link_script_and_stylesheet_reports_its_own_line(tmp_path, parser_case, newline):
    analyzer = HTMLAnalyzer(str(_write(tmp_path, newline)))
    assert all(getattr(a, 'sourceline', None) is None for a in analyzer.soup.find_all('a'))
    assert _links(analyzer) == LINKS
    assert [(s['type'], s['line']) for s in analyzer._extract_scripts()] == SCRIPTS
    assert [(s['href'], s['line']) for s in analyzer._extract_styles()] == STYLES


def test_grep_output_names_each_link_line(tmp_path, no_sourceline):
    path = _write(tmp_path)
    result = _run_reveal_direct(str(path), '--links', '--format', 'grep')
    assert result.returncode == 0, result.stderr
    rows = [line for line in result.stdout.split('\n') if line.startswith(str(path))]
    assert [row[len(str(path)):] for row in rows] == [f':{line}:{url}' for url, line in LINKS]


def test_html_parser_sourceline_path_is_unchanged(tmp_path):
    """Negative control: with the stdlib builder bs4's own sourceline answers, as before."""
    analyzer = HTMLAnalyzer(str(_write(tmp_path)))
    if analyzer.soup.builder.NAME != 'html.parser':
        pytest.skip('lxml is installed; this control needs the stdlib builder')
    assert analyzer.soup.find('a').sourceline == 3
    assert _links(analyzer) == LINKS


def test_soup_that_disagrees_with_the_source_keeps_the_old_fallback(tmp_path, no_sourceline):
    """When the parsed tree holds a tag the source scan did not see, ordinal mapping is unsafe
    for that tag name; each element falls back to the id/class scan instead of a wrong line."""
    analyzer = HTMLAnalyzer(str(_write(tmp_path)))
    analyzer.soup.body.append(analyzer.soup.new_tag('a', href='made.html'))
    lines = dict((url, line) for url, line in _links(analyzer) if url in ('c.html', 'made.html'))
    assert lines['c.html'] == 12  # the id still locates it
    assert lines['made.html'] == 3  # first '<a' line: the documented fallback
