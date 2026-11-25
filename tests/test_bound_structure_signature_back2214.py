"""A noun that binds its controls at construction takes no keywords in its structure call (BACK-2214).

Every core noun binds its query controls in its constructor (``factory.uses_bound_query_call``), and every route
calls its ``get_structure()`` with no arguments. A ``**kwargs`` left on that method swallowed a direct keyword
silently, and diff handed its API keywords on to each side's structure call, which crashed on a side that takes none.
"""
import inspect
import json
import subprocess

import pytest

from reveal import api
from reveal.adapters.base import get_adapter_class
from reveal.adapters.factory import _canonical_init, uses_bound_query_call
from reveal.adapters.registry import BUILTIN_SCHEMES
from reveal.errors import NotApplicableError, UnsupportedOverrideError

BOUND_SCHEMES = [scheme for scheme in BUILTIN_SCHEMES if uses_bound_query_call(get_adapter_class(scheme))]

# Still counted by the boundary ratchet until they go: classify and depends are retired (deleted at the cut), domain
# and mysql leave core with the ops family (D4/D13), demo is the scaffold example and the ratchet's positive control.
EXCLUDED_SITES = {
    'reveal/adapters/classify.py', 'reveal/adapters/demo.py', 'reveal/adapters/depends.py',
    'reveal/adapters/domain/adapter.py', 'reveal/adapters/mysql/adapter.py',
}


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / 'a.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'b.py').write_text('def f():\n    return 2\n\n\ndef g():\n    pass\n', encoding='utf-8')
    (tmp_path / 'd.json').write_text(json.dumps({'k': [1, 2, 3]}), encoding='utf-8')
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs' / 'x.md').write_text('---\ntitle: X\n---\n# X\n', encoding='utf-8')
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'test_a.py').write_text(
        'from unittest import mock\n\n\n@mock.patch("a.f")\ndef test_x(m):\n    pass\n', encoding='utf-8')
    git = ['git', '-c', 'user.email=t@example.com', '-c', 'user.name=t', '-c', 'commit.gpgsign=false']
    subprocess.run(git + ['init', '-q', '.'], cwd=tmp_path, check=True, timeout=30)
    subprocess.run(git + ['add', '.'], cwd=tmp_path, check=True, timeout=30)
    subprocess.run(git + ['commit', '-qm', 'init'], cwd=tmp_path, check=True, timeout=30)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _components(root, count=7):
    for number in range(count):
        folder = root / f'part{number}'
        folder.mkdir()
        (folder / 'value.py').write_text('VALUE=1\n', encoding='utf-8')


@pytest.mark.parametrize('scheme', BOUND_SCHEMES)
def test_every_bound_noun_takes_no_structure_keywords(scheme):
    # The AST ratchet counts only a bare (self, **kwargs); this sees named and inherited parameters too
    # (ast's structures, overview's and architecture's all).
    cls = get_adapter_class(scheme)
    assert list(inspect.signature(cls.get_structure).parameters) == ['self'], cls.__qualname__


@pytest.mark.parametrize('scheme,resource', [
    ('ast', 'a.py'), ('deps', '.'), ('diff', 'a.py:b.py'), ('git', '.'), ('help', ''), ('json', 'd.json'),
    ('markdown', 'docs'), ('overview', '.'), ('architecture', '.'), ('patches', 'tests'), ('reveal', ''),
    # already (self): the siblings this must not change
    ('env', ''), ('surface', '.'),
])
def test_a_direct_structure_keyword_is_refused(project, scheme, resource):
    adapter = _canonical_init(get_adapter_class(scheme), resource)
    with pytest.raises(TypeError, match="unexpected keyword argument 'bogus'"):
        adapter.get_structure(bogus=1)


def test_diff_does_not_hand_its_keywords_to_a_side():
    # A side that takes no keyword crashed with a raw TypeError; it declines as it does without the keyword.
    with pytest.raises(NotApplicableError):
        api.query('diff://env://:env://', 'PATH')
    with pytest.raises(NotApplicableError):
        api.query('diff://env://:env://', 'PATH', exclude='x')


def test_diff_element_answers_with_an_api_keyword(project):
    plain = api.query('diff://a.py:b.py', 'f')
    assert api.query('diff://a.py:b.py', 'f', exclude='zz')['name'] == plain['name'] == 'f'


@pytest.mark.parametrize('scheme', ['overview', 'architecture'])
def test_all_is_a_constructor_control(tmp_path, scheme):
    _components(tmp_path)
    cls = get_adapter_class(scheme)
    assert cls(str(tmp_path)).get_structure()['map']['components']['returned'] == 5
    assert cls(str(tmp_path), params={'all': True}).get_structure()['map']['components']['returned'] == 7
    with pytest.raises(TypeError, match="unexpected keyword argument 'all'"):
        cls(str(tmp_path)).get_structure(all=True)


def test_ast_takes_no_precollected_structures(project):
    adapter = _canonical_init(get_adapter_class('ast'), 'a.py')
    assert adapter.get_structure()['total_files'] == 1
    with pytest.raises(TypeError, match="unexpected keyword argument 'structures'"):
        adapter.get_structure(structures=[])


@pytest.mark.parametrize('uri', [
    'ast://a.py', 'deps://.', 'diff://a.py:b.py', 'git://.', 'help://', 'json://d.json', 'markdown://docs',
    'overview://.', 'patches://tests', 'reveal://', 'env://',
])
def test_an_unknown_api_keyword_stays_refused(project, uri):
    # Already true before the signature cleanup: the binding refuses before any structure call.
    with pytest.raises(UnsupportedOverrideError):
        api.query(uri, bogus_kw=1)


def _counted_files():
    from scripts.check_boundaries import ROOT, find_sites
    counted = set()
    for path in sorted((ROOT / 'reveal/adapters').rglob('*.py')):
        rel = path.relative_to(ROOT).as_posix()
        if find_sites(path.read_text(encoding='utf-8'), rel)['bare-get-structure-kwargs']:
            counted.add(rel)
    return counted


def test_no_bound_noun_is_a_counted_site():
    assert _counted_files() == EXCLUDED_SITES


def test_the_baseline_counts_only_the_excluded_owners():
    from scripts.check_boundaries import BASELINE
    baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
    assert set(baseline['bare-get-structure-kwargs']) == EXCLUDED_SITES
