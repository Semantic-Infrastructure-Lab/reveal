"""An element is a control too (COMMAND_MODEL "Applicability"; Scott 2026-11-18, BACK-2687, BACK-2656 note #4).

On a declared noun ``api.query(uri, element_name=...)`` is the CLI's positional element: no answer reads it, so it is
the same invalid request, carrying ``unread_element_message`` (which names the URI form), raised once in
``api.query`` before the adapter is built, never in an adapter's ``get_element`` (V020 requires that to return None
for a missing element). It also closes the bypass where an element skipped the unsupported-control check
(``bogus=1`` answered). Plugin subclasses and undeclared adapters keep forwarding the element and keywords to their
``get_element`` (tests/test_{surface,calls,contracts,trace}_api_overlay_back23*.py pin that, unchanged).
"""
import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.adapters.base import unread_element_message
from reveal.cli.invocation import RETIREMENTS
from reveal.errors import RequestValidationError
from test_vocabulary_conformance_back2654 import NOUNS, TARGETS, _adapter, workspace  # noqa: F401

# help:// and reveal:// keep their positional element, noted, until the cut (their target:SCHEME.element rows; BACK-2767:
# tests/test_resource_scheme_keywords_back2764.py pins that), so they refuse no element yet.
KEEPS_ELEMENT = {noun for noun in NOUNS if f'target:{noun}.element' in RETIREMENTS}


def _uri(noun):
    return f"{noun}://{TARGETS.get(noun, 'proj')}"


def test_only_help_and_reveal_keep_an_element():
    assert KEEPS_ELEMENT == {'help', 'reveal'}


@pytest.mark.parametrize('noun', sorted(set(NOUNS) - KEEPS_ELEMENT))
def test_a_declared_noun_refuses_an_element_on_the_api_before_its_adapter_is_built(workspace, monkeypatch,  # noqa: F811
                                                                                   noun):
    adapter = _adapter(noun)
    calls = []
    for method in ('__init__', 'get_structure', 'get_element'):
        original = getattr(adapter, method, None)
        if original is not None:
            monkeypatch.setattr(adapter, method,
                                lambda *a, _m=method, _o=original, **k: (calls.append(_m), _o(*a, **k))[1])
    expected = unread_element_message(adapter, noun, 'x')
    with pytest.raises(RequestValidationError) as raised:
        api.query(_uri(noun), element_name='x')
    assert str(raised.value) == expected
    assert calls == [], calls


@pytest.mark.parametrize('noun', sorted(set(NOUNS) - {'stats'} - KEEPS_ELEMENT))  # stats://: BACK-2656 Step 3 report
def test_the_api_refusal_is_the_clis(workspace, noun):  # noqa: F811
    cli = _run_reveal_direct(_uri(noun), 'x', '--format', 'json')
    assert cli.returncode == 2, (cli.returncode, cli.stderr)
    with pytest.raises(RequestValidationError) as raised:
        api.query(_uri(noun), element_name='x')
    assert str(raised.value) in cli.stderr, (str(raised.value), cli.stderr)


@pytest.mark.parametrize('keywords', [{}, {'bogus': 1}])
def test_an_existing_element_is_refused_and_no_longer_skips_the_unsupported_control_check(workspace,  # noqa: F811
                                                                                          keywords):
    """``items`` exists: the element answered raw, and with it an undeclared keyword answered too."""
    with pytest.raises(RequestValidationError, match='takes no positional element'):
        api.query('json://proj/data.json', element_name='items', **keywords)
    with pytest.raises(ValueError, match="unsupported control 'bogus'"):
        api.query('json://proj/data.json', bogus=1)


# --- negative controls -------------------------------------------------------------------------------------------

def test_no_element_answers_as_before(workspace):  # noqa: F811
    assert api.query('json://proj/data.json', element_name=None)['type'] == api.query('json://proj/data.json')['type']


def test_an_undeclared_adapter_still_answers_an_element(monkeypatch):
    # help:// is undeclared; env:// is declared since BACK-2626 and refuses an element as every declared noun does
    answer = api.query('help://', element_name='env')
    assert answer['topic'] == 'env' and 'Env Adapter Guide' in answer['content'], answer


def test_a_plugin_subclass_of_a_declared_noun_still_forwards_its_element(monkeypatch, tmp_path):
    from reveal.adapters.json.adapter import JsonAdapter
    from reveal.adapters.registry import _ADAPTER_REGISTRY

    class Plugin(JsonAdapter):
        """Inherits the declaration, not its contract: the element reaches its own get_element."""
        def get_element(self, element_name, **kwargs):
            return {'name': element_name, **kwargs}

    monkeypatch.setitem(_ADAPTER_REGISTRY, 'json-element-plugin', Plugin)
    (tmp_path / 'd.json').write_text('{"k": 1}', encoding='utf-8')
    assert api.query(f'json-element-plugin://{(tmp_path / "d.json").as_posix()}', element_name='k',
                     extra=2) == {'name': 'k', 'extra': 2}
