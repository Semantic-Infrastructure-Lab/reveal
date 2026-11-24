"""A typed ``None`` selects the default on every declared noun that takes ``limit`` or ``offset`` (BACK-2779, D21).

``api.query``'s documented rule: a keyword given ``None`` is the default, as if it were not given. On the URI form,
``api.query('metrics://P', limit=None)`` raised ``ValueError: limit must be a non-negative integer: 'None'`` while
``ast://``, ``markdown://`` and the noun form answered as without it: the shared binder wrote the typed ``None`` as a
present key holding the declaration's default, and Metrics renders every present key into its control query as text.
One meaning per keyword across nouns (D21): the request with ``None`` answers exactly as the request without it.

Measured on every declared noun (``test_vocabulary_conformance_back2654.NOUNS``) that declares the control, on that
file's workspace and default request; a plain parametrized test (manager ruling 1 on the P1 inventory), no new
conformance column.
"""
import json

import pytest

from test_vocabulary_conformance_back2654 import NOUNS, _specs, _uri, workspace  # noqa: F401  (workspace: fixture)
from reveal import api

CONTROLS = ('limit', 'offset')
CASES = [(noun, control) for noun in NOUNS for control in CONTROLS
         if control in {spec.name for spec in _specs(noun)}]


def _outcome(call, *, notes=True):
    """What a library caller gets: the answer as JSON text, or the raised class and message. ``notes=False`` leaves
    out the retirement notes, which a request that typed a URI query says and one without it does not."""
    try:
        answer = call()
    except Exception as exc:  # the raised class and message are the measured outcome
        return 'raised', type(exc).__name__, str(exc)
    meta = answer.get('meta') if isinstance(answer, dict) else None
    if not notes and isinstance(meta, dict) and isinstance(meta.get('warnings'), list):
        meta['warnings'] = [w for w in meta['warnings'] if not (isinstance(w, dict) and w.get('type') == 'retired_spelling')]
    return 'answer', json.dumps(answer, sort_keys=True, default=str)


def test_every_declaring_noun_is_measured():
    """The population is the declarations', not a hand list: Metrics, AST and Markdown declare both controls."""
    assert {('metrics', 'limit'), ('metrics', 'offset'), ('ast', 'limit'), ('markdown', 'offset')} <= set(CASES)


@pytest.mark.parametrize('noun, control', CASES)
def test_a_typed_none_answers_as_the_request_without_it(workspace, noun, control):
    uri = _uri(noun, control=control)
    assert _outcome(lambda: api.query(uri, **{control: None})) == _outcome(lambda: api.query(uri))


@pytest.mark.parametrize('noun, control', CASES)
def test_a_typed_none_clears_the_uris_own_value(workspace, noun, control):
    """``None`` over the URI's own ``?control=1`` is the default again (the documented override rule), so the answer is
    the request without either, its retirement notes aside (the typed URI query notes; the bare URI may not)."""
    uri, given = _uri(noun, control=control), _uri(noun, f'{control}=1', control=control)
    assert (_outcome(lambda: api.query(given, **{control: None}), notes=False)
            == _outcome(lambda: api.query(uri), notes=False))
