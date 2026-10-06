"""BACK-1384: contracts lists 5 implementers per contract in text; ?impls=N widens it and a cut names it."""

from io import StringIO
from contextlib import redirect_stdout

import pytest

from reveal.adapters.contracts import ContractsAdapter, ContractsRenderer

pytestmark = pytest.mark.component


@pytest.fixture
def abc_tree(tmp_path):
    src = ["from abc import ABC, abstractmethod", "class Base(ABC):",
           "    @abstractmethod", "    def go(self): ..."]
    for i in range(8):
        src += [f"class Impl{i}(Base):", "    def go(self): pass"]
    (tmp_path / "m.py").write_text("\n".join(src) + "\n", encoding="utf-8")
    return tmp_path


def _text(abc_tree, query):
    result = ContractsAdapter(str(abc_tree), query).get_structure()
    out = StringIO()
    with redirect_stdout(out):
        ContractsRenderer.render_structure(result, "text")
    return out.getvalue(), result


def test_contracts_default_lists_five_and_names_the_knob(abc_tree):
    text, _ = _text(abc_tree, "")
    assert "Impl4" in text and "Impl5" not in text
    assert "and 3 more" in text and "?impls=" in text


def test_contracts_impls_param_widens_and_zero_lists_all(abc_tree):
    text, _ = _text(abc_tree, "impls=7")
    assert "Impl6" in text and "Impl7" not in text and "and 1 more" in text
    text, _ = _text(abc_tree, "impls=0")
    assert "Impl7" in text and "more" not in text


def test_contracts_json_always_carries_every_implementer(abc_tree):
    _, result = _text(abc_tree, "impls=2")
    assert len(result["abcs"][0]["implementations"]) == 8


def test_contracts_impls_param_rejects_bad_values(abc_tree):
    for bad in ("impls=-1", "impls=x"):
        with pytest.raises(ValueError, match="impls"):
            ContractsAdapter(str(abc_tree), bad).get_structure()
