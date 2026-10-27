"""ast:// filter keys that repeat AND together (BACK-2307).

``parse_query`` folded the shared parser's list of conditions into a dict keyed by field,
so a second condition on the same key replaced the first: ``type!=method&type=function``
returned methods and ``lines>3&lines<8`` dropped ``lines>3``. Every ast filter key went
through that dict, so every key had the bug. markdown:// and json:// filter the shared
parser's list directly and already ANDed a repeated key; they are the controls. git://
does not (its query is a dict before it reaches the parser): a strict xfail records that.
"""
import os
import subprocess

import pytest

from reveal.adapters.ast.adapter import AstAdapter
from reveal.adapters.ast.queries import format_query, parse_query

SOURCE = '''import os


def free_fn():
    return 1


def big_free(x):
    a = 1
    b = 2
    c = 3
    return a + b + c + x


def branchy(x):
    if x:
        return 1
    if x > 2:
        return 2
    return 3


class K:
    def meth(self):
        return free_fn()

    @property
    def prop(self):
        return 3

    @staticmethod
    @property
    def both():
        return 4
'''


@pytest.fixture
def tree(tmp_path):
    (tmp_path / 'm.py').write_text(SOURCE, encoding='utf-8')
    return tmp_path


def _names(tree, query):
    return sorted(r['name'] for r in AstAdapter(str(tree), query).get_structure()['results'])


@pytest.mark.parametrize('query', ['type!=method&type=function', 'type=function&type!=method'])
def test_type_not_method_and_type_function_is_free_functions_only(tree, query):
    assert _names(tree, query) == ['big_free', 'branchy', 'free_fn']


def test_name_glob_and_name_not_equal(tree):
    # name=*f* alone also matches big_free and free_fn; the second condition drops free_fn.
    assert _names(tree, 'name=*free*&name!=free_fn') == ['big_free']


def test_lines_lower_and_upper_bound(tree):
    # line_count: free_fn 2, meth 2, prop 3, both 4, big_free 5, branchy 6, K 12.
    assert _names(tree, 'lines>4&lines<8') == ['big_free', 'branchy']


def test_complexity_repeated(tree):
    assert _names(tree, 'type=function&complexity>1&complexity<10') == ['branchy']


@pytest.mark.parametrize('query', ['decorator=staticmethod&decorator=property',
                                   'decorator=property&decorator=staticmethod'])
def test_decorator_repeated(tree, query):
    assert _names(tree, query) == ['both']


def test_three_conditions_on_one_key(tree):
    assert _names(tree, 'type=function&name=*f*&name!=free_fn&name!=branchy') == ['big_free']


def test_single_condition_shape_is_unchanged():
    """Negative control: a key given once keeps the dict shape every reader expects."""
    assert parse_query('type=function&lines>3') == {
        'type': {'op': '==', 'value': 'function'},
        'lines': {'op': '>', 'value': 3},
    }


def test_format_query_lists_every_condition():
    assert format_query(parse_query('type!=method&type=function')) == 'type!=method AND type==function'


def test_outline_eligible_query_unchanged(tree):
    """Negative control: name/type queries the outline answers still agree with a full scan."""
    assert _names(tree, 'type=function&name=meth') == ['meth']
    assert _names(tree, 'name=*free*') == ['big_free', 'free_fn']


# --- sibling adapters filter parse_query_filters' list --------------------------------

def test_markdown_repeated_key_control(tmp_path):
    from reveal.adapters.markdown import MarkdownQueryAdapter
    for name, n in (('a.md', 1), ('b.md', 5), ('c.md', 9)):
        (tmp_path / name).write_text(f'---\nn: {n}\n---\n# T\n', encoding='utf-8')
    results = MarkdownQueryAdapter(str(tmp_path), 'n>2&n<8').get_structure()['results']
    assert [os.path.basename(r['path']) for r in results] == ['b.md']


def test_json_repeated_key_control(tmp_path):
    from reveal.adapters.json.adapter import JsonAdapter
    (tmp_path / 'j.json').write_text('[{"n": 1}, {"n": 5}, {"n": 9}]', encoding='utf-8')
    assert JsonAdapter(str(tmp_path / 'j.json'), 'n>2&n<8').get_structure()['value'] == [{'n': 5}]


@pytest.mark.xfail(strict=True, reason=(
    'BACK-2307 finding: git:// reads its query through parse_query_params, a dict, so a '
    'repeated message~= keeps only the last; git:// filters belong to another lane'))
def test_git_repeated_key_control(tmp_path):
    from reveal.adapters.git.adapter import GitAdapter

    def git(*args):
        subprocess.run(['git', *args], cwd=tmp_path, check=True, capture_output=True, timeout=30)
    git('init', '-q', '.')
    for i, msg in enumerate(('feat: one', 'feat: fix two', 'chore: fix three')):
        (tmp_path / f'f{i}').write_text(str(i), encoding='utf-8')
        git('add', f'f{i}')
        git('-c', 'user.name=A', '-c', 'user.email=a@example.com', 'commit', '-q', '-m', msg)
    history = GitAdapter(f'{tmp_path}?type=log&message~=feat&message~=fix').get_structure()['history']
    assert [c['message'] for c in history] == ['feat: fix two']
