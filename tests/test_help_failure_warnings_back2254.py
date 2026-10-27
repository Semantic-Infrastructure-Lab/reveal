"""BACK-2254: a plugin adapter whose get_help()/get_schema() raises is named in meta.warnings.

BACK-1614 made both failures log a warning instead of passing silently, but the log goes to
stderr only (reveal sets up no logging handlers), so ``--format json`` showed a guide without
its see_also, or a schema menu without the adapter, and nothing said why. The rest of the page
still renders; the warning says what is missing and which adapter's error caused it.
"""

import json
import logging

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.base import _ADAPTER_REGISTRY
from reveal.adapters.registry import get_adapter_class


class _BrokenSchemaAdapter:
    @staticmethod
    def get_help():
        return {'description': 'a plugin with a broken schema'}

    @staticmethod
    def get_schema():
        raise ValueError('schema malformed')


@pytest.fixture
def broken_schema_plugin(monkeypatch):
    monkeypatch.setitem(_ADAPTER_REGISTRY, 'brokenx', _BrokenSchemaAdapter)


@pytest.fixture
def broken_ast_help(monkeypatch):
    """A plugin registered over ast:// whose get_help() raises; help://ast is a static guide."""
    real = get_adapter_class('ast')

    class _BrokenHelpAst(real):  # type: ignore[misc, valid-type]
        @staticmethod
        def get_help():
            raise ValueError('help data malformed')

    monkeypatch.setitem(_ADAPTER_REGISTRY, 'ast', _BrokenHelpAst)


def _json(*args):
    run = _run_reveal_direct(*args, '--format', 'json')
    return run, json.loads(run.stdout)


def _warnings(result):
    return (result.get('meta') or {}).get('warnings') or []


def test_guide_json_names_the_failed_get_help(broken_ast_help, caplog):
    with caplog.at_level(logging.WARNING, logger='reveal.adapters.help'):
        run, result = _json('help://ast')
    assert run.returncode == 0
    assert result['type'] == 'static_guide' and result['content']  # the guide still renders
    assert 'see_also' not in result
    [warning] = [w for w in _warnings(result) if w.get('field') == 'see_also']
    assert warning['type'] == 'adapter_help_failed'
    assert warning['adapters'] == ['ast']
    assert 'ValueError: help data malformed' in warning['message']
    assert 'help://ast: see_also not shown' in caplog.text  # the log line stays


def test_schema_menu_json_names_the_failed_get_schema(broken_schema_plugin, caplog):
    with caplog.at_level(logging.WARNING, logger='reveal.adapters.help'):
        run, result = _json('help://schemas')
    assert run.returncode == 0
    assert result['type'] == 'adapter_schema_index'
    assert 'brokenx' not in result['available_adapters']
    assert 'ast' in result['available_adapters']  # the rest of the menu still renders
    [warning] = [w for w in _warnings(result) if w.get('field') == 'available_adapters']
    assert warning['type'] == 'adapter_help_failed'
    assert warning['adapters'] == ['brokenx']
    assert 'brokenx' in warning['message']
    assert 'ValueError: schema malformed' in warning['message']
    assert 'brokenx:// left out of the schema menu' in caplog.text


def test_unknown_adapter_did_you_mean_names_the_failed_get_schema(broken_schema_plugin):
    _run, result = _json('help://schemas/nosuchadapter')
    assert result['error'] == 'Unknown adapter'
    assert 'brokenx' not in result['available_adapters']
    [warning] = [w for w in _warnings(result) if w.get('field') == 'available_adapters']
    assert warning['adapters'] == ['brokenx']


def test_schema_menu_text_shows_the_warning(broken_schema_plugin):
    out = _run_reveal_direct('help://schemas').stdout
    assert 'brokenx' in out and 'ValueError: schema malformed' in out


def test_clean_menu_and_guide_carry_no_warning():
    """Negative control: nothing failed, nothing is said."""
    _run, menu = _json('help://schemas')
    _run, guide = _json('help://ast')
    assert not [w for w in _warnings(menu) if w.get('type') == 'adapter_help_failed']
    assert not [w for w in _warnings(guide) if w.get('type') == 'adapter_help_failed']
    assert guide.get('see_also')
