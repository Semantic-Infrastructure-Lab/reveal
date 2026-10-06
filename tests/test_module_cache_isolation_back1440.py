"""The autouse ``_reset_module_caches`` fixture empties module-level caches between tests (BACK-1440)."""
import importlib

import pytest

from tests.conftest import _MODULE_CACHES, _clear_module_caches

pytestmark = pytest.mark.component


def test_every_listed_cache_exists_and_is_clearable():
    """A rename would otherwise drop the cache from the sweep (or break every test)."""
    for mod_name, attr in _MODULE_CACHES:
        cache = getattr(importlib.import_module(mod_name), attr)
        assert hasattr(cache, 'cache_clear') or hasattr(cache, 'clear'), (mod_name, attr)


def test_leak_seed_populates_i002_graph_cache():
    """First half of a cross-test pair: leaves an entry behind on purpose."""
    from reveal.rules.imports import I002
    I002._graph_cache[object()] = object()  # type: ignore[index]
    assert I002._graph_cache


def test_leak_seed_is_gone_in_the_next_test():
    """Negative control: with the fixture removed this fails when run after the seed test
    in the same process (``-n0``; xdist keeps a file's tests in order on one worker)."""
    from reveal.rules.imports import I002
    assert not I002._graph_cache


def test_clear_covers_dict_and_lru_caches():
    from reveal.analyzers.imports import python as py_imports
    from reveal.rules.maintainability import M102
    M102._import_cache['x'] = {'y'}  # type: ignore[index]
    py_imports._python_project_inventory.cache_info()
    _clear_module_caches()
    assert not M102._import_cache
    assert py_imports._python_project_inventory.cache_info().currsize == 0
