"""python:// is removed, not moved (BACK-2225, Scott 2026-10-25; REVEAL_PLAN D4).

Its one trace is the ``scheme:python`` row of the RETIREMENTS table (cli/invocation.py) at the
``error`` stage: every spelling of the scheme exits 2 with one line that says it was removed and
names the Python tools that answer the same questions, since no reveal scheme replaces it. The
sibling ``env://`` route is the negative control: it answers as before.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct

REMOVED = 'error: python:// was removed;'


def _error_lines(stderr):
    return [line for line in stderr.splitlines() if line.startswith('error:')]


@pytest.mark.parametrize('uri', ['python://', 'python://doctor', 'python://packages/pytest',
                                 'python://module/reveal', 'python://debug/bytecode', 'PYTHON://version'])
def test_every_python_uri_exits_2_with_one_removal_line(uri):
    result = _run_reveal_direct(uri)
    assert result.returncode == 2, result.stdout[:300]
    assert result.stdout == ''
    errors = _error_lines(result.stderr)
    assert len(errors) == 1 and errors[0].startswith(REMOVED), result.stderr
    assert 'no reveal scheme replaces it' in errors[0]


def test_json_format_is_also_refused_with_no_document():
    result = _run_reveal_direct('python://version', '--format', 'json')
    assert result.returncode == 2
    assert result.stdout == ''
    assert REMOVED in result.stderr


def test_health_refuses_a_python_target():
    result = _run_reveal_direct('health', 'python://')
    assert result.returncode == 2
    assert REMOVED in result.stderr


def test_the_mcp_tool_returns_the_removal_as_an_error():
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_query
    out = reveal_query('python://')
    assert 'python:// was removed' in out
    assert 'Python Environment' not in out


def _has_source(name):
    """True when *name* imports real code. A checkout that ran python:// before the removal keeps an
    ignored ``__pycache__``-only directory, which Python imports as an empty namespace package: that
    spec has no origin and no .py file, and is not the adapter."""
    spec = importlib.util.find_spec(name)
    if spec is None:
        return False
    if spec.origin is not None:
        return True
    return any(next(Path(loc).glob('*.py'), None) is not None
               for loc in (spec.submodule_search_locations or ()))


def test_the_adapter_package_and_renderer_are_gone():
    assert not _has_source('reveal.adapters.python')
    assert not _has_source('reveal.rendering.adapters.python')


def test_adapter_listings_do_not_name_python():
    listing = _run_reveal_direct('--adapters', '--format', 'json')
    assert listing.returncode == 0, listing.stderr
    adapters = json.loads(listing.stdout)['adapters']
    assert 'env' in adapters  # positive control: the listing is the scheme-keyed map
    assert 'python' not in adapters
    topic = _run_reveal_direct('help://adapters')
    assert topic.returncode == 0, topic.stderr
    assert 'python://' not in topic.stdout


def test_env_scheme_still_answers():
    """Negative control: the sibling runtime scheme on the same URI route is untouched."""
    result = _run_reveal_direct('env://PATH', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert 'python://' not in result.stderr
    assert json.loads(result.stdout)
