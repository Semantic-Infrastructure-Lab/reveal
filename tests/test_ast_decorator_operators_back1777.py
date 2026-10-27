"""ast://?decorator!= and decorator~= do what help://ast documents (BACK-1777).

`help://ast` lists `decorator!=property` and its schema declares `~=` for `decorator`, but
the matcher handled only `==` and globs: both returned no element at all. `!=` keeps the
elements none of whose attributes match (undecorated ones included); `~=` searches the
decorator's source text and each attribute's text and qualified name.
"""

import pytest

from reveal.adapters.ast.adapter import AstAdapter

SOURCE = {
    'k.py': '''\
class K:
    @property
    def prop(self): return 1
    @staticmethod
    def static(): pass
    def plain(self): pass
''',
    'C.cs': '''\
public class C
{
    [HttpGet, Authorize]
    public void Get() {}
    [HttpPost]
    public void Post() {}
}
''',
}


@pytest.fixture(scope='module')
def root(tmp_path_factory):
    directory = tmp_path_factory.mktemp('back1777ops')
    for name, text in SOURCE.items():
        (directory / name).write_text(text, encoding='utf-8')
    return directory


def _names(path, query) -> set:
    return {r['name'] for r in AstAdapter(str(path), query).get_structure()['results']}


def test_equal_is_the_sibling_control(root):
    # Passes on master: the positive operator already worked for at-style decorators.
    assert _names(root / 'k.py', 'decorator=property') == {'prop'}


def test_not_equal_keeps_elements_without_the_decorator(root):
    names = _names(root / 'k.py', 'decorator!=property&type=function')
    assert names == {'static', 'plain'}


def test_not_equal_reads_bracket_groups(root):
    assert _names(root / 'C.cs', 'decorator!=Authorize&type=function') == {'Post'}


def test_regex_searches_names(root):
    assert _names(root / 'k.py', 'decorator~=^static') == {'static'}
    assert _names(root / 'C.cs', 'decorator~=^Http(Get|Post)$') == {'Get', 'Post'}
    assert _names(root / 'C.cs', 'decorator~=^Auth') == {'Get'}
