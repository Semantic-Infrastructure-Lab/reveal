"""``diff://LEFT:RIGHT/ELEMENT`` answers the element when the right side is a ``git://`` URI (BACK-2768, pathread P5 B20).

The embedded element was split off plain file paths only: ``diff://git://m.py@HEAD~1:git://m.py@HEAD/ok`` read
``HEAD/ok`` as the ref and failed ("Cannot resolve ref: HEAD/ok", exit 1), so the positional ``reveal diff://A:B ok``
was the only element address for refs, and a note retiring it would have named a replacement that does not answer.
A ref may itself contain ``/`` (``feature/x``), so the split is decided against the repository: the trailing word is
an element only when the whole side does not name a file at its ref but the side without it does, as a plain path is
split only when it does not exist but its parent is a file.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from conftest import _run_reveal_direct  # noqa: E402

from reveal import api  # noqa: E402
from reveal.adapters.diff.parsing import split_trailing_element  # noqa: E402
from reveal.errors import RequestValidationError  # noqa: E402

pytestmark = [pytest.mark.component]

OLD = 'def ok():\n    return 1\n\n\nclass Box:\n    def size(self):\n        return 1\n'
NEW = 'def ok():\n    return 2\n\n\nclass Box:\n    def size(self):\n        return 2\n'

# (the element-in-URI form, the positional form it replaces): the modern path@REF side, the legacy REF/path side,
# a dotted method, a ref whose name has a slash, and a plain right side (the control: it already answered).
FORMS = {
    'path-at-ref': ('git://pkg/m.py@HEAD~1:git://pkg/m.py@HEAD/ok', 'ok'),
    'ref-slash-path': ('git://HEAD~1/pkg/m.py:git://HEAD/pkg/m.py/ok', 'ok'),
    'method': ('git://pkg/m.py@HEAD~1:git://pkg/m.py@HEAD/Box.size', 'Box.size'),
    'ref-with-slash': ('git://pkg/m.py@feature/old:git://pkg/m.py@feature/new/ok', 'ok'),
    'plain-right-side': ('git://pkg/m.py@HEAD~1:pkg/m.py/ok', 'ok'),
}


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Two commits of pkg/m.py (both bodies change), branches ``feature/old`` and ``feature/new`` on them."""
    pygit2 = pytest.importorskip('pygit2')
    root = tmp_path / 'repo'
    (root / 'pkg').mkdir(parents=True)
    git = pygit2.init_repository(str(root))
    sig = pygit2.Signature('fixture', 'fixture@example.invalid')
    parents = []
    for text in (OLD, NEW):
        (root / 'pkg' / 'm.py').write_text(text, encoding='utf-8')
        git.index.add('pkg/m.py')
        git.index.write()
        parents = [git.create_commit('HEAD', sig, sig, 'fixture', git.index.write_tree(), parents)]
        git.branches.local.create('feature/old' if text is OLD else 'feature/new', git[parents[0]])
    monkeypatch.chdir(root)
    return root


def _element_facts(doc):
    return doc['type'], doc['name'], doc['change'], sorted(doc.get('changes') or {})


def _json(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    assert run.returncode == 0, (argv, run.returncode, run.stderr[-600:])
    return json.loads(run.stdout)


@pytest.mark.parametrize('form', sorted(FORMS))
def test_cli_embedded_element_on_a_git_side_answers_the_element(repo, form):
    embedded, element = FORMS[form]
    positional = _json(f'diff://{embedded.rpartition("/")[0]}', element)
    answer = _json(f'diff://{embedded}')
    assert _element_facts(answer) == _element_facts(positional), (answer.get('error'), positional.get('error'))
    assert _element_facts(answer)[:3] == ('diff_element', element, 'modified')


@pytest.mark.parametrize('form', sorted(FORMS))
def test_api_embedded_element_on_a_git_side_answers_the_element(repo, form):
    embedded, element = FORMS[form]
    answer = api.query(f'diff://{embedded}')
    assert _element_facts(answer)[:3] == ('diff_element', element, 'modified'), answer.get('error')


def test_mcp_embedded_element_on_a_git_side_answers_the_element(repo):
    from reveal.mcp_server import reveal_query, _ToolFailure
    answer = reveal_query(f"diff://{FORMS['path-at-ref'][0]}")
    assert not isinstance(answer, _ToolFailure), str(answer)[:400]
    assert 'Element Diff: ok' in str(answer), str(answer)[:400]


def test_api_missing_element_on_a_git_side_is_an_invalid_request(repo):
    with pytest.raises(RequestValidationError):
        api.query('diff://git://pkg/m.py@HEAD~1:git://pkg/m.py@HEAD/nosuch')


# --- controls: a side that names a file, a directory or a ref with a slash is never split --------------------------

@pytest.mark.parametrize('uri', ['git://pkg/m.py@HEAD~1:git://pkg/m.py@HEAD', 'git://HEAD~1/pkg/m.py:git://HEAD/pkg/m.py',
                                 'git://pkg/m.py@feature/old:git://pkg/m.py@feature/new'])
def test_whole_git_sides_still_compare(repo, uri):
    assert _json(f'diff://{uri}')['type'] == 'diff_comparison'
    assert api.query(f'diff://{uri}')['type'] == 'diff_comparison'


@pytest.mark.parametrize('right,expected', [
    ('git://pkg/m.py@HEAD/ok', ('git://pkg/m.py@HEAD', 'ok')),
    ('git://HEAD/pkg/m.py/Box.size', ('git://HEAD/pkg/m.py', 'Box.size')),
    ('git://pkg/m.py@feature/new/ok', ('git://pkg/m.py@feature/new', 'ok')),
    ('git://pkg/m.py@feature/new', ('git://pkg/m.py@feature/new', None)),   # the whole ref resolves
    ('git://HEAD/pkg/m.py', ('git://HEAD/pkg/m.py', None)),
    ('git://HEAD/pkg/ok', ('git://HEAD/pkg/ok', None)),                     # parent is a directory, not a file
    ('git://pkg/m.py@HEAD/not-a-name', ('git://pkg/m.py@HEAD/not-a-name', None)),
])
def test_split_is_decided_against_the_repository(repo, right, expected):
    assert split_trailing_element(right, 'git://pkg/m.py@HEAD~1') == expected  # a file left
