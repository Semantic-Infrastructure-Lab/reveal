"""``reveal diff://env://:env:// PATH`` declines the pair, as ``reveal diff env:// env://`` does (BACK-2817).

The positional element joins the resource after a ``/`` (``declared.legacy_element_resource``, the
``target:diff.element`` row), but the join stripped every trailing ``/`` first, so a right side spelled ``env://`` lost
its own slashes: ``env://:env://`` and ``PATH`` became ``env://:env:/PATH``, which the pair parser reads as the left
``env://:env`` and the right ``/PATH``. The answer was "Element ':env' not found", exit 2, source ``/PATH``; before the
element became a join (D4) the request declined, exit 0. A path that ends in ``://`` now keeps it: the element follows
it (``env://:env:///PATH``), diff does not split a non-git URI side, and the pair declines with the row's note.

Shared owner: ``cli/routing/declared.py`` (``legacy_element_resource``). Effect on other nouns: only a noun with a
``target:NOUN.element`` row joins (diff, help, reveal), and help's and reveal's paths never end in ``://``.

The API's element form answered through its own ``get_element`` route, which raised NotApplicableError; since BACK-2813
it takes the CLI's join and returns the decline.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.cli.routing.declared import legacy_element_resource

pytestmark = [pytest.mark.component]

ROW = 'target:diff.element'


def _warnings(doc):
    return (doc.get('meta') or {}).get('warnings') or []


def _noted(doc):
    return [w.get('field') for w in _warnings(doc) if w.get('code') == 'retired_spelling']


def _declined(doc):
    assert doc['type'] == 'diff_comparison', doc
    assert doc['applicable'] is False and 'functions, classes and imports' in doc['reason'], doc
    assert 'not_applicable' in [w.get('code') for w in _warnings(doc)], doc


def _json(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run.returncode, (json.loads(run.stdout) if run.stdout.strip() else None), run.stderr


# --- the shared join (cli/routing/declared.py) ----------------------------------------------------------------------

def test_the_join_keeps_a_path_that_ends_in_a_scheme_separator():
    assert legacy_element_resource('diff', 'env://:env://', 'PATH') == 'env://:env:///PATH'


def test_the_join_still_drops_an_ordinary_trailing_slash():
    """Sibling: the joins the row already answered are unchanged."""
    assert legacy_element_resource('diff', 'dA:dB/', 'h') == 'dA:dB/h'
    assert legacy_element_resource('diff', 'a.py:b.py', 'ok') == 'a.py:b.py/ok'
    assert legacy_element_resource('help', '', 'quick') == 'quick'


# --- the transports ------------------------------------------------------------------------------------------------

def test_cli_positional_element_on_an_env_pair_declines_with_the_note():
    code, doc, stderr = _json('diff://env://:env://', 'PATH')
    assert code == 0, (stderr, doc)
    _declined(doc)
    assert _noted(doc) == [ROW], doc


def test_cli_env_pair_without_an_element_declines():
    """Sibling: the pair alone, and the element in the right side's own path, already declined."""
    for argv in (('diff', 'env://', 'env://'), ('diff://env://:env://PATH',)):
        code, doc, stderr = _json(*argv)
        assert code == 0, (argv, stderr)
        _declined(doc)


@pytest.mark.mcp
def test_mcp_positional_element_on_an_env_pair_declines():
    pytest.importorskip('mcp')
    from reveal.mcp_server import _ToolFailure, reveal_run
    shown = reveal_run(['diff://env://:env://', 'PATH', '--format', 'json'])
    assert not isinstance(shown, _ToolFailure), shown[:400]
    _declined(json.loads(shown))


def test_api_positional_element_on_an_env_pair_declines():
    doc = api.query('diff://env://:env://', 'PATH')
    _declined(doc)
    assert _noted(doc) == [ROW], doc
