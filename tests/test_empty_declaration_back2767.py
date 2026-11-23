"""A noun that declares no control (``PARAM_SPECS = ()``) is still a declared noun to the URI route's flag binding
(BACK-2767): a control flag it does not take (``--since``) and ``--verbose`` (``--detail full``) exit 2 naming its
controls, ``(none)``, and ``--all`` is satisfied quietly, as on every other declared noun. The checks in
``cli/routing/flag_specs.py`` read the declaration's truthiness, so an empty one counted as undeclared and the flag got
the "has no effect" note.

Effect on every noun: only a class whose own ``PARAM_SPECS`` is empty changes, and the one such class is
``reveal://`` (declared by BACK-2767); every noun with controls already took these branches, and an undeclared adapter
(no ``PARAM_SPECS``: a plugin since diff:// was declared, BACK-2214) keeps its note.
"""
import io
from contextlib import redirect_stderr

import pytest

import reveal.adapters  # noqa: F401  registers every adapter
from reveal.adapters.base import get_adapter_class, list_supported_schemes
from reveal.adapters.reveal.adapter import RevealAdapter
from reveal.cli.defaults import _default_args
from reveal.cli.routing.flag_specs import inject_query_flags
from reveal.errors import RequestValidationError
from undeclared_plugin import undeclared_plugin  # noqa: F401  (a fixture: the plugin that declares nothing)

pytestmark = [pytest.mark.unit]


def _inject(resource, scheme, **flags):
    err = io.StringIO()
    with redirect_stderr(err):
        out = inject_query_flags(resource, scheme, _default_args(**flags))
    return out, err.getvalue()


@pytest.fixture
def empty(monkeypatch):
    monkeypatch.setattr(RevealAdapter, 'PARAM_SPECS', (), raising=False)


def test_a_control_flag_is_refused_naming_no_controls(empty):
    with pytest.raises(RequestValidationError, match=r"unsupported control '--since'; supported controls: \(none\)"):
        _inject('config', 'reveal', since='2026-01-01')


def test_verbose_is_detail_full_and_refused(empty):
    with pytest.raises(RequestValidationError, match=r"--verbose is --detail full: unsupported control 'detail'"):
        _inject('config', 'reveal', verbose=True)


def test_all_is_satisfied_quietly(empty):
    assert _inject('config', 'reveal', all=True) == ('config', '')


def test_an_undeclared_adapter_keeps_its_note(undeclared_plugin):
    assert getattr(get_adapter_class(undeclared_plugin), 'PARAM_SPECS', None) is None
    out, err = _inject('x', undeclared_plugin, since='2026-01-01')
    assert out == 'x' and '--since has no effect on undeclared://' in err


def test_only_reveal_declares_no_control():
    empty_declarations = {scheme for scheme in list_supported_schemes()
                          if vars(get_adapter_class(scheme)).get('PARAM_SPECS', None) == ()}
    assert empty_declarations <= {'reveal'}
