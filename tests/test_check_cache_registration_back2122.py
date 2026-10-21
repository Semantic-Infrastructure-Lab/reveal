"""scripts/check_cache_registration.py: every cache has an owner class (BACK-2122).

The real manifest is checked against the real tree, then each rule is shown to fire on a small
synthetic input (a negative control for every guard), and a runtime guard runs two MCP checks
(markdown and JavaScript) across threads, which panics on the language-pack 1.8.1 floor when a
process-wide cache hands one thread's tree-sitter nodes to another.
"""
import copy
import functools
import importlib.util
import json
import threading
from pathlib import Path

import pytest

from reveal import mcp_server

_SCRIPT = Path(__file__).resolve().parent.parent / 'scripts' / 'check_cache_registration.py'
_SPEC = importlib.util.spec_from_file_location('check_cache_registration', _SCRIPT)
ccr = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ccr)


@functools.lru_cache(maxsize=None)
def _real_scan():
    return ccr.scan()


def _sites(source, rel='reveal/m.py', wrappers=None):
    return {ident: site.kind for ident, site in ccr.find_sites(source, rel, wrappers).items()}


def _scan(**overrides):
    base = dict(sites={}, file_of={}, aliases={}, tree_sitter_modules=set(), requests=set(), validated={})
    base.update(overrides)
    return ccr.Scan(**base)


def _site(ident, kind='container', module='reveal/m.py'):
    return _scan(sites={ident: ccr.Site(kind, 1)}, file_of={ident: module})


# --- the real tree --------------------------------------------------------------------------

def test_the_manifest_matches_the_tree():
    manifest = json.loads(ccr.MANIFEST.read_text(encoding='utf-8'))
    conftest = Path(__file__).resolve().parent / 'conftest.py'
    module_caches = ccr.conftest_module_caches(conftest.read_text(encoding='utf-8'))
    assert module_caches, 'the conftest scan found no _MODULE_CACHES pairs'
    assert ccr.check(manifest, _real_scan(), module_caches) == []


def test_every_conftest_module_cache_is_a_site_the_scan_finds():
    """Positive control for the conftest cross-check: its ids are real scan ids (or aliases)."""
    found = _real_scan()
    conftest = Path(__file__).resolve().parent / 'conftest.py'
    for ident in ccr.conftest_module_caches(conftest.read_text(encoding='utf-8')):
        assert found.aliases.get(ident, ident) in found.sites, ident


# --- what the scan finds --------------------------------------------------------------------

@pytest.mark.parametrize('source,expected', [
    ("_c = {}\ndef f(k):\n    _c[k] = 1\n", {'reveal/m.py::_c': 'container'}),
    ("_seen = set()\ndef f(k):\n    _seen.add(k)\n", {'reveal/m.py::_seen': 'container'}),
    ("_memo = {}\n", {'reveal/m.py::_memo': 'container'}),  # named like a cache, filled elsewhere
    ("from collections import OrderedDict\n_c = OrderedDict()\ndef f(k):\n    _c.move_to_end(k)\n",
     {'reveal/m.py::_c': 'container'}),
    ("class A:\n    _c: dict = {}\n    @classmethod\n    def put(cls, k):\n        cls._c[k] = 1\n",
     {'reveal/m.py::A._c': 'container'}),
    ("class A:\n    def __init__(self):\n        self._node_cache = {}\n",
     {'reveal/m.py::A._node_cache': 'instance'}),
    ("import functools\n@functools.lru_cache(maxsize=4)\ndef f(x):\n    return x\n",
     {'reveal/m.py::f': 'lru'}),
    ("from functools import cache\n@cache\ndef f(x):\n    return x\n", {'reveal/m.py::f': 'lru'}),
    ("import functools\nclass A:\n    @functools.lru_cache(maxsize=None)\n    def m(self, x):\n        return x\n",
     {'reveal/m.py::A.m': 'lru'}),
    ("import functools\ng = functools.lru_cache(maxsize=2)(len)\n", {'reveal/m.py::g': 'lru'}),
    ("import threading\n_t = threading.local()\n", {'reveal/m.py::_t': 'thread-local'}),
    ("_n = ImportsDiskCache('ns_a')\n", {'disk:ns_a': 'disk'}),
    ("_X_NAMESPACE = 'ns_b'\n", {'disk:ns_b': 'disk'}),
    ("from reveal.core import disk_cache\ndef f():\n    return disk_cache.get('ns_c', 'k')\n",
     {'disk:ns_c': 'disk'}),
    ("_N = 'ns_d'\ndef f():\n    disk_cache.put(_N, 'k', 1)\n", {'disk:ns_d': 'disk'}),
])
def test_scan_finds_the_cache_shapes(source, expected):
    assert _sites(source) == expected


@pytest.mark.parametrize('source', [
    "TABLE = {}\n",                                      # empty, never filled, not named like a cache
    "NAMES = ['a', 'b']\n_c = {'a': 1}\n",               # filled literals are constants
    "def f():\n    _c = {}\n    _c['k'] = 1\n    return _c\n",   # a local
    "class A:\n    patterns = []\n",                     # class attribute nobody fills
    "def f(x):\n    return x\n",
    "x = 3\n",
])
def test_scan_ignores_what_is_not_a_cache(source):
    assert _sites(source) == {}


def test_scan_finds_a_cache_wrapper_instance_by_its_class():
    source = ("class Pair:\n    cache_clear = staticmethod(print)\n"
              "class Memo:\n    def __init__(self):\n        self._local = threading.local()\n"
              "    def cache_clear(self):\n        pass\n")
    wrappers = ccr.find_wrappers(source)
    assert wrappers == {'Pair': 'lru', 'Memo': 'thread-local'}
    assert _sites("a = Pair()\nb = Memo(3)\nc = Other()\n", wrappers=wrappers) == {
        'reveal/m.py::a': 'lru', 'reveal/m.py::b': 'thread-local'}


# --- what the check enforces ----------------------------------------------------------------

def _manifest(entries, ceiling=None):
    exempt = sum(1 for e in entries.values() if e['owner'] == 'process-exempt')
    return {'exempt_ceiling': exempt if ceiling is None else ceiling, 'caches': entries}


def _problems(entries, found, ceiling=None, module_caches=()):
    return ccr.check(_manifest(entries, ceiling), found, list(module_caches))


M = 'reveal/m.py::_c'


def test_a_cache_the_manifest_does_not_list_fails():
    problems = _problems({}, _site(M))
    assert len(problems) == 1 and problems[0].startswith(f'unlisted container cache {M}')


def test_a_manifest_entry_without_a_cache_fails():
    problems = _problems({M: {'owner': 'pure'}}, _scan())
    assert problems == [f'stale manifest entry {M}: no cache site matches it any more; delete it']


def test_an_unknown_owner_fails():
    assert 'is not one of' in _problems({M: {'owner': 'sometimes'}}, _site(M))[0]


def test_process_exempt_needs_a_reason():
    assert _problems({M: {'owner': 'process-exempt'}}, _site(M)) == [f'{M}: process-exempt needs a "reason"']
    assert _problems({M: {'owner': 'process-exempt', 'reason': 'why'}}, _site(M)) == []


def test_the_exempt_count_may_only_fall():
    entries = {M: {'owner': 'process-exempt', 'reason': 'why'}}
    assert 'the count may only fall' in _problems(entries, _site(M), ceiling=0)[0]
    assert 'lower "exempt_ceiling" to 1' in _problems(entries, _site(M), ceiling=2)[0]


def test_thread_local_owns_exactly_the_thread_local_sites():
    assert 'cannot have owner thread-local' in _problems({M: {'owner': 'thread-local'}}, _site(M))[0]
    tl = _site(M, kind='thread-local')
    assert 'cannot have owner pure' in _problems({M: {'owner': 'pure'}}, tl)[0]
    assert _problems({M: {'owner': 'thread-local'}}, tl) == []


def test_disk_owns_exactly_the_namespaces():
    ident = 'disk:ns'
    assert _problems({ident: {'owner': 'disk'}}, _site(ident, kind='disk')) == []
    assert 'cannot have owner disk' in _problems({M: {'owner': 'disk'}}, _site(M))[0]
    assert 'cannot have owner pure' in _problems({ident: {'owner': 'pure'}}, _site(ident, kind='disk'))[0]


def test_pure_is_only_for_lru_sites():
    assert 'only an lru_cache' in _problems({M: {'owner': 'pure'}}, _site(M))[0]
    assert _problems({M: {'owner': 'pure'}}, _site(M, kind='lru')) == []


def test_request_needs_a_registration_in_the_module():
    assert 'never calls register_request_cache' in _problems({M: {'owner': 'request'}}, _site(M))[0]
    here = _scan(sites={M: ccr.Site('container', 1)}, file_of={M: 'reveal/m.py'}, requests={'reveal/m.py'})
    assert _problems({M: {'owner': 'request'}}, here) == []
    elsewhere = {M: {'owner': 'request', 'registered_in': 'reveal/other.py'}}
    found = _scan(sites={M: ccr.Site('container', 1)}, file_of={M: 'reveal/m.py'}, requests={'reveal/other.py'})
    assert _problems(elsewhere, found) == []


def test_validated_needs_the_cache_passed_to_register_validated_cache():
    found = _scan(sites={M: ccr.Site('container', 1)}, file_of={M: 'reveal/m.py'},
                  validated={'reveal/m.py': {'_other'}})
    assert 'never passes _c to register_validated_cache' in _problems({M: {'owner': 'validated'}}, found)[0]
    found = _scan(sites={M: ccr.Site('container', 1)}, file_of={M: 'reveal/m.py'},
                  validated={'reveal/m.py': {'_c'}})
    assert _problems({M: {'owner': 'validated'}}, found) == []


def test_a_cache_in_a_tree_sitter_module_must_say_what_it_holds():
    found = _scan(sites={M: ccr.Site('container', 1)}, file_of={M: 'reveal/m.py'},
                  tree_sitter_modules={'reveal/m.py'}, requests={'reveal/m.py'})
    assert 'touches tree-sitter' in _problems({M: {'owner': 'request'}}, found)[0]
    assert _problems({M: {'owner': 'request', 'holds': 'plain'}}, found) == []
    # a thread-local owner needs no statement
    tl = _scan(sites={M: ccr.Site('thread-local', 1)}, file_of={M: 'reveal/m.py'},
               tree_sitter_modules={'reveal/m.py'})
    assert _problems({M: {'owner': 'thread-local'}}, tl) == []


def test_a_cache_that_holds_tree_sitter_values_must_be_thread_local():
    entry = {'owner': 'process-exempt', 'reason': 'why', 'holds': 'tree-sitter'}
    problems = _problems({M: entry}, _site(M))
    assert 'must be thread-local' in problems[0]
    assert _problems({M: {'owner': 'thread-local', 'holds': 'tree-sitter'}}, _site(M, kind='thread-local')) == []
    # one instance that a call builds may hold nodes
    assert _problems({M: entry}, _site(M, kind='instance')) == []


def test_a_conftest_module_cache_the_manifest_lacks_fails():
    problems = _problems({}, _scan(), module_caches=['reveal/x.py::_y'])
    assert problems == ['tests/conftest.py _MODULE_CACHES lists reveal/x.py::_y, which the manifest does not']
    found = _scan(aliases={'reveal/x.py::_y': 'disk:ns'})
    assert _problems({'disk:ns': {'owner': 'disk'}}, _scan(
        sites={'disk:ns': ccr.Site('disk', 1)}, file_of={'disk:ns': 'reveal/x.py'}, aliases=found.aliases),
        module_caches=['reveal/x.py::_y']) == []


def test_the_real_manifest_fails_when_one_entry_is_removed_or_misowned():
    """Mutations of the real manifest: each is caught."""
    manifest = json.loads(ccr.MANIFEST.read_text(encoding='utf-8'))
    found = _real_scan()
    gone = copy.deepcopy(manifest)
    del gone['caches']['reveal/utils/gitignore.py::_REPO_CACHE']
    assert any('unlisted' in p and '_REPO_CACHE' in p for p in ccr.check(gone, found, []))
    wrong = copy.deepcopy(manifest)
    wrong['caches']['reveal/core/treesitter_parse.py::_parse_recent']['owner'] = 'pure'
    assert any('_parse_recent' in p for p in ccr.check(wrong, found, []))
    ts = copy.deepcopy(manifest)
    ts['caches']['reveal/treesitter.py::_parse_cache_local']['owner'] = 'process-exempt'
    assert any('_parse_cache_local' in p for p in ccr.check(ts, found, []))


# --- the runtime guard ----------------------------------------------------------------------

_MD = '# T\n\nSee [a](missing.md) and `code` and [b](#nope).\n'
_JS = ('function f(a) {\n  try { g(a); } catch (e) {}\n'
       '  if (a) { if (a > 1) { if (a > 2) { return 1; } } }\n  return 0;\n}\n')


def _on_new_thread(fn):
    box = {}

    def run():
        try:
            box['result'] = fn()
        except BaseException as e:  # noqa: BLE001 - PanicException derives from BaseException
            box['error'] = e

    worker = threading.Thread(target=run)
    worker.start()
    worker.join()
    return box.get('result'), box.get('error')


@pytest.mark.mcp
def test_mcp_checks_of_a_markdown_and_a_javascript_file_alternate_across_threads(tmp_path):
    """Each call lands on a new thread, as anyio dispatches; no cache may hand a tree across."""
    doc, src = tmp_path / 'doc.md', tmp_path / 'app.js'
    doc.write_text(_MD, encoding='utf-8')
    src.write_text(_JS, encoding='utf-8')
    answers = {}
    for round_number in range(2):
        for path, marker in ((doc, 'L001'), (src, 'B006')):
            result, error = _on_new_thread(lambda p=path: mcp_server.reveal_check(str(p)))
            assert error is None, f'{path.name} round {round_number}: {type(error).__name__}: {error}'
            assert marker in result, result  # positive control: the rule that needs a tree ran
            assert answers.setdefault(path.name, result) == result
