"""BACK-2139: I007's project import scan is not kept across host requests after a transient failure.

``_dep_reconciliation._scan_cache`` keeps a project's scan while its tree is unchanged. A file
whose extraction failed in reveal's machinery (the analyzer lookup raised, BACK-2136) is
recorded in ``ProjectImports.skipped``, the scan's own disclosure channel, but the entry was
kept like any other: the file's mtime and size did not change when the failure went away, so
request after request on the unchanged tree reported the file as unread, and a dependency only
that file imports as unused. A syntax error of unchanged content is the same every time and
stays cached.
"""

import os
import time
from pathlib import Path

import pytest

from reveal import mcp_server
from reveal.analyzers.imports import base as imports_base
from reveal.rules.imports import _dep_reconciliation as dep
from reveal.utils import request_cache

pytestmark = pytest.mark.integration


def _write(path, text):
    path.write_text(text, encoding='utf-8')
    aged = time.time_ns() - 60_000_000_000
    os.utime(path, ns=(aged, aged))
    return path


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    root = tmp_path / 'proj'
    root.mkdir()
    _write(root / 'pyproject.toml', '[project]\nname="p"\ndependencies=["requests", "orjson"]\n')
    _write(root / 'uses_orjson.py', 'import orjson\n')
    _write(root / 'uses_requests.py', 'import requests\n')
    request_cache._STAMPS.clear()
    dep._scan_cache.clear()
    yield root.resolve()
    dep._scan_cache.clear()


@pytest.fixture
def lookup_fails_once(monkeypatch):
    """The imports extractor's analyzer lookup raises for the armed file once, then works."""
    armed, fired = set(), []
    real = imports_base.get_analyzer

    def get_analyzer_once(path, *args, **kwargs):
        resolved = Path(str(path)).resolve()
        if resolved in armed:
            armed.discard(resolved)
            fired.append(resolved.name)
            raise RuntimeError('analyzer registry unavailable')
        return real(path, *args, **kwargs)

    monkeypatch.setattr(imports_base, 'get_analyzer', get_analyzer_once)
    return armed, fired


def _check(root):
    return mcp_server.reveal_check(str(root / 'pyproject.toml'), select='I007')


def test_a_transient_scan_failure_is_not_kept_for_the_next_host_request(project, lookup_fails_once):
    armed, fired = lookup_fails_once
    armed.add(project / 'uses_requests.py')
    first = _check(project)
    assert fired == ['uses_requests.py'], 'fixture: the failure should hit the scan once'
    assert 'requests' in first, f'the request that hit the failure should report the dependency it could not see: {first}'
    second = _check(project)
    assert 'requests' not in second and 'orjson' not in second, (
        f'request 2 was answered from the scan built while the lookup failed: {second}')


def test_a_syntax_error_scan_is_still_kept(project):
    """Negative control: the same bytes fail the same way, so a recovered parse stays cached."""
    _write(project / 'uses_requests.py', 'import requests\nx = (\n')
    first = _check(project)
    entry = dep._scan_cache[project]
    kept = next(iter(entry.values()))
    assert kept.imports.skipped, f'fixture: the broken file should be a skipped file: {first}'
    _check(project)
    assert dep._scan_cache.get(project) and next(iter(dep._scan_cache[project].values())) is kept, (
        'a scan of unchanged content should still be reused')
