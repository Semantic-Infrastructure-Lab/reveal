"""Tests for reveal/adapters/ast/nav_surface_common.py shared helpers.

categorize_by_prefix (BACK-912) replaced 5 near-identical per-language
_categorize_module functions (kotlin, php, csharp, java, go) — this locks
down its prefix-match semantics independent of any one language's fixtures.
"""

from reveal.adapters.ast.nav_surface_common import categorize_by_prefix


def _taxonomy():
    return (
        (frozenset({'net/http', 'net/rpc'}), 'network'),
        (frozenset({'database/sql'}), 'db'),
    )


def _surfaces():
    return {'network': [], 'db': [], 'sdk': []}


def test_exact_match():
    surfaces = _surfaces()
    categorize_by_prefix('net/http', 'f.go', 1, surfaces, _taxonomy(), '/')
    assert surfaces['network'] == [
        {'type': 'import', 'name': 'net/http', 'file': 'f.go', 'line': 1}
    ]


def test_prefix_match_requires_separator():
    """A submodule import (`net/http/httptest`) matches; a same-prefix
    sibling with no separator (`net/httputil`) must not."""
    surfaces = _surfaces()
    categorize_by_prefix('net/http/httptest', 'f.go', 2, surfaces, _taxonomy(), '/')
    categorize_by_prefix('net/httputil', 'f.go', 3, surfaces, _taxonomy(), '/')
    assert len(surfaces['network']) == 1
    assert surfaces['network'][0]['name'] == 'net/http/httptest'


def test_no_match_is_a_noop():
    surfaces = _surfaces()
    categorize_by_prefix('fmt', 'f.go', 4, surfaces, _taxonomy(), '/')
    assert surfaces == _surfaces()


def test_first_matching_category_wins():
    """Taxonomy order matters — the first (group, category) pair a module
    matches is used, later groups are never consulted."""
    taxonomy = (
        (frozenset({'os'}), 'first'),
        (frozenset({'os'}), 'second'),
    )
    surfaces = {'first': [], 'second': []}
    categorize_by_prefix('os', 'f.py', 1, surfaces, taxonomy, '.')
    assert surfaces['first'] and not surfaces['second']


def test_separator_is_language_specific():
    """Same module string, different separators — dotted (Java/C#/Kotlin)
    vs. backslash (PHP) vs. slash (Go) taxonomies must not cross-match."""
    taxonomy = ((frozenset({'App'}), 'app'),)
    dotted = _surfaces() | {'app': []}
    categorize_by_prefix('App.Models', 'f.cs', 1, dotted, taxonomy, '.')
    assert dotted['app']

    backslash = _surfaces() | {'app': []}
    categorize_by_prefix('App.Models', 'f.php', 1, backslash, taxonomy, '\\')
    assert not backslash['app']  # '.' separator wouldn't match a '\\'-keyed taxonomy


def test_dedup_on_name_file_line():
    """categorize_by_prefix delegates to _add_once — a repeat entry with the
    same (name, file, line) must not be double-recorded."""
    surfaces = _surfaces()
    categorize_by_prefix('net/http', 'f.go', 1, surfaces, _taxonomy(), '/')
    categorize_by_prefix('net/http', 'f.go', 1, surfaces, _taxonomy(), '/')
    assert len(surfaces['network']) == 1
